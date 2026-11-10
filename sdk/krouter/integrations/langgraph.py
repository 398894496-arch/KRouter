"""KRouter as a LangGraph store: long-term memory as Markdown pages you can open and edit, searched the KRouter way.

    from krouter.integrations.langgraph import KRouterStore
    store = KRouterStore("./memory")                     # any folder; inside your KRouter vault works too
    graph = builder.compile(checkpointer=..., store=store)

    store.put(("users", "alice", "memories"), "diet", {"content": "Alice is vegetarian and never eats fish."})
    hits = store.search(("users", "alice", "memories"), query="does she eat fish?")
    hits[0].value, hits[0].page                          # the memory, and the page it came from

A namespace is a folder (`("users", "alice")` is `users/alice/`), an item is one Markdown page in it. A value that
is one string field (`{"content": "..."}`) is the page's text, so editing the text in any editor changes the memory;
any other value is kept as JSON in the page's frontmatter, with a readable list of its fields as the text.

Search with `query` runs KRouter's own recall (no embeddings, no model, nothing sent anywhere) over that namespace
alone: other namespaces are not in the index it searches, so one user's or thread's memories cannot come back for
another. When the namespace does not know, the result is empty instead of the nearest weak match. Writing a key that
already has a page keeps the old page under `.history/`, marked as superseded by the new one, and the new page names
it (`supersedes:`); `delete` keeps the last version there too, marked retired. `history()` reads them back;
`purge()` removes a key with its history (when it really has to be gone).

Needs `langgraph` (`pip install "krouter[langgraph]"`). Without it, nothing else in KRouter imports this module.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from langgraph.store.base import (
    BaseStore,
    GetOp,
    InvalidNamespaceError,
    Item,
    ListNamespacesOp,
    MatchCondition,
    Op,
    PutOp,
    Result,
    SearchItem,
    SearchOp,
    get_text_at_path,
)

import krouter

__all__ = ["KRouterStore", "KRouterItem", "KRouterSearchItem"]

log = logging.getLogger(__name__)

KIND = "langgraph-memory"
HISTORY = ".history"
DEAD = {"superseded", "retired", "rejected", "deprecated", "archived", "deleted"}  # KRouter 的失效状态，加上 deleted
CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}
# 文件名里不能出现、或在 Obsidian 链接里有特殊含义的字符；`%` 是转义符本身，`~` 留给区分大小写的标记
UNSAFE = set('/\\:*?"<>|%~#^[]')
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
TAG = 10            # 标记长度（sha256 前 10 位）：`Alice` 和 `alice` 在不分大小写的磁盘上也是两个文件夹
LABEL_MAX = 120     # 命名空间的一段转义后最多这么多字节（做文件夹名）
KEY_MAX = 150       # 键转义后超过这么多字节就截断并加标记，完整的键记在页面的 frontmatter 里
LOCK_STALE = 30.0   # 写锁超过这么多秒没释放，当作上次写到一半的进程留下的
RECALL_CAP = 80     # KRouter 召回一次最多看这么多候选
EMPTY_KEY = "~"
# 按用户分的命名空间里，问句的「the user」「用户」就是这个命名空间的主人，和 KRouter 本来就不计的 I、my、我 一样；
# 记忆里多半写的是名字（Bob is allergic…），留着它，KRouter 会把它当成库里没有的词而拒答
OWNER_WORDS = re.compile(r"(?i)\b(?:the\s+)?users?(?:'s|s')?\b|用户的?|使用者的?")


# ---------------------------------------------------------------------------------------------------------------
# 命名空间和键 ↔ 文件名：可逆、跨平台（Windows 保留名、大小写不敏感的磁盘、macOS 的 Unicode 规范化）


def _tag(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()[:TAG]


def _escape(label: str) -> str:
    out = []
    last = len(label) - 1
    for i, ch in enumerate(label):
        if ch in UNSAFE or ord(ch) < 32 or ord(ch) == 127 or (ch in ". " and i in (0, last)):
            out.append("".join(f"%{b:02X}" for b in ch.encode("utf-8")))
        else:
            out.append(ch)
    s = "".join(out)
    if s.split(".")[0].lower() in RESERVED:  # CON、nul.txt……在 Windows 上不能做文件名
        s = f"%{ord(s[0]):02X}" + s[1:]
    return s


def _needs_tag(label: str) -> bool:
    return label != label.lower() or unicodedata.normalize("NFC", label) != label


def _encode(label: str, limit: int) -> str:
    if label == "":
        return EMPTY_KEY
    s = _escape(label)
    if len(s.encode("utf-8")) > limit:
        cut = s
        while len(cut.encode("utf-8")) > limit - TAG - 1:
            cut = cut[:-1]
        return cut + "~" + _tag(label)
    return s + ("~" + _tag(label) if _needs_tag(label) else "")


def _decode(name: str) -> str:
    if name == EMPTY_KEY:
        return ""
    base, sep, tag = name.rpartition("~")
    if sep and len(tag) == TAG and all(c in "0123456789abcdef" for c in tag):
        raw = unquote(base)
        for cand in (raw, unicodedata.normalize("NFC", raw), unicodedata.normalize("NFD", raw)):
            if _tag(cand) == tag:
                return cand
        return raw
    return unicodedata.normalize("NFC", unquote(name))  # 没标记的名字原本就是 NFC（老 HFS+ 盘会存成 NFD）


def _label_dir(label: str) -> str:
    name = _encode(label, 10**6)
    if len(name.encode("utf-8")) > LABEL_MAX:
        raise InvalidNamespaceError(f"namespace label {label[:40]!r}... is too long for a folder name "
                                    f"({LABEL_MAX} bytes once escaped)")
    return name


def _is_label_dir(name: str) -> bool:
    if name.startswith("."):
        return False
    try:
        return _label_dir(_decode(name)) == name
    except InvalidNamespaceError:
        return False


def _check_labels(labels: Iterable[Any], where: tuple) -> None:
    for label in labels:
        if not isinstance(label, str):
            raise InvalidNamespaceError(f"Namespace labels must be strings, got {type(label).__name__} in {where}")
        if label == "*" and where and where[0] == "match":
            continue
        if not label:
            raise InvalidNamespaceError(f"Namespace labels cannot be empty strings. Got {where}")
        if "." in label:
            raise InvalidNamespaceError(f"Namespace labels cannot contain periods ('.'). Got {where}")
        if "\x00" in label:
            raise InvalidNamespaceError(f"Namespace labels cannot contain NUL bytes. Got {where}")


def _validate(op: Op) -> None:
    if isinstance(op, (GetOp, PutOp)):
        _check_labels(op.namespace, tuple(op.namespace))
    elif isinstance(op, SearchOp):
        _check_labels(op.namespace_prefix, tuple(op.namespace_prefix))
    elif isinstance(op, ListNamespacesOp):
        for cond in op.match_conditions or ():
            _check_labels(cond.path, ("match", *cond.path))
    if isinstance(op, PutOp) and op.ttl is not None:
        raise NotImplementedError("KRouterStore does not support TTL")
    if isinstance(op, PutOp) and op.value is not None:
        if not op.namespace:
            raise InvalidNamespaceError("Namespace cannot be empty.")
        if op.namespace[0] == "langgraph":
            raise InvalidNamespaceError(f'Root label for namespace cannot be "langgraph". Got: {op.namespace}')
        if not isinstance(op.value, Mapping):
            raise TypeError(f"a store value is a dict, got {type(op.value).__name__}")


# ---------------------------------------------------------------------------------------------------------------
# 页面：frontmatter（每个值一行 JSON，也是合法 YAML）+ 正文


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _time(raw: Any, fallback: datetime) -> datetime:
    if isinstance(raw, str):
        try:
            t = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return fallback


def _split(text: str) -> tuple[dict[str, Any], str, str]:
    """(frontmatter as values, frontmatter text, body). Values are read as JSON when they are JSON."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, "", text
    end = text.find("\n---\n", 3)
    if end < 0:
        if text.endswith("\n---"):
            end = len(text) - 4
        else:
            return {}, "", text
    head = text[4:end] if end >= 4 else ""
    meta: dict[str, Any] = {}
    for line in head.split("\n"):
        if not line or line[0] in " \t-#" or ":" not in line:
            continue
        k, _, v = line.partition(":")
        v = v.strip()
        try:
            meta[k.strip()] = json.loads(v)
        except ValueError:
            meta[k.strip()] = v.strip("\"'")
    return meta, head, text[end + 5:]


