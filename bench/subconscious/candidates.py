"""Set 51 (bench/memory_honesty/HELDOUT.md): when the per-message hook brings nothing, the pages closest to the message
by wording, as candidates for someone else to judge: the host (condition H, names only, in a note) or a model the hook
asks (condition J, names and one line each, one number back). A bench-side prototype: the engine does not do this yet.

A candidate is a hit of the hook's own full-text recall over the message (the index as it is, the refusal gate ignored),
in order, that the hook would be allowed to bring: in force, not a log or a session excerpt, not secret, not a knowledge
-base page, not already brought. A message lighter than MIN_WEIGHT (two per CJK character, one per Latin letter or
digit) gets none: a go-ahead or an acknowledgement has nothing to look up."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

K_HOST = 3
K_JUDGE = 5
MIN_WEIGHT = 12
HEAD = {
    "zh": "KRouter 候选（按字面最接近这句话的几页，只有名字，没核对过，多半与这句话无关。只有这句话确实在说其中某一件事时"
          "才去取那一页；否则当这段不存在，回复里也不要提）：",
    "en": "KRouter candidates (the pages closest to this message by wording; names only, not checked, most likely "
          "unrelated. Fetch a page only if the message really is about that matter; otherwise act as if this note were "
          "not here and do not mention it):",
}
ASK = {
    "zh": "下面是用户刚说的一句话，和记忆库里按字面最接近的几页（每页一行：名字：记的是什么）。判断这句话是不是在说其中某一页"
          "记的那件事：换了说法、没提名字也算；只是碰巧有相同的词、说的是别的事不算；粘贴的日志、代码、别人的话不算。\n"
          "只回答一个数字：是哪一页就回它的编号；都不是、或拿不准，回 0。不要解释。\n\n用户的话：{text}\n\n{pages}\n",
    "en": "Below are a message the user just sent and the pages of their memory vault closest to it by wording (one line "
          "each: name: what it records). Decide whether the message is about the matter one of the pages records: said "
          "another way or without the name counts; sharing a word while being about something else does not; pasted "
          "logs, code or someone else's words do not.\nAnswer with one number only: the page's number, or 0 when it is "
          "none of them or you are not sure. No explanation.\n\nThe message: {text}\n\n{pages}\n",
}


def weight(text: str) -> int:
    return 2 * len(re.findall(r"[㐀-鿿]", text)) + len(re.findall(r"[A-Za-z0-9]", text))


def candidates(vault: Path, text: str, have: set[str], k: int, today: date | None = None) -> list[dict]:
    """[{rel, real, title, how}], at most k, best first."""
    import recollect
    import zones

    today = today or date.today()
    said = recollect.prose(text)
    if not said or len(said) > recollect.PROSE_MAX or weight(said) < MIN_WEIGHT:
        return []
    res = recollect._ranked(vault, said) or {}
    out: list[dict] = []
    for h in res.get("hits") or []:
        if h.get("tier") in ("log", "dead"):
            continue
        cur = recollect.current(vault, zones.real(vault, h["rel"]), today)
        if cur is None or cur[0] in have or any(c["real"] == cur[0] for c in out):
            continue
        fm = (recollect.page(vault, cur[0]) or ({}, ""))[0]
        if (fm.get("type") or "").lower() in recollect.LOG_TYPES:
            continue
        d = recollect.describe(vault, cur[0], "", "", today)
        out.append({"rel": d["rel"], "real": cur[0], "how": d["how"],
                    "title": re.sub(r"\s+", " ", str(fm.get("title") or Path(cur[0]).stem)).strip()})
        if len(out) >= k:
            break
    return out


def render(cands: list[dict], lang: str) -> str:
    if not cands:
        return ""
    return "\n".join([HEAD[lang]] + [f"- {c['title']} 〔{c['real']}〕" if lang == "zh" else f"- {c['title']} [{c['real']}]"
                                     for c in cands])


def ask(text: str, cands: list[dict], lang: str) -> str:
    sep = "：" if lang == "zh" else ": "
    return ASK[lang].format(text=text.strip(), pages="\n".join(f"{i}. {c['title']}{sep}{c['how']}" for i, c in enumerate(cands, 1)))


def pick(reply: str, n: int) -> int:
    """The number the model answered, 0 for none, anything unreadable or out of range counts as 0."""
    m = re.search(r"\d+", reply or "")
    v = int(m.group()) if m else 0
    return v if 1 <= v <= n else 0


# Set 52: the same question for a decision model (one that returns a typed choice with probabilities, no text).
NONE = "none"
INSTRUCT = {
    "zh": "state 是用户刚说的一句话。判断它是不是在说下面某一页记的那件事：换了说法、没提名字也算；只是碰巧有相同的词、"
          "说的是别的事不算；粘贴的日志、代码、别人的话不算。都不是或拿不准，选 none。",
    "en": "The state is a message the user just sent. Decide whether it is about the matter one of the pages below "
          "records: said another way or without the name counts; sharing a word while being about something else does "
          "not; pasted logs, code or someone else's words do not. If it is none of them, or you are not sure, choose none.",
}
NONE_SAYS = {
    "zh": "都不是，或拿不准：这句话不是在说上面任何一页记的事",
    "en": "None of the pages, or not sure: the message is not about any matter recorded above",
}


def question(cands: list[dict], lang: str) -> dict:
    """One `choice` question: an option per candidate (p1..pN, its name and one line) and `none`."""
    sep = "：" if lang == "zh" else ": "
    criteria = {f"p{i}": f"{c['title']}{sep}{c['how']}" for i, c in enumerate(cands, 1)}
    criteria[NONE] = NONE_SAYS[lang]
    return {"type": "choice", "instructions": INSTRUCT[lang], "criteria": criteria}


def chosen(answer: dict | None, n: int) -> tuple[int, float]:
    """(the candidate's number or 0, the model's confidence in its pick or -1) from a decision model's answer."""
    answer = answer or {}
    pick = str(answer.get("choice") or "")
    conf = answer.get("confidence")
    try:
        conf = float(conf)
    except (TypeError, ValueError):
        probs = answer.get("probabilities") or {}
        conf = float(probs.get(pick, -1)) if isinstance(probs, dict) else -1.0
    m = re.fullmatch(r"p(\d+)", pick)
    v = int(m.group(1)) if m else 0
    return (v if 1 <= v <= n else 0), conf
