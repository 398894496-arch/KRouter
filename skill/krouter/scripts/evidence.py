"""段落级证据：把一页切成段落（会话按轮次），问题的词在同一段里同时出现才算对得上；问的是数量、时间、金额、
频率这类具体的东西时，那一段里要有这一类的内容。只用规则和正则，没有模型。

recall_index 在建索引时调 `blocks()` 把每页切好（存在可重建的缓存里），查询时调 `best_window()` 给候选页打分。
"""

from __future__ import annotations

import math
import re
import unicodedata

# ---------- 切段 ----------

# 说话人行：`**user:** …`、`**Caroline:** …`（冒号在粗体里，行首），`- **问**（10:02）：…`、`  **答**：…`
SPEAKER_IN = re.compile(r"^\*\*([^*\n:：]{1,40})[:：]\*\*")
SPEAKER_OUT = re.compile(r"^\s*(?:[-*+]\s+)?\*\*(问|答|Q|A|user|assistant)\*\*\s*(?:[（(][^)）\n]{0,40}[)）])?\s*[:：]", re.I)
HEADING_RE = re.compile(r"^#{1,6}\s")
BLOCK_LINES = 12   # 一段最多这么多行（长回答按段落再切）
BLOCK_CHARS = 900  # 一段最多这么多字符；单行太长的照样算一段（会话里一轮常常就是一行）
ROLE_USER = {"user", "human", "me", "我", "问", "q", "用户"}
ROLE_ASSISTANT = {"assistant", "ai", "bot", "答", "a", "助手", "claude", "codex", "cursor"}


def speakers(lines: list[str]) -> set[str]:
    """这一页的说话人：行首 `**名字:**` 出现两次以上的名字（`**Note:**` 偶尔一次不算），加上问/答这类固定写法。"""
    seen: dict[str, int] = {}
    for line in lines:
        m = SPEAKER_IN.match(line)
        if m and len(m.group(1).split()) <= 3:
            name = m.group(1).strip().lower()
            seen[name] = seen.get(name, 0) + 1
    return {n for n, c in seen.items() if c >= 2 or n in ROLE_USER or n in ROLE_ASSISTANT}


def speaker_of(line: str, names: set[str]) -> str | None:
    m = SPEAKER_IN.match(line)
    if m and m.group(1).strip().lower() in names:
        return m.group(1).strip().lower()
    m = SPEAKER_OUT.match(line)
    return m.group(1).lower() if m else None


def blocks(body: str) -> list[tuple[int, int, str, str]]:
    """[(first line, last line, text, speaker)]，行号从 0 起、相对于 `body`。新段从空行、说话人行、标题开始；
    一段超过 BLOCK_LINES 行或 BLOCK_CHARS 字符就断开。说话人沿用到下一个说话人行（会话页），没有就是空串。"""
    out: list[tuple[int, int, str, str]] = []
    cur: list[str] = []
    start = 0
    who = ""
    size = 0

    def flush(end: int) -> None:
        nonlocal cur, size
        text = "\n".join(cur).strip()
        if text:
            out.append((start, end, text, who))
        cur, size = [], 0

    lines = body.split("\n")
    names = speakers(lines)
    for i, line in enumerate(lines):
        if not line.strip():
            if cur:
                flush(i - 1)
            continue
        sp = speaker_of(line, names)
        if sp is not None or HEADING_RE.match(line) or len(cur) >= BLOCK_LINES or (cur and size + len(line) > BLOCK_CHARS):
            if cur:
                flush(i - 1)
        if sp is not None:
            who = sp
        if not cur:
            start = i
        cur.append(line)
        size += len(line)
    if cur:
        flush(len(lines) - 1)
    return out


def role(speaker: str) -> str:
    """`user` / `assistant` / 人名 / 空串。"""
    if speaker in ROLE_USER:
        return "user"
    if speaker in ROLE_ASSISTANT:
        return "assistant"
    return speaker


# ---------- 答案类型 ----------

_NUM_WORDS = ("one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
              "seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand "
              "dozen couple single double pair half first second third")
