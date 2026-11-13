#!/usr/bin/env python3
"""Mention it and it comes to mind: what the prompt hook hands the agent when your message names something the vault
knows.

`session_hook.py prompt` calls `recollect()` on every message you send. It looks the message up on this machine, with
no model call, and when a phrase in it names a page it returns at most two pages: each page's conclusion (`how`), its
path, the phrase that brought it up and the path it came by. The hook hands them to the agent as context marked as
memory, not as something you said. When nothing matches it returns nothing and the hook prints nothing.

What counts as a mention, from most to least sure (`ROUTES`; the default is `DEFAULT_ROUTES`):

- `alias`: a name from the alias table (`canonical_sources.psv`), the same table and the same rules as the lock: the
  whole message is the alias, or the alias is inside it and carries it (four or more characters once spaces and
  punctuation are dropped, or half the message). A Latin alias must be whole words (`port` is not in `import`). A
  phrase two pages claim equally picks neither.
- `trigger`: a phrase from the trigger sidecars (`下意识触发词*.psv`: generated trigger words, and questions the
  nightly step learned from real lookups). Same matching, and a learned question counts only when the message repeats
  it.
- `recall`: full-text recall over the message, at `medium` or `high` confidence with the top page at least
  `RECALL_MARGIN` times the second, never a log page. Off by default and not settled (set 45, C1a):
  `KROUTER_RECALL_MARGIN_LOW=<m>` (1.0 ≤ m < `RECALL_MARGIN`) also brings a top page at least `m` times the second when
  the message says `KROUTER_RECALL_KEYWORDS_MIN` (default 1) of its keywords that no other page has (`page_keys.py`,
  the index's `kw` table: names, headings, bold phrases, identifiers, computed with no model).

A name or trigger match also needs a second key: full-text recall over the whole message must not refuse it, or its
top page must match at least `GATE_STRONG` of the message's content words. A name inside a message about something
else ("a sunset header banner for my photography site") fails it. Recall reads the index as it is and never builds it
in the hook: `keep_index_fresh` updates it in a detached process at most every ten minutes, and until the first build
finishes nothing is brought.

On by default (`DEFAULT_ON`), together with the standing index the session-start hook hands over
(`compile_subconscious.standing_index`). Alone, on set 32's held-out half (`bench/memory_honesty/HELDOUT.md`), it
stayed quiet (1 of 24 should-be-quiet messages brought a page, no wrong or superseded page) but brought the right page
on only 7 of 24 mentions: people mostly say a thing in other words. With the index in front of the host (set 35), the
two together remembered 23 or 24 of 24 mentions and 12 of 12 changed rules on held-out, with 1 or 2 of 24 quiet
messages moving either layer, for both Haiku 5.5 and Sonnet 5.5.

Never brought: a page marked superseded (or retired, rejected, …), expired, not yet valid, or secret, and a page in
the knowledge base (`kb.py`: reference material, not something you decided; the standing index leaves it out too). A mention of an
old page brings the page that replaced it (`superseded_by`) and says an earlier page said otherwise; a page that
`supersedes` another says so too; a page with a later "⚠ 已改" line says what changed. Pages the brought page links to
come along as titles only.

Not matched: code fences, and lines that read like pasted code, logs, stack traces, diffs, commands or config (the hook
already drops blocks the app attached). A message over `PROSE_MAX` characters of prose is not matched at all.

Quiet: a page already brought in this session is not brought again unless its conclusion changed; at most
`PER_SESSION` pages per session. `KROUTER_RECALL_PROMPT=0` turns the prompt hook's lookup off (a comma list such as
`alias,trigger` picks the routes), `KROUTER_RECALL_INDEX=0` the standing index, `KROUTER_INJECT=0` both;
`KROUTER_RECALL_GATE=0` drops the second key (not advised). `KROUTER_RECALL_LEARN=1` turns on learning from what the
agent fetched (`learn_mentions.py`; off by default, set 36).

Every page brought is written to `~/.local/state/krouter/recalled.jsonl` (`KROUTER_STATE_DIR`): time, app and session,
the sentence (redacted, cut to 200 characters), the phrase, the route, the page. That file is what `why` and the
viewer read. It is outside the vault and never sent anywhere.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import zones  # noqa: E402
from canonical_lookup import DEAD_STATUSES, PARTICLES, in_force, load_rows, map_for, parse_frontmatter  # noqa: E402
from krouter_redact import is_secret_page, redact  # noqa: E402

ROUTES = ("alias", "trigger", "recall")
DEFAULT_ROUTES = ("alias", "trigger", "recall")
DEFAULT_ON = True  # 第 32 套钩子单独没过（想起 7/24）；第 35 套钩子加下意识索引两个宿主都过线：两层默认打开
PER_PROMPT = 2
PER_SESSION = 10
PROSE_MAX = 2000
HOW_MAX = 160
SENTENCE_MAX = 200
TRIGGER_GLOB = "下意识触发词*.psv"
LEARNED_MARK = "自学习"
PROVISIONAL_MARK = "待验证"  # learn_mentions.py 夜里从「钩子没递、宿主自己取了」学到的说法
KEEP_DAYS = 3
# 第二把钥匙：名字对上之后，这句话其余的词也要和库对得上（召回没拒答，或首条页对上至少这么多实词）
GATE = os.environ.get("KROUTER_RECALL_GATE", "1") != "0"
GATE_STRONG = 4
RECALL_CONF = ("medium", "high")
RECALL_MARGIN = 2.5
# 第 45 套 C1a：领先不到 RECALL_MARGIN 时，领先不低于这个较低倍数、且这页的特有关键词（page_keys.py，库里只此一页有）
# 在消息里出现至少 KEYWORDS_MIN 个，也递。默认关（不设就和原来逐字节相同）；较低倍数没定默认值，开发集上选
MARGIN_LOW_ENV = "KROUTER_RECALL_MARGIN_LOW"
KEYWORDS_MIN_ENV = "KROUTER_RECALL_KEYWORDS_MIN"
LOG_TYPES = {"log", "daily-log", "session", "session-excerpt", "correction-candidates"}


def routes() -> tuple[str, ...]:
    """The routes in force: `KROUTER_RECALL_PROMPT` (0 off, 1 the default routes, or a comma list), else the
    default."""
    if os.environ.get("KROUTER_INJECT") == "0":
        return ()
    raw = (os.environ.get("KROUTER_RECALL_PROMPT") or "").strip().lower()
    if raw in ("0", "off", "false", "no"):
        return ()
    if raw in ("", "1", "on", "true", "yes"):
        return DEFAULT_ROUTES if (raw or DEFAULT_ON) else ()
    return tuple(r for r in ROUTES if r in {p.strip() for p in raw.split(",")})


# ---------- what you typed, without what you pasted ----------

FENCE = re.compile(r"^[ \t]*(```|~~~).*?(^[ \t]*\1[^\n]*$|\Z)", re.S | re.M)
CJK = re.compile(r"[㐀-鿿]")
LOG_LINE = re.compile(
    r"^\s*(\[?\d{4}-\d{2}-\d{2}[T ]\d{1,2}:\d{2}|\[?\d{1,2}:\d{2}:\d{2}|Traceback \(most recent|File \"[^\"]+\", line \d+"
    r"|at [\w.$<>\[\]/]+[(:]|[\w.]*(Error|Exception|Warning)\b[:(]|(ERROR|WARN|WARNING|INFO|DEBUG|TRACE|FATAL|CRITICAL)\b"
    r"|(\+\+\+|---|@@) |diff --git|index [0-9a-f]{7,}|[+-](?![ +-])\S|[+-]\s+[A-Za-z_][\w.-]*:(\s|$)"
    r"|<{7}|={7}|>{7}|[\w.-]+\s+\|\s"
    r"|[$#%>] |>>> |\.\.\. |PS [A-Z]:\\|[A-Z]:\\|~?/[\w.-]+/[\w./-]+(:\d+)?\s*$)")
KEYWORD_LINE = re.compile(
    r"^\s*(import|from|def|class|return|const|let|var|function|func|package|public|private|protected|static|async|await"
    r"|if|elif|else|for|while|try|except|catch|finally|switch|case|resource|module|provider|variable)\b")
SQL_LINE = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|WITH)\s")
CODE_LINE = re.compile(
    r"^\s*([{}\[\]<]|\"[\w.-]+\"\s*:|[A-Za-z_][\w.-]*\s*(=|:=|=>|->)\s*\S|[a-z_][\w.-]*:\s*\S*\s*$"
    r"|(apiVersion|kind|metadata|spec):"
    r"|(git|npm|pnpm|yarn|npx|pip3?|python3?|docker|kubectl|helm|curl|wget|terraform|psql|mysql|redis-cli|ssh|scp|brew"
    r"|sudo|apt|cargo)\s+[-\w./~\"'$]"
    r"|(go|make|cd|ls|cat|grep|echo|export|node)\s+[-./~$])")
SENTENCE = re.compile(r"([.?!。？！]\s*$|,\s|，)")
SYMBOLS = set("{}[]()<>;=|\\$&*`^~")


def code_like(line: str) -> bool:
    s = line.rstrip()
    if not s.strip():
        return False
    if s.startswith(("    ", "\t")) or LOG_LINE.match(s):
        return True
    if s.startswith("  ") and not CJK.search(s) and not SENTENCE.search(s):
        return True  # 缩进的配置、代码（「  GPU hours: 8」）
    n = sum(c in SYMBOLS for c in s)
    words = len(s.split())
    if CJK.search(s) and len(CJK.findall(s)) * 3 >= len(s.strip()):
        return False  # 以中文为主的行是你说的话（「if 明天还挂就回滚」也算）
    if n == 0 and words >= 5 and SENTENCE.search(s):
        return False  # 一句完整的英文：「terraform plan failed again, can you look?」
    if SQL_LINE.match(s) or CODE_LINE.match(s):
        return True
    if KEYWORD_LINE.match(s) and re.search(r"[:{;(=]\s*$|\(.*\)|=", s):
        return True
    return not CJK.search(s) and n >= 3 and n * 12 >= len(s)


def prose(text: str) -> str:
    """What the person wrote in their own words: code fences dropped, and lines that read like pasted code, logs or
    command output."""
    text = FENCE.sub("\n", text.replace("\r\n", "\n"))
    return "\n".join(ln for ln in text.split("\n") if not code_like(ln)).strip()


# ---------- matching ----------

def squash(text: str) -> tuple[str, list[int], set[int]]:
    """The lock's normalisation (`canonical_lookup.normalize`) with a map back to the text: (normalised, position in
    `text` of each kept character, positions in the normalised string where a word boundary sits)."""
    out: list[str] = []
    where: list[int] = []
    cut: set[int] = {0}
    gap = False
    for i, ch in enumerate(text):
        if ch in PARTICLES or ch.isspace() or unicodedata.category(ch).startswith(("P", "S")):
            gap = True
            continue
        if gap:
            cut.add(len(out))
            gap = False
        out.append(ch.lower())
        where.append(i)
    s = "".join(out)
    cut.add(len(s))
    for k in range(1, len(s)):
        if not (_latin(s[k - 1]) and _latin(s[k])):
            cut.add(k)
    return s, where, cut


def _latin(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


def norm(value: str) -> str:
    return squash(value)[0]


def carries(a: str, q: str) -> bool:
    """The lock's rule (`canonical_lookup.carries`): a short name inside a long message is not what it is about."""
    return a == q or len(a) >= 4 or len(a) * 2 >= len(q)


