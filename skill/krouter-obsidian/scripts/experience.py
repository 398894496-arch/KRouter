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


def enabled() -> bool:
    return os.environ.get("KROUTER_EXPERIENCE", "").strip() == "1"


# ---------- 读卡 ----------

def _fields(body: str) -> dict[str, str]:
    out = {}
    for line in body.splitlines():
        m = re.match(r"^\s*[-*]\s*(处境|做法|结果|通用说法|适用于|出处)\s*[:：]\s*(.+)$", line)
        if m and m.group(1) not in out:
            out[m.group(1)] = m.group(2).strip()
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
            "title": (meta.get("title") or page.stem).removeprefix("经验｜"),
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
DIGEST_HEAD = ("KRouter 经验摘要：别的任务里攒下的经验，不是这个项目的事实，也不保证对。每行是「处境 → 做法〔编号〕」，"
               "卡片在「{folder}」，编号就是卡里的 card_id 或文件名。")
DIGEST_USE = ("用法：只有当用户这次要做的事和某一行的处境确实相同（不是只沾到同一个词或同一个题材）时，才在回复里顺带提一句"
              "「别的任务里的经验，可以试试：……〔编号〕」，最多两条；没有处境相同的，就一个字都不要提，也不要说没有相关经验。")


def digest_line(card: dict) -> str:
    """One card as "situation → what to do〔id〕", subject-free (the lesson, split at its "…时，")."""
    lesson = re.sub(r"\s+", " ", card["lesson"] or card["title"]).strip().rstrip("。")
    m = re.match(r"^(.{2,60}?)(?:时|的时候)[，,]\s*(.+)$", lesson)
    body = f"{m.group(1)} → {m.group(2)}" if m else lesson
    return f"- {body}〔{card['id']}〕"


def ranked(cards: list[dict]) -> list[dict]:
    """Most recently adopted first (`adopted_at`), then confirmed (`status: active`), then newest (`date`)."""
    return sorted(cards, key=lambda c: (c["adopted_at"], c["status"] == "active", c["date"], c["rel"]), reverse=True)


def digest(vault: Path, max_lines: int = DIGEST_MAX_LINES, cards: list[dict] | None = None) -> str:
    """The whole experience digest the session-start hook gives the host model; "" when there are no cards."""
    cards = load_cards(vault) if cards is None else cards
    if not cards:
        return ""
    shown = ranked(cards)[:max_lines]
    out = [DIGEST_HEAD.format(folder=zones.real(vault, FOLDER))] + [digest_line(c) for c in shown]
    if len(cards) > len(shown):
        out.append(f"（还有 {len(cards) - len(shown)} 张没列出：按最近采纳、已确认、最新的顺序只列前 {max_lines} 张）")
    out.append(DIGEST_USE)
    return redact("\n".join(out))


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


def _json_array(text: str) -> list:
    m = re.search(r"\[.*\]", text or "", re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def valid(item: dict, excerpt: str) -> dict | None:
    """The card when it holds up, else None: every field filled, no key-shaped text, situation and action grounded
    in the excerpt, 2–6 usable `when` phrases that do not name the subject's latin words."""
    import answer_cards

    if not isinstance(item, dict):
        return None
    card = {k: re.sub(r"\s+", " ", str(item.get(k) or "")).strip() for k in ("title", "situation", "action", "result",
                                                                            "lesson")}
    when = item.get("when") if isinstance(item.get("when"), list) else SPLIT.split(str(item.get("when") or ""))
    if any(not v for v in card.values()) or len(card["title"]) > 40:
        return None
    if any(answer_cards.secret_like(v) for v in list(card.values()) + [str(w) for w in when]):
        return None
    seen = set(ri.tokens(excerpt))
    grounded = set(ri.tokens(card["situation"] + " " + card["action"])) & seen
    if len(grounded) < 2:
        return None
    subject = {t for t in ri.tokens(card["situation"]) if not ri.is_cjk_bigram(t)}
    phrases = []
    for w in when:
        w = str(w).strip()
        if 2 <= len(w) <= 12 and not (set(ri.tokens(w)) & subject) and w not in phrases:
            phrases.append(w)
    # 词表外的短语（`发平`、`寡淡`）照留给人看，但词法匹配用不上它；至少要有一条用得上
    if len(phrases) < 2 or not any(words(w) for w in phrases):
        return None
    card["when"] = phrases[:6]
    return card


def same_lesson(a: str, b: str) -> bool:
    wa, wb = set(words(a)), set(words(b))
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.5


def file_name(title: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|#^\[\]\n]', "", title).strip()[:40] or "经验"
    return f"经验｜{safe}.md"


def page_text(card: dict, source: str, day: str) -> str:
    when = "; ".join(card["when"])
    return ("---\n"
            f"title: \"经验｜{card['title']}\"\n"
            f"type: {TYPE}\n"
            "status: provisional\n"
            f"when: {when}\n"
            f"source_ref: \"{source}\"\n"
            f"date: {day}\n"
            "source: krouter-capture\n"
            "---\n\n"
            f"# 经验｜{card['title']}\n\n"
            f"- 处境：{card['situation']}\n"
            f"- 做法：{card['action']}\n"
            f"- 结果：{card['result']}\n"
            f"- 通用说法：{card['lesson']}\n"
            f"- 适用于：{'；'.join(card['when'])}\n"
            f"- 出处：{source}（模型从会话里抽出，没人核对过；不对就改或删）\n")


def extract(e: dict, excerpt: str, vault: Path, source: str, dry: bool = False) -> tuple[list[Path], int]:
    """Write up to two experience cards from one session-day's excerpt. Returns (pages written, characters sent).
    No model lane: ([], 0), quietly."""
    prompt = PROMPT.format(day=e["day"].isoformat(), project=e.get("project") or "?", text=excerpt)
    if dry:
        return [], len(prompt)
    import llm

    try:
        text = llm.complete(prompt, vault)
    except llm.NoModel:
        return [], 0
    folder = zones.path(vault, FOLDER)
    have = load_cards(vault)
    written: list[Path] = []
    for item in _json_array(redact(text))[:2]:
        card = valid(item, excerpt)
        if not card or any(same_lesson(card["lesson"], c["lesson"]) for c in have):
            continue
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / file_name(card["title"])
        if path.exists():
            path = path.with_name(path.stem + "-" + hashlib.sha1(card["lesson"].encode()).hexdigest()[:6] + ".md")
        path.write_text(page_text(card, source, e["day"].isoformat() if hasattr(e["day"], "isoformat")
                                  else str(date.today())), encoding="utf-8")
        written.append(path)
        have.append({"lesson": card["lesson"]})
    return written, len(prompt)


def main() -> int:
    import argparse

    from krouter_home import vault_path

    ap = argparse.ArgumentParser(description="Experience cards that match a task description (read-only).")
    ap.add_argument("query")
    ap.add_argument("--vault", default=vault_path())
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not args.vault:
        print("set OBSIDIAN_VAULT", file=sys.stderr)
        return 2
    vault = Path(args.vault).expanduser()
    found = suggest(vault, args.query)
    if args.json:
        print(json.dumps([{k: c[k] for k in ("rel", "title", "lesson", "source", "matched", "score")} for c in found],
                         ensure_ascii=False))
    else:
        print("\n".join(render(found, vault)) or "suggestions: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