NUM_EN = r"(?:\d+(?:[.,]\d+)?|(?:" + "|".join(_NUM_WORDS.split()) + r")s?|an?|several|few)"
CN_NUM = r"[0-9零〇一二两三四五六七八九十百千万半几]+"
UNIT_EN = r"(?:second|sec|minute|min|hour|hr|day|night|week|weekend|fortnight|month|year|yr|decade|semester|season)s?"
UNIT_CN = r"(?:秒钟?|分钟|个?小时|个?钟头|天|晚|日|个?星期|周|个?月|年|季度|学期)"
MONTHS = ("january february march april may june july august september october november december "
          "jan feb mar apr jun jul aug sep sept oct nov dec").split()
DAYS = "monday tuesday wednesday thursday friday saturday sunday mondays tuesdays wednesdays thursdays fridays saturdays sundays weekend weekends".split()

TYPE_TEXT = {
    # 数量：数字、数词、中文数字
    "count": re.compile(r"\d|\b(?:" + "|".join(_NUM_WORDS.split()[:30]) + r"|dozens?|couple|several|both|single|"
                        r"twice|once|thrice|pair)\b|[零〇一二两三四五六七八九十百千万几]", re.I),
    "duration": re.compile(r"\b" + NUM_EN + r"[\s-]+(?:and a half\s+)?" + UNIT_EN + r"\b|\bsince\s+(?:\d{4}|last|"
                           + "|".join(MONTHS[:12]) + r"|i\s+was|high school|college|childhood)\b|\bfor (?:ages|years|months|weeks|"
                           r"decades|a while|a long time|the past)\b|\b(?:all|whole) (?:day|week|month|year|summer|weekend)\b|"
                           + CN_NUM + r"\s*" + UNIT_CN + r"|从.{1,12}(?:开始|起)|以来|多年", re.I),
    "date": re.compile(r"\b(?:" + "|".join(MONTHS + DAYS) + r")\b|\b(?:19|20)\d\d\b|\b\d{1,2}[/.-]\d{1,2}\b|"
                       r"\b\d{1,2}(?:st|nd|rd|th)\b|\b(?:yesterday|today|tomorrow|tonight|ago|recently|"
                       r"last (?:week|month|year|night|weekend|time|summer|winter|spring|fall|autumn)|"
                       r"next (?:week|month|year|weekend)|this (?:morning|afternoon|evening|week|month|year|weekend)|"
                       r"earlier|morning|afternoon|evening|o'clock|am|pm|\d{1,2}:\d\d)\b|"
                       r"\d+\s*[年月日号点]|[一二三四五六七八九十]+[月日号点]|周[一二三四五六日天末]|星期[一二三四五六日天]|"
                       r"昨天|今天|明天|前天|后天|上周|上个月|去年|今年|明年|下周|下个月|早上|上午|下午|晚上|刚才|前几天|最近", re.I),
    "money": re.compile(r"[$€£¥￥]\s?\d|\d\s?(?:k|K)?\s?(?:dollars?|bucks|usd|eur|euros?|pounds?|gbp|yuan|rmb|cents?|yen)\b|"
                        r"\b(?:dollars?|bucks|euros?|cents?)\b|\d+(?:\.\d+)?\s*(?:元|块|万|美元|美金|欧元|英镑|日元|人民币|刀)|"
                        r"[一二两三四五六七八九十百千万]+\s*(?:块|元|万)", re.I),
    "freq": re.compile(r"\b(?:every|each|daily|weekly|monthly|yearly|annually|nightly|once|twice|thrice|regularly|"
                       r"usually|always|often|biweekly|fortnightly)\b|\btimes? (?:a|an|per|each)\b|\bper (?:day|week|month|year)\b|"
                       r"\b(?:on|most) (?:" + "|".join(DAYS) + r")\b|\bx (?:a|per) (?:day|week)\b|"
                       r"每(?:天|日|周|个?星期|个?月|年|晚|次|隔)|[一二两三四五六七八九十几\d]+\s*次|隔天|经常|常常|定期", re.I),
}
# 年龄：一个数，或「… years old」「… 岁」
TYPE_TEXT["age"] = re.compile(r"\d|\b(?:" + "|".join(_NUM_WORDS.split()[:28]) + r")\b|岁|years? old|\bteens?\b|"
                              r"\b(?:twenties|thirties|forties|fifties)\b", re.I)
# 「多少」可能是数量、金额或时长：三类里有一类就算
TYPE_TEXT["quantity"] = re.compile("|".join(TYPE_TEXT[k].pattern for k in ("count", "money", "duration")), re.I)

