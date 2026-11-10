#!/usr/bin/env python3
"""Experience cards: a lesson from one task, offered as a suggestion on another task in the same situation.

A fact page answers "what was decided about X". An experience card keeps something else: in situation S, doing D gave
R, and the lesson without the subject ("the stew tasted flat; a spoonful of sugar fixed it" → "when something is
flat as a whole, add a little of the opposite"). Cards are plain Markdown pages in `02 经验与方法/经验卡/`, one per
lesson, which a person can read, fix or delete:

    ---
    title: "经验｜整体发平、没有层次时，加一点点反差的东西"
    type: experience-card
    status: provisional
    when: 发平; 平淡; 没有层次; 寡淡; 缺点什么
    source_ref: "[[05 时间日志/会话摘录/2026-01-01｜…]]"
    ---
    - 处境：… - 做法：… - 结果：… - 通用说法：… - 适用于：… - 出处：…

**Writing.** Two ways, neither needs a key. The agent that ran the session writes the card itself: `krouter_learn`
over MCP, or `experience.py learn` (JSON on stdin) for a host without MCP; `learn()` checks it and writes it. And,
with `KROUTER_EXPERIENCE=1`, `extract()` runs where a session is distilled (`import_sessions.py`): one more call through
`llm.py` (a key, or the host's own CLI on the user's login) asks for at most two cards. A card is kept when its fields
are filled, nothing in it looks like a key, its situation and action share words with the excerpt (model-lane cards
only), `when` phrases, if any are given (no longer asked for), are kept only when they do not name the subject, and no
card with the same lesson is on file. With no model lane
(`llm.NoModel`) the model step does nothing and says nothing.

**Use records.** When sessions are imported (every turn, no model call), an answer that cites a card id in brackets
(〔C08〕, [C08]) records `offered`; the next question records `adopted` only when it says the lesson was followed or
worked (ADOPT) and does not turn it down (REJECT), and either the answer cited that card alone or the question names
it; anything unclear stays `offered`. Records go to USES (one JSON line each, never written twice). The digest lists
adopted cards first (most recent adoption first), then the rest by times offered and date; a card offered
IGNORED_AFTER times and never adopted sinks to the bottom.

**Suggesting.** Nothing is matched. At session start the hook (`session_hook.py start`) gives the host model the whole
digest (`digest()`): every card as one subject-free line "situation → what to do〔id〕", at most DIGEST_MAX_LINES (most
recently adopted first, then confirmed, then newest), and one line on how to use it: offer at most two, worded as
lessons from another task with their id, only when the task's situation is the same, and say nothing otherwise. The
host model, which reads the task anyway, judges the situation; one situation in other words shares no words, so a
retriever cannot (set 13). Cards never appear among recalled facts. `suggest()` (the lexical matcher of set 13) is
kept only to reproduce that set; nothing calls it.

**Switch.** On by default (DEFAULT_ON, since set 23 passed): the digest when the vault has cards, the use records,
and `krouter_learn`. `KROUTER_EXPERIENCE=0` turns all of it off; `KROUTER_EXPERIENCE=1` also turns on the model-lane
extraction at distill time, which spends a call per session-day and stays off otherwise.
Measured: sets 13, 15, 16, 17, 19, 20, 21, 23 in `bench/memory_honesty/HELDOUT.md`; numbers in `docs/EXPERIENCE.md`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import recall_index as ri  # noqa: E402
import zones  # noqa: E402
from krouter_redact import redact  # noqa: E402

FOLDER = ri.EXPERIENCE_DIR  # 02 经验与方法/经验卡
TYPE = "experience-card"
MAX_SUGGESTIONS = 2
# 安静门槛（只在开发集上定，见 bench/transfer/run.py）：一条触发语的词要被当前任务覆盖这么多，且至少对上这么多个词
MIN_COVER = 0.6
MIN_WORDS = 2
GENERIC_WEIGHT = 0.5  # 词表前 1000 的常用词（之后、以前、问题）分量减半
FIELDS = ("处境", "做法", "结果", "通用说法", "适用于", "出处")
SPLIT = re.compile(r"[;；,，、/|]")


DEFAULT_ON = True  # 第 23 套过线（2026-11-10）：库里有经验卡时摘要、使用记录、krouter_learn 默认开；KROUTER_EXPERIENCE=0 总是关


def _flag() -> str:
    return os.environ.get("KROUTER_EXPERIENCE", "").strip().lower()


def enabled() -> bool:
    """The model-lane extraction at distill time: one more model call per session-day, so only on request."""
    return _flag() == "1"


def digest_on() -> bool:
    """The digest at session start, the use records and `krouter_learn`: on by default when DEFAULT_ON, else only with
    `KROUTER_EXPERIENCE=1`; `KROUTER_EXPERIENCE=0` always off. With no cards the digest prints nothing anyway."""
    flag = _flag()
    if flag in ("0", "off", "false", "no"):
        return False
    return flag == "1" or DEFAULT_ON


# ---------- 读卡 ----------

EN_FIELDS = {"situation": "处境", "action": "做法", "result": "结果", "lesson": "通用说法", "when": "适用于",
             "source": "出处"}
FIELD_RE = re.compile(r"^\s*[-*]\s*(处境|做法|结果|通用说法|适用于|出处|Situation|Action|Result|Lesson|When|Source)"
                      r"\s*[:：]\s*(.+)$", re.I)


def _fields(body: str) -> dict[str, str]:
    """The card's fields under their Chinese names, whether the page writes `- 处境：` or `- Situation:`."""
    out = {}
    for line in body.splitlines():
        m = FIELD_RE.match(line)
        if m:
            key = EN_FIELDS.get(m.group(1).lower(), m.group(1))
            out.setdefault(key, m.group(2).strip())
    return out


