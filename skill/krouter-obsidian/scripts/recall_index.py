#!/usr/bin/env python3
"""L1 recall: a rebuildable SQLite FTS5 cache over the vault's Markdown.

The lock (canonical_lookup) stays the only thing that may claim a page. Recall only ranks.
Text is pre-split into CJK bigrams and latin words, so FTS5's own bm25() does the scoring.
The cache lives outside the vault, follows file mtimes, and can be deleted at any time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zones  # noqa: E402
import krouter_redact  # noqa: E402

redact = krouter_redact.redact
is_secret_page = krouter_redact.is_secret_page  # 其他夜间脚本经 ri.is_secret_page 用它

SCHEMA_VERSION = "recall-v13"  # v13：机密页不存 how、脱敏规则扩大，旧缓存必须重建
STRONG_W = 0.5  # 软权重 ≥ 此值才算"有效匹配词"
MIN_STRONG_MATCH = 2
SCORE_MIN = 8.5  # bm25×分层权重的绝对下限
SINGLE_TERM_SCORE = 25.0  # 只有一个有效词时，分数要高到这个程度才回答
# 双字"像词"的下限：df(xy)/min(df(x),df(y))；跨词边界的拼接双字通常 < 0.1
WORDNESS_MIN = 0.12
STATUS_LINE_RE = re.compile(r"^(active|provisional|candidate|superseded|retired|rejected|status|状态)\b", re.I)
SKIP_PARTS = {"Clippings", ".trash", ".obsidian", "迁移备份", "node_modules", ".git"}
RULE_PREFIXES = (
    "02 经验与方法/",
    "90 系统文件/Agent记忆/",
    "90 系统文件/自动化/",
)
RULE_FILES = {"AGENTS.md", "Agent第二大脑.md", "01 项目/项目.md"}
DEAD_STATUS = {"superseded", "retired", "rejected", "deprecated", "archived"}
HOW_MAX = 80
# 问句里的功能性双字，几乎每页都有，不参与召回
QUERY_STOP = {
    "什么", "怎么", "怎样", "能不", "不能", "是不", "不是", "哪个", "哪些", "哪里", "应该",
    "可以", "现在", "到底", "一下", "我的", "我们", "你的", "为什", "么要", "有没", "没有",
    "是什", "么样", "要不", "不要", "还是", "这个", "那个", "如何", "多少", "吗我",
    "关于", "帮我", "请问", "一首", "一个", "一下",
}
# 英文问句里的功能词：小库里多半一次都没出现，但它们不是「问的东西」。不当库外词数，只影响拒答
EN_FUNCTION = set("""
a an the and or but if then so of to in on at by for from with about into over under as is are was were be been
being am do does did done doing have has had having can could should would will shall may might must need needs
what which who whom whose when where why how many much long often far old there here this that these those it its
i me my we us our you your he him his she her they them their one ones any some all each every no not more most
less other else than too very just also only ever still again use used using get got make made way ways thing things
please tell know want like
""".split())
# 含这些虚字的双字（`天的`、`帮我`）出现得极频繁，"像词"指标会误判；只影响拒答，不影响排序
FUNCTION_CHARS = set("的了我你他她吗呢吧啊么什")
CJK_RE = re.compile(r"[㐀-鿿豈-﫿]+")
LATIN_RE = re.compile(r"[a-z0-9]+")  # 与 FTS5 unicode61 的切分一致


def cache_path(vault: Path) -> Path:
    base = Path(os.environ.get("KROUTER_CACHE_DIR") or Path.home() / ".cache" / "krouter")
    digest = hashlib.sha1(str(vault.resolve()).encode("utf-8")).hexdigest()[:12]
    return base / f"recall-{digest}.sqlite"


def tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text or "").lower()
    out: list[str] = []
    for run in CJK_RE.findall(text):
        if len(run) == 1:
            out.append(run)
        else:
            out.extend(run[i : i + 2] for i in range(len(run) - 1))
    out.extend(w for w in LATIN_RE.findall(text) if len(w) >= 2)
    return out


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    # Windows 编辑器常存 CRLF：不规范化的话 frontmatter 整个读不出来，`status: superseded` 也就失效
    text = (text or "").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    meta: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith((" ", "-", "\t")):
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, text[end + 4 :].lstrip("-\n")


def unigrams(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text or "").lower()
    return sorted({c for run in CJK_RE.findall(text) for c in run})


def _clean(line: str) -> str:
    line = re.sub(r"^(>\s*(\[![^\]]+\]\s*)?|[-*+]\s+|\d+\.\s+)", "", line.strip())
    return re.sub(r"[*`_]|\[\[([^|\]]*\|)?|\]\]", "", line).strip()


def first_rule_line(body: str) -> str:
    plain = ""
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "|", "```", "<", "![", "%%")):
            continue
        cleaned = _clean(line)
        if len(cleaned) < 8 or STATUS_LINE_RE.match(cleaned):
            continue
        if "**" in line:
            # 准纠错/方法页的第一条加粗规则就是结论
            text = cleaned
            return text[: HOW_MAX - 1] + "…" if len(text) > HOW_MAX else text
        if not plain:
            plain = cleaned
    return plain[: HOW_MAX - 1] + "…" if len(plain) > HOW_MAX else plain


TRIGGER_GLOB = "下意识触发词*.psv"
CARD_GLOB = "下意识问答*.jsonl"  # answer_cards.py  # 人工/生成的触发词 + 夜间自学习的触发词


def alias_map(vault: Path | None = None) -> tuple[dict[str, list[str]], str]:
    """页面的召回触发词：人工锁别名（canonical_sources.psv）+ 90 系统文件/ 下的旁路 `下意识触发词.psv`（rel|词;词）。

    只用于召回排序，不参与锁定；锁定仍只认人工别名表。
    """
    from canonical_lookup import map_for

    sources = [map_for(vault)]
    system = zones.path(vault, "90 系统文件") if vault is not None else None
    if system is not None and system.is_dir():
        sources += sorted(system.rglob(TRIGGER_GLOB))
        sources += sorted(system.rglob(CARD_GLOB))
    out: dict[str, list[str]] = {}
    digest = hashlib.sha1()
    for path in sources:
        if not path.is_file():
            continue
        data = path.read_bytes()
        digest.update(data)
        for line in data.decode("utf-8", errors="replace").splitlines():
            if not line or line.startswith("#"):
                continue
            if line.startswith("{"):  # answer cards are read by card_triggers(), filtered by page hash
                continue
            parts = line.split("|")
            if len(parts) == 4:  # canonical map: id|aliases|source|anchor
                rel, words = parts[2], parts[1]
            elif len(parts) == 2:  # trigger sidecar: rel|words
                rel, words = parts
            else:
                continue
            out.setdefault(rel.strip(), []).extend(a.strip() for a in words.split(";") if a.strip())
    return out, digest.hexdigest()


TOPIC_PREFIX = "02 经验与方法/主题档案/"


def body_hash(raw_bytes: bytes) -> str:
    """问答卡绑定的哈希：只算正文。frontmatter 由机器和 agent 频繁改写（`nightly_at`、`status`、`verified_at`），
    改了它卡片说的事并没有变，不该让卡作废。"""
    _meta, body = split_frontmatter(raw_bytes.decode("utf-8", errors="replace"))
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:16]


def card_hashes(raw_bytes: bytes) -> frozenset[str]:
    """一张卡还算数的哈希：正文哈希（0.11.1 起写入的卡），或整页哈希（更早写入的卡，不必全部重写）。"""
    return frozenset({body_hash(raw_bytes), hashlib.sha1(raw_bytes).hexdigest()[:16]})


def card_triggers(vault: Path | None) -> dict[str, list[dict]]:
    """{rel: [card]} from 下意识问答*.jsonl; refresh() keeps only cards that match and are grounded in the page."""
    if vault is None or not zones.path(vault, "90 系统文件").is_dir():
        return {}
    return load_cards(vault)


def tier_of(rel: str, status: str) -> str:
    if status in DEAD_STATUS or status == "generated":
        return "dead"
    if rel.startswith(TOPIC_PREFIX):
        return "topic"
    if rel in RULE_FILES or rel.startswith(RULE_PREFIXES) or ("协作/" in rel and rel.startswith("90 系统文件/")):
        return "rule"
    if rel.startswith("05 时间日志/"):
        return "log"
    if rel.startswith("01 项目/") or rel.startswith("04 已完成与复盘/"):
        return "project"
    return "other"


def walk_md(vault: Path):
    """(absolute path, vault-relative posix path) as plain strings: no per-file pathlib work."""
    base = str(vault).rstrip("/")
    cut = len(base) + 1
    for root, dirs, files in os.walk(base, followlinks=True):
        dirs[:] = [d for d in dirs if d not in SKIP_PARTS and not d.startswith(".")]
        # 库内相对路径一律用 `/`：Windows 上 os.walk 给的是 `\`，分级、区名映射、卡片、别名表都按 `/` 比对
        reldir = root[cut:].replace(os.sep, "/")
        for name in files:
            if name.endswith(".md"):
                yield f"{root}/{name}", (f"{reldir}/{name}" if reldir else name)


def iter_markdown(vault: Path):
    for full, rel in walk_md(vault):
        yield Path(full), rel


def connect(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT)")
    row = con.execute("SELECT v FROM meta WHERE k='schema'").fetchone()
    if not row or row[0] != SCHEMA_VERSION:
        con.executescript(
            """
            DROP TABLE IF EXISTS vcol; DROP TABLE IF EXISTS vinst; DROP TABLE IF EXISTS vrow; DROP TABLE IF EXISTS docs; DROP TABLE IF EXISTS files;
            CREATE VIRTUAL TABLE docs USING fts5(
                rel UNINDEXED, title, triggers, body, uni, tier UNINDEXED, status UNINDEXED, how UNINDEXED, name UNINDEXED,
                tokenize='unicode61');
            CREATE VIRTUAL TABLE vrow USING fts5vocab(docs, 'row');
            CREATE VIRTUAL TABLE vinst USING fts5vocab(docs, 'instance');
            CREATE VIRTUAL TABLE vcol USING fts5vocab(docs, 'col');
            CREATE TABLE files(rel TEXT PRIMARY KEY, mtime_ns INTEGER, size INTEGER, rid INTEGER);
            """
        )
        con.execute("INSERT OR REPLACE INTO meta VALUES('schema', ?)", (SCHEMA_VERSION,))
        con.commit()
        con.execute("VACUUM")  # 旧表的页还留在文件里（旧版本存的是未脱敏的原文），一并清掉
    return con


def refresh(vault: Path, con: sqlite3.Connection) -> dict[str, int]:
    seen: dict[str, tuple[int, int, Path]] = {}
    for full, rel in walk_md(vault):
        try:
            st = os.stat(full)
        except OSError:
            continue
        seen[rel] = (st.st_mtime_ns, st.st_size, full)
    known = {rel: (m, s, rid) for rel, m, s, rid in con.execute("SELECT rel, mtime_ns, size, rid FROM files")}
    aliases, map_sha = alias_map(vault)
    cards = card_triggers(vault)
    old_sha = (con.execute("SELECT v FROM meta WHERE k='map_sha'").fetchone() or [""])[0]
    if map_sha != old_sha:
        # 别名或触发词变了：全部重建（一次约 1–2 秒），避免被删掉的触发词残留
        known = {rel: (-1, s, rid) for rel, (_m, s, rid) in known.items()}
        con.execute("INSERT OR REPLACE INTO meta VALUES('map_sha', ?)", (map_sha,))
    changed = added = removed = 0
    for rel, (_m, _s, rid) in known.items():
        if rel not in seen:
            con.execute("DELETE FROM docs WHERE rowid=?", (rid,))
            con.execute("DELETE FROM files WHERE rel=?", (rel,))
            removed += 1
    for rel, (mtime, size, path) in seen.items():
        old = known.get(rel)
        if old and old[0] == mtime and old[1] == size:
            continue
        path = Path(path)
        try:
            raw_bytes = path.read_bytes()
        except OSError:
            continue
        # 索引、how、问答卡核对用的都是脱敏后的文字：密钥值不进缓存，也不会从这里被打印或外发
        text = redact(raw_bytes.decode("utf-8", errors="replace"))
        meta, body = split_frontmatter(text)
        page_hash = card_hashes(raw_bytes)
        title = meta.get("title") or path.stem
        status = (meta.get("status") or "").lower()
        # 卡片问题只在卡片还对得上这一页当前内容、且核对得过时才算触发词：页面一改旧卡不再影响排序，
        # 答案对不上原文或问题跟这页无关的卡也不能把这页顶上来
        mine = [c for c in cards.get(rel, []) if c.get("sha") in page_hash]
        terms = set(tokens(text)) if mine else set()
        live_cards = [c["q"] for c in mine if grounded(c, text, terms)]
        trig = " ".join([meta.get("triggers") or meta.get("aliases") or ""] + aliases.get(rel, []) + live_cards)
        secret = is_secret_page(zones.canon(vault, rel), meta)
        how = "（机密页：只给路径，不引用原文）" if secret else (meta.get("how") or first_rule_line(body))
        dirs = " ".join(rel.split("/")[:-1])
        if old:
            con.execute("DELETE FROM docs WHERE rowid=?", (old[2],))
            changed += 1
        else:
            added += 1
        cur = con.execute(
            "INSERT INTO docs(rel, title, triggers, body, uni, tier, status, how, name) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                rel,
                " ".join(tokens(title + " " + path.stem + " " + meta.get("topic_terms", ""))),
                " ".join(tokens(trig)),
                " ".join(tokens(dirs + "\n" + body)),
                " ".join(unigrams(title + " " + trig + " " + body)),
                tier_of(zones.canon(vault, rel), status),
                status,
                how,
                compact(title + "|" + path.stem + "|" + meta.get("topic_terms", "")),
            ),
        )
        con.execute("INSERT OR REPLACE INTO files VALUES(?,?,?,?)", (rel, mtime, size, cur.lastrowid))
    if changed or added or removed:
        con.execute("INSERT OR REPLACE INTO meta VALUES('built_at', ?)", (time.strftime("%Y-%m-%dT%H:%M:%S"),))
        con.commit()
    return {"added": added, "changed": changed, "removed": removed, "docs": len(seen)}


TIER_BOOST = {"rule": 1.6, "topic": 1.4, "project": 1.0, "other": 0.9, "log": 0.8, "dead": 0.25}
# 主题档案只在问题点到这个主题时才相关；没点名就大幅降权，免得大页靠泛词抢第一
TOPIC_UNNAMED = 0.35
TOPIC_NAMED = 1.25
TITLE_HIT = 2.0
CARD_MIN = 0.5  # 问答卡至少覆盖问题一半的实词分量才输出
ANSWER_SUPPORT_MIN = 0.3  # 答案用词至少这么多在原页出现
ALIEN_MIN = 2  # 库里从没出现过的汉字达到这么多、且只对上一个实词：判为库外
# 整句问题只对上一个实词也作答时（分数够、又没有库外证据），首条页可能是对的，也可能只是借了一个词。
# 开发集上这种情况对错各半，分数分不开，所以不改答不答，只把话说清楚
PARTIAL_NOTE = ("recall_note: only one word of the question matched these pages; they may be about something else. "
                "Say what they say and that the vault may not cover the question; do not give it as the answer.")


def recall(vault: Path, query: str, scope: str = "", limit: int = 5, refresh_first: bool = True,
           gate: bool = True) -> dict:
    con = connect(cache_path(vault))
    stats = refresh(vault, con) if refresh_first else {}
    raw: list[str] = []
    for t in tokens(query):
        if len(t) == 1 and CJK_RE.fullmatch(t):
            continue  # 单个汉字（`的`）不是词
        if t not in QUERY_STOP and t not in raw:
            raw.append(t)
    # 英文功能词（what / is / the / do）不参与排序和拒答判断：小库里它们只会把「Error messages」这种
    # 恰好写了 what 和 do 的页顶上来。全是功能词的问句照旧用原词
    raw = [t for t in raw if t not in EN_FUNCTION] or raw
    if not raw:
        return {"hits": [], "stats": stats, "query_tokens": [], "confidence": "none", "margin": 0.0}
    df = term_df(con, raw + [c for t in raw if is_cjk_bigram(t) for c in t]
                 + [f for t in raw if not is_cjk_bigram(t) for f in latin_forms(t)])
    present = [t for t in raw if df.get(t, 0) > 0]
    bigrams = [t for t in present if is_cjk_bigram(t)]
    named = phrase_terms(con, bigrams)
    titled = phrase_terms(con, bigrams, ("title",))
    qtok = [t for t in present if not is_cjk_bigram(t) or t in named or wordness(t, df) >= WORDNESS_MIN] or present
    if not qtok:
        return {"hits": [], "stats": stats, "query_tokens": [], "confidence": "none", "margin": 0.0}
    match = "{title triggers body} : (" + " OR ".join('"' + t.replace('"', "") + '"' for t in qtok) + ")"
    rows = con.execute(
        "SELECT rowid, rel, tier, status, how, title, name, bm25(docs, 0, 4.0, 4.0, 1.0, 0, 0, 0, 0, 0) AS s "
        "FROM docs WHERE docs MATCH ? ORDER BY s LIMIT 80",
        (match,),
    ).fetchall()
    scope = scope.strip("/")
    hits = []
    qset = set(raw)
    qname = compact(query)
    single = is_single_concept(query)
    for rid, rel, tier, status, how, title, name, s in rows:
        if scope and not (rel == scope or rel.startswith(scope + "/")):
            continue
        boost = TIER_BOOST.get(tier, 1.0)
        if tier == "topic":
            # 点名的主题档案是这个主题的总入口，排在同名的零散规则页前面；没点名就大幅降权
            boost *= TOPIC_NAMED if set(title.split()) & qset else TOPIC_UNNAMED
        if qname and len(qname) >= 2 and qname in (name or ""):
            boost *= TITLE_HIT  # 问的就是这页的名字（`DSH`、`SyGJ`、`封账`）
        hits.append({"rid": rid, "rel": rel, "tier": tier, "status": status, "how": how,
                     "score": round(-s * boost, 3)})
    hits.sort(key=lambda h: -h["score"])
    hits = hits[:limit]
    if not hits:
        return {"hits": [], "stats": stats, "query_tokens": qtok, "confidence": "none", "margin": 0.0}
    n_docs = con.execute("SELECT count(*) FROM files").fetchone()[0] or 1
    strong = strong_matches(con, hits[0]["rid"], present, df, titled, small=n_docs < SMALL_VAULT, known=named)
    top = hits[0]["score"]
    second = hits[1]["score"] if len(hits) > 1 else 0.0
    margin = top / second if second else 9.9
    # bm25 的量级随库大小变化：小库按文档数等比缩放下限，千篇以上用满额
    scale = min(1.0, n_docs / 1000)
    # 关键词式查询（`DSH`、`SyGJ`）本身只有一个实词，命中它就够；整句问题仍要求至少两个实词
    need = min(MIN_STRONG_MATCH, query_content_terms(raw, df, titled))
    # 问题的核心词库里一次都没出现（`Kubernetes`），只靠一两个边角词凑上的，判为库外
    unknown = unknown_content_terms(raw, df)
    # 问题里有库里一次都没出现过的汉字（`咖啡`、`除垢`），而首条只对上一个实词：问的是库外的事，
    # 只是借了库里的一个词（`定时`）。字比词稳：换个说法会产生库里没有的双字，但不会凭空多出库里没有的字
    alien = alien_chars(raw, df)
    # 问题里的真词有两个以上整库都没有，而且比首条页对上的真词还多：问的主要是库外的事（`纠错之后的房贷利率`）
    absent_words, top_words = outside_words(con, hits[0]["rid"], raw, df)
    off_vault = absent_words >= 2 and absent_words > top_words
    if single:
        # 一个概念的短查询：只有一个词可比，不按"至少两个实词"拦；但仍要过（减半的）分数下限
        refuse = top < SCORE_MIN * scale * 0.5 or (unknown and strong == 0)
    else:
        refuse = (top < SCORE_MIN * scale or (strong < need and top < SINGLE_TERM_SCORE * scale) or strong == 0
                  or (unknown and strong <= 2) or (strong < need and alien >= ALIEN_MIN) or off_vault)
    partial = not single and strong < need
    if gate and refuse:
        conf = "none"
    elif partial:
        conf = "low"
    elif margin >= 1.5 and hits[0]["tier"] in ("rule", "topic"):
        conf = "high"
    elif margin >= 1.15:
        conf = "medium"
    else:
        conf = "low"
    for h in hits:
        h.pop("rid", None)
    if hits and conf != "none" and not partial:
        attach_answers(vault, hits, raw, df)  # 只对上一个词时不给生成的答案：那一行读起来像定论
    return {"hits": hits, "stats": stats, "query_tokens": qtok, "margin": round(margin, 2),
            "strong": strong, "confidence": conf, "partial": partial and conf != "none"}


def strong_matches(con: sqlite3.Connection, rid: int, terms: list[str], df: dict[str, int],
                   named: set[str] = frozenset(), small: bool = False, known: set[str] = frozenset()) -> int:
    """首条命中页里出现了几个"像词"的查询词。只碰上一个泛词的，多半是巧合。"""
    if not terms:
        return 0
    marks = ",".join("?" * len(terms))
    hit = {t for (t,) in con.execute(
        f"SELECT DISTINCT term FROM vinst WHERE term IN ({marks}) AND doc = ? AND col IN ('title','triggers','body')",
        terms + [rid],
    )}
    # 纯数字（年份、日期、序号）到处都有，只参与排序，不算实词
    content, generic = lexicon() if small else (set(), set())

    def wordlike(t: str) -> bool:
        # 小库里 `天会` 这种跨词碎片看起来也"像词"；只认通用词表里的词和标题、触发词里出现过的词
        return not small or not is_cjk_bigram(t) or t in named or t in known or t in content or t in generic

    return sum(1 for t in hit if (soft_weight(t, df) >= STRONG_W or t in named) and not t.isdigit()
               and not set(t) & FUNCTION_CHARS and wordlike(t))


# 通用汉字频率前 1500（由 jieba 0.42.1 自带词典 dict.txt 的词频累加得出，MIT）。小库里没有「知道」「已经」
# 不说明问的是库外；没有「咖啡」「除垢」才说明。只有不在这张表里、库里也没出现过的字，才算库外证据
COMMON_CHARS = frozenset(
    "一是人了不在有大中国和为这上他个地年来我会以到时要出的生学说道民家子也成行下们于后就发自之对得主长可过天作分方用多你着部能市等业全里工公经本都而高政法面门动日进区事代那去心小同北定开产前其军还然起种所"
    "如现理机体表力好外与文当两实重新三么只山水关明从化平建又制南内西没此将员名手最东头者月间无安看见各城十相但已些正口通想度加第她合院物性战由位常点海意场武使次二向治因立数样身情入原问把路被并利石老教万知"
    "级量任江及应省资委务元美特期世湖回系比气汉总展电科金先声提品设或义王社很统处四首共马形己儿司太目基领队直计别女权话少流命至报米给打变果书清活几州华解议更称程今决张导术府才保交放管结师便走达族反再题色五"
    "京河接条规式县白它改风光运信受什组听布百济党指论强做取技黄神选记斯真却职号界件花类何眼兵传带空干农边据集联古广完质阳难增历史专官每住商即步认车台林必死游举线言皇土团收考求德叫近备研争非具李众连调感转笑"
    "革该持始英克士尔让拉思根格造较际亲单朝红型价校约器字段周亚深候则功属积快图火千准究往极育装许参半令吃观鱼精办像帝八复影告远群包整构料随划算象容示投势热值夫网望源息语股铁断派速怎需片爱律纪支早况病境证编"
    "越局推满且列觉服双未居除乐企引标确织初青志率项飞球节察龙响药站施均消客失轻存低甚般击曾防请离落显罗营足素视护副食创余照兴占巴虽洲村费易试星木黑左宝置跟央识维采六底宫房音环案批切斗富乡另倒若按查故突责严"
    "桥模仅胜杀围席态破承招杨负层须父供续状域似依银范修找九致密终血旅钱赛独细效玉冲获习医演毛尽脸弹楼艺航陆右协七攻镇检写苏宗章注阿抗弟坐验封紧劳户优财养适陈喜卫排射哥油刻留急降念云微伤例景拿绝阶座刘刚害印"
    "亿沙母酒助闻超审待压升送监策略限竟香配藏敌呢差仍兰温园树征善波哪词岛止预怕继皮执味份角草男普答益谁船惊核街夏宣掌田久著画辑奇尼剑吧谈背免孩礼材愿洋春架筑括晚乱乎讲尚良友临激刀夜室既敢邦挥昌板胡欧福港叶"
    "简苦担句岁荆贵娘守辖威宜衣帮块堂额错剧充欢够孙班呼阵销坚练脚退读测吴希宁换版异某顾曲楚典朱毒菜判救宋茶洪含顺啊鲜败货矿端兄归冷忙买险康评肉吗厂永哈沉散遗停笔假输牛洞松渐顶训录否述毕督控丰献姑忽爷互亮纳"
    "襄登咱钟伯臣雄季脑介鄂召饭暗扩祖齐短烈赶牌恩诉移诗础露届蒙静喝盘卖植授伊湾博痛减穿逐秘庭陵固禁票灵杂姓泽吸侧庆妈遇追甲馆补唐炮沿殿刺怪彩俄旧警索岸轮妇载靠附毫怀软骨探雷旁罪枪牙迎序慢盛雨墙恶谷顿危稳熟"
    "概酸操诸绿佛荣针托宽折野付午肯库厚缺罢耳屋嘴末谢巨培页瓦款犯困店智拥雪翻圣戏旗吉婚奖岩疑币圆歌廷健卡烧析讨跑烟误仙疗舞亡闭汽伸脱秋姐繁侵川莫麻秀借寻私岗卷跳丽横驻套兼您君丁束纸夺袁灯坏坦丝径购阴床瞧择"
    "墓宪峰遍鲁庙掉丹桃御舰避售怒课播拔奥延虚隐粮络遭摇潜庄混厅婆奴鼓赵访睡震予童徐韦殖抓拜吨扬址洛休纵逃染纷贸透汇灭蛋森仪塔距狐融郡缓聚盖拍迹忠释润粉涓孔岭搜紫虑促抵钢塞寺津液码虎坛珍硬梁奔累役偏迫锛凡损"
    "壁哭替税综伦冰盟挂韩竞乌尤弱铺妹秦尊竹珠迅脉泥鬼纯睛刑途隆潮幅杯握谋剂幸奉乘抱朋谓频崇壮骑紝恐享鸡虫绍铜呈泛械摆欲奶敬措爆暴签猛郭嘉障缩亦废搞胞埃曰撤暖寒订俗绩阻盐萨勒忘奏孝贴灰梅触玩默醒胸莲篇柱裁啦"
    "淡抢捕闹纺截讯朗誉雅忍梦伙勇峡徒丈尾迷唱泉泰佳残闪伍呀疾署剩贼冠倾豆申贫诺麦泪羊尖辈镜涉贡爹缘摩妻殊贝零映甘骂糖岳饮奋棉雕跃汗冒渡努赞启阁斤裂患伏池鹿洗劲晋倍圈媒箭沟锋胆凭挑抬闯隔弄曹汤苗迁叹唯振储贯"
    "彻桌祭符僧衡炸旋喊凤黎郎援肥磁忌赏辽祥董仁辛瑞询敏浪貌毁昨巧腿抽荷陷焦净腹弃乃湘亩滑狗冬宏皆番尸伟桂览恢龄绕趣晶坡魏摸伴墨浓绪舍蓝荡阅井鸿旦惯症鸟窗扎辞聘穷堰宇键荒递恨隶厉杜闲腰袭侍灾涨叔湿寨幕豪郑磨"
)


LEXICON_FILE = Path(__file__).resolve().parent / "lexicon_zh2.txt"
COUNT_CHARS = set("一二两三四五六七八九十百千几每这那哪某各")
SMALL_VAULT = 300  # 页数少于这个，库内统计判断不了一个双字是不是词，改用通用词表和标题
GENERIC_WORDS = 1000  # 词表前 1000 个（之后、以后、正常、项目……）太常见，不作库外证据
_LEX: dict[str, set[str]] = {}


def lexicon() -> tuple[set[str], set[str]]:
    """(content words, generic words) from the bundled general-Chinese two-character word list."""
    if not _LEX:
        words = []
        if LEXICON_FILE.is_file():
            words = [w for w in LEXICON_FILE.read_text(encoding="utf-8").splitlines() if w and not w.startswith("#")]
        _LEX["generic"] = set(words[:GENERIC_WORDS])
        _LEX["content"] = set(words[GENERIC_WORDS:])
    return _LEX["content"], _LEX["generic"]


def outside_words(con: sqlite3.Connection, rid: int, raw: list[str], df: dict[str, int]) -> tuple[int, int]:
    """(真词里整库都没有的个数, 真词里首条页有的个数)。真词按通用词表判断，不靠库内统计——小库的统计判断不了
    `天会` 是不是词，也说明不了 `房贷`、`报销` 不在库里意味着什么；通用词表都能。"""
    content, _generic = lexicon()
    # 「两条」「这次」「每天」是数量和指代，不是在问什么东西
    words = [t for t in dict.fromkeys(raw) if is_cjk_bigram(t) and t in content and t[0] not in COUNT_CHARS]
    if not words:
        return 0, 0
    absent = sum(1 for t in words if not df.get(t, 0))
    marks = ",".join("?" * len(words))
    on_top = {t for (t,) in con.execute(
        f"SELECT DISTINCT term FROM vinst WHERE term IN ({marks}) AND doc = ?", words + [rid])}
    return absent, len(on_top)


def alien_chars(raw: list[str], df: dict[str, int]) -> int:
    """问题里有几个汉字在整个库里一次都没出现过、且不是通用常用字（虚字不算）。"""
    chars = {c for t in raw if is_cjk_bigram(t) for c in t if c not in FUNCTION_CHARS and c not in COMMON_CHARS}
    return sum(1 for c in chars if not df.get(c, 0))


def latin_forms(t: str) -> list[str]:
    """`services` 和库里的 `service` 是同一个词：复数 / 单数互认。"""
    forms = [t + "s", t + "es"]
    if t.endswith("ies"):
        forms.append(t[:-3] + "y")
    if t.endswith("es"):
        forms.append(t[:-2])
    if t.endswith("s"):
        forms.append(t[:-1])
    return forms


def _known_latin(t: str, df: dict[str, int]) -> bool:
    return any(df.get(f, 0) for f in [t, *latin_forms(t)])


def unknown_content_terms(raw: list[str], df: dict[str, int]) -> int:
    n = 0
    for t in raw:
        if df.get(t, 0) or t in EN_FUNCTION or (not is_cjk_bigram(t) and _known_latin(t, df)):
            continue
        # 只看拉丁专名（`Kubernetes`）。中文词库里没有多半只是换了说法（`讲究`），不代表问的是库外
        if not is_cjk_bigram(t):
            n += len(t) >= 4 and not t.isdigit()
    return n


def query_content_terms(raw: list[str], df: dict[str, int], named: set[str] = frozenset()) -> int:
    """问题里有几个实词：拉丁词、像词的双字；库里没有但由少见字组成的双字也算（说明问的是库外的东西）。"""
    n = 0
    for t in raw:
        if not is_cjk_bigram(t):
            n += len(t) >= 2 and not t.isdigit()
        elif set(t) & FUNCTION_CHARS:
            continue
        elif df.get(t, 0) > 0:
            n += soft_weight(t, df) >= STRONG_W or t in named
        else:
            n += min(df.get(t[0], 0), df.get(t[1], 0)) < 30
    return n


def soft_weight(t: str, df: dict[str, int]) -> float:
    """跨词拼接的双字降权而不删除，真词（含由常用字组成的少见词）保留部分分量。"""
    if not is_cjk_bigram(t):
        return 1.0
    return max(0.2, min(1.0, wordness(t, df) / 0.3))


def phrase_terms(con: sqlite3.Connection, terms: list[str], cols: tuple[str, ...] = ("title", "triggers")) -> set[str]:
    """出现在任意标题（或触发词）里的双字：这些是完整写出来的短语，跨词拼接的垃圾双字基本不会出现。

    排序用标题+触发词；拒答只用标题——模型生成的口语触发词里有泛词（`帮我`），不能拿来撑"像词"。
    """
    if not terms:
        return set()
    marks = ",".join("?" * len(terms))
    return {t for (t,) in con.execute(
        f"SELECT DISTINCT term FROM vcol WHERE term IN ({marks}) AND col IN ({','.join('?' * len(cols))})",
        terms + list(cols))}


def compact(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"[\s\W_]+", "", text)


def is_single_concept(query: str) -> bool:
    """`DSH`、`发版`、`自动化`：一个英文词，或不超过 4 个汉字、没有空格。"""
    q = (query or "").strip()
    if not q or re.search(r"\s", q) or q.isdigit():
        return False  # 纯数字（年份、序号）不是一个概念
    if re.fullmatch(r"[A-Za-z0-9._+-]+", q):
        return True
    return bool(CJK_RE.fullmatch(q)) and len(q) <= 4


def load_cards(vault: Path) -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = {}
    base = zones.path(vault, "90 系统文件")
    for path in sorted(base.rglob(CARD_GLOB)) if base.is_dir() else []:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                card = json.loads(line)
            except json.JSONDecodeError:
                continue
            if card.get("rel") and card.get("q") and card.get("a"):
                by.setdefault(card["rel"], []).append(card)
    return by


SPECIFIC_BACKTICK = re.compile(r"`([^`]+)`")
SPECIFIC_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:~+#-]*[A-Za-z0-9]|\d")


def card_specifics(answer: str) -> list[str]:
    """What a card claims verbatim: backticked spans, numbers, paths / versions / commands, latin words ≥ 3."""
    # 全角冒号是中文标点，不是标识符的一部分（`Opus 5.5：/opt/…` 是两个片段）
    text = unicodedata.normalize("NFKC", (answer or "").replace("：", " "))
    found = [m.strip() for m in SPECIFIC_BACKTICK.findall(text) if m.strip()]
    for tok in SPECIFIC_TOKEN.findall(SPECIFIC_BACKTICK.sub(" ", text)):
        if any(c.isdigit() for c in tok) or any(c in tok for c in "./_:~#") or len(tok) >= 3:
            found.append(tok)
    return found


def occurs(spec: str, page: str) -> bool:
    """`spec` appears in `page` as a whole token: `3` is not in `30`, `80` is not in `8080`, `3` is not in `1.3`."""
    left = right = ""
    if spec[:1].isdigit():
        left = r"(?<![0-9_])(?<![0-9]\.)"  # `v0.9.2` 前面的字母可以有
    elif spec[:1].isalpha() and spec[:1].isascii():
        left = r"(?<![a-z0-9_])"
    if spec[-1:].isascii() and spec[-1:].isalnum():
        right = r"(?![a-z0-9_])(?!\.[0-9])"
    return re.search(left + re.escape(spec) + right, page) is not None


def faithful(answer: str, page_text: str) -> bool:
    """Every specific in the answer appears verbatim in the page, as a whole token.

    This checks specifics only. An answer with no numbers / paths / latin words has nothing to check,
    and a reworded sentence that flips the page's meaning still passes; checkup counts those cards.
    """
    page = unicodedata.normalize("NFKC", page_text or "").lower()

    def present(spec: str) -> bool:
        spec = spec.lower()
        if occurs(spec, page):
            return True
        # `utun1/utun7`、`push/release`、`llm+DeepSeek`：答案把原文里分开写的词连在一起了，逐段核对。
        # 只拆带字母的词；纯数字组合（`1:3.3`、`8/16`）常是模型自己算出来的，必须整串在原文出现
        parts = [x for x in re.split(r"[/+]", spec) if x]
        words = len(parts) > 1 and all(len(x) >= 2 and re.search(r"[a-z]", x) for x in parts)
        return bool(words) and all(occurs(x, page) for x in parts)

    return all(present(spec) for spec in card_specifics(answer))


def question_terms(question: str) -> list[str]:
    """The card question's content words: no question words (`多少`), no function-char bigrams (`了吗`)."""
    return [t for t in dict.fromkeys(tokens(question))
            if len(t) > 1 and t not in QUERY_STOP and not (is_cjk_bigram(t) and set(t) & FUNCTION_CHARS)]