def _dumps(v: Any) -> str:
    try:
        return json.dumps(v, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        raise TypeError(f"a store value must be JSON-serializable: {e}") from None


def _scalar(v: Any) -> str:
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def _lines(obj: Any, prefix: str = "") -> Iterator[str]:
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            yield from _lines(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, (list, tuple)):
        if all(not isinstance(v, (Mapping, list, tuple)) for v in obj):
            if obj:
                yield f"{prefix}: " + ", ".join(_scalar(v) for v in obj if v is not None)
        else:
            for i, v in enumerate(obj):
                yield from _lines(v, f"{prefix}[{i}]")
    elif obj is not None:
        yield f"{prefix}: {_scalar(obj)}" if prefix else _scalar(obj)


def _one_line(s: str) -> str:
    return " ".join(s.split())


@dataclass
class _Page:
    path: Path
    namespace: tuple[str, ...]
    key: str
    value: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    status: str
    meta: dict[str, Any]
    ours: bool  # 这个存储写的（有 key: 一行）；没有的是人自己加进文件夹的页

    @property
    def live(self) -> bool:
        return self.status not in DEAD

    @property
    def searchable(self) -> bool:
        return self.meta.get("index") is not False


# ---------------------------------------------------------------------------------------------------------------
# 结果：LangGraph 的 Item / SearchItem，多带出处


class KRouterItem(Item):
    """An `Item`, plus where it lives: `page` (path inside the store folder), `path` (on disk), `supersedes` (the
    page this version replaced, or None), `version`, `status`."""

    __slots__ = ("page", "path", "supersedes", "version", "status")

    def __init__(self, *, page: str = "", path: str = "", supersedes: str | None = None, version: int = 1,
                 status: str = "active", **kw: Any) -> None:
        super().__init__(**kw)
        self.page, self.path, self.supersedes, self.version, self.status = page, path, supersedes, version, status

    def dict(self) -> dict:
        d = super().dict()
        d.update(page=self.page, supersedes=self.supersedes, version=self.version, status=self.status)
        return d


class KRouterSearchItem(SearchItem):
    """A `SearchItem`, plus `page`, `path`, `supersedes`, `version`; with a query also `how` (the line recall
    matched) and `confidence` (KRouter's: high, medium or low). `score` is relative to the first result (1.0)."""

    __slots__ = ("page", "path", "supersedes", "version", "how", "confidence")

    def __init__(self, namespace: tuple[str, ...], key: str, value: dict[str, Any], created_at: datetime,
                 updated_at: datetime, score: float | None = None, *, page: str = "", path: str = "",
                 supersedes: str | None = None, version: int = 1, how: str = "", confidence: str = "") -> None:
        super().__init__(namespace, key, value, created_at, updated_at, score)
        self.page, self.path, self.supersedes, self.version = page, path, supersedes, version
        self.how, self.confidence = how, confidence

    def dict(self) -> dict:
        d = super().dict()
        d.update(page=self.page, supersedes=self.supersedes, version=self.version)
        if self.confidence:
            d.update(how=self.how, confidence=self.confidence)
        return d


# ---------------------------------------------------------------------------------------------------------------
# 召回：在子进程里跑 KRouter 自己的 recall，不进调用方的进程、不写查询日志

_RUNNER = r"""
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import recall_index
res = recall_index.recall(Path(sys.argv[2]), sys.argv[3], scope="_", limit=int(sys.argv[4]), assoc=False)
keep = ("rel", "tier", "status", "how", "score")
print(json.dumps({"confidence": res.get("confidence", "none"), "partial": bool(res.get("partial")),
                  "hits": [{k: h.get(k) for k in keep} for h in res.get("hits", [])]}))
"""


def _corpus() -> list[Path]:
    """KRouter's two sample vaults (English, Chinese): a fixed set of pages every namespace's index also holds, so
    word statistics mean something in a namespace of two pages. They are never returned."""
    out = []
    for mod, rel in (("krouter_template", "template"), ("krouter_template_zh", "template-zh")):
        try:
            out.append(Path(list(importlib.import_module(mod).__path__)[0]).resolve())
        except ImportError:
            here = Path(krouter.__file__).resolve().parents[2] / rel
            if here.is_dir():
                out.append(here)
    return out


def _link(target: Path, link: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        import _winapi  # 没开开发者模式的 Windows 不让普通用户建符号链接；目录联接（junction）不需要权限

        _winapi.CreateJunction(str(target), str(link))


def _points_to(link: Path, target: Path) -> bool:
    try:
        return Path(os.readlink(link)).resolve() == target.resolve()
    except (OSError, ValueError):
        return False


def _unlink(link: Path) -> None:
    try:
        link.unlink()
    except IsADirectoryError:
        os.rmdir(link)  # Windows 的目录联接
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------------------------------------------


class KRouterStore(BaseStore):
    """A LangGraph `BaseStore` whose items are Markdown pages under `root`, searched with KRouter's recall.

    root: the memory folder (created when missing). It can sit inside your KRouter vault, e.g. `<vault>/LangGraph`;
        its pages then also answer in your coding apps.
    cache_dir: where the rebuildable search indexes live (default `$KROUTER_CACHE_DIR/langgraph`, else
        `~/.cache/krouter/langgraph`); never inside `root`.
    min_confidence: the lowest KRouter confidence a query result may have: "low" (default), "medium" or "high".
    text_field: the field a page you added by hand is read into (`{"content": <its text>}`).
    fields: which value fields become the page's searchable text, as LangGraph paths; default the whole value.
        `put(..., index=[...])` overrides it for one item and `index=False` keeps an item out of query search.
    """

    supports_ttl = False

    def __init__(self, root: str | os.PathLike, *, cache_dir: str | os.PathLike | None = None,
                 min_confidence: str = "low", text_field: str = "content", fields: list[str] | None = None,
                 timeout: float = 120) -> None:
        if min_confidence not in CONFIDENCE_RANK:
            raise ValueError("min_confidence is one of low, medium, high")
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        base = Path(cache_dir).expanduser() if cache_dir else (
            Path(os.environ.get("KROUTER_CACHE_DIR") or Path.home() / ".cache" / "krouter") / "langgraph")
        self.cache_dir = base.resolve()
        if self.cache_dir == self.root or self.root in self.cache_dir.parents:
            raise ValueError("cache_dir must be outside the memory folder")
        self.min_confidence = min_confidence
        self.text_field = text_field
        self.fields = list(fields) if fields else ["$"]
        self.timeout = timeout
        self._mutex = threading.RLock()

    def __repr__(self) -> str:
        return f"KRouterStore({str(self.root)!r})"

    # -- LangGraph 的两个必需方法 ---------------------------------------------------------------------------------

    def batch(self, ops: Iterable[Op]) -> list[Result]:
        ops = list(ops)
        for op in ops:  # 先全部检查，有一个不合法就一个都不做
            _validate(op)
        results: list[Result] = []
        for op in ops:
            if isinstance(op, GetOp):
                results.append(self._get(op.namespace, str(op.key)))
            elif isinstance(op, SearchOp):
                results.append(self._search(op))
            elif isinstance(op, PutOp):
                if op.value is None:
                    self._delete(op.namespace, str(op.key))
                else:
                    self._put(op.namespace, str(op.key), dict(op.value), op.index)
                results.append(None)
            elif isinstance(op, ListNamespacesOp):
                results.append(self._list_namespaces(op))
            else:
                raise ValueError(f"Unknown operation type: {type(op)}")
        return results

    async def abatch(self, ops: Iterable[Op]) -> list[Result]:
        return await asyncio.to_thread(self.batch, list(ops))

    # -- KRouter 多给的：旧版本、彻底删除 ----------------------------------------------------------------------------

    def history(self, namespace: tuple[str, ...], key: str) -> list[KRouterItem]:
        """Earlier versions of `key`, newest first: each one superseded by the next (or retired by a delete)."""
        _check_labels(namespace, tuple(namespace))
        d = self._dir(namespace) / HISTORY
        if not d.is_dir():
            return []
        stem = self._stem(key)
        out = []
        for f in d.iterdir():
            if f.suffix == ".md" and f.stem.rpartition("@")[0] == stem:
                page = self._load(f, tuple(namespace))
                if page and page.key == key:
                    out.append(self._item(page))
        return sorted(out, key=lambda i: _archived_order(Path(i.path).stem), reverse=True)

    async def ahistory(self, namespace: tuple[str, ...], key: str) -> list[KRouterItem]:
        return await asyncio.to_thread(self.history, namespace, key)

    def purge(self, namespace: tuple[str, ...], key: str) -> int:
        """Remove `key` and every earlier version of it. Unlike `delete`, nothing is kept. Returns pages removed."""
        _check_labels(namespace, tuple(namespace))
        key = str(key)
        d = self._dir(namespace)
        if not d.is_dir():
            return 0
        n = 0
        with self._lock(d / (self._stem(key) + ".md")):
            # 当前页，以及同名但被人标成失效的页：都删
            for name in dict.fromkeys([self._stem(key) + ".md", _escape(key) + ".md"]):
                page = self._load(d / name, tuple(namespace)) if (d / name).is_file() else None
                if page and page.key == key and (page.ours or name in os.listdir(d)):
                    page.path.unlink()
                    n += 1
            for old in self.history(namespace, key):
                Path(old.path).unlink(missing_ok=True)
                n += 1
        return n

    async def apurge(self, namespace: tuple[str, ...], key: str) -> int:
        return await asyncio.to_thread(self.purge, namespace, key)

    # -- 路径 ---------------------------------------------------------------------------------------------------

    def _dir(self, namespace: tuple[str, ...]) -> Path:
        return self.root.joinpath(*(_label_dir(label) for label in namespace)) if namespace else self.root

    @staticmethod
    def _stem(key: str) -> str:
        return _encode(key, KEY_MAX)

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    # -- 读 -----------------------------------------------------------------------------------------------------

    def _load(self, path: Path, namespace: tuple[str, ...]) -> _Page | None:
        try:
            raw = path.read_text(encoding="utf-8")
            st = path.stat()
        except (OSError, UnicodeDecodeError):
            return None
        meta, _head, body = _split(raw)
        mtime = datetime.fromtimestamp(st.st_mtime, timezone.utc)
        ours = isinstance(meta.get("key"), str)
        key = meta["key"] if ours else _decode(path.stem.rpartition("@")[0] if path.parent.name == HISTORY
                                               else path.stem)
        text = body.strip()
        field = meta.get("text_field")
        if isinstance(field, str):
            value = {field: text}
        elif isinstance(meta.get("value"), dict):
            value = meta["value"]
        else:
            if "value" in meta:
                log.warning("KRouterStore: %s has a value line that is not a JSON object; reading its text instead",
                            path)
            value = {self.text_field: text}
        status = str(meta.get("status") or "active").strip().lower()
        return _Page(path=path, namespace=tuple(namespace), key=key, value=value,
                     created_at=_time(meta.get("created_at"), mtime), updated_at=_time(meta.get("updated_at"), mtime),
                     status=status, meta=meta, ours=ours)

    def _current(self, namespace: tuple[str, ...], key: str) -> _Page | None:
        """The live page for `key`: the store's own file name, else a page someone added with the key as its name."""
        d = self._dir(namespace)
        names = [self._stem(key) + ".md"]
        if key and _escape(key) + ".md" not in names:
            names.append(_escape(key) + ".md")
        listing = None
        for name in names:
            p = d / name
            if not p.is_file():
                continue
            page = self._load(p, namespace)
            if not page or not page.live:
                continue
            if not page.ours:  # 人加的页：磁盘不分大小写时，确认文件名确实是这个键
                listing = listing if listing is not None else set(os.listdir(d))
                if name not in listing:
                    continue
            if page.key == key:
                return page
        return None

    def _get(self, namespace: tuple[str, ...], key: str) -> KRouterItem | None:
        try:
            page = self._current(tuple(namespace), key)
        except InvalidNamespaceError:
            return None
        return self._item(page) if page else None

    def _pages(self, prefix: tuple[str, ...]) -> Iterator[_Page]:
        """Every live page under `prefix`, one per key (the store's own page wins over a hand-added namesake)."""
        try:
            base = self._dir(prefix)
        except InvalidNamespaceError:
            return
        if not base.is_dir():
            return
        for dirpath, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if _is_label_dir(d))
            parts = Path(dirpath).relative_to(self.root).parts
            if not parts:
                continue  # 直接放在根目录的页不属于任何命名空间
            ns = tuple(_decode(p) for p in parts)
            seen: dict[str, _Page] = {}
            for f in sorted(files):
                if not f.endswith(".md") or f.startswith("."):
                    continue
                page = self._load(Path(dirpath) / f, ns)
                if page and page.live and (page.key not in seen or (page.ours and not seen[page.key].ours)):
                    seen[page.key] = page
            yield from seen.values()

    def _item(self, page: _Page) -> KRouterItem:
        return KRouterItem(value=page.value, key=page.key, namespace=page.namespace, created_at=page.created_at,
                           updated_at=page.updated_at, page=self._rel(page.path), path=str(page.path),
                           supersedes=self._supersedes(page), version=int(page.meta.get("version") or 1),
                           status=page.status)

    def _supersedes(self, page: _Page) -> str | None:
        s = page.meta.get("supersedes")
        return self._rel(page.path.parent / s) if isinstance(s, str) and s else None

    # -- 搜索 ---------------------------------------------------------------------------------------------------

    def _search(self, op: SearchOp) -> list[SearchItem]:
        prefix = tuple(op.namespace_prefix)
        if op.query:
            return self._search_query(prefix, op)
        pages = [p for p in self._pages(prefix) if _matches(p.value, op.filter)]
        pages.sort(key=lambda p: (p.updated_at, p.namespace, p.key), reverse=True)
        return [self._search_item(p) for p in pages[op.offset:op.offset + op.limit]]

    def _search_item(self, p: _Page, score: float | None = None, how: str = "", conf: str = "") -> KRouterSearchItem:
        return KRouterSearchItem(p.namespace, p.key, p.value, p.created_at, p.updated_at, score,
                                 page=self._rel(p.path), path=str(p.path), supersedes=self._supersedes(p),
                                 version=int(p.meta.get("version") or 1), how=how, confidence=conf)

    def _search_query(self, prefix: tuple[str, ...], op: SearchOp) -> list[SearchItem]:
        try:
            base = self._dir(prefix)
        except InvalidNamespaceError:
            return []
        if not base.is_dir():
            return []
        want = op.offset + op.limit
        res = self._recall(self._view(prefix, base), _question(op.query), min(RECALL_CAP, max(10, want * 3)))
        conf = res.get("confidence") or "none"
        if CONFIDENCE_RANK.get(conf, 0) < CONFIDENCE_RANK[self.min_confidence]:
            return []  # 这个命名空间里没有能回答的页：空，而不是最像的那条
        out: list[KRouterSearchItem] = []
        seen = set()
        top = None
        for h in res.get("hits", []):
            rel = h.get("rel") or ""
            if not rel.startswith("_/") or h.get("tier") == "dead" or (h.get("status") or "") in DEAD:
                continue
            path = base / rel[2:]
            parts = Path(rel[2:]).parent.parts
            if any(not _is_label_dir(p) for p in parts):
                continue
            page = self._load(path, prefix + tuple(_decode(p) for p in parts))
            if not page or not page.live or not page.searchable or (page.namespace, page.key) in seen:
                continue
            if page.ours and path.name != self._stem(page.key) + ".md":
                continue  # 被改过名的旧文件，不是这个键的当前页
            if not _matches(page.value, op.filter):
                continue
            seen.add((page.namespace, page.key))
            s = float(h.get("score") or 0.0)
            top = top if top is not None else (s or 1.0)
            out.append(self._search_item(page, round(s / top, 4), h.get("how") or "", conf))
        return out[op.offset:op.offset + op.limit]

    def _view(self, prefix: tuple[str, ...], base: Path) -> Path:
        """A folder that holds only this namespace (as `_`) and the fixed sample pages: what recall indexes."""
        digest = hashlib.sha1(json.dumps([str(self.root), list(prefix)]).encode("utf-8")).hexdigest()[:16]
        view = self.cache_dir / "views" / digest
        view.mkdir(parents=True, exist_ok=True)
        links = {"_": base}
        for i, corpus in enumerate(_corpus()):
            links[f"__corpus{i}"] = corpus
        with self._mutex:
            for name, target in links.items():
                link = view / name
                if os.path.lexists(link):
                    if _points_to(link, target):
                        continue
                    _unlink(link)
                try:
                    _link(target, link)
                except FileExistsError:  # 另一个进程刚建好同一个链接
                    if not _points_to(link, target):
                        raise
        return view

    def _recall(self, view: Path, query: str, limit: int) -> dict:
        env = dict(os.environ)
        env["KROUTER_CACHE_DIR"] = str(self.cache_dir / "index")
        env["KROUTER_NO_QUERY_LOG"] = "1"  # 你应用里用户的问题不进本机 KRouter 的夜间学习
        env.pop("KROUTER_REFRESH_EVERY", None)  # 每次查询前都对一遍文件：刚写的记忆马上能搜到
        proc = subprocess.run([sys.executable, "-I", "-c", _RUNNER, str(krouter.router_dir()), str(view), query,
                               str(limit)], env=env, capture_output=True, text=True, timeout=self.timeout,
                              stdin=subprocess.DEVNULL)
        if proc.returncode != 0:
            raise RuntimeError("KRouter recall failed: " + (proc.stderr or proc.stdout).strip()[-2000:])
        return json.loads(proc.stdout.strip().splitlines()[-1])

    # -- 命名空间列表 -----------------------------------------------------------------------------------------------

    def _list_namespaces(self, op: ListNamespacesOp) -> list[tuple[str, ...]]:
        namespaces = {p.namespace for p in self._pages(())}
        if op.match_conditions:
            namespaces = {ns for ns in namespaces if all(_does_match(c, ns) for c in op.match_conditions)}
        if op.max_depth is not None:
            namespaces = {ns[:op.max_depth] for ns in namespaces}
        return sorted(namespaces)[op.offset:op.offset + op.limit]

    # -- 写 -----------------------------------------------------------------------------------------------------

    @contextmanager
    def _lock(self, path: Path) -> Iterator[None]:
        """One writer per key, across threads and processes: an exclusive lock file next to the page."""
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = path.parent / f".{path.stem}.lock"
        deadline = time.monotonic() + 20
        with self._mutex:
            while True:
                try:
                    os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                    break
                except FileExistsError:
                    try:
                        if time.time() - lock.stat().st_mtime > LOCK_STALE:
                            lock.unlink()
                            continue
                    except FileNotFoundError:
                        continue
                    if time.monotonic() > deadline:
                        raise TimeoutError(f"{lock} is held by another writer") from None
                    time.sleep(0.02)
            try:
                yield
            finally:
                try:
                    lock.unlink()
                except FileNotFoundError:
                    pass

    def _render(self, namespace: tuple[str, ...], key: str, value: dict, index: Any, created: datetime,
                updated: datetime, version: int, supersedes: str | None) -> str:
        fields = self.fields if index is None else (index or [])
        text = None
        if len(value) == 1 and index is not False:
            (field, v), = value.items()
            if (isinstance(field, str) and isinstance(v, str) and v and v == v.strip() and "\r" not in v
                    and fields in (["$"], [field])):
                text = v
        meta: list[tuple[str, Any]] = [("kind", KIND), ("namespace", list(namespace)), ("key", key),
                                       ("status", "active"), ("version", version),
                                       ("created_at", created.isoformat()), ("updated_at", updated.isoformat())]
        if supersedes:
            meta.append(("supersedes", supersedes))
        if text is not None:
            meta.append(("text_field", next(iter(value))))
            body = text
        else:
            meta.append(("value", value))
            if index is not None:
                meta.append(("index", index if index is False else list(index)))
            if fields == ["$"]:
                lines = list(_lines(value))
            else:
                lines = [f"{f}: {_one_line(t)}" for f in fields for t in get_text_at_path(value, f)]
            body = "\n".join("- " + _one_line(ln) for ln in lines)
        head = "\n".join(f"{k}: {v}" if k == "status" else f"{k}: {_dumps(v)}" for k, v in meta)
        return f"---\n{head}\n---\n\n{body}\n" if body else f"---\n{head}\n---\n"

    def _archive(self, page: _Page, status: str, when: datetime, by: str | None) -> str:
        """Keep `page` under `.history/`, marked `status` (superseded or retired). Returns its path next to the page."""
        hist = page.path.parent / HISTORY
        hist.mkdir(exist_ok=True)
        stem = self._stem(page.key) + "@" + when.strftime("%Y%m%dT%H%M%S%fZ")
        dest, n = hist / f"{stem}.md", 1
        while dest.exists():
            n += 1
            dest = hist / f"{stem}-{n}.md"
        raw = page.path.read_text(encoding="utf-8").replace("\r\n", "\n")
        meta, head, body = _split(raw)
        drop = {"status", "superseded_by", "superseded_at", "retired_at"}
        keep = [ln for ln in head.split("\n") if ln and ln.partition(":")[0].strip() not in drop]
        if not page.ours:  # 人加的页：补上身份，读回来时还知道它是哪个键
            keep += [f"kind: {_dumps(KIND)}", f"namespace: {_dumps(list(page.namespace))}", f"key: {_dumps(page.key)}",
                     f"text_field: {_dumps(self.text_field)}" if "value" not in meta and "text_field" not in meta
                     else ""]
            keep += [] if "updated_at" in meta else [f"updated_at: {_dumps(page.updated_at.isoformat())}"]
            keep += [] if "created_at" in meta else [f"created_at: {_dumps(page.created_at.isoformat())}"]
        keep.append(f"status: {status}")
        if by:
            keep += [f"superseded_by: {_dumps('../' + by)}", f"superseded_at: {_dumps(when.isoformat())}"]
        else:
            keep.append(f"retired_at: {_dumps(when.isoformat())}")
        text = "---\n" + "\n".join(ln for ln in keep if ln) + "\n---\n" + (("\n" + body.lstrip("\n")) if body else "")
        _atomic_write(dest, text)
        return f"{HISTORY}/{dest.name}"

    def _put(self, namespace: tuple[str, ...], key: str, value: dict, index: Any) -> None:
        namespace = tuple(namespace)
        _dumps(value)  # 不能存成 JSON 的值在动任何文件之前就报错
        path = self._dir(namespace) / (self._stem(key) + ".md")
        with self._lock(path):
            cur = self._current(namespace, key)
            now = _now()
            if cur and cur.ours and cur.path == path:
                version = int(cur.meta.get("version") or 1)
                prev = cur.meta.get("supersedes") if isinstance(cur.meta.get("supersedes"), str) else None
                same = self._render(namespace, key, value, index, cur.created_at, cur.updated_at, version, prev)
                if same == path.read_text(encoding="utf-8"):
                    # 同样的内容再写一遍：不算改主意，不留新版本，只更新时间
                    _atomic_write(path, self._render(namespace, key, value, index, cur.created_at, now, version, prev))
                    return
            if path.is_file() and (cur is None or cur.path != path):
                # 存储自己的文件名上有一页，但它不是当前页（被人标成了失效）：原样收进 .history，不覆盖
                stale = self._load(path, namespace)
                if stale:
                    self._archive(stale, stale.status if not stale.live else "superseded", now, path.name)
            supersedes = self._archive(cur, "superseded", now, path.name) if cur else None
            version = int(cur.meta.get("version") or 1) + 1 if cur else 1
            text = self._render(namespace, key, value, index, cur.created_at if cur else now, now, version,
                                supersedes)
            _atomic_write(path, text)
            if cur and cur.path != path:
                cur.path.unlink()  # 人加的同名页已经存进 .history，现在由存储自己的页接替

    def _delete(self, namespace: tuple[str, ...], key: str) -> None:
        namespace = tuple(namespace)
        try:
            path = self._dir(namespace) / (self._stem(key) + ".md")
        except InvalidNamespaceError:
            return
        if not path.parent.is_dir():
            return
        with self._lock(path):
            cur = self._current(namespace, key)
            if cur:
                self._archive(cur, "retired", _now(), None)
                cur.path.unlink()


def _question(query: str) -> str:
    """The question as recall should read it: without the words that only name the namespace's owner."""
    rest = " ".join(OWNER_WORDS.sub(" ", query).split())
    return rest if re.search(r"\w", rest) else query


def _archived_order(stem: str) -> tuple[str, int]:
    when = stem.rpartition("@")[2]
    ts, _, n = when.partition("-")
    return ts, int(n) if n.isdigit() else 1


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.parent / f".{path.stem}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------------------------------------------
# 过滤和命名空间匹配：与 LangGraph 自带的 InMemoryStore 同样的语义


def _matches(value: Mapping, flt: dict | None) -> bool:
    return not flt or all(_compare(value.get(k), v) for k, v in flt.items())


def _compare(item: Any, want: Any) -> bool:
    if isinstance(want, dict):
        if any(k.startswith("$") for k in want):
            return all(_operator(item, k, v) for k, v in want.items())
        return isinstance(item, dict) and all(_compare(item.get(k), v) for k, v in want.items())
    if isinstance(want, (list, tuple)):
        return (isinstance(item, (list, tuple)) and len(item) == len(want)
                and all(_compare(a, b) for a, b in zip(item, want)))
    return item == want


def _operator(value: Any, op: str, arg: Any) -> bool:
    if op == "$eq":
        return value == arg
    if op == "$ne":
        return value != arg
    if op in ("$gt", "$gte", "$lt", "$lte"):
        try:
            a, b = float(value), float(arg)
        except (TypeError, ValueError):
            return False
        return {"$gt": a > b, "$gte": a >= b, "$lt": a < b, "$lte": a <= b}[op]
    raise ValueError(f"Unsupported operator: {op}")


def _does_match(cond: MatchCondition, ns: tuple[str, ...]) -> bool:
    path = tuple(cond.path)
    if len(ns) < len(path):
        return False
    pairs = zip(ns, path) if cond.match_type == "prefix" else zip(reversed(ns), reversed(path))
    if cond.match_type not in ("prefix", "suffix"):
        raise ValueError(f"Unsupported match type: {cond.match_type}")
    return all(p == "*" or a == p for a, p in pairs)
