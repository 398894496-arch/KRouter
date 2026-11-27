"""`KROUTER_ASK_JUDGE=1` (off by default): a reader decides what `krouter_ask` / `route_knowledge` answers from.

The lookup's own ranking finds the pages closest to the question by wording, but its refusal gate is a threshold on
wording too: it cites a neighbouring page when the words line up and refuses a right page when they do not. With the
switch on, the first K pages in force (the gate off) go to a small model with the question, and the model names the
pages that hold the answer or a part of it, most useful first, or none. A page of at most FULL characters is shown
whole; a longer one as its start and the lines closest to the question, and the reader may not refuse it: "none" is a
refusal only when every candidate was shown whole (set 54: shown parts of long chat pages, a reader refused more than
half of LongMemEval's answerable questions).

Set 54 (bench/memory_honesty/HELDOUT.md), held-out, `deepseek-flash`: on short rule pages (heldout3, 200 questions)
wrong citations 26.1% -> 5.9%, neighbour questions refused 47 -> 74 of 80, right answers 102 -> 111 of 120; on long
chat pages (LongMemEval's held-out half) 213 -> 218 of 235 with an answer cited, 10 -> 4 refused. What it does not
change: the ranking (BM25's five pages under the same reader did as well).

What leaves the machine with the switch on: the question, redacted, and for each candidate its title and what the
reader is shown of it (at most FULL characters), to `KROUTER_JUDGE_URL` (DeepSeek by default). It needs a key:
`KROUTER_JUDGE_KEY`, or `DEEPSEEK_API_KEY`, in the environment or the keys file, the same as the per-message hook's
reader (`KROUTER_RECALL_JUDGE`), and shares its daily cap and its metadata log (`judge.jsonl`, never the question). A
failed call, a timeout or a used-up day leaves the lookup exactly as it is without the switch.

The prompt, what the reader is shown, K and the rule in `outcome` are set 54's (`bench/ask_judge/ask_judge.py --v54`
and `lme_probe.py` call this module): change them and the numbers above no longer describe what ships.
"""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path

K = 5
TIMEOUT = 15.0  # 一次查询不是每句话都跑：可以比钩子（5 秒）多等一会儿；评测中位数约 1 秒
SWITCH = "KROUTER_ASK_JUDGE"
FULL = 1200  # set 54：正文不超过这么长的页整页给模型看；更长的页给开头 HEAD 字和最相关的几处，合起来不超过 FULL
HEAD = 300
SPOTS = 3
SPOT = 300
PASSAGE = FULL
ASK = ("Below is a question someone asked their own memory vault, and the vault pages closest to it (number, title, "
       "the passage of the page closest to the question). Decide which pages hold information needed to answer it: the "
       "answer itself, a fact the answer can be worked out from, one of several items the question counts, compares or "
       "orders in time, the latest state of something that changed, or what the person said they like or want. A page "
       "about a different matter that only shares words with the question does not.\n"
       "Answer with page numbers only, the most useful first, separated by commas; or 0 if none of them holds any of "
       "that. No explanation.\n\n"
       "The question: {q}\n\n{pages}\n")
NOTE = {
    "picked": "recall_judge: {model} read the passage closest to the question in each of the first {n} pages and named these as holding the answer, most useful first (KROUTER_ASK_JUDGE)",
    "none": "recall_judge: {model} read the passage closest to the question in each of the first {n} pages and found none that holds any of the answer (KROUTER_ASK_JUDGE)",
}


def _body(vault: Path, rel: str) -> tuple[str, list[str]]:
    """(title, the text's non-empty lines), front matter and the H1 left out."""
    text = (vault / rel).read_text(encoding="utf-8", errors="replace")
    title = Path(rel).stem
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            m = re.search(r"^title:\s*(.+)$", text[:end], re.M)
            title = m.group(1).strip().strip("'\"") if m else title
            text = text[end + 4:]
    return title, [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("# ")]


def is_long(vault: Path, rel: str) -> bool:
    return len(" ".join(_body(vault, rel)[1])) > FULL


