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

**Writing.** `extract()` runs where a session is distilled (`import_sessions.py`, session end or nightly): one more
model call through `llm.py` asks for at most two cards from the same excerpt, and only for a problem the session
solved with a result it shows. A card is kept when its fields are filled, nothing in it looks like a key, its
situation and action share words with the excerpt, and no card with the same lesson is on file. With no model lane
(`llm.NoModel`) it does nothing and says nothing.

**Suggesting.** Nothing is matched. At session start the hook (`session_hook.py start`) gives the host model the whole
digest (`digest()`): every card as one subject-free line "situation → what to do〔id〕", at most DIGEST_MAX_LINES (most
recently adopted first, then confirmed, then newest), and one line on how to use it: offer at most two, worded as
lessons from another task with their id, only when the task's situation is the same, and say nothing otherwise. The
host model, which reads the task anyway, judges the situation; one situation in other words shares no words, so a
retriever cannot (set 13). Cards never appear among recalled facts. `suggest()` (the lexical matcher of set 13) is
kept only to reproduce that set; nothing calls it.

**Switch.** `KROUTER_EXPERIENCE=1` turns on both writing and the digest; anything else (the default) leaves them off.
Measured: set 15 in `bench/memory_honesty/HELDOUT.md`, numbers and limits in `docs/EXPERIENCE.md`.
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


DEFAULT_ON = False  # 库里有经验卡时摘要默认开（第三轮第 5 项定）；KROUTER_EXPERIENCE=0 总是关


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
    """Adopted cards first, the most recent adoption first; then cards not yet passed over (offered IGNORED_AFTER
    times and never adopted sink to the bottom); then times offered; then confirmed; then the newest date."""
    u = used.get(card["id"], {})
    adopted = max(u.get("last_adopted", ""), card.get("adopted_at", ""))
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
    """{card id: {offered, adopted, last_offered, last_adopted}} from the use records."""
    path = zones.path(vault, USES)
    out: dict[str, dict] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        u = out.setdefault(str(d.get("card")), {"offered": 0, "adopted": 0, "last_offered": "", "last_adopted": ""})
        kind = d.get("kind")
        if kind in ("offered", "adopted"):
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

只做一件事：找出这段会话里**遇到一个问题、试了一个做法、摘录里看得到结果**的经验，最多 2 条；写成以后换一个题材、
遇到同样处境时也用得上的经验卡。没有这样的经验（只是讨论、没有结果、只是照做一个步骤）就回 []。

每条是一个 JSON 对象：
- "title"：一句话经验，去掉题材，12–30 字（例：「整体发平、没有层次时，加一点点反差的东西」）
- "situation"：当时的处境，照摘录写，可以带题材（例：「红烧肉炖好了，咸是够了，但吃着发平」）
- "action"：当时怎么做的
- "result"：结果怎样，只写摘录里看得到的
- "lesson"：去掉题材的通用说法，写成「……时，……」（例：「东西整体发平、缺一点层次时，加一点点与主调相反的元素」）
- "when"：3–5 个短语，2–10 字，是人遇到这个处境时会说的话，不能带题材里的名词
  （例：["发平", "没有层次", "寡淡", "缺点什么"]，不写「红烧肉」）
不写密钥、token、密码、人名和私人信息。只输出 JSON 数组。

摘录：

