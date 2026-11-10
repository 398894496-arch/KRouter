#!/usr/bin/env python3
"""The LangGraph store (krouter.integrations.langgraph) with many users: does a question asked in one user's namespace
get that user's page, nothing when the user never said it, and never another user's page?

    python3 bench/scale/langgraph_store.py [USERS] [WORKDIR]     # needs langgraph; default 300 users, a temp folder

Each user gets 5 of 12 facts (seeded, reproducible), written in that user's namespace. 40 users are asked 8
questions each; a question is answerable when that user has the fact. Outcomes: answered (the right page first),
refused correctly, refused though answerable (the question's words are not on the page), answered though the user
never said it, another user's page. No model is called. Prints one JSON line.
"""

from __future__ import annotations

import json
import os
import random
import statistics
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk"))
os.environ.setdefault("KROUTER_NO_QUERY_LOG", "1")
from krouter.integrations.langgraph import KRouterStore  # noqa: E402

FACTS = ["is vegetarian and never eats fish.", "loves spicy ramen with pork belly.",
         "is allergic to peanuts and avoids satay.", "has a dog called Biscuit who is afraid of thunder.",
         "keeps two cats named Miso and Tofu.", "lives in Lyon and commutes by bike.", "lives in Osaka near the river.",
         "works as a nurse on night shifts.", "is a backend engineer who writes Go.", "prefers answers in French.",
         "plays the cello in an amateur orchestra.", "drives an old red Volvo estate."]
QUESTIONS = {0: "does the user eat fish", 2: "is the user allergic to peanuts", 3: "what is the dog called",
             4: "what are the cats called", 5: "does the user commute by bike", 7: "does the user work night shifts",
             10: "does the user play the cello", 11: "which car does the user drive"}


def main() -> int:
    users = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    work = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(tempfile.mkdtemp(prefix="krouter-lg-scale-"))
    store = KRouterStore(work / "memory", cache_dir=work / "cache")
    rnd = random.Random(3)
    owned = {}
    t = time.monotonic()
    for u in range(users):
        owned[u] = set(rnd.sample(range(len(FACTS)), 5))
        for j in owned[u]:
            store.put(("users", f"u{u}"), f"f{j}", {"content": f"User{u} " + FACTS[j]})
    put_s = time.monotonic() - t
    outcome, times = Counter(), []
    for u in rnd.sample(range(users), min(40, users)):
        ns = ("users", f"u{u}")
        for j, q in QUESTIONS.items():
            t = time.monotonic()
            hits = store.search(ns, query=q, limit=3)
            times.append(time.monotonic() - t)
            top = hits[0].key if hits else None
            if any(h.namespace != ns for h in hits):
                outcome["another_users_page"] += 1
            elif j in owned[u]:
                outcome["answered" if top == f"f{j}" else "refused_though_answerable" if top is None
                        else "wrong_page_first"] += 1
            else:
                outcome["refused_correctly" if top is None else "answered_though_never_said"] += 1
    print(json.dumps({"users": users, "pages": 5 * users, "questions": len(times), **outcome,
                      "put_seconds": round(put_s, 1), "search_median_s": round(statistics.median(times), 3),
                      "search_max_s": round(max(times), 3)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