def passage(vault: Path, rel: str, question: str) -> tuple[str, str]:
    """(title, what the reader sees of the page): the whole text when it is at most FULL characters; otherwise its first
    HEAD characters and the SPOTS lines closest to the question (scored by the question's words they hold, each word
    weighted by how rare it is on the page), in page order, each cut to SPOT characters around its first question word,
    joined by " … ", at most FULL in all."""
    import math

    import recall_index as ri

    title, lines = _body(vault, rel)
    whole = " ".join(lines)
    if len(whole) <= FULL:
        return title, whole
    q = set(ri.tokens(question))
    toks = [set(ri.tokens(ln)) for ln in lines]
    df = {w: sum(1 for s in toks if w in s) for w in q}
    weight = {w: math.log((len(lines) + 1) / (df[w] + 0.5)) for w in q if df[w]}
    scores = [sum(weight.get(w, 0.0) for w in s & q) for s in toks]
    ranked = sorted((i for i in range(len(lines)) if scores[i] > 0), key=lambda i: (-scores[i], i))[:SPOTS]
    parts = [whole[:HEAD]]
    for i in sorted(ranked):
        text, low = lines[i], lines[i].lower()
        if len(text) > SPOT:
            hits = [low.find(w) for w in weight if low.find(w) >= 0]
            at = max(0, min(hits) - SPOT // 4) if hits else 0
            text = text[at:at + SPOT]
        parts.append(text)
    return title, " … ".join(parts)[:FULL]


def prompt(q: str, vault: Path, cands: list[str]) -> str:
    pages = []
    for i, rel in enumerate(cands, 1):
        title, text = passage(vault, rel, q)
        pages.append(f"{i}. {title}: {text}")
    return ASK.format(q=q.strip(), pages="\n".join(pages))


def pick(reply: str, n: int) -> list[int]:
    """The page numbers answered, in order, each once; [] for 0 or anything unreadable or out of range."""
    out: list[int] = []
    for m in re.findall(r"\d+", reply or ""):
        v = int(m)
        if 1 <= v <= n and v not in out:
            out.append(v)
    return out


def conf() -> dict | None:
    """The reader's settings, or None when the switch is off or there is no key."""
    import recollect

    c = recollect.judge_conf(SWITCH)
    if c is None:
        return None
    try:
        c["timeout"] = max(0.5, float(os.environ.get("KROUTER_ASK_JUDGE_TIMEOUT", "") or TIMEOUT))
    except ValueError:
        c["timeout"] = TIMEOUT
    return c


def decide(vault: Path, query: str, scope: str = "") -> dict | None:
    """The lookup's result with the reader's decision in it, or None to leave the lookup as it is (switch off, no key,
    no candidate, the day's questions used up, a failed or late call).

    Picked: {"hits": [that page], "confidence": "high", "judged": "picked", ...}. None of them:
    {"hits": [], "confidence": "none", "judged": "none", ...}. Both carry "judge_note", the receipt line."""
    c = conf()
    if c is None:
        return None
    import recall_index as ri
    import recollect

    res = ri.recall(vault, query, scope, gate=False)
    cands = [h["rel"] for h in res.get("hits") or []][:K]
    if not cands or recollect._judge_calls_today() >= c["cap"]:
        return None
    text = prompt(recollect.redact(query), vault, cands)
    box: dict = {}

    def work() -> None:
        try:
            box["reply"] = recollect._judge_call(c, text)
        except Exception as exc:  # noqa: BLE001  问不到就照没开这个开关时查
            box["error"] = type(exc).__name__

    t0 = time.perf_counter()
    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(c["timeout"])
    error = "timeout" if th.is_alive() else box.get("error", "")
    if not error and not (box.get("reply") or "").strip():
        error = "empty"
    picked = [] if error else pick(box.get("reply", ""), len(cands))
    recollect._judge_log(time.perf_counter() - t0, len(cands), bool(picked), error, route="ask")
    if error:
        return None
    got = outcome(vault, res["hits"][:len(cands)], picked)
    if got is None:
        return None
    if not got:
        return {**res, "hits": [], "confidence": "none", "judged": "none",
                "judge_note": NOTE["none"].format(model=c["model"], n=len(cands))}
    return {**res, "hits": got, "confidence": "high", "judged": "picked", "assoc": [], "more": [],
            "conflict": [], "judge_note": NOTE["picked"].format(model=c["model"], n=len(cands))}


def outcome(vault: Path, hits: list[dict], picked: list[int]) -> list[dict] | None:
    """What the lookup answers from, given the candidates and the reader's numbers: the pages named, most useful first,
    then the long candidates not named (the reader saw only parts of them), in their order; [] for "the memory does not
    have it", which only a reader that saw every candidate whole can say; None to answer as without the switch."""
    long = [h for h in hits if is_long(vault, h["rel"])]
    if not picked:
        return None if long else []  # 长页只给了片段：模型说都不是不算数（set 54：长对话页上模型拒得太多）
    named = [hits[i - 1] for i in picked]
    return named + [h for h in long if h not in named]