{text}
"""
PROMPT_EN = """Below is an excerpt of a session between a person and their coding agent on {day} (project: {project}; only the
questions and each turn's closing answer, redacted).

Do one thing: find where this session **hit a problem, tried something, and the excerpt shows how it turned out**, at
most 2; write each as an experience card that would still help on a task with another subject in the same situation.
If there is none (only discussion, no outcome, or just carrying out a step), reply [].

Each is a JSON object:
- "title": the lesson in one line without the subject, 5–14 words
- "situation": what the situation was, as in the excerpt; it may name the subject
- "action": what was done
- "result": how it turned out, only what the excerpt shows
- "lesson": the lesson without the subject, written "When …, …"
- "when": 3–5 short phrases, 2–6 words each, that a person in this situation would say; no nouns from the subject
Do not write keys, tokens, passwords, names or private details. Output only the JSON array.

Excerpt:

{text}
"""
# 宿主 agent 自己写卡（krouter_learn / `experience.py learn`）时看到的说明：和上面两段要的是同一张卡
LEARN_HELP = ("Record one lesson from this session as an experience card, so it can be offered on later tasks with "
              "another subject in the same situation. Only when the session hit a problem, tried something, and saw how "
              "it turned out; not for plain discussion or a step carried out. Fields: situation (what happened, may "
              "name the subject), action (what was done), result (how it turned out), lesson (the lesson without the "
              "subject, \"When …, …\" / 「……时，……」), when (3–5 short phrases a person in this situation would say, "
              "no nouns from the subject), title (optional, the lesson in one line). Skip it if the experience digest "
              "already has the same lesson. Write in the language of the session; no keys, names or private details.")


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
    # 处境由宿主模型自己判断（第 15 套），不再要求短语里有词表里的词
    if len(phrases) < 2:
        return None
    card["when"] = phrases[:6]
    return card


def same_lesson(a: str, b: str) -> bool:
    wa, wb = set(words(a)), set(words(b))
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.5


def file_name(title: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|#^\[\]\n]', "", title).strip()[:60] or "经验"
    return f"经验｜{safe}.md" if ri.CJK_RE.search(safe) else f"Lesson - {safe}.md"


def page_text(card: dict, source: str, day: str, writer: str = "krouter-capture") -> str:
    when = "; ".join(card["when"])
    zh = bool(ri.CJK_RE.search(card["lesson"] + card["title"]))
    title = f"经验｜{card['title']}" if zh else f"Lesson: {card['title']}"
    head = ("---\n"
            f"title: \"{title}\"\n"
            f"type: {TYPE}\n"
            "status: provisional\n"
            f"when: {when}\n"
            f"source_ref: \"{source}\"\n"
            f"date: {day}\n"
            f"source: {writer}\n"
            "---\n\n"
            f"# {title}\n\n")
    if zh:
        return head + (f"- 处境：{card['situation']}\n- 做法：{card['action']}\n- 结果：{card['result']}\n"
                       f"- 通用说法：{card['lesson']}\n- 适用于：{'；'.join(card['when'])}\n"
                       f"- 出处：{source}（从会话里抽出，没人核对过；不对就改或删）\n")
    return head + (f"- Situation: {card['situation']}\n- Action: {card['action']}\n- Result: {card['result']}\n"
                   f"- Lesson: {card['lesson']}\n- When: {'; '.join(card['when'])}\n"
                   f"- Source: {source} (taken from a session, not checked by anyone; fix or delete it if wrong)\n")


def write_card(vault: Path, card: dict, source: str, day: str, writer: str = "krouter-capture") -> Path | None:
    """Write one checked card; None when a card with the same lesson is already there."""
    if any(same_lesson(card["lesson"], c["lesson"]) for c in load_cards(vault)):
        return None
    folder = zones.path(vault, FOLDER)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / file_name(card["title"])
    if path.exists():
        path = path.with_name(path.stem + "-" + hashlib.sha1(card["lesson"].encode()).hexdigest()[:6] + ".md")
    path.write_text(page_text(card, source, day, writer), encoding="utf-8")
    return path


def learn(vault: Path, item: dict, source: str, writer: str = "krouter-learn") -> tuple[Path | None, str]:
    """A card the host agent wrote itself (no model lane, no key). (path, "") when written, (None, why) when not."""
    card = valid(item, None)
    if not card:
        return None, ("not written: fill situation, action, result, lesson and 2–6 short `when` phrases without the "
                      "subject's names; no key-shaped text")
    path = write_card(vault, card, source, date.today().isoformat(), writer)
    return (path, "") if path else (None, "not written: a card with the same lesson is already there")


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
        card = valid(item, excerpt)
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
        print("set OBSIDIAN_VAULT", file=sys.stderr)
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
