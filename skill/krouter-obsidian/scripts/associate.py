#!/usr/bin/env python3
"""The associative path of recall, and the no-model tie-break for a vault that changed its mind.

Recall's direct path (the lock, then words of the question) finds pages that say what was asked. This module adds a
second path: from those pages, along the vault's own connections, to pages the question did not name. The edges live
in the same rebuildable cache as the full-text index (`recall_index.connect`), so deleting the cache deletes them:

- `link`: a `[[wikilink]]` or a Markdown link to another `.md` page, either direction;
- `supersedes`: a page's `supersedes:` / `superseded_by:` / `replaces:` / `replaced_by:` frontmatter;
- `session`: two pages of the same imported session (`session:` / `forked_from:` frontmatter);
- `day`: two pages dated the same day (`date:` frontmatter, or a file name that starts with the date);
- `words`: two pages that share words that are rare in the vault (each page keeps its `KEY_TERMS` most frequent
  content words; a word in many pages spreads thinly, one in a third of the vault or more not at all);
- `cocite`: pages that were cited together before, read from a state file outside the vault. The nightly step
  `cocite.py` adds to it from the query log: the direct hits a confident lookup returned together (never the
  associated pages, so the path does not feed itself).

Spreading is one hop with decay: each of the first `SEEDS` direct hits passes on its share (its score over the top
score) along its edges; a page reached by several seeds or edges adds them up, then is weighted up by how well it
matches the question by itself (`QUERY_BOOST`). Hubs (index and overview pages, pages with `HUB_DEGREE` or more links)
are never offered, and what they pass on is split over all their links. Replaced pages are never offered.

Chosen on set 18's development half of LongMemEval (HELDOUT.md) and the memory-honesty development benches. Built in,
no switch: a lookup gives 5 pages, the first 3 always direct hits, the associated pages after them
(`recall_index.recall`). Set 18 measured it as 3 direct + 2 associated against BM25's top 5.

The conflict tie-break (`conflicts`) is on by default (`KROUTER_CONFLICT=0` turns it off).
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

KEY_TERMS = 64        # 每页存词频最高的这么多个实词，"共同的词"边从这里算
DF_SHARE_MAX = 0.3    # 出现在三成以上页面里的词不连边：到处都有的词说明不了两页相关
DF_ABS_MAX = 400      # 大库里一个词连出去的页数上限（再多每页也只分到一点点，只是白算）
SEEDS = 3             # 从前几条直接命中出发
QUERY_BOOST = 3.0     # 自己也对上问题的页，联想分 ×(1 + 3×它的直接得分/首条得分)
HUB_DEGREE = 12       # 链接数达到这个的页算枢纽，不作为联想给出
HUB_NAME = re.compile(r"(索引|总览|目录|导航|^index$|^readme$|^moc$|^home$|overview|第二大脑|^agents$)", re.I)
WEIGHTS = {"supersedes": 1.0, "link": 0.6, "session": 0.6, "cocite": 0.6, "day": 0.0, "words": 1.0}
# 同一天的边在开发半上不加分（每天十来段会话，同一天说明不了相关），先存着，权重为 0，WP4 的关系图要用
COCITE_SAT = 5.0      # 一起被引用这么多次，边权到顶
MAX_VIA = 3
MIN_WORDS = 6         # 只靠共同的词连上的页：至少共有这么多个少见词
MIN_SCORE = 0.2       # 而且联想分至少这么高
CANDIDATES = 64       # 过了门槛的前这么多页才去查层级、链接数（取代、枢纽要排除）

WIKILINK = re.compile(r"\[\[([^\]|#^]+)(?:[#^][^\]|]*)?(?:\|[^\]]*)?\]\]")
MDLINK = re.compile(r"\]\(<?([^)<>]+?\.md)>?(?:#[^)]*)?\)")
DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
SUPERSEDE_KEYS = ("supersedes", "superseded_by", "replaces", "replaced_by")
SESSION_KEYS = ("session", "forked_from")


def norm_key(ref: str) -> str:
    """How a link target and a page name are compared: NFKC, lower case, no `.md`, `/` separators."""
    from urllib.parse import unquote

    ref = unicodedata.normalize("NFKC", unquote(ref or "")).strip().strip("/").replace("\\", "/").lower()
    return ref[:-3] if ref.endswith(".md") else ref


def name_keys(rel: str) -> list[str]:
    full = norm_key(rel)
    return list(dict.fromkeys([full, full.rsplit("/", 1)[-1]]))


def _fm_values(head: str, key: str) -> list[str]:
    """`key: value` and its `  - item` lines in a frontmatter block."""
    m = re.search(rf"(?m)^{re.escape(key)}:[ \t]*(.*)\n?((?:[ \t]+-.*\n?|-[ \t].*\n?)*)", head)
    if not m:
        return []
    vals = [m.group(1)] + [ln.strip()[1:] for ln in m.group(2).splitlines()]
    return [v.strip().strip('"').strip("'").strip() for v in vals if v.strip().strip("[]\"'")]


def _refs(value: str) -> list[str]:
    links = WIKILINK.findall(value) + MDLINK.findall(value)
    if links:
        return links
    return [value] if value and not value.startswith("[") else []


def page_day(rel: str, meta: dict) -> str:
    for raw in (meta.get("date") or "", rel.rsplit("/", 1)[-1][:10]):
        m = DATE.match(raw.strip())
        if m:
            return m.group(0)
    return ""


def page_edges(rel: str, head: str, meta: dict, body: str) -> list[tuple[str, str]]:
    """(kind, key) for one page. `link`/`supersedes` keys are link targets (resolved against page names at query
    time); `session`/`day` keys are shared values."""
    out: list[tuple[str, str]] = []
    for key in SUPERSEDE_KEYS:
        for v in _fm_values(head, key):
            out += [("supersedes", norm_key(r)) for r in _refs(v)]
    sup = {k for kind, k in out}
    for target in WIKILINK.findall(body) + MDLINK.findall(body):
        k = norm_key(target)
        if k and k not in sup:
            out.append(("link", k))
    for key in SESSION_KEYS:
        v = (meta.get(key) or "").strip()
        if v and v not in {"-", "none"}:
            out.append(("session", v.lower()))
    day = page_day(rel, meta)
    if day:
        out.append(("day", day))
    mine = set(name_keys(rel))
    return [e for e in dict.fromkeys(out) if e[1] and e[1] not in mine]


_LETTER = re.compile(r"[a-z]")


def key_terms(ri, body: str) -> list[str]:
    """The page's most frequent content words: Latin words of 3+ letters (no function words, no numbers) and Chinese
    pairs without a function character."""
    tf = Counter(ri.tokens(body))
    skip = ri.EN_FUNCTION | ri.QUERY_STOP
    fn = ri.FUNCTION_CHARS
    keep = {}
    for t, n in tf.items():
        if t in skip:
            continue
        if len(t) == 2 and not t.isascii():  # 中文双字（tokens() 只产出双字和拉丁词）
            if t[0] in fn or t[1] in fn:
                continue
        elif len(t) < 3 or not _LETTER.search(t):
            continue
        keep[t] = n
    return [t for t, _ in sorted(keep.items(), key=lambda kv: (-kv[1], kv[0]))[:KEY_TERMS]]


SCHEMA = """
-- 每页的实词，rowid 与 docs 相同；kvrow 给每个词的页数，kvinst 给每个词在哪些页
CREATE VIRTUAL TABLE keyterms USING fts5(terms, tokenize='unicode61', detail=none);
CREATE VIRTUAL TABLE kvrow USING fts5vocab(keyterms, 'row');
CREATE VIRTUAL TABLE kvinst USING fts5vocab(keyterms, 'instance');
CREATE INDEX files_rid ON files(rid);
CREATE TABLE edges(rel TEXT, kind TEXT, key TEXT);
CREATE INDEX edges_key ON edges(kind, key);
CREATE INDEX edges_rel ON edges(rel);
CREATE TABLE names(rel TEXT, key TEXT);
CREATE INDEX names_key ON names(key);
CREATE TABLE cocite(a TEXT, b TEXT, w REAL, PRIMARY KEY(a, b));
"""
DROP = ("DROP TABLE IF EXISTS kvinst; DROP TABLE IF EXISTS kvrow; DROP TABLE IF EXISTS keyterms; "
        "DROP TABLE IF EXISTS edges; DROP TABLE IF EXISTS names; DROP TABLE IF EXISTS cocite;")


def forget(con: sqlite3.Connection, rel: str, rid: int | None) -> None:
    if rid is not None:
        con.execute("DELETE FROM keyterms WHERE rowid=?", (rid,))
    con.execute("DELETE FROM edges WHERE rel=?", (rel,))
    con.execute("DELETE FROM names WHERE rel=?", (rel,))


def index_page(con: sqlite3.Connection, ri, rel: str, rid: int, text: str, meta: dict, body: str) -> None:
    """A new or changed page's edges (the caller has `forget`-ten the old ones)."""
    head = text.split("\n---", 1)[0] if text.startswith("---\n") else ""
    con.execute("INSERT INTO keyterms(rowid, terms) VALUES(?, ?)", (rid, " ".join(key_terms(ri, body))))
    con.executemany("INSERT INTO edges VALUES(?,?,?)", [(rel, k, v) for k, v in page_edges(rel, head, meta, body)])
    con.executemany("INSERT INTO names VALUES(?,?)", [(rel, k) for k in name_keys(rel)])