def spans(a: str, s: str, cut: set[int]) -> list[tuple[int, int]]:
    out, i = [], s.find(a)
    while i >= 0:
        if i in cut and i + len(a) in cut:
            out.append((i, i + len(a)))
        i = s.find(a, i + 1)
    return out


SENT_END = re.compile(r"[。！？!?；;\n]|(?<=[.])\s")


def sentence_at(text: str, pos: int) -> str:
    start = 0
    for m in SENT_END.finditer(text):
        if m.end() <= pos:
            start = m.end()
        else:
            end = m.end()
            break
    else:
        end = len(text)
    return re.sub(r"\s+", " ", text[start:end]).strip()


# ---------- the vault side ----------

def _trigger_files(vault: Path) -> list[Path]:
    system = zones.path(vault, "90 系统文件")
    return sorted(system.rglob(TRIGGER_GLOB)) if system.is_dir() else []


def _sources(vault: Path) -> list[Path]:
    mp = map_for(vault)
    return ([mp] if mp.is_file() else []) + _trigger_files(vault)


def _entries_cache(vault: Path) -> Path:
    """Next to the recall index (`recall_index.cache_path`, same folder and key), without importing it."""
    base = Path(os.environ.get("KROUTER_CACHE_DIR") or Path.home() / ".cache" / "krouter")
    return base / f"mentions-{hashlib.sha1(str(vault.resolve()).encode('utf-8')).hexdigest()[:12]}.marshal"