def load_cards(vault: Path) -> list[dict]:
    """Every live card in the folder: [{rel, title, when: [phrase], lesson, source, …}]."""
    folder = zones.path(vault, FOLDER)
    if not folder.is_dir():
        return []
    cards = []
    for page in sorted(folder.glob("*.md")):
        try:
            text = page.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, body = ri.split_frontmatter(text)
        if meta.get("type") != TYPE or (meta.get("status") or "").lower() in ri.DEAD_STATUS:
            continue
        f = _fields(body)
        when = [p.strip() for p in SPLIT.split(meta.get("when") or f.get("适用于", "")) if p.strip()]
        lesson = f.get("通用说法", "")
        cards.append({
            "rel": str(page.relative_to(vault)).replace(os.sep, "/"),
            "title": (meta.get("title") or page.stem).removeprefix("经验｜").removeprefix("Lesson: "),
            "when": when,
            "lesson": lesson,
            "condition": condition(lesson),
            "source": meta.get("source_ref") or f.get("出处", ""),
            "status": (meta.get("status") or "").lower(),
            "id": meta.get("card_id") or "E" + hashlib.sha1(page.name.encode("utf-8")).hexdigest()[:4],
            "date": meta.get("date") or "",
            "adopted_at": meta.get("adopted_at") or "",
        })
    return cards


def condition(lesson: str) -> str:
    """The "when" half of a lesson: "改了东西却没有效果时，先确认…" → "改了东西却没有效果"."""
    m = re.match(r"^(.{2,40}?)(时|的时候|之前|以后)[，,]", lesson)
    return m.group(1) if m else ""


# ---------- 经验摘要（会话开始时整份交给宿主模型，由它判断处境像不像） ----------

DIGEST_MAX_LINES = 30
IGNORED_AFTER = 3  # 提过这么多次、一次都没被采纳：排到最后
HEAD = {
    "zh": ("KRouter 经验摘要：别的任务里攒下的经验，不是这个项目的事实，也不保证对。每行是「处境 → 做法〔编号〕」，"
           "卡片在「{folder}」，编号就是卡里的 card_id 或文件名。"),
    "en": ("KRouter experience digest: lessons collected on other tasks; not facts about this project, and not "
           "guaranteed right. Each line is \"When <situation>, <what to do> [id]\"; the cards are in \"{folder}\", and the id "
           "is the card's card_id or file name."),
}
USE = {
    "zh": ("用法：只有当用户这次要做的事和某一行的处境确实相同（不是只沾到同一个词或同一个题材）时，才在回复里顺带提一句"
           "「别的任务里的经验，可以试试：……〔编号〕」，最多两条；没有处境相同的，就一个字都不要提，也不要说没有相关经验。"),
    "en": ("How to use: only when what the user is doing now is genuinely the same situation as one line (not merely a "
           "shared word or the same subject), mention it in passing in your reply: \"A lesson from another task you "
           "could try: … [id]\", at most two. If none is the same situation, say nothing about them at all, and do "
           "not say that there are none."),
}
MORE = {"zh": "（还有 {n} 张没列出：按最近采纳、被提出的次数、日期只列前 {k} 张）",
        "en": "({n} more not listed: only the first {k}, by most recently adopted, times offered, then date)"}
DIGEST_HEAD, DIGEST_USE = HEAD["zh"], USE["zh"]  # 兼容旧名