# ---- co-citation: kept outside the cache (the cache can be deleted), read into it on refresh ----

def cocite_file(vault: Path) -> Path:
    import hashlib

    base = Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local/state/krouter")
    return base / f"cocite-{hashlib.sha1(str(vault.resolve()).encode('utf-8')).hexdigest()[:12]}.jsonl"


def reinforce(vault: Path, rels: list[str], amount: float = 1.0) -> int:
    """Pages cited together once more: every pair among `rels` gets `amount` added to its co-citation weight. For the
    nightly job (not wired yet). Returns how many pairs were written."""
    rels = sorted(dict.fromkeys(r for r in rels if r))
    pairs = [(a, b) for i, a in enumerate(rels) for b in rels[i + 1:]]
    if not pairs:
        return 0
    path = cocite_file(vault)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for a, b in pairs:
            fh.write(json.dumps({"a": a, "b": b, "w": amount}, ensure_ascii=False) + "\n")
    return len(pairs)


def _cocite_sig(vault: Path) -> str:
    try:
        st = cocite_file(vault).stat()
        return f"{st.st_size}:{st.st_mtime_ns}"
    except OSError:
        return ""


def cocite_changed(con: sqlite3.Connection, vault: Path) -> bool:
    return _cocite_sig(vault) != (con.execute("SELECT v FROM meta WHERE k='cocite_sig'").fetchone() or [""])[0]