def entries(vault: Path) -> list[tuple]:
    """Every phrase that can bring a page: alias rows (with their anchor) and trigger lines, normalised. Compiled once
    and kept next to the recall index, keyed by each source file's size and modification time, so a message does not
    re-read a 10,000-line trigger file."""
    key = str(vault)
    if key in _ENTRIES:
        return _ENTRIES[key]
    files = _sources(vault)
    stamp = []
    for f in files:
        try:
            st = f.stat()
            stamp.append([str(f), st.st_mtime_ns, st.st_size])
        except OSError:
            pass
    cache = _entries_cache(vault)
    try:
        import marshal

        got = marshal.loads(cache.read_bytes())
        if got[0] == ENTRIES_VERSION and got[1] == stamp:
            _ENTRIES[key] = got[2]
            return got[2]
    except (OSError, ValueError, EOFError, TypeError, IndexError):
        pass
    out = _compile(vault, files)
    try:
        import marshal

        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_name(cache.name + f".{os.getpid()}.tmp")
        tmp.write_bytes(marshal.dumps((ENTRIES_VERSION, stamp, out)))
        os.replace(tmp, cache)
    except (OSError, ValueError):
        pass
    _ENTRIES[key] = out
    return out


FIELDS = ("route", "a", "word", "rel", "anchor", "id", "learned", "provisional")  # 每条短语是这样一个元组（缓存里也是）


ENTRIES_VERSION = 4