def grounded(card: dict, page_text: str, page_terms: set[str] | None = None) -> bool:
    """A card may rank its page or answer only if its answer is faithful and its question is about the page.

    Real cards always share at least one content word with their page (447/447 on the reference vault);
    a card asking about something the page never mentions (`咖啡机除垢周期是多少`) shares none.
    """
    if not faithful(card.get("a", ""), page_text):
        return False
    if page_terms is None:
        page_terms = set(tokens(page_text))
    if not any(t in page_terms for t in question_terms(card.get("q", ""))):
        return False
    # 答案应当取自这一页：用词大多在原页。真卡最低 0.38（447 张），编出来的整句答案远低于此
    words = [t for t in tokens(card.get("a", "")) if len(t) > 1 and not (is_cjk_bigram(t) and set(t) & FUNCTION_CHARS)]
    return not words or sum(t in page_terms for t in words) / len(words) >= ANSWER_SUPPORT_MIN


def attach_answers(vault: Path, hits: list[dict], raw: list[str], df: dict[str, int]) -> None:
    """Pick the card on each hit page whose question/answer share most of the query's content words."""
    cards = load_cards(vault)
    if not cards:
        return
    weights = {t: (0.0 if is_cjk_bigram(t) and set(t) & FUNCTION_CHARS else soft_weight(t, df)) for t in raw}
    total = sum(weights.values()) or 1.0
    for h in hits:
        page = vault / h["rel"]
        options = cards.get(h["rel"])
        if not options or not page.is_file():
            continue
        page_bytes = page.read_bytes()
        current = card_hashes(page_bytes)
        page_text = page_bytes.decode("utf-8", errors="replace")
        if is_secret_page(zones.canon(vault, h["rel"]), split_frontmatter(page_text)[0]):
            continue  # 机密页不附答案（旧卡要到下次夜间才会被清掉）
        best, best_cov = None, 0.0
        page_terms: set[str] | None = None
        for card in options:
            if card.get("sha") not in current:
                continue  # 页面正文改过，旧卡作废，等夜间重写
            if page_terms is None:
                page_terms = set(tokens(page_text))
            if not grounded(card, page_text, page_terms):
                continue  # 答案里的数字/路径/命令在原文里找不到，或问题跟这页无关，不给
            have = set(tokens(card["q"] + " " + card["a"]))
            cov = sum(w for t, w in weights.items() if t in have) / total
            strong = any(t in have and w >= STRONG_W for t, w in weights.items())
            if strong and cov > best_cov:
                best, best_cov = card, cov
        if best and best_cov >= CARD_MIN:
            h["answer"] = best["a"]
            h["answer_q"] = best["q"]