def load_cocite(con: sqlite3.Connection, vault: Path) -> None:
    """Re-read the co-citation file into the cache when it changed (its size and mtime are the signature)."""
    path = cocite_file(vault)
    sig = _cocite_sig(vault)
    old = (con.execute("SELECT v FROM meta WHERE k='cocite_sig'").fetchone() or [""])[0]
    if sig == old:
        return
    sums: Counter = Counter()
    if sig:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
                a, b = sorted((str(row["a"]), str(row["b"])))
                sums[(a, b)] += float(row.get("w", 1.0))
            except (ValueError, KeyError, TypeError):
                continue
    con.execute("DELETE FROM cocite")
    con.executemany("INSERT INTO cocite VALUES(?,?,?)", [(a, b, w) for (a, b), w in sums.items() if w > 0])
    con.execute("INSERT OR REPLACE INTO meta VALUES('cocite_sig', ?)", (sig,))


# ---- query time ----

def _resolved_links(con: sqlite3.Connection, rels: list[str]) -> list[tuple[str, str, str]]:
    """(from, to, kind) for every link or supersedes edge touching `rels`, in either direction."""
    if not rels:
        return []
    marks = ",".join("?" * len(rels))
    out = con.execute(
        f"SELECT e.rel, n.rel, e.kind FROM edges e JOIN names n ON n.key = e.key "
        f"WHERE e.kind IN ('link','supersedes') AND e.rel IN ({marks})", rels).fetchall()
    out += con.execute(
        f"SELECT e.rel, n.rel, e.kind FROM names n JOIN edges e ON e.key = n.key "
        f"WHERE e.kind IN ('link','supersedes') AND n.rel IN ({marks})", rels).fetchall()
    return [(a, b, k) for a, b, k in dict.fromkeys(out) if a != b]


def degrees(con: sqlite3.Connection, rels: list[str]) -> dict[str, int]:
    deg: Counter = Counter()
    for a, b, _k in _resolved_links(con, rels):
        if a in rels:
            deg[a] += 1
        if b in rels:
            deg[b] += 1
    return deg


def is_hub(rel: str, degree: int) -> bool:
    stem = rel.rsplit("/", 1)[-1].removesuffix(".md")
    return degree >= HUB_DEGREE or bool(HUB_NAME.search(stem))