def _compile(vault: Path, files: list[Path]) -> list[tuple]:
    out: list[tuple] = []
    mp = map_for(vault)
    if mp.is_file():
        try:
            rows = load_rows(mp)
        except ValueError:
            rows = []
        for case_id, aliases, source, anchor in rows:
            for alias in aliases:
                a = norm(alias)
                if a:
                    out.append(("alias", a, alias, source, anchor, case_id, False, False))
    for f in files:
        if f == mp:
            continue
        learned = LEARNED_MARK in f.name
        provisional = PROVISIONAL_MARK in f.name
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if not line or line.startswith("#") or line.count("|") != 1:
                continue
            rel, words = (p.strip() for p in line.split("|"))
            for w in ([words] if learned else words.split(";")):
                a = norm(w)
                if a and (not learned or len(a) >= 6):
                    out.append(("trigger", a, w.strip(), rel, "", "", learned, provisional))
    return out


_ENTRIES: dict[str, list[tuple]] = {}
_PAGES: dict[str, tuple[dict, str] | None] = {}


def page(vault: Path, rel: str) -> tuple[dict, str] | None:
    """(frontmatter, body) of a vault page, or None when it is missing."""
    if rel in _PAGES:
        return _PAGES[rel]
    p = vault / rel
    got = None
    if p.is_file():
        try:
            text = p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        except OSError:
            text = None
        if text is not None:
            fm = parse_frontmatter(p)
            body = text.split("---", 2)[2] if text.startswith("---") and text.count("---") >= 2 else text
            got = (fm, body)
    _PAGES[rel] = got
    return got


LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")


def resolve(vault: Path, target: str, near: str = "", anywhere: bool = True) -> str:
    """The vault path a `[[link]]` names: next to `near` first, then at the top, then (with `anywhere`) by file name
    anywhere in the vault, which walks it once per process."""
    name = target.strip().strip('"').strip("'")
    m = LINK.search(name)
    name = (m.group(1) if m else name).strip()
    if not name:
        return ""
    if not name.endswith(".md"):
        name += ".md"
    if near:
        cand = (Path(near).parent / name).as_posix()
        if (vault / cand).is_file():
            return cand
    if (vault / name).is_file():
        return name
    if not anywhere:
        return ""
    return _by_name(vault).get(Path(name).name, "")


_NAMES: dict[str, dict[str, str]] = {}


def _by_name(vault: Path) -> dict[str, str]:
    key = str(vault)
    if key not in _NAMES:
        names: dict[str, str] = {}
        for root, dirs, files in os.walk(vault):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                if f.endswith(".md"):
                    names.setdefault(f, (Path(root) / f).relative_to(vault).as_posix())
        _NAMES[key] = names
    return _NAMES[key]


def alive(fm: dict, today: date) -> bool:
    return in_force(fm, today)[0]


def secret(vault: Path, rel: str, fm: dict) -> bool:
    return is_secret_page(zones.canon(vault, rel), fm)


def current(vault: Path, rel: str, today: date) -> tuple[str, str] | None:
    """(page to bring, the older page it stands in for or ""): a live page is itself; a replaced page is the page that
    replaced it (`superseded_by`, followed at most three steps), when that one is live; anything else is None."""
    import kb

    seen = []
    for _ in range(4):
        got = page(vault, rel)
        if got is None:
            return None
        if kb.reason(vault, rel):
            return None  # 知识库的页是参考资料，不当成「定过的事」递给宿主（kb.py）
        fm = got[0]
        if alive(fm, today):
            return (rel, seen[0] if seen else "") if not secret(vault, rel, fm) else None
        if (fm.get("status") or "").strip().lower() not in DEAD_STATUSES:
            return None  # 过期、还没生效：不递，也不顺着找
        nxt = resolve(vault, fm.get("superseded_by", ""), rel)
        if not nxt or nxt in seen or nxt == rel:
            return None
        seen.append(rel)
        rel = nxt
    return None


CHANGED_LINE = re.compile(r"⚠\s*(已改|changed)\s*[（(]([^）)]*)[）)]\s*[：:]\s*(.+)")


def gist(body: str) -> str:
    import recall_index as ri

    out = ""
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "|", "```", "<", "![", "%%")):
            continue
        cleaned = ri._clean(line)
        if len(cleaned) < 8 or ri.STATUS_LINE_RE.match(cleaned):
            continue
        out = (out + " " + cleaned).strip() if out else cleaned
        if len(out) >= HOW_MAX * 0.6:
            break
    return out