QUESTION_TYPES = [
    # 顺序有讲究：先认更具体的
    ("freq", re.compile(r"\bhow (?:often|frequently)\b|\bhow many times (?:a|per|each|every)\b|多久一次|多常|频率|"
                        r"(?:每|一)(?:天|周|个?星期|个?月|年)\s*(?:几|多少)\s*次", re.I)),
    ("money", re.compile(r"\bhow much (?:money|did .{0,40}(?:cost|spend|pay|save|earn|raise|donate)|does .{0,40}cost|"
                         r"will .{0,40}(?:cost|save|spend|pay)|would .{0,40}(?:cost|save|spend|pay)|was .{0,30}(?:worth|price))|"
                         r"\bwhat (?:is|was) the (?:total )?(?:cost|price|amount|budget)\b|\bhow much .{0,30}(?:cost|spent|paid|price)\b|"
                         r"多少钱|花了多少|多少块|价格是|价钱|费用是|多少费用|多贵|预算是多少|赚了多少|省了多少", re.I)),
    ("age", re.compile(r"\bhow old\b|\bwhat age\b|多大了|几岁|多少岁|年龄", re.I)),
    ("duration", re.compile(r"\bhow long\b(?! ago)|\bhow much time\b|\bhow many (?:seconds|minutes|hours|days|nights|weeks|"
                            r"weekends|months|years|decades)\b|多久(?!一次)|多长时间|多少(?:天|年|个月|小时|分钟|周)|"
                            r"几(?:天|年|个月|个小时|小时|分钟|周|个星期)", re.I)),
    ("date", re.compile(r"^\s*when\b|\bwhen (?:did|was|is|will|do|does|were|had|have)\b|\bwhat (?:date|day|time|year|month)\b|"
                        r"\bwhich (?:date|day|year|month)\b|\bhow long ago\b|什么时候|哪天|哪一天|几号|几月|哪年|哪一年|"
                        r"何时|几点|什么日子|哪个月|日期是", re.I)),
    ("count", re.compile(r"\bhow many\b|\bnumber of\b|\bwhat (?:is|was) the (?:total )?(?:number|count)\b|"
                         r"多少(?:个|次|人|位|本|件|只|条|家|部|台|场|篇|门|种|项|首|张|辆|座|所|名|处)|几(?:个|次|人|位|本|件|只|条|家|"
                         r"部|台|场|篇|门|种|项|首|张|辆|座|所|名|处)|一共(?:有)?多少|总共(?:有)?多少", re.I)),
    ("quantity", re.compile(r"\bhow much\b|多少", re.I)),
]


def answer_type(question: str) -> str | None:
    """问题在问哪一类具体的东西：count / duration / date / money / freq / age / quantity；拿不准就是 None
    （检查不启用）。`which … first` 这种比较题、`what` / `who` / `where` 都不认：它们的答案在文字里没有固定的样子。"""
    q = unicodedata.normalize("NFKC", question or "")
    for name, rx in QUESTION_TYPES:
        if rx.search(q):
            return name
    return None


def has_type(text: str, typ: str) -> bool:
    rx = TYPE_TEXT.get(typ)
    return bool(rx and rx.search(unicodedata.normalize("NFKC", text or "")))


TAG = {"count": "c", "duration": "d", "date": "t", "money": "$", "freq": "f", "age": "a"}


def type_tags(text: str) -> str:
    """一段文字里出现了哪几类具体内容（存进索引，查询时不用再跑正则）：`c` 数量、`d` 时长、`t` 日期时间、
    `$` 金额、`f` 频率、`a` 年龄。"""
    t = unicodedata.normalize("NFKC", text or "")
    return "".join(tag for k, tag in TAG.items() if TYPE_TEXT[k].search(t))


def tags_have(tags: str, typ: str) -> bool:
    if typ == "quantity":
        return any(c in tags for c in "cd$")
    return TAG.get(typ, "?") in tags


def idf(n_docs: int, df: int) -> float:
    return math.log((n_docs - df + 0.5) / (df + 0.5) + 1)


# ---------- 索引（recall_index.refresh 调；表跟着 recall_index 的缓存一起建、一起删） ----------