def spread(con: sqlite3.Connection, direct: list[dict], shown: set[str], scope: str = "") -> list[dict]:
    """Pages reached from the first `SEEDS` direct hits, best first, each with the edges it came along (`via`)."""
    seeds = [h for h in direct[:SEEDS] if h.get("score", 0) > 0]
    if not seeds:
        return []
    top = seeds[0]["score"]
    direct_norm = {h["rel"]: max(0.0, h["score"]) / top for h in direct}
    act: Counter = Counter()
    via: dict[str, Counter] = defaultdict(Counter)
    shared: dict[str, Counter] = defaultdict(Counter)
    n_docs = con.execute("SELECT count(*) FROM files").fetchone()[0] or 1
    seed_rels = [h["rel"] for h in seeds]
    seed_deg = degrees(con, seed_rels)

    def add(dst: str, kind: str, src: str, amount: float, word: str = "") -> None:
        # 种子页本身也可以被别的种子带出来：k=3 时第 3 条直接命中让位给联想，它若和前两条连得紧，照样回得来
        if amount <= 0 or dst == src or dst in shown:
            return
        act[dst] += amount
        via[dst][(kind, src)] += amount
        if word:
            shared[dst][word] += amount

    # 共同的词：种子页的实词 → 也把它列为实词的别的页；词越少见权重越大，连的页越多每页分得越少
    marks = ",".join("?" * len(seed_rels))
    rid_of = dict(con.execute(f"SELECT rel, rid FROM files WHERE rel IN ({marks})", seed_rels).fetchall())
    seed_terms: dict[str, list[str]] = {}
    for rel in seed_rels:
        row = con.execute("SELECT terms FROM keyterms WHERE rowid=?", (rid_of.get(rel, -1),)).fetchone()
        seed_terms[rel] = row[0].split() if row and row[0] else []
    terms = sorted({t for ts in seed_terms.values() for t in ts})
    df: dict[str, int] = {}
    holders: dict[str, list[int]] = defaultdict(list)
    cap = max(2, min(DF_ABS_MAX, int(DF_SHARE_MAX * n_docs)))
    for i in range(0, len(terms), 500):
        chunk = terms[i:i + 500]
        q = ",".join("?" * len(chunk))
        df.update(con.execute(f"SELECT term, doc FROM kvrow WHERE term IN ({q})", chunk).fetchall())
        live = [t for t in chunk if 2 <= df.get(t, 0) <= cap]
        if live:
            q = ",".join("?" * len(live))
            for term, doc in con.execute(f"SELECT term, doc FROM kvinst WHERE term IN ({q})", live):
                holders[term].append(doc)
    docs = sorted({d for ds in holders.values() for d in ds})
    rel_of: dict[int, str] = {}
    for i in range(0, len(docs), 500):
        chunk = docs[i:i + 500]
        rel_of.update(con.execute(f"SELECT rid, rel FROM files WHERE rid IN ({','.join('?' * len(chunk))})",
                                  chunk).fetchall())
    for h in seeds:
        a = h["score"] / top
        mine = seed_terms.get(h["rel"], [])
        for t in mine:
            n = df.get(t, 0)
            if not 2 <= n <= cap:
                continue
            share = a * WEIGHTS["words"] * math.log(n_docs / n) / len(mine) / (n - 1)
            for doc in holders[t]:
                rel = rel_of.get(doc)
                if rel and rel != h["rel"]:
                    add(rel, "words", h["rel"], share, t)
    # 链接、取代：沿边两头都算；枢纽页（索引、总览）发出去的分摊到它所有的链接上
    for a_rel, b_rel, kind in _resolved_links(con, seed_rels):
        for src, dst in ((a_rel, b_rel), (b_rel, a_rel)):
            if src in seed_rels:
                h = next(x for x in seeds if x["rel"] == src)
                deg = max(1, seed_deg.get(src, 1))
                split = deg if is_hub(src, deg) else math.sqrt(deg)
                add(dst, kind, src, h["score"] / top * WEIGHTS[kind] / split)
    # 同一次会话、同一天：共有同一个值的页
    for h in seeds:
        a = h["score"] / top
        for kind, key in con.execute("SELECT kind, key FROM edges WHERE rel=? AND kind IN ('session','day')", (h["rel"],)):
            if not WEIGHTS.get(kind):
                continue
            peers = [r for (r,) in con.execute("SELECT rel FROM edges WHERE kind=? AND key=? AND rel<>?",
                                               (kind, key, h["rel"]))]
            for rel in peers:
                add(rel, kind, h["rel"], a * WEIGHTS[kind] / math.sqrt(len(peers)))
    # 一起被引用过
    for h in seeds:
        a = h["score"] / top
        for other, w in con.execute("SELECT b, w FROM cocite WHERE a=? UNION ALL SELECT a, w FROM cocite WHERE b=?",
                                    (h["rel"], h["rel"])):
            add(other, "cocite", h["rel"], a * WEIGHTS["cocite"] * min(1.0, w / COCITE_SAT))
    if not act:
        return []
    scored = []
    for rel, amount in act.items():
        if rel in shown or scope and not (rel == scope or rel.startswith(scope + "/")):
            continue
        score = amount * (1 + QUERY_BOOST * direct_norm.get(rel, 0.0))
        explicit = any(k != "words" for k, _s in via[rel])
        # 安静门槛：只靠"共同的词"连上的，要共有足够多的少见词、分数也够，否则不出声（小库里只共有 `tests`、
        # `changed` 这类词的页，十有八九是巧合）
        if not explicit and (len(shared[rel]) < MIN_WORDS or score < MIN_SCORE):
            continue
        scored.append((score, rel))
    # 只给前几名查层级和链接数：大库里共同的词能连到上千页，逐个查 docs（rel 列不建索引）太慢
    scored = sorted(scored, key=lambda x: (-x[0], x[1]))[:CANDIDATES]
    if not scored:
        return []
    cands = [rel for _s, rel in scored]
    rids = dict(con.execute(f"SELECT rel, rid FROM files WHERE rel IN ({','.join('?' * len(cands))})", cands))
    info = {}
    for rel in cands:
        row = con.execute("SELECT tier, status, how FROM docs WHERE rowid=?", (rids.get(rel, -1),)).fetchone()
        if row:
            info[rel] = row
    deg = degrees(con, cands)
    out = []
    for score, rel in scored:
        if rel not in info:
            continue
        tier, status, how = info[rel]
        if tier == "dead" or is_hub(rel, deg.get(rel, 0)):
            continue
        steps = []
        # 显式的边（取代、链接、同会话、一起被引用）先说：比"共同的词"更能解释为什么想起它
        ranked_via = sorted(via[rel].items(), key=lambda kv: (kv[0][0] == "words", -kv[1]))
        for (kind, src), amount in ranked_via[:MAX_VIA]:
            step = {"kind": kind, "from": src}
            if kind == "words":
                step["words"] = [w for w, _ in shared[rel].most_common(3)]
            steps.append(step)
        out.append({"rel": rel, "tier": tier, "status": status, "how": how, "score": round(score, 4), "via": steps})
    out.sort(key=lambda x: (-x["score"], x["rel"]))
    return out