def cut(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def describe(vault: Path, rel: str, anchor: str, older: str, today: date) -> dict:
    fm, body = page(vault, rel) or ({}, "")
    how = fm.get("how") or anchor or gist(body) or fm.get("title") or Path(rel).stem
    notes = []
    changed = [m for m in CHANGED_LINE.finditer(body)]
    if changed:
        m = changed[-1]
        notes.append(("changed", f"{m.group(2).strip()}: {LINK.sub(lambda x: x.group(1), m.group(3)).strip()}"))
    old = older or resolve(vault, fm.get("supersedes", ""), rel)
    if old:
        notes.append(("older", zones.canon(vault, old)))
    links = []
    for m in LINK.finditer(body):
        r = resolve(vault, m.group(1), rel, anywhere=False)  # 只是带个标题：不为它走遍整个库
        if r and r not in (rel, old) and r not in links:
            got = page(vault, r)
            if got and alive(got[0], today) and not secret(vault, r, got[0]):
                links.append(r)
        if len(links) >= 2:
            break
    return {"rel": zones.canon(vault, rel), "real": rel, "how": cut(redact(how), HOW_MAX), "notes": notes,
            "related": [Path(r).stem for r in links]}


def recollect(vault: Path, text: str, use: tuple[str, ...] | None = None, today: date | None = None) -> list[dict]:
    """Pages the message names, best first, at most PER_PROMPT: [{rel, how, notes, related, route, word, sentence}]."""
    use = routes() if use is None else use
    if not use:
        return []
    today = today or date.today()
    said = prose(text)
    if not said or len(said) > PROSE_MAX:
        return []
    s, where, cuts = squash(said)
    if not s:
        return []
    found: list[dict] = []
    for row in entries(vault):
        a = row[1]
        if a not in s or row[0] not in use or not (row[6] or carries(a, s)):
            continue
        e = dict(zip(FIELDS, row))
        for sp in spans(a, s, cuts):
            found.append({**e, "span": sp})
    hits = _choose(vault, found, today)
    res = None
    if hits and GATE:
        res = _ranked(vault, said)
        if res is None or not (res.get("confidence") != "none" or (res.get("strong") or 0) >= GATE_STRONG):
            hits = []  # 名字对上了，这句话的其他词却和库对不上：多半说的是别的事
    if "recall" in use and len(hits) < PER_PROMPT:
        res = res or _ranked(vault, said)
        hits += _recall_hits(vault, res, today, {h["real"] for h in hits}, said)
    out = []
    brought_cold = [h for h in hits[:PER_PROMPT] if h.get("cold")]
    if brought_cold:
        import hot

        hot.warm_again(vault, [hot.key(h["a"], zones.canon(vault, h["rel"])) for h in brought_cold])  # 用到了：当场恢复
    for h in hits[:PER_PROMPT]:
        pos = where[h["span"][0]] if h.get("span") else 0
        d = describe(vault, h["real"], h.get("anchor", ""), h.get("older", ""), today)
        d.update(route=h["route"], word=h["word"], sentence=cut(redact(sentence_at(said, pos)), SENTENCE_MAX),
                 provisional=bool(h.get("provisional")))
        out.append(d)
    return out


def _choose(vault: Path, found: list[dict], today: date) -> list[dict]:
    """One hit per page. Longer phrases win where they overlap; a span two live pages claim equally brings neither;
    alias before trigger, then the longer phrase."""
    live = []
    for f in found:
        cur = current(vault, f["rel"], today)
        if cur is None:
            continue
        rel, older = cur
        if rel != f["rel"]:
            f = {**f, "anchor": "", "older": older}  # 旧页的锚点说的是旧结论：换成新页后不能再用
        live.append({**f, "real": rel})
    # 同一段文字：最长的那个短语说了算；它对应两个不同的页就都不递（锁不能猜）
    live.sort(key=lambda f: (-(f["span"][1] - f["span"][0]), f["route"] != "alias", bool(f.get("older"))))
    taken: list[tuple[int, int]] = []
    by_page: dict[str, dict] = {}
    blocked: set[tuple[int, int]] = set()
    for f in live:
        sp = f["span"]
        if sp in blocked:
            continue
        same = [g for g in live if g["span"] == sp and g["real"] != f["real"]
                and (g["route"] == f["route"] or g["route"] == "alias")]
        if same:
            blocked.add(sp)
            continue
        if any(a < sp[1] and sp[0] < b and (a, b) != sp for a, b in taken):
            continue
        taken.append(sp)
        if f["real"] not in by_page:
            by_page[f["real"]] = f
    # 冷的触发词（hot.py：hot_days 天没递出过）排在同类后面，先让出每句话两页的位置；别名表是你的，不降
    import hot

    frozen = hot.cold_triggers(vault)
    for f in by_page.values():
        f["cold"] = f["route"] == "trigger" and hot.key(f["a"], zones.canon(vault, f["rel"])) in frozen
    return sorted(by_page.values(), key=lambda f: (f["route"] != "alias", f["cold"], -(f["span"][1] - f["span"][0]),
                                                   f["span"][0]))


def _ranked(vault: Path, said: str) -> dict | None:
    """Full-text recall over the message, from the index as it is (never rebuilt here: this runs on every message)."""
    import recall_index as ri

    if not ri.cache_path(vault).is_file():
        return None
    try:
        return ri.recall(vault, said, refresh_first=False, assoc=False, conflict=True)
    except Exception:  # noqa: BLE001
        return None


def margin_low() -> tuple[float, int] | None:
    """(lower margin, keywords needed) when the corroborated margin is on (`KROUTER_RECALL_MARGIN_LOW`), else None."""
    try:
        low = float(os.environ.get(MARGIN_LOW_ENV) or 0)
        need = int(os.environ.get(KEYWORDS_MIN_ENV) or 1)
    except ValueError:
        return None
    return (low, max(1, need)) if 1.0 <= low < RECALL_MARGIN else None


def corroborating(vault: Path, rel: str, said: str) -> list[str]:
    """The keywords of `rel` that no other page has and that the message says (whole words for Latin), from the
    index's `kw` table, read-only. Empty when the table is missing or anything fails."""
    import sqlite3

    import recall_index as ri

    s, _where, cuts = squash(said)
    try:
        con = sqlite3.connect(f"file:{ri.cache_path(vault)}?mode=ro", uri=True, timeout=2)
        try:
            terms = [t for (t,) in con.execute("SELECT DISTINCT term FROM kw WHERE rel=?", (rel,)) if t and t in s]
            return [t for t in terms if spans(t, s, cuts) and con.execute(
                "SELECT count(DISTINCT rel) FROM kw WHERE term=?", (t,)).fetchone()[0] == 1]
        finally:
            con.close()
    except sqlite3.Error:
        return []


def _recall_hits(vault: Path, res: dict | None, today: date, have: set[str], said: str = "") -> list[dict]:
    import recall_index as ri

    allowed = ("high",) if ri.strict_on(vault) else RECALL_CONF  # 严格模式：全文召回只递有直接依据的页
    if not res or not res.get("hits") or res.get("partial") or res.get("confidence") not in allowed:
        return []
    top = res["hits"][0]
    word = " ".join(res.get("query_tokens", [])[:4])
    if top.get("tier") in ("log", "dead"):
        return []
    if (res.get("margin") or 0) < RECALL_MARGIN:
        low = margin_low()
        if low is None or (res.get("margin") or 0) < low[0]:
            return []
        keys = corroborating(vault, top["rel"], said)
        if len(keys) < low[1]:
            return []
        word = " ".join(keys[:4])
    real = zones.real(vault, top["rel"])
    cur = current(vault, real, today)
    if cur is None or cur[0] in have:
        return []
    if (page(vault, cur[0]) or ({}, ""))[0].get("type", "").lower() in LOG_TYPES:
        return []  # 日记、会话摘录是线索，不是结论：不靠全文召回递
    older = ""
    for c in res.get("conflict") or []:
        if isinstance(c, dict) and c.get("older"):
            older = zones.real(vault, c["older"])
    return [{"route": "recall", "word": word, "rel": real, "real": cur[0],
             "anchor": "", "older": cur[1] or older}]


REFRESH_EVERY = 600


def keep_index_fresh(vault: Path) -> None:
    """At most once every REFRESH_EVERY seconds, bring the recall index up to date in a detached process (it only
    re-reads pages that changed), so this hook never waits for it and a new page shows up within minutes."""
    stamp = state_dir() / f"recall-refresh-{hashlib.sha1(str(vault).encode()).hexdigest()[:12]}.stamp"
    try:
        if stamp.exists() and time.time() - stamp.stat().st_mtime < REFRESH_EVERY:
            return
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.touch()
        import subprocess

        kw = {"start_new_session": True} if os.name != "nt" else {"creationflags": 0x00000008}
        subprocess.Popen([sys.executable, str(HERE / "recall_index.py"), "--vault", str(vault), "--stats"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env={**os.environ, "KROUTER_NO_QUERY_LOG": "1"}, **kw)
    except OSError:
        pass


def index_on() -> bool:
    """Whether the session-start hook hands over the standing index (`KROUTER_RECALL_INDEX`, default DEFAULT_ON)."""
    if os.environ.get("KROUTER_INJECT") == "0":
        return False
    raw = (os.environ.get("KROUTER_RECALL_INDEX") or "").strip().lower()
    if raw in ("0", "off", "false", "no"):
        return False
    return DEFAULT_ON if raw in ("",) else True


# ---------- learning: what the host fetched when the hook said nothing ----------

LEARN_LOG = "recall-learn.jsonl"
TAIL_BYTES = 2_000_000
CANON_LINE = re.compile(r"canonical_source:\s*(\S[^\n\"]*\.md)")
RECALL_LINE = re.compile(r"(?:^|\n)recall:\n- ([^\n]+?\.md) tier=")


def _strings(obj):
    """Every string in a transcript row (its tool results, its text), as written: not the JSON dump, whose escaping
    hid Windows paths (`C:\\Users\\…`) from the patterns."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _last_file(agent: str, session: str) -> Path:
    safe = re.sub(r"[^\w.-]", "_", f"{agent}-{session}")[:120]
    return state_dir() / "recalled" / f"{safe}.last.json"


def no_capture(agent: str, session: str, now: bool) -> bool:
    """Whether this session is marked `#不记`: `now` (this message says so) sets the mark for the rest of it."""
    if not session:
        return now
    f = _last_file(agent, session).with_suffix(".nocapture")
    if now:
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.touch()
        except OSError:
            pass
        return True
    return f.exists()


def learn_on() -> bool:
    """Whether the turn hook notes what the agent fetched for the nightly `learn_mentions` step (`KROUTER_RECALL_LEARN=1`;
    off by default: set 36 did not show it works, and it keeps the latest message's words in the state folder)."""
    return bool(routes()) and os.environ.get("KROUTER_RECALL_LEARN", "") in ("1", "on", "true", "yes")


def remember_turn(agent: str, session: str, text: str, hits: list[dict], quiet: bool = False) -> None:
    """What this message said (redacted prose, at most 300 characters; nothing under `#不记`) and what was brought for
    it. Overwritten every message, so only the latest one is kept; the turn hook reads it when the turn ends. Only
    with `learn_on()`."""
    if not session or not learn_on():
        return
    f = _last_file(agent, session)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"ts": time.time(), "sentence": "" if quiet else cut(redact(prose(text)), 300),
                                 "pages": [{"page": h["rel"], "route": h["route"], "word": h["word"],
                                            "provisional": bool(h.get("provisional"))} for h in hits]},
                                ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _tail_lines(path: Path) -> list[dict]:
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - TAIL_BYTES))
            data = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for line in data.splitlines()[1 if size > TAIL_BYTES else 0:]:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict):
            out.append(d)
    return out