def lang_of(cards: list[dict]) -> str:
    """English when most cards' lessons have no Chinese in them."""
    en = sum(1 for c in cards if not ri.CJK_RE.search(c["lesson"] or c["title"]))
    return "en" if en * 2 > len(cards) else "zh"


def digest_line(card: dict, lang: str = "zh") -> str:
    """One card as "situation → what to do〔id〕", subject-free (the lesson, split at its "…时，" / "When …,")."""
    lesson = re.sub(r"\s+", " ", card["lesson"] or card["title"]).strip().rstrip("。.")
    if lang != "zh":
        return f"- {lesson} [{card['id']}]"  # 英文本来就写成 "When …, …"；里面的逗号不止一个，不拆
    m = re.match(r"^(.{2,60}?)(?:时|的时候)[，,]\s*(.+)$", lesson)
    body = f"{m.group(1)} → {m.group(2)}" if m else lesson
    return f"- {body}〔{card['id']}〕"


def rank_key(card: dict, used: dict) -> tuple:
    """Adopted or seen again cards first, the most recent first; then cards not yet passed over (offered IGNORED_AFTER
    times and never adopted sink to the bottom); then times offered; then confirmed; then the newest date."""
    u = used.get(card["id"], {})
    # 被采纳、或在别的会话里又遇到一次（宿主判定"摘要里已有这条"）：都是这条经验站得住的证据
    adopted = max(u.get("last_adopted", ""), u.get("last_again", ""), card.get("adopted_at", ""))
    passed_over = not adopted and u.get("offered", 0) >= IGNORED_AFTER
    fresh = max(card.get("date", ""), u.get("last_offered", "")[:10])
    return (bool(adopted), adopted, not passed_over, u.get("offered", 0), card.get("status") == "active", fresh,
            card["rel"])


def ranked(cards: list[dict], used: dict | None = None) -> list[dict]:
    return sorted(cards, key=lambda c: rank_key(c, used or {}), reverse=True)


def digest(vault: Path, max_lines: int = DIGEST_MAX_LINES, cards: list[dict] | None = None,
           used: dict | None = None) -> str:
    """The whole experience digest the session-start hook gives the host model; "" when there are no cards."""
    cards = load_cards(vault) if cards is None else cards
    if not cards:
        return ""
    lang = lang_of(cards)
    shown = ranked(cards, usage(vault) if used is None else used)[:max_lines]
    out = [HEAD[lang].format(folder=zones.real(vault, FOLDER))] + [digest_line(c, lang) for c in shown]
    if len(cards) > len(shown):
        out.append(MORE[lang].format(n=len(cards) - len(shown), k=max_lines))
    out.append(USE[lang])
    return redact("\n".join(out))


# ---------- 使用记录：经验被提出、被采纳（会话导入时从记录里读，不调模型） ----------

USES = "90 系统文件/自动化/经验卡使用记录.jsonl"
# 采纳的判据要保守：提出经验的那一轮之后，下一句话明说照做了、或说管用了。拿不准的只记"被提出"
ADOPT = re.compile(r"(就?(按|照)(你说的|这个|这条|这样|你的)|就这么(做|办|来|改)|试了.{0,12}(好了|可以了|行了|管用|有用|解决)|"
                   r"果然|确实是这个|管用|有用|这招|学到了|"
                   r"\b(that|it) worked\b|\bgood (idea|call|tip|catch)\b|\blet'?s (try|do) (that|it|this)\b|"
                   r"\btried (it|that|this)\b.{0,30}\b(works?|worked|fixed|helped)\b|\bthat fixed it\b|\byou were right\b)",
                   re.I)
REJECT = re.compile(r"(不用|不对|没用|不行|不管用|算了|不是这个|不相关|没关系|别提|"
                    r"\b(didn'?t|doesn'?t|does not|did not) (work|help|apply)\b|\bnot (it|that|relevant)\b|\bnope\b|"
                    r"\bno thanks\b|\birrelevant\b)", re.I)


def cited(text: str, ids: set[str]) -> list[str]:
    """Card ids the text cites in brackets (〔C08〕, [C08], (C08)), in order, each once."""
    out = []
    for m in re.finditer(r"[〔\[（(]\s*([A-Za-z][A-Za-z0-9]{1,11})\s*[〕\]）)]", text or ""):
        if m.group(1) in ids and m.group(1) not in out:
            out.append(m.group(1))
    return out