def conflict_enabled() -> bool:
    return (os.environ.get("KROUTER_CONFLICT") or "").strip().lower() not in {"0", "off", "no", "false"}


# ---- the vault changed its mind: newer page first, the conflict named ----

CHANGE_RE = re.compile(
    r"\b(switch(?:ed|ing)?\s+(?:\w+\s+){0,4}?to|switch(?:ed|ing)?\s+from|instead\s+of|chang(?:e|ed|ing)\s+(?:\w+\s+){0,4}?to|"
    r"replac(?:e|ed|es|ing)|mov(?:e|ed|ing)\s+(?:\w+\s+){0,3}?to|migrat(?:e|ed|ing)\s+(?:\w+\s+){0,3}?to|no\s+longer|"
    r"drop(?:ped|ping)?|from\s+now\s+on|rather\s+than|going\s+with|went\s+with|go\s+with|decided\s+against|"
    r"changed\s+(?:my|our)\s+mind|on\s+second\s+thought)\b"
    r"|改成|改为|改用|改回|换成|换用|换回|不再用|不用了|弃用|替换|迁到|迁移到|以后都用|以后一律|还是用|决定用|定成",
    re.I)
CONFLICT_RATIO = 0.5   # 较新那页的直接得分至少是首条的一半，才算"也在说这件事"
CONFLICT_SHARE = 0.6   # 首条对上的问题实词，较新那页至少也有这么多
CONFLICT_DEPTH = 3     # 只看前三条
CONFLICT_NOTE = ("recall_conflict: an earlier page says otherwise. {new} ({new_day}) changes what {old} ({old_day}) "
                 "says; the newer page is listed first. Answer from the newer page and say it was changed.")