def _when(d: dict) -> float:
    raw = str(d.get("timestamp") or "")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _final_text(rows: list[dict]) -> str:
    """The agent's last words in these transcript lines (Claude Code and Codex shapes)."""
    said = ""
    for d in rows:
        if d.get("type") == "assistant":
            content = (d.get("message") or {}).get("content")
            texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"] \
                if isinstance(content, list) else ([content] if isinstance(content, str) else [])
            if any(x.strip() for x in texts):
                said = "\n".join(texts)
        p = d.get("payload") if isinstance(d.get("payload"), dict) else {}
        if d.get("type") == "response_item" and p.get("type") == "message" and p.get("role") == "assistant":
            texts = [c.get("text", "") for c in p.get("content") or [] if isinstance(c, dict)]
            if any(x.strip() for x in texts):
                said = "\n".join(texts)
    return said


def fetched_pages(vault: Path, rows: list[dict]) -> list[str]:
    """Vault pages a lookup in these transcript lines returned (a lock's `canonical_source`, recall's first page) or a
    tool read directly, in order; logical paths."""
    roots = {str(vault.resolve()).replace("\\", "/"), str(vault).replace("\\", "/")}
    out: list[str] = []
    for d in rows:
        found = []
        for text in _strings(d):
            if "canonical_source" not in text and " tier=" not in text and not any(r in text.replace("\\", "/") for r in roots):
                continue
            text = text.replace("\\", "/")  # Windows 的路径分隔符
            found += [m.group(1) for m in CANON_LINE.finditer(text)]
            found += [m.group(1) for m in RECALL_LINE.finditer(text)]
            for root in roots:
                found += [m.group(1) for m in re.finditer(re.escape(root) + r"/([^\"\n]+?\.md)", text)]
        for raw in found:
            raw = raw.replace("\\", "/")
            for root in sorted(roots, key=len, reverse=True):
                if raw.startswith(root + "/"):
                    raw = raw[len(root) + 1:]
                    break
            rel = zones.canon(vault, raw)
            if (vault / zones.real(vault, rel)).is_file() and rel not in out:
                out.append(rel)
    return out