SCHEMA = """
-- 每页切成的段：rid 与 docs 相同；行号从 1 起、相对于整个文件；toks 是这一段去重后的词（已脱敏）
CREATE TABLE psg(rid INTEGER, k INTEGER, l0 INTEGER, l1 INTEGER, spk TEXT, tags TEXT, toks TEXT, PRIMARY KEY(rid, k))
    WITHOUT ROWID;
-- 每页的日期（frontmatter `date:`，没有就取文件名开头的日期）和说话人
-- head：这一页标题、文件名、触发词的词（每一段都算带着它们：标题是每一段的上下文）
CREATE TABLE pinfo(rid INTEGER PRIMARY KEY, day TEXT, spk TEXT, head TEXT);
"""
DROP = "DROP TABLE IF EXISTS psg; DROP TABLE IF EXISTS pinfo;"
DAY_RE = re.compile(r"((?:19|20)\d\d)-(\d\d)-(\d\d)")


def forget(con, rid: int | None) -> None:
    if rid is not None:
        con.execute("DELETE FROM psg WHERE rid=?", (rid,))
        con.execute("DELETE FROM pinfo WHERE rid=?", (rid,))


def page_day(rel: str, meta: dict) -> str:
    for key in ("date", "day", "created", "日期"):
        m = DAY_RE.search(str(meta.get(key) or ""))
        if m:
            return "-".join(m.groups())
    m = DAY_RE.search(rel.rsplit("/", 1)[-1])
    return "-".join(m.groups()) if m else ""


def index_page(con, tokens, rid: int, rel: str, text: str, meta: dict, body: str, head: str = "") -> None:
    """一页的段落、日期和说话人。`text` 是整页（已脱敏、LF 换行），`body` 是 frontmatter 之后的正文，`head` 是
    标题、文件名和触发词。"""
    offset = text[: max(0, len(text) - len(body))].count("\n") if text.endswith(body) else 0
    rows, who = [], set()
    for k, (l0, l1, chunk, spk) in enumerate(blocks(body)):
        toks = " ".join(dict.fromkeys(tokens(chunk)))
        if not toks:
            continue
        if spk:
            who.add(spk)
        rows.append((rid, k, l0 + offset + 1, l1 + offset + 1, spk, type_tags(chunk), toks))
    con.executemany("INSERT INTO psg VALUES(?,?,?,?,?,?,?)", rows)
    con.execute("INSERT OR REPLACE INTO pinfo VALUES(?,?,?,?)", (rid, page_day(rel, meta), " ".join(sorted(who)),
                                                                   " ".join(dict.fromkeys(tokens(head)))))


# ---------- 查询：候选页的段落证据 ----------

FIRST_PERSON = re.compile(r"\b(?:i|my|me|mine|myself|i'm|i've|i'd|i'll)\b|我", re.I)
# 问的是助手说过的话（`what did you recommend`、`你上次说`）：不按「你自己说的」绑
SECOND_PERSON = re.compile(r"\b(?:you|your|yours|you've|you'd|you're)\b|你|您", re.I)
STEM_FORMS = 30  # 一个拉丁词按词干最多认这么多个库里的变形（`migrate` ~ `migration`）


def term_forms(con, ri, terms: list[str]) -> dict[str, set[str]]:
    """每个问题词在库里的写法：本身、单复数，5 个字母以上的拉丁词再加库里同词干的词。"""
    out = {}
    for t in terms:
        forms = {t}
        if not ri.is_cjk_bigram(t):
            forms.update(ri.latin_forms(t))
            if len(t) >= 5:
                stem = t[: max(4, len(t) - 2)]
                forms.update(w for (w,) in con.execute(
                    "SELECT term FROM vrow WHERE term >= ? AND term < ? LIMIT ?", (stem, stem + "￿", STEM_FORMS)))
        out[t] = forms
    return out