CONFLICT_FLAG = ("recall_conflict: possible. {a} ({a_day}) and {b} ({b_day}) are both about this and may disagree; "
                 "the order was not changed. Read both before answering.")


def _page_text(vault: Path, rel: str) -> str:
    try:
        return (vault / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def change_lines(ri, text: str, subject: set[str]) -> tuple[bool, bool]:
    """(a line says something was changed, such a line also names the subject)."""
    any_change = named = False
    for line in text.splitlines():
        if not CHANGE_RE.search(line):
            continue
        any_change = True
        if subject & set(ri.tokens(line)):
            named = True
            break
    return any_change, named


def conflicts(ri, con: sqlite3.Connection, vault: Path, hits: list[dict], qtok: list[str]) -> dict | None:
    """The first pair among the top hits that look like the same thing said twice, at different dates.

    Both pages match the question about as well and share most of its words, both are dated, and the newer one has a
    line that says something was changed and names the subject. Sure, at different dates: the newer page goes first
    (if it is not already) and both are marked. Unsure, the same date (which is newer cannot be told): marked, order
    kept. Anything less (no change line naming the subject, a page without a date): nothing. Replaced pages are left
    to their own marking."""
    live = [h for h in hits[:CONFLICT_DEPTH] if h.get("tier") != "dead" and h.get("status") not in ri.DEAD_STATUS]
    if len(live) < 2 or not qtok:
        return None
    marks = ",".join("?" * len(qtok))

    def have(rel: str) -> set[str]:
        rid = con.execute("SELECT rid FROM files WHERE rel=?", (rel,)).fetchone()
        if not rid:
            return set()
        return {t for (t,) in con.execute(
            f"SELECT DISTINCT term FROM vinst WHERE term IN ({marks}) AND doc=? AND col IN ('title','triggers','body')",
            qtok + [rid[0]])}

    first = live[0]
    words0 = have(first["rel"])
    if not words0:
        return None
    meta0 = ri.split_frontmatter(_page_text(vault, first["rel"]))[0]
    day0 = page_day(first["rel"], meta0)
    for other in live[1:]:
        if other["score"] < CONFLICT_RATIO * first["score"]:
            continue
        words1 = have(other["rel"])
        common = words0 & words1
        if len(common) < min(2, len(words0)) or len(common) < CONFLICT_SHARE * len(words0):
            continue
        text1 = _page_text(vault, other["rel"])
        day1 = page_day(other["rel"], ri.split_frontmatter(text1)[0])
        if not day0 or not day1:
            continue
        text0 = _page_text(vault, first["rel"])
        if day1 < day0 or day1 == day0 and change_lines(ri, ri.split_frontmatter(text0)[1], common)[1]:
            # 首条才是较新的（或同一天、改动的话在首条）：顺序已经对了，只说明较早的一页说法不同
            older, newer, new_text = other, first, text0
        else:
            older, newer, new_text = first, other, text1
        _changed, named = change_lines(ri, ri.split_frontmatter(new_text)[1], common)
        if not named:  # 改动的话没点到这件事（长会话里随处都有 instead of、replace）：不算
            continue
        sure = day1 != day0
        reorder = sure and newer is other
        return {"older": older["rel"], "newer": newer["rel"], "older_day": min(day0, day1),
                "newer_day": max(day0, day1), "sure": sure, "reorder": reorder}
    return None


def apply_conflict(hits: list[dict], c: dict) -> None:
    """Newer page first when sure; both marked either way."""
    if c["reorder"]:
        i = next(i for i, h in enumerate(hits) if h["rel"] == c["newer"])
        hits.insert(0, hits.pop(i))
    for h in hits:
        if h["rel"] == c["newer"]:
            h["conflict"] = "newer" if c["sure"] else "possible"
        elif h["rel"] == c["older"]:
            h["conflict"] = "older" if c["sure"] else "possible"


def conflict_note(c: dict) -> str:
    if c["sure"]:
        return CONFLICT_NOTE.format(new=c["newer"], new_day=c["newer_day"], old=c["older"], old_day=c["older_day"])
    return CONFLICT_FLAG.format(a=c["newer"], a_day=c["newer_day"], b=c["older"], b_day=c["older_day"])