def uses_in(turns: list[dict], ids: set[str]) -> list[dict]:
    """Use events in one session's turns: `offered` for every card an answer cites; `adopted` for the card when the
    next question says it was followed or worked (ADOPT) and does not turn it down (REJECT), and either that answer
    cited only that card or the question names it."""
    out = []
    for i, t in enumerate(turns):
        got = cited(t.get("answer", ""), ids)
        for cid in got:
            out.append({"card": cid, "kind": "offered", "turn": t.get("ts", ""), "why": "回复里带了编号"})
        nxt = turns[i + 1]["ask"] if i + 1 < len(turns) else ""
        if not got or not nxt:
            continue
        named = cited(nxt, ids) or [c for c in got if re.search(rf"(?<![A-Za-z0-9]){c}(?![A-Za-z0-9])", nxt)]
        target = named[:1] or (got if len(got) == 1 else [])
        cue = ADOPT.search(nxt)
        if target and cue and not REJECT.search(nxt):
            out.append({"card": target[0], "kind": "adopted", "turn": t.get("ts", ""),
                        "why": f"下一句说「{cue.group(0)[:20]}」"})
    return out


def record_uses(vault: Path, session: str, turns: list[dict]) -> int:
    """Append this session's use events not yet on file (key: kind, card, session, turn). Returns how many."""
    cards = load_cards(vault)
    if not cards:
        return 0
    events = uses_in(turns, {c["id"] for c in cards})
    if not events:
        return 0
    path = zones.path(vault, USES)
    have = set()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            have.add((d.get("kind"), d.get("card"), d.get("session"), d.get("turn")))
    new = [{**ev, "session": session} for ev in events if (ev["kind"], ev["card"], session, ev["turn"]) not in have]
    if new:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for ev in new:
                fh.write(json.dumps({"at": ev["turn"][:19] or date.today().isoformat(), **ev}, ensure_ascii=False) + "\n")
    return len(new)


def usage(vault: Path) -> dict:
    """{card id: {offered, adopted, again, last_offered, last_adopted, last_again}} from the use records."""
    path = zones.path(vault, USES)
    out: dict[str, dict] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        u = out.setdefault(str(d.get("card")), {"offered": 0, "adopted": 0, "again": 0, "last_offered": "",
                                                "last_adopted": "", "last_again": ""})
        kind = d.get("kind")
        if kind in ("offered", "adopted", "again"):
            u[kind] += 1
            u["last_" + kind] = max(u["last_" + kind], str(d.get("at") or "")[:10])
    return out


def token_estimate(text: str) -> int:
    """An upper-end estimate with no tokenizer download: one token per CJK character, one per three other
    characters. Real tokenizers usually come in lower on Chinese."""
    cjk = sum(len(r) for r in ri.CJK_RE.findall(text))
    return cjk + (len(text) - cjk + 2) // 3


# ---------- 词法匹配（Set 13：留出集 0/14，没有接进任何通路，只留着复现） ----------

def words(text: str) -> dict[str, float]:
    """{word: weight} of a phrase: latin words, and CJK bigrams that are words in the bundled list (the generic
    thousand at half weight). Function bigrams (`什么`, `一下`) never count."""
    content, generic = ri.lexicon()
    out: dict[str, float] = {}
    for t in ri.tokens(text):
        if t in ri.QUERY_STOP or t in ri.EN_FUNCTION:
            continue
        if ri.is_cjk_bigram(t):
            if set(t) & ri.FUNCTION_CHARS and t not in content:
                continue
            if t in content:
                out[t] = 1.0
            elif t in generic:
                out[t] = GENERIC_WEIGHT
        elif len(t) >= 2 and not t.isdigit():
            out[t] = 1.0
    return out


def phrase_score(phrase: str, query_words: dict[str, float]) -> tuple[float, int]:
    """(share of the phrase's word weight the query covers, how many of its words it has)."""
    pw = words(phrase)
    if not pw:
        return 0.0, 0
    hit = [t for t in pw if t in query_words]
    return sum(pw[t] for t in hit) / sum(pw.values()), len(hit)


def suggest(vault: Path, query: str, limit: int = MAX_SUGGESTIONS, min_cover: float = MIN_COVER,
            min_words: int = MIN_WORDS, cards: list[dict] | None = None) -> list[dict]:
    """Cards whose situation the query reads like, best first, at most `limit`; [] when none clears the threshold."""
    cards = load_cards(vault) if cards is None else cards
    qw = words(query)
    if not cards or not qw:
        return []
    found = []
    for c in cards:
        best = (0.0, 0, "")
        for phrase in c["when"] + ([c["condition"]] if c["condition"] else []):
            cover, n = phrase_score(phrase, qw)
            if (cover, n) > best[:2]:
                best = (cover, n, phrase)
        cover, n, phrase = best
        if cover >= min_cover and n >= min_words:
            found.append({**c, "score": round(cover + 0.01 * n, 3), "matched": phrase})
    found.sort(key=lambda c: -c["score"])
    return found[:limit]