def question_plan(con, ri, query: str, n_docs: int, qtok: list[str] | None = None) -> dict | None:
    """问题里参与段落比对的词和它们的分量（idf × 像不像词），答案类型，点名的人，是不是在问「我自己」。
    `qtok`：召回自己认作实词的那些词（中文只留像词的双字，跨词的碎片不算）；没给就从问题里取。"""
    raw = [t for t in (qtok if qtok is not None else ri.question_raw(query)) if not t.isdigit()]
    raw = [t for t in raw if not ri.is_cjk_bigram(t) or not set(t) & ri.FUNCTION_CHARS]
    if not raw:
        return None
    forms = term_forms(con, ri, raw)
    df = ri.term_df(con, sorted({f for fs in forms.values() for f in fs}) + [c for t in raw if ri.is_cjk_bigram(t) for c in t])
    weight = {}
    for t in raw:
        d = max(df.get(f, 0) for f in forms[t])
        if d <= 0:
            continue
        w = idf(n_docs, d)
        if ri.is_cjk_bigram(t):
            w *= ri.soft_weight(t, df)
        weight[t] = w
    if not weight:
        return None
    names = [t for t in ri.named_words(query) if t in weight or any(f in df for f in forms.get(t, ()))]
    nums = [n for n in dict.fromkeys(QNUM.findall(unicodedata.normalize("NFKC", query or ""))) if n.isdigit() and len(n) >= 2]
    return {"weight": weight, "forms": {t: forms[t] for t in weight}, "type": answer_type(query), "names": names,
            "first": bool(FIRST_PERSON.search(query)) and not SECOND_PERSON.search(query), "nums": nums}


QNUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])|\d+(?=-)")


def page_evidence(con, plan: dict, rids: list[int]) -> dict[int, dict]:
    """每个候选页最好的一段（一段，或相邻两段合成的窗口）：

    - `pc`：这一段覆盖了问题实词分量的几成（同一段里同时出现才算；散在页面各处的不算）；`l0` / `l1`：它在文件里的行号；
    - `rare_in`：问题里分量最重的词在不在这一段里；`num_ok`：问题里写的数（`30-gallon` 的 30）在不在这一段里；
    - `type_ok`：问题问的是数量、时长、日期、金额、频率、年龄时，覆盖最好的那些段里有没有这一类内容（None：不检查）；
    - `bind`：问题点名了这一页的某个说话人（或问的是「我」、页上有 user / assistant 的轮次），只看那个人自己说的段时
      的覆盖；`bind_other`：同一口径下别的说话人的最好覆盖；`type_bound`：那个人覆盖最好的那段里有没有这一类内容。"""
    if not rids:
        return {}
    weight, forms = plan["weight"], plan["forms"]
    total = sum(weight.values()) or 1.0
    names = set(plan["names"])
    typ = plan["type"]
    rare = max(weight, key=lambda t: (weight[t], t))
    nums = plan.get("nums") or []
    marks = ",".join("?" * len(rids))
    info = {rid: (day, set(spk.split()), set(head.split())) for rid, day, spk, head in
            con.execute(f"SELECT rid, day, spk, head FROM pinfo WHERE rid IN ({marks})", rids)}
    rows: dict[int, list] = {}
    for rid, k, l0, l1, spk, tags, toks in con.execute(
            f"SELECT rid, k, l0, l1, spk, tags, toks FROM psg WHERE rid IN ({marks}) ORDER BY rid, k", rids):
        ts = set(toks.split())
        hit = frozenset(t for t, fs in forms.items() if not fs.isdisjoint(ts))
        nhit = frozenset(n for n in nums if n in ts)
        rows.setdefault(rid, []).append((l0, l1, spk, tags, hit, nhit))
    out = {}
    for rid in rids:
        day, who, head = info.get(rid, ("", set(), set()))
        top_hit = frozenset(t for t, fs in forms.items() if not fs.isdisjoint(head))
        bl = [(l0, l1, spk, tags, hit | top_hit, nhit) for l0, l1, spk, tags, hit, nhit in rows.get(rid, [])]
        if not bl and top_hit:
            bl = [(0, 0, "", "", top_hit, frozenset())]
        best = (0.0, 0, 0, frozenset(), frozenset())
        cover = []
        for i, (l0, l1, spk, tags, hit, nhit) in enumerate(bl):
            for j in (i, i + 1):
                if j >= len(bl):
                    continue
                h = hit | bl[j][4] if j != i else hit
                c = sum(weight[t] for t in h) / total
                cover.append((c, i, j))
                if c > best[0]:
                    best = (c, bl[i][0], bl[j][1], h, nhit | bl[j][5] if j != i else nhit)
        ev = {"pc": round(best[0], 4), "l0": best[1], "l1": best[2], "day": day, "rare_in": rare in best[3]}
        if nums:
            ev["num_ok"] = len(best[4]) == len(set(nums))
        if typ:
            if typ == "date" and day:
                ev["type_ok"] = True  # 会话页自带日期：日期本身就是答案的一部分
            else:
                top = [w for w in cover if w[0] >= best[0] - 1e-9 and best[0] > 0]
                ev["type_ok"] = any(tags_have(bl[i][3] + bl[j][3], typ) for _c, i, j in top)
        # 说话人绑定：问的是谁，就看谁自己说的话
        named = {n for n in names if n in who}
        bound = named or ({"user", "问", "q"} if plan["first"] and who & {"user", "问", "q"} else None)
        content = {t: w for t, w in weight.items() if t not in named}
        ctotal = sum(content.values())
        if bound and ctotal > 0:
            mine = other = 0.0
            mine_tags = []
            for l0, l1, spk, tags, hit, _n in bl:
                c = sum(content.get(t, 0.0) for t in hit - top_hit) / ctotal
                if spk in bound:
                    if c > mine + 1e-9:
                        mine, mine_tags = c, [tags]
                    elif c > 0 and abs(c - mine) <= 1e-9:
                        mine_tags.append(tags)
                elif spk:
                    other = max(other, c)
            ev["bind"] = round(mine, 4)
            ev["bind_other"] = round(other, 4)
            if typ and not (typ == "date" and day):
                ev["type_bound"] = any(tags_have(t, typ) for t in mine_tags)
        out[rid] = ev
    return out