def cited(text: str, rel: str) -> bool:
    stem = Path(rel).stem
    return rel in text or (len(stem) >= 2 and stem in text)


def capture_turn(vault: Path, agent: str, session: str, transcript: Path) -> list[dict]:
    """At the end of a turn: pages the agent fetched and then used (named in its answer) that the prompt hook had not
    brought become `learn` events; a page the hook brought by a provisional trigger that the agent passed over for
    another page it fetched and used becomes a `contradict` event. Written to LEARN_LOG for `learn_mentions.py`."""
    f = _last_file(agent, session)
    try:
        last = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = [d for d in _tail_lines(transcript) if _when(d) >= last.get("ts", 0) - 5 or not d.get("timestamp")]
    if not rows:
        return []
    answer = _final_text(rows)
    used = [p for p in fetched_pages(vault, rows) if cited(answer, p)]
    given = {g["page"] for g in last.get("pages", [])}
    events = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for p in used:
        if p not in given and last.get("sentence"):
            events.append({"ts": ts, "kind": "learn", "agent": agent, "session": session[:8],
                           "sentence": last["sentence"], "page": p})
    if used:
        for g in last.get("pages", []):
            if g.get("provisional") and g["page"] not in used and not cited(answer, g["page"]):
                events.append({"ts": ts, "kind": "contradict", "agent": agent, "session": session[:8],
                               "phrase": g["word"], "page": g["page"], "instead": used[0]})
    if events:
        try:
            with (state_dir() / LEARN_LOG).open("a", encoding="utf-8") as fh:
                for e in events:
                    fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        except OSError:
            pass
    try:
        f.unlink()  # 一轮只判一次
    except OSError:
        pass
    return events