NOTE = {
    "zh": "建议（别的任务里的经验，不是这个问题的事实；处境像的话可以试试，不像就忽略）：",
    "en": "Suggestions (lessons from other tasks, not facts about this question; try one if the situation fits, "
          "otherwise ignore):",
}


def render(found: list[dict], vault: Path | None = None) -> list[str]:
    """Lines for the router's receipt / the hook's context."""
    if not found:
        return []
    lang = "zh" if any(ri.CJK_RE.search(c["lesson"] or c["title"]) for c in found) else "en"
    out = [NOTE[lang]]
    for c in found:
        rel = zones.canon(vault, c["rel"]) if vault else c["rel"]
        src = f"；出处 {c['source']}" if c["source"] else ""
        out.append(f"- {c['lesson'] or c['title']}〔{rel}{src}；对上「{c['matched']}」〕")
    return [redact(x) for x in out]


# ---------- 写卡 ----------

PROMPT = """下面是一个人和他的编程 agent 在 {day} 的一段会话摘录（项目：{project}；只有提问和每轮最后的回答，已脱敏）。

只做一件事：找出这段会话里**遇到一个问题（有东西不对、不行或出了错）、试了一个办法、摘录里看得到成没成**的经验，最多
2 条；写成以后换一个题材、遇到同样处境时也用得上的经验卡。起草、润色、排版、比较方案、照着做一个步骤都不算；没有这样的
经验，或者拿不准，就回 []。

每条是一个 JSON 对象：
- "title"：一句话经验，去掉题材，12–30 字（例：「整体发平、没有层次时，加一点点反差的东西」）
- "situation"：当时的处境，照摘录写，可以带题材（例：「红烧肉炖好了，咸是够了，但吃着发平」）
- "action"：一句话，只写摘录里确实做了、或这个人确认做了的；只是被建议、计划过或中途放弃的不写
- "result"：一句话，会话结束时的结果；中途被改正过的数字或原因，用改正后的；摘录没说的细节不加
- 做法和结果里除非经验离不开，否则不写具体数字；卡里留下的每个数字都必须是摘录里原样有的，否则这张卡不要
- "subject"：点出这段会话题材的 2–6 个词（工具、产品、东西、专业词），例：["红烧肉", "糖"]
- "lesson"：去掉题材的通用说法，写成「……时，……」（例：「东西整体发平、缺一点层次时，加一点点与主调相反的元素」），
  里面不能出现 subject 里的词，也不能有别的专业词：要能原样用到完全不相干的领域，专门的词换成一般的说法
  （「执行计划」→「实际怎么跑的」，「大件家具」→「东西」）。自测：这句话原样讲给修 bug 的人、写报告的人、做饭的人都说得通吗？
  只适合这一类事，就再往上概括一层
写之前回头逐句对照摘录核对 situation、action、result。不写密钥、token、密码、人名和私人信息。只输出 JSON 数组。

摘录：

{text}
"""
PROMPT_EN = """Below is an excerpt of a session between a person and their coding agent on {day} (project: {project}; only the
questions and each turn's closing answer, redacted).

Do one thing: find where this session **hit a problem (something did not work or went wrong), tried a way out, and the
excerpt shows whether it worked**, at most 2; write each as an experience card that would still help on a task with
another subject in the same situation. Drafting, polishing, formatting, comparing options or carrying out a step do not
count; if there is none, or you are unsure, reply [].

Each is a JSON object:
- "title": the lesson in one line without the subject, 5–14 words
- "situation": what the situation was, as in the excerpt; it may name the subject
- "action": one sentence, only steps the excerpt shows were carried out or the person confirmed (not what was only
  suggested, planned or dropped along the way)
- "result": one sentence, the outcome as the session ends (a figure or cause corrected later: the corrected one); no
  detail the excerpt does not state
- leave specific numbers out of action and result unless the lesson cannot do without them; any number left in the
  card must occur verbatim in the excerpt, or the card is dropped
- "subject": the 2–6 words that name the session's subject (tools, products, objects, domain terms)
- "lesson": "When …, …" with none of the subject words and no other domain term, so it reads unchanged for a task in
  an unrelated area ("the execution plan" → "how it actually runs"). Test it: would it make sense word for word to
  someone fixing a bug, writing a report and cooking? If it only fits this kind of thing, say it one level higher
Before writing, check situation, action and result against the excerpt sentence by sentence. Do not write keys,
tokens, passwords, names or private details. Output only the JSON array.

Excerpt:

{text}
"""
# 宿主 agent 自己写卡（krouter_learn / `experience.py learn`）时看到的说明：和上面两段要的是同一张卡
LEARN_HELP = ("Record one lesson from this session as an experience card, so it can be offered on later tasks with "
              "another subject in the same situation. Only when the session hit a problem (something did not work or went "
              "wrong), tried a way out, and saw whether it worked; not for drafting, polishing, formatting or comparing "
              "options, nor for a step carried out as asked. When in doubt, do not record. Fields, one plain sentence each: situation "
              "(what the problem was; may name the subject); action (only steps the session shows were actually carried "
              "out, by the person or confirmed by them; leave out anything only suggested, planned or dropped along the "
              "way); result (the outcome as the session ends: where a figure or a cause was corrected later in the "
              "session, use the corrected one; add no detail the session does not state); subject (the 2–6 words that name this session's subject: tools, products, objects, domain terms, "
              "e.g. [\"nginx\", \"server_name\"] or [\"红烧肉\", \"糖\"]); lesson (\"When …, …\" / 「……时，……」 with none of "
              "the subject words and no other domain term, so that it reads unchanged for a task in an unrelated area: "
              "replace each specific term with a general word, \"the execution plan\" → \"how it actually runs\", "
              "「大件家具」→「东西」). Test it: would the lesson make sense word for word to someone fixing a bug, someone "
              "writing a report and someone cooking? If it only fits this kind of thing, say it once more one level "
              "higher); title (optional, the lesson in one line, same rule). Write in the language of the session; no keys, names or private "
              "details. Leave specific numbers out of action and result unless the lesson cannot do without them; every "
              "number that stays anywhere in the card must appear in quotes (the short verbatim snippets of the session "
              "that state it), or the card is sent back. If the experience digest already has this lesson (the same "
              "situation and the same way out, whatever the subject), write no new card: call with same_as set to that "
              "line's id instead, which records that the lesson came up again. Before calling, reread the session and check situation, action "
              "and result against it sentence by sentence.")