# ---------- 时间线索 ----------

import datetime as _dt  # noqa: E402

MONTH_NUM = {m: i + 1 for i, m in enumerate("january february march april may june july august september october "
                                            "november december".split())}
MONTH_NUM.update({m[:3]: n for m, n in list(MONTH_NUM.items())})
MONTH_NUM["sept"] = 9
WEEKDAY = {d: i for i, d in enumerate("monday tuesday wednesday thursday friday saturday sunday".split())}
CN_DIGIT = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
EN_COUNT = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve".split())}
EN_COUNT.update({"a": 1, "an": 1, "couple": 2, "few": 3, "several": 3})
UNIT_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365, "天": 1, "日": 1, "周": 7, "星期": 7, "月": 30, "年": 365}
CN_WEEKDAY = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}


def _cn_int(s: str) -> int | None:
    if s.isdigit():
        return int(s)
    if not s or any(c not in CN_DIGIT and c != "十" for c in s):
        return None
    if "十" in s:
        a, _, b = s.partition("十")
        return (CN_DIGIT.get(a, 1) if a else 1) * 10 + (CN_DIGIT.get(b, 0) if b else 0)
    return CN_DIGIT.get(s)


def today(default: _dt.date | None = None) -> _dt.date:
    """今天（评测时用 `KROUTER_TODAY=YYYY-MM-DD` 指定问题提问的那一天）。"""
    import os

    raw = os.environ.get("KROUTER_TODAY") or ""
    m = DAY_RE.search(raw)
    if m:
        try:
            return _dt.date(*map(int, m.groups()))
        except ValueError:
            pass
    return default or _dt.date.today()


def _month_range(y: int, m: int) -> tuple[_dt.date, _dt.date]:
    start = _dt.date(y, m, 1)
    nxt = _dt.date(y + (m == 12), m % 12 + 1, 1)
    return start, nxt - _dt.timedelta(days=1)