# ---------- the session: no repeats, a cap ----------

def state_dir() -> Path:
    return Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local/state/krouter")


def _hash(d: dict) -> str:
    return hashlib.sha1(json.dumps([d["how"], d["notes"]], ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def keep_new(hits: list[dict], agent: str, session: str) -> list[dict]:
    """The hits not yet brought in this session (or whose conclusion changed since), within PER_SESSION; records them."""
    if not hits or not session:
        return hits
    folder = state_dir() / "recalled"
    safe = re.sub(r"[^\w.-]", "_", f"{agent}-{session}")[:120]
    f = folder / f"{safe}.json"
    try:
        st = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {"given": {}, "n": 0}
    out = []
    for h in hits:
        k = _hash(h)
        if st["given"].get(h["rel"]) == k or st["n"] >= PER_SESSION:
            continue
        st["given"][h["rel"]] = k
        st["n"] += 1
        out.append(h)
    if out:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            fresh = not f.exists()
            f.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
            if fresh:
                old = time.time() - KEEP_DAYS * 86400
                for g in folder.glob("*"):
                    try:
                        if g.stat().st_mtime < old:  # 连同 .last.json / .nocapture
                            g.unlink()
                    except OSError:
                        pass
        except OSError:
            pass
    return out


def log(hits: list[dict], agent: str, session: str) -> None:
    """One line per page brought, outside the vault: what `why` and the viewer show."""
    if not hits:
        return
    try:
        base = state_dir()
        base.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with (base / "recalled.jsonl").open("a", encoding="utf-8") as fh:
            for h in hits:
                row = {"ts": ts, "agent": agent, "session": session[:8], "route": h["route"], "word": h["word"],
                       "sentence": h["sentence"], "page": h["rel"]}
                if h["notes"]:
                    row["notes"] = [list(n) for n in h["notes"]]
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ---------- what the agent sees ----------

HEAD = {"zh": "KRouter 记忆提示（从用户的记忆库里想起的，不是用户这句话里说的；和这句话无关就不用管）：",
        "en": "KRouter memory note (recalled from the user's vault, not typed by the user; it may not bear on this message):"}
VIA = {"zh": {"alias": "别名", "trigger": "触发词", "recall": "全文召回"},
       "en": {"alias": "alias", "trigger": "trigger", "recall": "full-text recall"}}
OLDER = {"zh": "更早的一页说法不同（{p}），以这页为准", "en": "an earlier page said otherwise ({p}); this one holds"}
CHANGED = {"zh": "这页后来改过：{t}", "en": "changed later: {t}"}
RELATED = {"zh": "相关页：{t}", "en": "related: {t}"}
TAIL = {"zh": "用到就注明出处页。", "en": "If you use it, cite the page."}


def render(hits: list[dict]) -> str:
    if not hits:
        return ""
    lang = "zh" if any(CJK.search(h["how"] + h["word"]) for h in hits) else "en"
    body = [HEAD[lang]]
    for h in hits:
        extra = []
        for kind, val in h["notes"]:
            extra.append((OLDER if kind == "older" else CHANGED)[lang].format(p=val, t=val))
        if h["related"]:
            extra.append(RELATED[lang].format(t="、".join(h["related"]) if lang == "zh" else ", ".join(h["related"])))
        tail = ("；" if lang == "zh" else "; ").join(extra)
        q = f"「{h['word']}」" if lang == "zh" else f"\"{h['word']}\""
        page = h.get("real") or h["rel"]  # 给宿主看库里真实的路径（英文库是 02 Methods/…）；recalled.jsonl 仍记逻辑路径
        body.append(f"- {q} → {h['how']} 〔{page}，{VIA[lang][h['route']]}〕" if lang == "zh"
                    else f"- {q} → {h['how']} [{page}, {VIA[lang][h['route']]}]")
        if tail:
            body.append(f"  {tail}")
    body.append(TAIL[lang])
    return "\n".join(body)


def main(argv: list[str]) -> int:
    """`recollect.py --vault V "message"`: print what the prompt hook would hand over (for trying it by hand)."""
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--vault", default="")
    ap.add_argument("--routes", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("text")
    args = ap.parse_args(argv)
    from krouter_home import vault_path

    raw = args.vault or vault_path()
    if not raw:
        print("set KROUTER_VAULT", file=sys.stderr)
        return 2
    use = tuple(r for r in args.routes.split(",") if r in ROUTES) if args.routes else None
    hits = recollect(Path(raw), args.text, use)
    print(json.dumps(hits, ensure_ascii=False, indent=1) if args.json else render(hits))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