def _json_array(text: str) -> list:
    m = re.search(r"\[.*\]", text or "", re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def _short(phrase: str) -> bool:
    if ri.CJK_RE.search(phrase):
        return 2 <= len(phrase) <= 12
    return 1 <= len(phrase.split()) <= 8 and len(phrase) <= 60


def valid(item: dict, excerpt: str | None) -> dict | None:
    """The card when it holds up, else None: every field filled, no key-shaped text, situation and action grounded
    in the excerpt (skipped when the host agent writes the card itself: `excerpt` None), 2–6 short `when` phrases that
    do not name the situation's Latin words (`nginx`, `postgres`)."""
    import answer_cards

    if not isinstance(item, dict):
        return None
    card = {k: re.sub(r"\s+", " ", str(item.get(k) or "")).strip() for k in ("title", "situation", "action", "result",
                                                                            "lesson")}
    if not card["title"]:
        card["title"] = card["lesson"].split("，")[0].split(",")[0][:40] if card["lesson"] else ""
    when = item.get("when") if isinstance(item.get("when"), list) else SPLIT.split(str(item.get("when") or ""))
    limit = 40 if ri.CJK_RE.search(card["title"]) else 100
    if any(not v for v in card.values()) or len(card["title"]) > limit:
        return None
    if any(answer_cards.secret_like(v) for v in list(card.values()) + [str(w) for w in when]):
        return None
    if excerpt is not None:
        seen = set(ri.tokens(excerpt))
        grounded = set(ri.tokens(card["situation"] + " " + card["action"])) & seen
        if len(grounded) < 2:
            return None
    if ri.CJK_RE.search(card["situation"] + card["lesson"]):
        # 中文卡：处境里的拉丁字母词（`nginx`、`postgres`）就是题材的名字
        subject = {t for t in ri.tokens(card["situation"]) if not ri.is_cjk_bigram(t)} - ri.EN_FUNCTION
    else:
        # 英文卡：处境和做法里都有、通用说法里没有的词（`nginx`）；只在处境里出现的普通词（`nothing`）不算
        subject = ((set(ri.tokens(card["situation"])) & set(ri.tokens(card["action"])))
                   - set(ri.tokens(card["lesson"])) - ri.EN_FUNCTION)
    phrases = []
    for w in when:
        w = str(w).strip()
        if _short(w) and not (set(ri.tokens(w)) & subject) and w not in phrases:
            phrases.append(w)
    # `when` 短语不再要求（第 15 套起处境由宿主模型判断，摘要只列通用说法；第 17 套的两处题材泄漏都在这里）。
    # 给了就留下不带题材名的，留给人看
    card["when"] = phrases[:6]
    return card


def names_subject(item: dict) -> str:
    """The first of the card's own `subject` words that its lesson or title still uses, or ""."""
    terms = item.get("subject") if isinstance(item.get("subject"), list) else []
    text = (str(item.get("lesson") or "") + " " + str(item.get("title") or "")).lower()
    for t in terms:
        t = str(t).strip().lower()
        if len(t) >= 2 and t in text:
            return t
    return ""


FIGURE = re.compile(r"\d+(?:[.:/×x]\d+)*")


def _norm(text: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"(?<=\d)[,，\s](?=\d{3}\b)", "", text)  # 3,000 / 3 000 → 3000


def unsupported_figures(item: dict, source: str) -> list[str]:
    """The numbers in a card (situation, action, result, lesson, title) that do not occur in `source` as a whole number:
    `20` must stand on its own there, not inside `2026`. A mechanical check, no model."""
    text = _norm(" ".join(str(item.get(k) or "") for k in ("situation", "action", "result", "lesson", "title")))
    src = _norm(source)
    out = []
    for fig in dict.fromkeys(FIGURE.findall(text)):
        if not re.search(rf"(?<![\d.]){re.escape(fig)}(?![\d])", src):
            out.append(fig)
    return out


def near_duplicates(vault: Path, share: float = 0.4) -> list[tuple[dict, dict, float]]:
    """Pairs of cards whose lessons share at least `share` of their words: listed for a person to merge, never
    merged or deleted by the code."""
    cards = load_cards(vault)
    out = []
    for i, a in enumerate(cards):
        wa = set(words(a["lesson"]))
        for b in cards[i + 1:]:
            wb = set(words(b["lesson"]))
            if wa and wb:
                j = len(wa & wb) / len(wa | wb)
                if j >= share:
                    out.append((a, b, round(j, 2)))
    return sorted(out, key=lambda x: -x[2])


def same_lesson(a: str, b: str) -> bool:
    wa, wb = set(words(a)), set(words(b))
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.5


def file_name(title: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|#^\[\]\n]', "", title).strip()[:60] or "经验"
    return f"经验｜{safe}.md" if ri.CJK_RE.search(safe) else f"Lesson - {safe}.md"


def page_text(card: dict, source: str, day: str, writer: str = "krouter-capture") -> str:
    when = "; ".join(card["when"])
    zh = bool(ri.CJK_RE.search(card["lesson"] + card["title"]))
    fm_when = f"when: {when}\n" if when else ""
    title = f"经验｜{card['title']}" if zh else f"Lesson: {card['title']}"
    head = ("---\n"
            f"title: \"{title}\"\n"
            f"type: {TYPE}\n"
            "status: provisional\n"
            f"{fm_when}"
            f"source_ref: \"{source}\"\n"
            f"date: {day}\n"
            f"source: {writer}\n"
            "---\n\n"
            f"# {title}\n\n")
    if zh:
        return head + (f"- 处境：{card['situation']}\n- 做法：{card['action']}\n- 结果：{card['result']}\n"
                       f"- 通用说法：{card['lesson']}\n" + (f"- 适用于：{'；'.join(card['when'])}\n" if when else "")
                       + f"- 出处：{source}（从会话里抽出，没人核对过；不对就改或删）\n")
    return head + (f"- Situation: {card['situation']}\n- Action: {card['action']}\n- Result: {card['result']}\n"
                   f"- Lesson: {card['lesson']}\n" + (f"- When: {'; '.join(card['when'])}\n" if when else "")
                   + f"- Source: {source} (taken from a session, not checked by anyone; fix or delete it if wrong)\n")


def record_again(vault: Path, card_id: str, source: str, why: str) -> None:
    """The lesson of card `card_id` came up again in another session: one `again` line in the use records."""
    path = zones.path(vault, USES)
    path.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime

    row = {"at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "card": card_id, "kind": "again", "session": source,
           "turn": "", "why": why}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def lexical_twin(vault: Path, lesson: str) -> dict | None:
    """A card on file whose lesson shares most of its words with `lesson` (the code's own fallback check)."""
    return next((c for c in load_cards(vault) if same_lesson(lesson, c["lesson"])), None)


def write_card(vault: Path, card: dict, source: str, day: str, writer: str = "krouter-capture") -> Path | None:
    """Write one checked card; None when a card with the same lesson is already there (recorded as seen again)."""
    twin = lexical_twin(vault, card["lesson"])
    if twin:
        record_again(vault, twin["id"], source, "同一条经验（字面检查）")
        return None
    folder = zones.path(vault, FOLDER)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / file_name(card["title"])
    if path.exists():
        path = path.with_name(path.stem + "-" + hashlib.sha1(card["lesson"].encode()).hexdigest()[:6] + ".md")
    path.write_text(page_text(card, source, day, writer), encoding="utf-8")
    return path


def learn(vault: Path, item: dict, source: str, writer: str = "krouter-learn") -> tuple[Path | None, str]:
    """A card the host agent wrote itself (no model lane, no key). (path, "") when written, (None, why) when not.
    With `same_as` naming a card on file, no card is written: that card gets one `again` record ("again: <id>")."""
    same = str(item.get("same_as") or "").strip().strip("〔〕[]") if isinstance(item, dict) else ""
    if same:
        if same not in {c["id"] for c in load_cards(vault)}:
            return None, f"not written: same_as {same!r} is not the id of a card in the digest"
        record_again(vault, same, source, str(item.get("situation") or "")[:200])
        return None, f"again: {same}"
    named = names_subject(item) if isinstance(item, dict) else ""
    quotes = item.get("quotes") if isinstance(item, dict) and isinstance(item.get("quotes"), list) else []
    loose = unsupported_figures(item, "\n".join(str(q) for q in quotes)) if isinstance(item, dict) else []
    if loose:
        return None, (f"not written: these numbers are not in quotes: {', '.join(loose[:6])}. Quote the session line that "
                      "states each one, or leave the number out (better, unless the lesson needs it)")
    if named:
        return None, (f"not written: the lesson or title still names the subject ({named}); rewrite it with a general "
                      "word so it reads the same on another subject")
    card = valid(item, None)
    if not card:
        return None, "not written: fill situation, action, result and lesson; no key-shaped text"
    path = write_card(vault, card, source, date.today().isoformat(), writer)
    if path:
        return path, ""
    twin = lexical_twin(vault, card["lesson"])
    return None, f"again: {twin['id'] if twin else '?'}"


def extract(e: dict, excerpt: str, vault: Path, source: str, dry: bool = False) -> tuple[list[Path], int]:
    """Write up to two experience cards from one session-day's excerpt. Returns (pages written, characters sent).
    No model lane: ([], 0), quietly."""
    template = PROMPT if ri.CJK_RE.search(excerpt) else PROMPT_EN
    prompt = template.format(day=e["day"].isoformat(), project=e.get("project") or "?", text=excerpt)
    if dry:
        return [], len(prompt)
    import llm

    try:
        text = llm.complete(prompt, vault)
    except llm.NoModel:
        return [], 0
    written: list[Path] = []
    day = e["day"].isoformat() if hasattr(e["day"], "isoformat") else str(date.today())
    for item in _json_array(redact(text))[:2]:
        ok = isinstance(item, dict) and not names_subject(item) and not unsupported_figures(item, excerpt)
        card = valid(item, excerpt) if ok else None  # 模型通道手里有摘录：卡里的数字摘录里没有就不要
        path = write_card(vault, card, source, day) if card else None
        if path:
            written.append(path)
    return written, len(prompt)


def main() -> int:
    import argparse

    from krouter_home import vault_path

    ap = argparse.ArgumentParser(description="Experience cards: the digest, writing one, or set 13's lexical matcher.")
    ap.add_argument("--vault", default=vault_path())
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("digest", help="print the session-start digest")
    lp = sub.add_parser("learn", help="write one card the agent drafted (JSON on stdin or --json); " + LEARN_HELP)
    lp.add_argument("--json", default="", help="the card as JSON; read from stdin when left out")
    lp.add_argument("--source", default="", help="where it came from (a session page link); default: the CLI")
    sp = sub.add_parser("suggest", help="set 13's lexical matcher (not used by anything)")
    sp.add_argument("query")
    args = ap.parse_args()
    if not args.vault:
        print("set KROUTER_VAULT (or the older name OBSIDIAN_VAULT)", file=sys.stderr)
        return 2
    vault = Path(args.vault).expanduser()
    if args.cmd == "learn":
        try:
            item = json.loads(args.json or sys.stdin.read() or "{}")
        except ValueError:
            print("learn: the card must be JSON", file=sys.stderr)
            return 2
        path, why = learn(vault, item, args.source or "experience.py learn")
        print(json.dumps({"written": str(path.relative_to(vault)) if path else "", "reason": why}, ensure_ascii=False))
        return 0 if path else 1
    if args.cmd == "suggest":
        print("\n".join(render(suggest(vault, args.query), vault)) or "suggestions: none")
        return 0
    print(digest(vault) or "(no experience cards)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
