"""`KROUTER_ASK_JUDGE=1` (off by default): a reader decides what `krouter_ask` / `route_knowledge` answers from.

The lookup's own ranking finds the pages closest to the question by wording, but its refusal gate is a threshold on
wording too: it cites a neighbouring page when the words line up and refuses a right page when they do not. With the
switch on, the first K pages in force (the gate off) go to a small model with the question, each as its title and the
start of its text, and the model names the one that answers the question, or none. That page is cited alone, or the
receipt says the memory does not have it. Set 53 (bench/memory_honesty/HELDOUT.md), held-out, 200 questions: wrong
citations 26.1% -> 4.1%, neighbour questions refused 47 -> 76 of 80, right answers 102 -> 117 of 120, with
`deepseek-flash`. What it does not change: the ranking itself (BM25's five pages under the same reader did as well).

What leaves the machine with the switch on: the question, redacted, and for each candidate its title and its first 240
characters, to `KROUTER_JUDGE_URL` (DeepSeek by default). It needs a key: `KROUTER_JUDGE_KEY`, or `DEEPSEEK_API_KEY`,
in the environment or the keys file, the same as the per-message hook's reader (`KROUTER_RECALL_JUDGE`), and shares its
daily cap and its metadata log (`judge.jsonl`, never the question). A failed call, a timeout or a used-up day leaves
the lookup exactly as it is without the switch.

The prompt, the page excerpt and K are set 53's, word for word (`bench/ask_judge/ask_judge.py`; a test holds them
equal): change them and the numbers above no longer describe what ships.
"""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path

K = 5
EXCERPT = 240
TIMEOUT = 15.0  # 一次查询不是每句话都跑：可以比钩子（5 秒）多等一会儿；评测中位数约 1 秒
SWITCH = "KROUTER_ASK_JUDGE"
ASK = ("Below is a question someone asked their own memory vault, and the vault pages closest to it (number, title, "
       "the start of the page). Decide which page answers the question. A page about a neighbouring matter, or one that "
       "only shares words with the question, does not answer it.\n"
       "Answer with one number only: the page's number, or 0 if none of them answers the question. No explanation.\n\n"
       "The question: {q}\n\n{pages}\n")
NOTE = {
    "picked": "recall_judge: {model} read the first {n} pages and named this one as the answer (KROUTER_ASK_JUDGE)",
    "none": "recall_judge: {model} read the first {n} pages and found none that answers this (KROUTER_ASK_JUDGE)",
}


def excerpt(vault: Path, rel: str) -> tuple[str, str]:
    """(title, the start of the text) of a page, front matter and the H1 left out."""
    text = (vault / rel).read_text(encoding="utf-8", errors="replace")
    title = Path(rel).stem
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            m = re.search(r"^title:\s*(.+)$", text[:end], re.M)
            title = m.group(1).strip().strip("'\"") if m else title
            text = text[end + 4:]
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("# ")]
    return title, re.sub(r"\s+", " ", " ".join(lines))[:EXCERPT]


def prompt(q: str, vault: Path, cands: list[str]) -> str:
    pages = []
    for i, rel in enumerate(cands, 1):
        title, start = excerpt(vault, rel)
        pages.append(f"{i}. {title}: {start}")
    return ASK.format(q=q.strip(), pages="\n".join(pages))


def pick(reply: str, n: int) -> int:
    m = re.search(r"\d+", reply or "")
    v = int(m.group()) if m else 0
    return v if 1 <= v <= n else 0


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
    n = 0 if error else pick(box.get("reply", ""), len(cands))
    recollect._judge_log(time.perf_counter() - t0, len(cands), bool(n), error, route="ask")
    if error:
        return None
    if not n:
        return {**res, "hits": [], "confidence": "none", "judged": "none",
                "judge_note": NOTE["none"].format(model=c["model"], n=len(cands))}
    hit = res["hits"][n - 1]
    return {**res, "hits": [hit], "confidence": "high", "judged": "picked", "assoc": [], "more": [], "conflict": [],
            "judge_note": NOTE["picked"].format(model=c["model"], n=len(cands))}