def time_window(question: str, now: _dt.date) -> tuple[_dt.date, _dt.date] | None:
    """问题里的时间线索对应的日期范围（含两端）；没有线索、或线索说不清是哪段时间就是 None。

    认：`2023-05-20`、`May 20(, 2023)`、`in May (2023)`、`5月20日`、`2023年5月`、`yesterday` / `昨天`、
    `last Saturday` / `上周六`、`last week` / `上周`、`last month` / `上个月`、`this week` / `这周`、
    `N days / weeks / months ago` / `N天前`、`in the past / last N days / weeks / months` / `最近N天`、`last year` / `去年`。"""
    q = unicodedata.normalize("NFKC", question or "").lower()
    d = _dt.timedelta
    m = DAY_RE.search(q)
    if m:
        try:
            day = _dt.date(*map(int, m.groups()))
            return day, day
        except ValueError:
            return None
    m = re.search(r"(?:(\d{4})\s*年\s*)?(\d{1,2}|[一二三四五六七八九十]{1,3})\s*月(?:\s*(\d{1,2}|[一二三四五六七八九十]{1,3})\s*[日号])?", q)
    if m:
        mon = _cn_int(m.group(2))
        if mon and 1 <= mon <= 12:
            y = int(m.group(1)) if m.group(1) else (now.year if mon <= now.month else now.year - 1)
            if m.group(3):
                dd = _cn_int(m.group(3))
                try:
                    day = _dt.date(y, mon, dd)
                    return day - d(1), day + d(1)
                except (TypeError, ValueError):
                    return None
            return _month_range(y, mon)
    months = "|".join(sorted(MONTH_NUM, key=len, reverse=True))
    m = re.search(rf"\b({months})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s*(\d{{4}}))?|\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({months})\b(?:,?\s*(\d{{4}}))?", q)
    if m:
        mon = MONTH_NUM[m.group(1) or m.group(5)]
        dd = int(m.group(2) or m.group(4))
        yr = m.group(3) or m.group(6)
        y = int(yr) if yr else (now.year if (mon, dd) <= (now.month, now.day) else now.year - 1)
        try:
            day = _dt.date(y, mon, dd)
            return day - d(1), day + d(1)
        except ValueError:
            return None
    m = re.search(rf"\b({months})\.?\s+(?:to|and|through|until|till|-)\s+({months})\b", q)
    if m and "may" not in (m.group(1), m.group(2)) or m and re.search(r"\b(?:from|between|in)\s+" + m.group(1), q):
        a, b = MONTH_NUM[m.group(1)], MONTH_NUM[m.group(2)]
        yb = now.year if b <= now.month else now.year - 1
        ya = yb if a <= b else yb - 1
        return _month_range(ya, a)[0], _month_range(yb, b)[1]
    m = re.search(rf"\b(?:in|during|since|of|from|last)\s+({months})\b(?:\s+(\d{{4}}))?", q)
    if m and m.group(1) != "may" or m and m.group(2):
        mon = MONTH_NUM[m.group(1)]
        y = int(m.group(2)) if m.group(2) else (now.year if mon <= now.month else now.year - 1)
        return _month_range(y, mon)
    if re.search(r"\byesterday\b|昨天", q):
        return now - d(1), now - d(1)
    if re.search(r"前天", q):
        return now - d(2), now - d(2)
    m = re.search(r"\b(last|this|past)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|(上|这|本)(?:个)?(?:周|星期)([一二三四五六日天])", q)
    if m:
        wd = WEEKDAY[m.group(2)] if m.group(2) else CN_WEEKDAY[m.group(4)]
        back = (now.weekday() - wd) % 7 or 7
        day = now - d(back)
        if (m.group(1) == "this" or m.group(3) in ("这", "本")) and back > now.weekday():
            day = now + d((wd - now.weekday()) % 7)
        return day - d(1), day + d(1)
    m = re.search(r"\b(\d+|" + "|".join(EN_COUNT) + r")\s+(day|week|month|year)s?\s+ago\b|(\d+|[一二两三四五六七八九十]+)\s*(?:个)?(天|周|星期|月|年)(?:以)?前", q)
    if m:
        n = int(m.group(1)) if (m.group(1) or "").isdigit() else EN_COUNT.get(m.group(1) or "") if m.group(1) else _cn_int(m.group(3))
        unit = UNIT_DAYS[m.group(2) or m.group(4)]
        if n:
            center = now - d(n * unit)
            slack = d(max(2, n * unit // 4))
            return center - slack, min(now, center + slack)
    m = re.search(r"\b(?:in\s+|over\s+|during\s+)?the\s+(?:past|last)\s+(\d+|" + "|".join(EN_COUNT) + r")?\s*(day|week|month|year)s?\b|"
                  r"(?:最近|过去|近)\s*(\d+|[一二两三四五六七八九十]+)?\s*(?:个)?(天|周|星期|月|年)", q)
    if m:
        raw_n = m.group(1) or m.group(3)
        n = (int(raw_n) if raw_n.isdigit() else EN_COUNT.get(raw_n) or _cn_int(raw_n)) if raw_n else 1
        unit = UNIT_DAYS[m.group(2) or m.group(4)]
        if n:
            return now - d(n * unit), now
    if re.search(r"\blast week\b|上周|上个星期|上星期", q):
        start = now - d(now.weekday() + 7)
        return start, start + d(6)
    if re.search(r"\bthis week\b|这周|本周|这个星期", q):
        return now - d(now.weekday()), now
    if re.search(r"\blast month\b|上个月|上月", q):
        y, mon = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
        return _month_range(y, mon)
    if re.search(r"\bthis month\b|这个月|本月", q):
        return _dt.date(now.year, now.month, 1), now
    if re.search(r"\blast year\b|去年", q):
        return _dt.date(now.year - 1, 1, 1), _dt.date(now.year - 1, 12, 31)
    if re.search(r"\bthis year\b|今年", q):
        return _dt.date(now.year, 1, 1), now
    return None


# ---------- 加总题、列举题 ----------

AGGREGATE = re.compile(r"\bhow many (?:times|different|total|kinds|types)\b|\bin total\b|\btotal (?:number|amount|cost|"
                       r"of|time|distance)\b|\baltogether\b|\bcombined\b|\ball (?:the|of the|my)\b|\blist\b|"
                       r"\bwhat are (?:all|the)\b|\bwhich .{0,40}\bhave i\b|\bhow many\b.{0,60}\b(?:did i|have i|do i)\b|"
                       r"一共|总共|合计|加起来|总计|都有哪些|有哪些|哪几|列出|所有的|几次|多少次", re.I)


def aggregate(question: str) -> bool:
    """加总题、列举题：答案散在好几页里（`how many times`、`in total`、`都有哪些`）。"""
    return bool(AGGREGATE.search(unicodedata.normalize("NFKC", question or "")))


# ---------- 用段落证据重排、补一道拒答（参数在第 39 套开发数据上定） ----------

EV_EPS = 0.3        # 重排：页分 × (EV_EPS + 最好一段的覆盖)^EV_BETA
EV_BETA = 1.0
TIME_BOOST = 1.0    # 问题里有时间线索时，日期落在那段时间里的页 ×(1 + TIME_BOOST)
VETO_PC = 0.25      # 重排后首条最好的一段覆盖不到这么多：记忆里没有（None：不启用）
VETO_BIND = 0.4     # 问的是某个说话人（或「我」）：前三页里那个人自己说的话，覆盖不到别人说的话的这么多倍：没有
RESCUE_PC = None    # 门槛拒了、但首条有一段完整覆盖、而且是被问的那个人自己说的：照样交出去（None：不启用）
RESCUE_BIND = 0.9


def rank_key(h: dict, window=None) -> float:
    ev = h.get("ev") or {}
    s = h["score"] * (EV_EPS + ev.get("pc", 0.0)) ** EV_BETA
    if window and TIME_BOOST and ev.get("day") and window[0].isoformat() <= ev["day"] <= window[1].isoformat():
        s *= 1 + TIME_BOOST
    return s


def rerank(hits: list[dict], n: int, window=None) -> list[dict]:
    """前 n 页按段落证据重排（其余照旧排在后面）。没有证据的页（ev 为空）按覆盖 0 算。"""
    head = sorted(hits[:n], key=lambda h: -rank_key(h, window))
    return head + hits[n:]


def _bind(top: list[dict]) -> tuple[float | None, float | None]:
    evs = [h.get("ev") or {} for h in top]
    bs = [e for e in evs if e.get("bind") is not None]
    if not bs:
        return None, None
    return max(e["bind"] for e in bs), max(e["bind_other"] for e in bs)


def veto(top: list[dict]) -> str:
    """Why the paragraph evidence says the memory does not hold this (``: it may)."""
    if not top:
        return ""
    if VETO_PC is not None and (top[0].get("ev") or {}).get("pc", 0.0) < VETO_PC:
        return "no-paragraph"
    mine, other = _bind(top)
    if VETO_BIND is not None and mine is not None and mine < VETO_BIND * other:
        return "other-speaker"
    return ""


def rescue(top: list[dict]) -> bool:
    if RESCUE_PC is None or not top:
        return False
    mine, other = _bind(top)
    return ((top[0].get("ev") or {}).get("pc", 0.0) >= RESCUE_PC and mine is not None and mine >= RESCUE_BIND
            and mine >= other)