def is_cjk_bigram(t: str) -> bool:
    return len(t) == 2 and all(CJK_RE.fullmatch(c) for c in t)


def term_df(con: sqlite3.Connection, terms: list[str]) -> dict[str, int]:
    uniq = sorted(set(terms))
    if not uniq:
        return {}
    marks = ",".join("?" * len(uniq))
    return dict(con.execute(f"SELECT term, doc FROM vrow WHERE term IN ({marks})", uniq).fetchall())


def wordness(bigram: str, df: dict[str, int]) -> float:
    pair = df.get(bigram, 0)
    base = min(df.get(bigram[0], 0), df.get(bigram[1], 0))
    return pair / base if base else 0.0


def best_lines(path: Path, qtok: list[str], k: int = 1) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if is_secret_page(path.name, split_frontmatter(text)[0]):
        return []  # 机密页只给路径
    lines = text.splitlines()
    scored = []
    for i, line in enumerate(lines, 1):
        lt = set(tokens(line))
        n = sum(1 for t in qtok if t in lt)
        if n:
            scored.append((n, i, redact(line.strip())[:160]))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return sorted((i, text) for _n, i, text in scored[:k])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT", ""))
    ap.add_argument("--query", default="")
    ap.add_argument("--scope", default="", help="vault-relative dir or file to restrict to")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--lines", type=int, default=1, help="best matching lines to show per hit")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()
    if not args.vault:
        print("set OBSIDIAN_VAULT", file=sys.stderr)
        return 2
    vault = Path(args.vault)
    db = cache_path(vault)
    if args.rebuild and db.exists():
        db.unlink()
    if args.stats or not args.query:
        con = connect(db)
        st = refresh(vault, con)
        tiers = dict(con.execute("SELECT tier, count(*) FROM docs GROUP BY tier").fetchall())
        built = (con.execute("SELECT v FROM meta WHERE k='built_at'").fetchone() or [""])[0]
        print(json.dumps({"cache": str(db), "built_at": built, "tiers": tiers, **st}, ensure_ascii=False))
        return 0
    res = recall(vault, args.query, args.scope, args.limit)
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
        return 0
    print(f"recall_confidence: {res.get('confidence', 'none')}")
    print(f"recall_margin: {res.get('margin', 0)}")
    print(f"recall_strong_terms: {res.get('strong', 0)}")
    if res.get("partial"):
        print(PARTIAL_NOTE)
    if not res["hits"] or res.get("confidence") == "none":
        print("recall: none (no page covers enough of the question; do not guess)")
        return 0
    print("recall:")
    for h in res["hits"]:
        flag = f" status={h['status']}" if h["status"] else ""
        print(f"- {h['rel']} tier={h['tier']}{flag} score={h['score']}")
        if h.get("answer"):
            print(f"  answer (generated): {redact(h['answer'])}")
        if h["how"]:
            print(f"  how: {h['how']}")
        for ln, text in best_lines(vault / h["rel"], res["query_tokens"], args.lines):
            print(f"  L{ln}: {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
