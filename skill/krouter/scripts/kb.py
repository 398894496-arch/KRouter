#!/usr/bin/env python3
"""The knowledge base: reference material in the memory folder, kept apart from what you decided.

A memory folder holds two kinds of page. **Your memory** is what you decided, your rules and corrections, and what
sessions were distilled into. **The knowledge base** is reference material: articles, web clippings, research notes,
documents someone else wrote. Both are indexed and both are found with their source, but a knowledge-base page is never
evidence of what you decided: a lookup lists it in a block of its own, and only your memory sets the confidence.

A page is in the knowledge base when

- a folder on its path is declared in `krouter-kb.txt` at the root of the memory folder (one folder per line, relative
  to the memory folder, `#` for comments; it travels with the memory folder, and a person can read and edit it), or
- a folder on its path is named for clippings (`剪藏`, `Clippings`, `Web clips`), or its frontmatter is a web
  clipper's (a `source:` URL, a `clippings` tag, `type: clipping`). These were treated as clippings before the
  knowledge base existed and need no declaration. (A folder named exactly `Clippings` is not indexed at all.)

    kb.py list                       # the declared folders, and the pages each holds
    kb.py add Research "03 资料"      # declare folders (they must exist)
    kb.py remove Research
    kb.py suggest                    # folders that look like reference material and are not declared (a suggestion only)
    kb.py import report.pdf [--to Research] [--force]   # PDF, Word, HTML, … to a Markdown page in the knowledge base

`suggest` never declares anything; `krouter doctor` shows its findings. `import` converts with a tool already on this
machine (`markitdown`, `pandoc`, or `pdftotext` for PDF); HTML falls back to a plain converter in the standard
library. Nothing is installed for you: when no tool can read the file, it says which one to install.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zones  # noqa: E402

KB_FILE = "krouter-kb.txt"
# 剪藏识别（2.0 起）：文件夹名，或网页剪藏插件写的 frontmatter。它们自动算知识库，不用声明
CLIP_PATH = re.compile(r"(^|/)[^/]*(剪藏|clippings?|web ?clips?)[^/]*/", re.I)
CLIP_FM = re.compile(r"^source:\s*[\"']?https?://|^type:\s*[\"']?(web[- ]?)?clip|^tags:.*\bclippings?\b|^\s*-\s*clippings?\s*$",
                     re.M)
DEFAULT_FOLDER = {"zh": "知识库", "en": "Knowledge base"}
HEADER = {
    "zh": ("# 知识库：这里列出的文件夹里是参考资料（文章、剪藏、研究材料、文档）。\n"
           "# 它们照样被索引、能查到、带出处，但不算「你定过的事」：回执把它们单列在 knowledge_base 下，置信度只看你的记忆。\n"
           "# 一行一个文件夹，相对于记忆文件夹；# 开头是注释。改它用 `krouter kb add/remove`，或者直接编辑。\n"),
    "en": ("# Knowledge base: the folders listed here hold reference material (articles, clippings, research, documents).\n"
           "# They are indexed and found with their source, but never count as something you decided: a lookup lists\n"
           "# them under knowledge_base, and only your memory sets the confidence.\n"
           "# One folder per line, relative to the memory folder; lines starting with # are comments. Edit it with\n"
           "# `krouter kb add/remove`, or by hand.\n"),
}
_CACHE: dict[str, tuple[float, list[str]]] = {}


def kb_file(vault: Path) -> Path:
    return Path(vault) / KB_FILE


def _norm(folder: str) -> str:
    return str(folder).strip().replace("\\", "/").strip("/")


def declared(vault: Path | None) -> list[str]:
    """The declared knowledge-base folders (vault-relative, `/`-separated), as the file lists them. Cached per mtime."""
    if vault is None:
        return []
    path = kb_file(vault)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return []
    key = str(path)
    if key in _CACHE and _CACHE[key][0] == mtime:
        return _CACHE[key][1]
    out: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(MINE_PREFIX):
            continue
        f = _norm(line)
        if f and f not in out and not f.startswith("..") and not Path(f).is_absolute():
            out.append(f)
    _CACHE[key] = (mtime, out)
    return out


def path_reason(vault: Path | None, rel: str, folders: list[str] | None = None) -> str:
    """`declared` or `clippings` when the path alone puts the page in the knowledge base, else ``."""
    rel = rel.replace("\\", "/")
    for f in declared(vault) if folders is None else folders:
        if rel == f or rel.startswith(f + "/"):
            return "declared"
    return "clippings" if CLIP_PATH.search(rel) else ""


def fm_reason(fm_text: str) -> str:
    return "clippings" if CLIP_FM.search(fm_text or "") else ""


def head_of(text: str) -> str:
    """The frontmatter block of a page (lowercased, as the index's `fm` table stores it), or ``."""
    text = (text or "").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---", 4)
    return text[: end + 4].lower() if end >= 0 else ""


def reason(vault: Path, rel: str, text: str | None = None) -> str:
    """Why this page is in the knowledge base (`declared`, `clippings`), or `` when it is part of your memory.
    `text`: the page's text when the caller has it; otherwise the page is read."""
    why = path_reason(vault, rel)
    if why == "declared":
        return why
    if _under(rel, mine_marked(vault)):
        return ""
    if why:
        return why
    if rel in alias_targets(vault):
        return ""
    stored = _stored_origin(vault, rel)
    if stored is not None:
        return stored
    if text is None:
        try:
            text = (Path(vault) / rel).read_text(encoding="utf-8", errors="replace")[:AUTO_READ]
        except OSError:
            return ""
    if fm_reason(head_of(text)):
        return "clippings"
    if not auto_on(vault):
        return ""
    score, _why, hard = page_origin(rel, text, zones.lang(vault))
    return "auto" if not hard and score >= AUTO_MIN else ""


_ORIGIN: dict[str, tuple[tuple, dict[str, str]]] = {}


def _stored_origin(vault: Path, rel: str) -> str | None:
    """The index's verdict for one page (with its folder's majority), when the index has the page; None otherwise.
    The verdicts of the whole vault are read once per index change (one query), so listing pages stays cheap."""
    try:
        import sqlite3

        import recall_index

        db = recall_index.cache_path(Path(vault))
        st = db.stat()
        wal = db.with_name(db.name + "-wal")
        sig = (st.st_mtime_ns, st.st_size, wal.stat().st_mtime_ns if wal.exists() else 0,
               tuple(declared(vault)), tuple(mine_marked(vault)), auto_on(vault))
        cached = _ORIGIN.get(str(db))
        if not cached or cached[0] != sig:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
            try:
                if not con.execute("SELECT 1 FROM sqlite_master WHERE name='origin'").fetchone():
                    return None
                rels = [r for (r,) in con.execute("SELECT rel FROM origin")]
                got = classify(con, Path(vault), rels)
            finally:
                con.close()
            cached = (sig, {r: got.get(r, "") for r in rels})
            _ORIGIN[str(db)] = cached
        return cached[1].get(rel)
    except Exception:  # noqa: BLE001 - 索引读不了就按这一页自己判断
        return None


def classify(con, vault: Path, rels: list[str]) -> dict[str, str]:
    """{rel: reason} for the knowledge-base pages among `rels`, from the paths and the index's stored frontmatter."""
    folders = declared(vault)
    mine = mine_marked(vault)
    named = alias_targets(vault)
    out = {}
    rest = []
    for rel in dict.fromkeys(rels):
        why = path_reason(vault, rel, folders)
        if why == "declared":
            out[rel] = why
        elif _under(rel, mine):
            continue  # 你标成自己的：不管长什么样都是记忆
        elif rel in named and not why:
            continue  # 别名表指向的页：你命名过的主题，是你的记忆
        elif why:
            out[rel] = why
        else:
            rest.append(rel)
    auto = auto_on(vault)
    for i in range(0, len(rest), 400):
        chunk = rest[i:i + 400]
        marks = ",".join("?" * len(chunk))
        for rel, text in con.execute(f"SELECT rel, text FROM fm WHERE rel IN ({marks})", chunk):
            if fm_reason(text):
                out[rel] = "clippings"
        if not auto:
            continue
        try:
            rows = con.execute(f"SELECT rel, dir, score, hard FROM origin WHERE rel IN ({marks})", chunk).fetchall()
        except Exception:  # noqa: BLE001 - 旧缓存没有这张表
            rows = []
        bonus = dir_bonus(con, {d for _r, d, _s, _h in rows})
        for rel, d, score, hard in rows:
            if rel not in out and not hard and score + bonus.get(d, 0.0) >= AUTO_MIN:
                out[rel] = "auto"
    return out


def dir_bonus(con, dirs: set[str]) -> dict[str, float]:
    """+DIR_BONUS for a folder where most pages (at least DIR_MIN) look like reference material on their own;
    -DIR_BONUS where almost none do."""
    out = {}
    for d in dirs:
        n, soft = con.execute("SELECT count(*), sum(score >= ?) FROM origin WHERE dir=? AND hard=''", (SOFT, d)).fetchone()
        if n and n >= DIR_MIN:
            share = (soft or 0) / n
            out[d] = DIR_BONUS if share >= DIR_SHARE else 0.0  # 只加不减：一个目录里混着两类时，资料页照样逐页认
    return out


def origin_rows(con, vault: Path, rels: list[str]) -> dict[str, dict]:
    """{rel: {kb, score, why, hard, dir_bonus}} for `krouter why` / `view`: the verdict and the signals behind it."""
    got = classify(con, vault, rels)
    out = {}
    try:
        marks = ",".join("?" * len(rels))
        rows = con.execute(f"SELECT rel, dir, score, why, hard FROM origin WHERE rel IN ({marks})", rels).fetchall()
    except Exception:  # noqa: BLE001
        rows = []
    bonus = dir_bonus(con, {r[1] for r in rows})
    mine = mine_marked(vault)
    for rel, d, score, why, hard in rows:
        out[rel] = {"kb": got.get(rel, ""), "score": score, "why": why, "hard": hard,
                    "dir_bonus": bonus.get(d, 0.0), "marked_mine": _under(rel, mine)}
    return out


def auto_pages(vault: Path) -> list[str]:
    """Every page recognised automatically as reference material (`auto`), from the index (refreshed first)."""
    import recall_index

    con = recall_index.connect(recall_index.cache_path(Path(vault)))
    try:
        recall_index.refresh(Path(vault), con)
        rels = [r for (r,) in con.execute("SELECT rel FROM origin WHERE hard=''")]
        got = classify(con, Path(vault), rels)
    finally:
        con.close()
    return sorted(r for r, why in got.items() if why == "auto")


def auto_news(vault: Path) -> tuple[list[str], list[str]]:
    """(all auto-recognised pages, the ones new since the last call): for the nightly report. The list of the last
    call is kept in the state folder (`KROUTER_STATE_DIR`), not in the memory folder."""
    import hashlib
    import json

    now = auto_pages(vault)
    base = Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local/state/krouter")
    state = base / f"kb-auto-{hashlib.sha1(str(Path(vault).resolve()).encode('utf-8')).hexdigest()[:12]}.json"
    try:
        before = set(json.loads(state.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        before = set()
    try:
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps(now, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return now, [r for r in now if r not in before]


def auto_on(vault: Path | None) -> bool:
    """Automatic recognition is OFF by default: on only with `KROUTER_KB_AUTO=1`, or `kb_auto|on` in krouter-settings.psv
    (the variable wins). Declared folders, clippings and `!` marks work either way. Why off: on a synthetic vault it found 30 of
    32 held-out outside articles and misjudged 0 of 43 own pages (set 40), but on one real vault (1,473 pages, read-only, once)
    it found 74 of 84 research pages and also took about 80 of the user's own pages (about 5.8%, an estimate) for outside
    material, over the 2% line set for it."""
    raw = os.environ.get("KROUTER_KB_AUTO", "").strip().lower()
    if raw in ("0", "off", "false", "no"):
        return False
    if raw in ("1", "on", "true", "yes"):
        return True
    try:
        text = (Path(vault) / "krouter-settings.psv").read_text(encoding="utf-8", errors="replace") if vault else ""
    except OSError:
        text = ""
    for line in text.splitlines():
        key, _, val = line.partition("|")
        if key.strip().lower() == "kb_auto" and not line.lstrip().startswith("#") \
                and val.strip().lower() in ("on", "1", "true", "yes"):
            return True
    return False


def index_origin(con, rel: str, canon: str, text: str, vault_lang: str, aliased: bool) -> None:
    """`rel`: the page's path in this vault (the key); `canon`: the same path in the default layout (zones.canon),
    which the folder rules are written for."""
    score, why, hard = page_origin(canon, text[:AUTO_READ], vault_lang, aliased)
    d = rel.rsplit("/", 1)[0] if "/" in rel else ""
    con.execute("INSERT OR REPLACE INTO origin VALUES(?,?,?,?,?)", (rel, d, score, why, hard))


# ---------- 自动识别（不用声明）：按来历逐页判断 ----------
#
# 「你的记忆」靠来历认：KRouter 自己记下、提炼、纠正出来的页（会话摘录、时间日志、经验卡、技能、规则目录、主题档案、
# 带 KRouter 自己 frontmatter 标记的页），别名表指向的页，你用 `krouter kb mine` 标成自己的页。其余的页逐页看像不像
# 别人写的资料：来源网址、转载/译者/署名、像文章的标题、长篇叙述而没有决定和待办、作者不是你、主要语言和库不同，
# 再加上同一目录里这类页占多数。分数够高才算资料（`auto`）；错把你自己的页当资料代价更大，所以门槛从严。

ORIGIN_SCHEMA = """
-- 每页的来历判断：hard 是 mine（来历就是你的记忆）/ kb（剪藏）/ 空；score 是「像别人写的资料」的分；why 是理由
CREATE TABLE origin(rel TEXT PRIMARY KEY, dir TEXT, score REAL, why TEXT, hard TEXT);
CREATE INDEX origin_dir ON origin(dir);
"""
ORIGIN_DROP = "DROP TABLE IF EXISTS origin;"
MINE_PREFIX = "!"  # krouter-kb.txt 里以 ! 开头的一行：这一页或这个文件夹是你自己的（优先于自动判断）
OWN_DIRS = ("05 时间日志/", "90 系统文件/", "02 经验与方法/", "Agent记忆/")
OWN_TYPE = re.compile(r"^type:\s*[\"']?(session-excerpt|decision|correction|method|rule|topic|experience|"
                      r"experience-card|skill|krouter-skill|log|daily|daily-log|automation-log|agent-notes|imported|"
                      r"correction-candidates|note)\b", re.M | re.I)
OWN_KEYS = re.compile(r"^(status|how|supersedes|superseded_by|valid_from|triggers|topic_terms|session|forked_from|"
                      r"krouter)\s*:", re.M | re.I)
SOURCE_LINE = re.compile(r"^\s*(?:[>*_-]\s*)*(?:\*\*)?(?:source|original(?:ly published)?|via|from|url|link|来源|出处|原文"
                         r"(?:链接|地址)?|原载|转载自|转自|本文(?:链接|地址))(?:\*\*)?\s*[:：]\s*\S", re.I | re.M)
REPRINT = re.compile(r"转载|整理[:：]|主办方|译者|译自|翻译[:：]|编译|原作者|作者[:：]|撰文|编辑[:：]|责任编辑|阅读原文|版权(?:所有|归)|"
                     r"未经授权|公众号|\bwritten by\b|\bposted (?:on|by)\b|\bpublished (?:on|in|by)\b|"
                     r"\boriginally (?:published|appeared)\b|©|\bcopyright\b|\ball rights reserved\b|\bsubscribe\b|"
                     r"\bnewsletter\b|\bread more\b|\btranslated (?:by|from)\b|\btranslator\b|\bminute read\b", re.I)
BYLINE = re.compile(r"^\s*(?:by|written by|posted by)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\s*$", re.M)
FIRST_PERSON = re.compile(r"我|\b(?:i|me|my|mine|we|us|our|i'm|i've|we're|we've)\b", re.I)
DECISION = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?(?:决定|结论|待办|下一步|负责人|决议|行动项|TODO|Decision|Decided|"
                      r"Action items?|Next steps?|Owner)(?:\*\*)?\s*[:：]|- \[[ xX]\]|我们决定|我决定|定下来|以后都|以后统一|"
                      r"\bwe decided\b|\bi decided\b|\bfrom now on\b|\bgoing forward we\b", re.I | re.M)
ANNOTATE = re.compile(r"我的(?:批注|看法|想法|笔记|理解|评论)|批注[:：]|按[:：]|我觉得|我认为|我想|对我们|对我来说|"
                      r"\bmy (?:take|notes?|thoughts|comments?)\b|\bnote to self\b|\bi think\b|\bfor us\b", re.I)
CJK_CHAR = re.compile(r"[㐀-鿿]")
LATIN_WORD = re.compile(r"[A-Za-z]{2,}")
LONG_WORDS = 400    # 大致的词数到这个算长篇
NARRATIVE_WORDS = 150
AUTO_READ = 20000   # 判断来历只读每页前这么多字符
AUTO_MIN = 3.0      # 分数到这个才算资料（第 40 套开发部分定：你自己的页开发部分最高 1.5）
DIR_SHARE = 0.6     # 同目录里像资料的页占这么多（至少 DIR_MIN 页），每页再加 DIR_BONUS
DIR_MIN = 3
DIR_BONUS = 1.0
SOFT = 3.0          # 目录统计里「像资料」的页：自己的分到这个


def text_lang(text: str) -> str:
    cjk = len(CJK_CHAR.findall(text))
    latin = len(LATIN_WORD.findall(text))
    if cjk + latin < 20:
        return ""
    return "zh" if cjk >= latin else "en"


def page_origin(rel: str, text: str, vault_lang: str, aliased: bool = False) -> tuple[float, str, str]:
    """(score, why, hard) for one page. `hard`: `mine` when where it came from makes it your memory, `kb` for a
    clipping (2.0's rule), `` when only the score decides. `why` names the signals, comma-separated."""
    rel = rel.replace("\\", "/")
    head = head_of(text)
    if CLIP_PATH.search(rel) or fm_reason(head):
        return 9.0, "clipping", "kb"
    if aliased:
        return -9.0, "alias", "mine"
    if rel.startswith(OWN_DIRS) or "/" not in rel and rel in ("AGENTS.md", "Agent第二大脑.md"):
        return -9.0, "krouter-folder", "mine"
    if OWN_TYPE.search(head) or OWN_KEYS.search(head):
        return -9.0, "krouter-frontmatter", "mine"
    body = text[len(head):] if head else text
    lines = [ln for ln in body.splitlines() if ln.strip()]
    edge = "\n".join(lines[:8] + lines[-5:])
    why, score = [], 0.0
    if (SOURCE_FM.search(head) and URL_RE.search(head)) or SOURCE_LINE.search(edge) or \
            any(URL_RE.search(ln) and len(ln.strip()) < 200 for ln in lines[:4]):
        score += 3.5
        why.append("source")
    if re.search(r"^author\s*:", head, re.M | re.I) and not re.search(r"^author\s*:\s*[\"']?(me|我|self)\b", head, re.M | re.I):
        score += 2.0
        why.append("author")
    if REPRINT.search(edge) or BYLINE.search(edge):
        score += 2.0
        why.append("byline")
    stem = rel.rsplit("/", 1)[-1][:-3] if rel.endswith(".md") else rel.rsplit("/", 1)[-1]
    first_h = next((ln.lstrip("# ").strip() for ln in lines[:3] if ln.startswith("# ")), "")
    title = first_h or stem
    n_words = len(LATIN_WORD.findall(title)) + len(CJK_CHAR.findall(title)) / 2
    if n_words >= 6 or (n_words >= 4 and re.search(r"[:：？?！!《》|]|——|\bhow\b|\bwhy\b|\bwhat\b", title, re.I)):
        score += 1.0
        why.append("article-title")
    size = len(LATIN_WORD.findall(body)) + len(CJK_CHAR.findall(body)) / 1.5  # 大致的词数：中文按 1.5 个字一个词
    if size >= LONG_WORDS:
        score += 1.0
        why.append("long")
    paras = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    listy = sum(1 for ln in lines if re.match(r"\s*([-*+]|\d+\.|\|)\s", ln))
    if paras and size >= NARRATIVE_WORDS and listy <= 0.2 * len(lines) and size / len(paras) >= 40:
        score += 1.0
        why.append("narrative")
    fp = len(FIRST_PERSON.findall(body)) * 100 / max(size, 1)
    if size >= NARRATIVE_WORDS and fp < 0.5:
        score += 1.0
        why.append("impersonal")
    elif fp >= 2.0:
        score -= 1.5
        why.append("-personal")
    if DECISION.search(body):
        score -= 2.0
        why.append("-decision")
    if ANNOTATE.search(body):
        score -= 3.0
        why.append("-annotated")
    lang = text_lang(body)
    if lang and vault_lang and lang != vault_lang:
        score += 1.5
        why.append("other-language")
    return round(score, 2), ",".join(why), ""


def mine_marked(vault: Path | None) -> list[str]:
    """Pages or folders marked as your own (`!path` lines in krouter-kb.txt): never knowledge base, whatever they look
    like."""
    if vault is None:
        return []
    path = kb_file(vault)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [_norm(ln.strip()[1:]) for ln in text.splitlines() if ln.strip().startswith(MINE_PREFIX) and _norm(ln.strip()[1:])]


_ALIAS: dict[str, tuple[tuple, frozenset]] = {}


def alias_targets(vault: Path | None) -> frozenset:
    """Pages the vault's own alias table (`90 系统文件/canonical_sources.psv`) points to: a topic you named is yours.
    Read live (cached per file time), so a row added a minute ago counts before the index is rebuilt."""
    if vault is None:
        return frozenset()
    path = zones.path(Path(vault), "90 系统文件/canonical_sources.psv")
    try:
        st = path.stat()
    except OSError:
        return frozenset()
    sig = (st.st_mtime_ns, st.st_size)
    hit = _ALIAS.get(str(path))
    if hit and hit[0] == sig:
        return hit[1]
    out = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split("|")
        if len(parts) == 4 and not line.startswith("#"):
            out.add(_norm(parts[2]))
    got = frozenset(out)
    _ALIAS[str(path)] = (sig, got)
    return got


def _under(rel: str, items: list[str]) -> bool:
    return any(rel == f or rel.startswith(f + "/") or rel == f + ".md" for f in items)


# ---------- 声明 ----------

def _write(vault: Path, folders: list[str]) -> Path:
    path = kb_file(vault)
    lang = "en" if zones.lang(vault) == "en" else "zh"
    keep_head = []
    if path.is_file():
        keep_head = [ln for ln in path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.startswith("#")]
    head = "\n".join(keep_head) + "\n" if keep_head else HEADER[lang]
    marks = [MINE_PREFIX + f for f in mine_marked(vault)]  # 「这是我自己的」那几行原样留着
    path.write_text(head + "".join(f + "\n" for f in folders + marks), encoding="utf-8")
    _CACHE.pop(str(path), None)
    return path


def add(vault: Path, folders: list[str]) -> list[str]:
    """Declare these folders (each must exist in the memory folder). Returns the ones newly added."""
    have = declared(vault)
    new = []
    for raw in folders:
        f = _norm(raw)
        p = Path(raw).expanduser()
        if p.is_absolute():
            try:
                f = _norm(p.resolve().relative_to(Path(vault).resolve()).as_posix())
            except ValueError:
                raise ValueError(f"{raw} is not inside the memory folder {vault}")
        if not f or f.startswith(".."):
            raise ValueError(f"{raw}: give a folder inside the memory folder")
        if not (Path(vault) / f).is_dir():
            raise ValueError(f"{f}: no such folder in {vault}")
        if f not in have and f not in new:
            new.append(f)
    if new:
        _write(vault, have + new)
    return new


def _rel_in(vault: Path, raw: str) -> str:
    f = _norm(raw)
    p = Path(raw).expanduser()
    if p.is_absolute():
        try:
            f = _norm(p.resolve().relative_to(Path(vault).resolve()).as_posix())
        except ValueError:
            raise ValueError(f"{raw} is not inside the memory folder {vault}")
    if not f or f.startswith(".."):
        raise ValueError(f"{raw}: give a page or folder inside the memory folder")
    if not (Path(vault) / f).exists():
        raise ValueError(f"{f}: no such page or folder in {vault}")
    return f


def _lines(vault: Path) -> list[str]:
    path = kb_file(vault)
    return path.read_text(encoding="utf-8", errors="replace").splitlines() if path.is_file() else []


def mark_mine(vault: Path, paths: list[str]) -> list[str]:
    """Mark pages or folders as your own (`!path` in krouter-kb.txt). Automatic recognition leaves them alone; a
    declared knowledge-base folder still wins for the pages under it."""
    have = mine_marked(vault)
    new = []
    for raw in paths:
        f = _rel_in(vault, raw)
        if f not in have and f not in new:
            new.append(f)
    if new:
        lines = _lines(vault) or HEADER["en" if zones.lang(vault) == "en" else "zh"].rstrip("\n").splitlines()
        kb_file(vault).write_text("\n".join(lines + [MINE_PREFIX + f for f in new]) + "\n", encoding="utf-8")
        _CACHE.pop(str(kb_file(vault)), None)
    return new


def unmark_mine(vault: Path, paths: list[str]) -> list[str]:
    drop = {_norm(p) for p in paths}
    lines = _lines(vault)
    gone = [ln.strip()[1:] for ln in lines if ln.strip().startswith(MINE_PREFIX) and _norm(ln.strip()[1:]) in drop]
    if gone:
        keep = [ln for ln in lines if not (ln.strip().startswith(MINE_PREFIX) and _norm(ln.strip()[1:]) in drop)]
        kb_file(vault).write_text("\n".join(keep) + "\n", encoding="utf-8")
        _CACHE.pop(str(kb_file(vault)), None)
    return gone


def remove(vault: Path, folders: list[str]) -> list[str]:
    have = declared(vault)
    gone = [f for f in (_norm(x) for x in folders) if f in have]
    if gone:
        _write(vault, [f for f in have if f not in gone])
    return gone


# ---------- 建议（只建议，不生效） ----------

URL_RE = re.compile(r"https?://\S+")
OWN_FM = re.compile(r"^(status|how|supersedes|superseded_by|valid_from|aliases|triggers):|^type:\s*[\"']?(session-excerpt|"
                    r"decision|correction|method|rule|topic|experience|skill|log|daily)", re.M | re.I)
SOURCE_FM = re.compile(r"^(source|url|link|original|origin|来源|原文|原文链接|source_url|source_file):\s*\S", re.M | re.I)
SUGGEST_MIN_PAGES = 3
SUGGEST_SKIP = ("90 系统文件", "05 时间日志", "02 经验与方法/经验卡", "02 经验与方法/技能", "02 经验与方法/主题档案")
LONG_CHARS = 4000


def _page_signals(full: str) -> dict:
    try:
        with open(full, encoding="utf-8", errors="replace") as fh:
            text = fh.read(LONG_CHARS + 4000)  # 判断「长」只要读到这么多
    except OSError:
        return {}
    head = head_of(text)
    body = text[len(head):] if head else text
    first = [ln for ln in body.splitlines() if ln.strip()][:6]
    stem = Path(full).stem
    words = len(re.findall(r"[A-Za-z]+", stem)) + len(re.findall(r"[㐀-鿿]", stem)) / 2
    return {
        "url": bool(SOURCE_FM.search(head) and URL_RE.search(head)) or any(URL_RE.search(ln) for ln in first),
        "long": len(body) >= LONG_CHARS,
        "article": words >= 6 or "author:" in head,
        "own": bool(OWN_FM.search(head)),
    }


def suggest(vault: Path, limit: int = 8) -> list[dict]:
    """Folders that look like reference material someone else wrote and are not in the knowledge base yet. Conservative
    on purpose: at least three pages, few with KRouter's own markers (status, how, a decision or session type), and
    most with a source address at the top, or most long and titled like articles. A suggestion only: nothing changes
    until you declare the folder. Returns [{folder, pages, url, long, article}], largest first."""
    vault = Path(vault)
    folders = declared(vault)
    skip = tuple(zones.real(vault, s) for s in SUGGEST_SKIP)
    stats: dict[str, dict] = {}
    base = str(vault).rstrip("/")
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "迁移备份", "Clippings")]
        reldir = root[len(base) + 1:].replace(os.sep, "/")
        if not reldir or reldir.startswith(skip) or path_reason(vault, reldir + "/x.md", folders):
            continue
        for name in files:
            if not name.endswith(".md"):
                continue
            sig = _page_signals(f"{root}/{name}")
            if not sig:
                continue
            parts = reldir.split("/")
            for i in range(1, len(parts) + 1):  # 每一级上层文件夹都累加：整个子树一起看
                s = stats.setdefault("/".join(parts[:i]), {"pages": 0, "url": 0, "long": 0, "article": 0, "own": 0})
                s["pages"] += 1
                for k in ("url", "long", "article", "own"):
                    s[k] += sig[k]

    def looks(s: dict) -> bool:
        n = s["pages"]
        if n < SUGGEST_MIN_PAGES or s["own"] > 0.2 * n:
            return False
        return s["url"] >= 0.6 * n or (s["long"] >= 0.6 * n and s["article"] >= 0.5 * n)

    hit = sorted(f for f, s in stats.items() if looks(s))
    # 上层文件夹只比某个子文件夹多出同样像资料的页时才列上层；一页不多（`Projects` 下只有 `Research`）就列子文件夹
    hit = [f for f in hit if not any(o.startswith(f + "/") and stats[o]["pages"] == stats[f]["pages"] for o in hit)]
    top = [f for f in hit if not any(f.startswith(o + "/") for o in hit if o != f)]  # 上层已经算上就不再列子文件夹
    out = [{"folder": f, **{k: stats[f][k] for k in ("pages", "url", "long", "article")}} for f in top]
    out.sort(key=lambda d: (-d["pages"], d["folder"]))
    return out[:limit]


# ---------- 导入 ----------

class _HTML(HTMLParser):
    """A plain HTML → Markdown conversion: headings, paragraphs, lists, links, code blocks; scripts and styles dropped."""

    SKIP = {"script", "style", "noscript", "svg", "template", "head"}
    BLOCK = {"p", "div", "section", "article", "main", "header", "footer", "blockquote", "table", "tr", "ul", "ol",
             "figure", "figcaption", "aside", "nav", "form", "dl"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0
        self.pre = 0
        self.title = ""
        self._in_title = False
        self.href: list[str] = []
        self.link_text: list[list[str]] = []

    def _nl(self, n: int = 2) -> None:
        tail = "".join(self.out[-3:])
        have = len(tail) - len(tail.rstrip("\n"))
        if self.out:
            self.out.append("\n" * max(0, n - have))

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag in self.SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if re.fullmatch(r"h[1-6]", tag):
            self._nl()
            self.out.append("#" * int(tag[1]) + " ")
        elif tag in self.BLOCK:
            self._nl()
        elif tag == "br":
            self.out.append("\n")
        elif tag == "li":
            self._nl(1)
            self.out.append("- ")
        elif tag in ("td", "th"):
            self.out.append(" | ")
        elif tag == "pre":
            self._nl()
            self.out.append("```\n")
            self.pre += 1
        elif tag == "code" and not self.pre:
            self.out.append("`")
        elif tag in ("strong", "b"):
            self.out.append("**")
        elif tag in ("em", "i"):
            self.out.append("*")
        elif tag == "a":
            self.href.append(dict(attrs).get("href") or "")
            self.link_text.append([])
            self.out.append("\x00")  # 链接文字的起点，结束标签时替换

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if re.fullmatch(r"h[1-6]", tag) or tag in self.BLOCK:
            self._nl()
        elif tag == "pre":
            self.pre = max(0, self.pre - 1)
            self.out.append("\n```")
            self._nl()
        elif tag == "code" and not self.pre:
            self.out.append("`")
        elif tag in ("strong", "b"):
            self.out.append("**")
        elif tag in ("em", "i"):
            self.out.append("*")
        elif tag == "a" and self.href:
            href = self.href.pop()
            self.link_text.pop()
            i = len(self.out) - 1 - self.out[::-1].index("\x00") if "\x00" in self.out else len(self.out)
            text = "".join(self.out[i + 1:]).strip()
            del self.out[i:]
            ok = href and not href.startswith(("#", "javascript:"))
            self.out.append(f"[{text}]({href})" if ok and text else text)

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self.skip:
            return
        self.out.append(data if self.pre else re.sub(r"\s+", " ", data))

    def markdown(self) -> str:
        text = "".join(x for x in self.out if x != "\x00")
        lines = [ln.rstrip() for ln in text.splitlines()]
        text = "\n".join(ln.lstrip() if not ln.startswith("    ") else ln for ln in lines)
        return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def html_to_markdown(text: str) -> tuple[str, str]:
    """(markdown, title) from HTML, with the standard library only."""
    p = _HTML()
    p.feed(text)
    p.close()
    return p.markdown(), html.unescape(p.title).strip()


PANDOC_IN = {".docx": "docx", ".odt": "odt", ".rtf": "rtf", ".epub": "epub", ".html": "html", ".htm": "html",
             ".tex": "latex", ".rst": "rst", ".org": "org"}
TEXT_IN = {".md", ".markdown", ".txt"}


class ImportFailed(Exception):
    pass


def _run(argv: list[str]) -> str | None:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 and proc.stdout.strip() else None


def convert(src: Path) -> tuple[str, str, str]:
    """(markdown, title, tool) for one file, with whatever converter this machine has. Raises ImportFailed with the
    tool to install when none can read it."""
    ext = src.suffix.lower()
    if ext in TEXT_IN:
        return src.read_text(encoding="utf-8", errors="replace"), "", "copy"
    tried = []
    mid = shutil.which("markitdown")
    if mid:
        tried.append("markitdown")
        out = _run([mid, str(src)])
        if out:
            return out, "", "markitdown"
    try:
        from markitdown import MarkItDown  # type: ignore

        tried.append("markitdown (python)")
        res = MarkItDown().convert(str(src))
        text = getattr(res, "text_content", "") or getattr(res, "markdown", "")
        if text.strip():
            return text, getattr(res, "title", "") or "", "markitdown"
    except Exception:  # noqa: BLE001 - 没装或读不了：试下一个
        pass
    pandoc = shutil.which("pandoc")
    if pandoc and ext in PANDOC_IN:
        tried.append("pandoc")
        out = _run([pandoc, "-f", PANDOC_IN[ext], "-t", "gfm", "--wrap=none", str(src)])
        if out:
            return out, "", "pandoc"
    if ext == ".pdf" and shutil.which("pdftotext"):
        tried.append("pdftotext")
        out = _run([shutil.which("pdftotext"), "-layout", "-enc", "UTF-8", str(src), "-"])
        if out:
            return out, "", "pdftotext"
    if ext in (".html", ".htm", ".xhtml"):
        md, title = html_to_markdown(src.read_text(encoding="utf-8", errors="replace"))
        if md.strip():
            return md, title, "builtin-html"
    if ext == ".pdf":
        need = "markitdown (`pipx install 'markitdown[pdf]'`) or pdftotext (poppler: `brew install poppler`, `apt install poppler-utils`)"
    elif ext in PANDOC_IN:
        need = "markitdown (`pipx install 'markitdown[all]'`) or pandoc (https://pandoc.org/installing.html)"
    else:
        need = "markitdown (`pipx install 'markitdown[all]'`), which reads most document formats"
    did = f" (tried: {', '.join(tried)})" if tried else ""
    raise ImportFailed(f"cannot convert {src.name} on this machine{did}. Install {need}, then run this again. "
                       "KRouter does not convert documents itself, apart from plain HTML.")


def _title_of(md: str, fallback: str) -> str:
    for line in md.splitlines()[:40]:
        m = re.match(r"^#\s+(.+?)\s*#*$", line.strip())
        if m:
            return m.group(1).strip()
    return fallback


def _yaml(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def import_file(vault: Path, src: Path, folder: str | None = None, force: bool = False) -> dict:
    """Convert `src` to a Markdown page in the knowledge base. `folder`: where (declared if it was not); default the
    one declared folder, else `知识库` / `Knowledge base` at the root, which is then declared. The page's frontmatter
    keeps the source file's path, the time of the import and the tool. Returns {page, folder, tool, declared}."""
    vault = Path(vault)
    src = Path(src).expanduser()
    if not src.is_file():
        raise ImportFailed(f"no such file: {src}")
    have = declared(vault)
    if folder:
        target = _norm(folder)
    elif len(have) == 1:
        target = have[0]
    elif have:
        raise ImportFailed("more than one knowledge-base folder is declared; say which with --to: " + ", ".join(have))
    else:
        target = DEFAULT_FOLDER["en" if zones.lang(vault) == "en" else "zh"]
    md, title, tool = convert(src)
    if src.suffix.lower() in TEXT_IN and md.startswith("---\n"):
        end = md.find("\n---", 4)
        md = md[end + 4:].lstrip("-\n") if end >= 0 else md  # 原来的 frontmatter 换成导入记录
    title = (title or _title_of(md, src.stem)).strip() or src.stem
    (vault / target).mkdir(parents=True, exist_ok=True)
    newly = [] if path_reason(vault, target + "/x.md") == "declared" else add(vault, [target])
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", src.stem).strip() or "imported"
    page = vault / target / f"{name}.md"
    n = 2
    while page.exists() and not force:
        page = vault / target / f"{name} ({n}).md"
        n += 1
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    head = ["---", f"title: {_yaml(title)}", "type: imported", f"source_file: {_yaml(str(src.resolve()))}",
            f"imported_at: {stamp}", f"imported_with: {tool}", "---", ""]
    page.write_text("\n".join(head) + md.rstrip() + "\n", encoding="utf-8")
    return {"page": page.relative_to(vault).as_posix(), "folder": target, "tool": tool, "declared": newly}


# ---------- 命令行 ----------

def _vault(arg: str | None) -> Path | None:
    import krouter_home

    raw = arg or krouter_home.vault_path()
    return Path(raw).expanduser() if raw else None


def count_pages(vault: Path, folder: str) -> int:
    root = Path(vault) / folder
    return sum(1 for p in root.rglob("*.md")) if root.is_dir() else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="krouter kb", description="Declare reference folders as the knowledge base, "
                                 "see suggestions, import documents.")
    ap.add_argument("--vault", default=None, help="the memory folder (default: the installed one)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="the declared folders")
    a = sub.add_parser("add", help="declare folders as the knowledge base")
    a.add_argument("folders", nargs="+")
    r = sub.add_parser("remove", help="stop treating folders as the knowledge base")
    r.add_argument("folders", nargs="+")
    sub.add_parser("suggest", help="folders that look like reference material and are not declared (nothing changes)")
    m = sub.add_parser("mine", help="mark pages or folders as your own: never reference material, whatever they look like")
    m.add_argument("paths", nargs="+")
    u = sub.add_parser("unmine", help="drop a `mine` mark (automatic recognition decides again)")
    u.add_argument("paths", nargs="+")
    i = sub.add_parser("import", help="convert a PDF, Word, HTML, … file into a Markdown page in the knowledge base")
    i.add_argument("files", nargs="+")
    i.add_argument("--to", default=None, help="the knowledge-base folder (default: the declared one, or a new "
                                              "`知识库` / `Knowledge base`)")
    i.add_argument("--force", action="store_true", help="overwrite a page of the same name")
    args = ap.parse_args(argv)
    vault = _vault(args.vault)
    if vault is None or not vault.is_dir():
        print("set KROUTER_VAULT to your memory folder, or pass --vault", file=sys.stderr)
        return 2
    try:
        if args.cmd == "list":
            folders = declared(vault)
            if not folders:
                print(f"no folder is declared as the knowledge base ({kb_file(vault)} is missing or empty). Clipping "
                      "folders and clipper pages count without it. `krouter kb suggest` lists candidates.")
            for f in folders:
                print(f"{f}\t{count_pages(vault, f)} pages")
        elif args.cmd == "add":
            new = add(vault, args.folders)
            for f in new:
                print(f"declared: {f} ({count_pages(vault, f)} pages) -> {kb_file(vault)}")
            if not new:
                print("already declared: " + ", ".join(_norm(f) for f in args.folders))
        elif args.cmd == "remove":
            gone = remove(vault, args.folders)
            print(("removed: " + ", ".join(gone)) if gone else "none of these is declared")
        elif args.cmd == "mine":
            new = mark_mine(vault, args.paths)
            print(("marked as yours: " + ", ".join(new) + f" -> {kb_file(vault)}") if new else "already marked")
        elif args.cmd == "unmine":
            gone = unmark_mine(vault, args.paths)
            print(("unmarked: " + ", ".join(gone)) if gone else "none of these is marked")
        elif args.cmd == "suggest":
            found = suggest(vault)
            if not found:
                print("no undeclared folder looks like reference material")
            for s in found:
                print(f"{s['folder']}\t{s['pages']} pages: {s['url']} with a source address, {s['long']} long, "
                      f"{s['article']} titled like articles -> krouter kb add {shlex_quote(s['folder'])}")
        else:
            for f in args.files:
                res = import_file(vault, Path(f), args.to, args.force)
                extra = f"; declared {res['folder']} as the knowledge base" if res["declared"] else ""
                print(f"imported: {f} -> {res['page']} (with {res['tool']}{extra})")
    except (ValueError, ImportFailed) as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


def shlex_quote(s: str) -> str:
    import shlex

    return shlex.quote(s)


if __name__ == "__main__":
    raise SystemExit(main())
