#!/usr/bin/env python3
"""Count what a host did, from the run records (one `record.json` per scenario, any host).

    python3 bench/behavior/judge.py SET.json RECORD_DIR [--card-id-pattern ...]

Rules (registered with the set in HELDOUT.md, applied mechanically):
  offer   a card id in square brackets (`[C01]`, `〔C01〕`) in any message of the session. Should: group `offer` (its
          own card id for the strict count, any id for the loose one). Should not: groups correct, notcorrect, quiet.
  learn   a `krouter_learn` call. Should: group `learn`. Should not: groups correct, notcorrect, quiet.
  correct a `krouter_correct` call. Should: group `correct`. Should not: groups offer, learn, notcorrect, quiet.
Also printed: `krouter_ask` calls, `krouter_note` calls, calls that errored, and the learn calls with `same_as`.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ID = re.compile(r"[\[〔](C\d\d)[\]〕]")
SHOULD = {"offer": {"offer"}, "learn": {"learn"}, "correct": {"correct"}}
SHOULD_NOT = {"offer": {"correct", "notcorrect", "quiet"}, "learn": {"correct", "notcorrect", "quiet"},
              "correct": {"offer", "learn", "notcorrect", "quiet"}}


def acts(rec: dict, sc: dict) -> dict:
    text = "\n".join(rec.get("messages", []))
    ids = set(ID.findall(text))
    tools = [c.get("tool") for c in rec.get("calls", [])]
    return {"offer": bool(ids), "offer_right": sc.get("card") in ids, "learn": "krouter_learn" in tools,
            "correct": "krouter_correct" in tools, "ask": tools.count("krouter_ask"), "note": tools.count("krouter_note"),
            "errors": sum(1 for c in rec.get("calls", []) if c.get("status") not in (None, "completed")),
            "same_as": sum(1 for c in rec.get("calls", []) if c.get("tool") == "krouter_learn"
                           and (c.get("arguments") or {}).get("same_as"))}


def main() -> int:
    scenarios = {s["id"]: s for s in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))}
    recs = {}
    for f in Path(sys.argv[2]).glob("*/record.json"):
        r = json.loads(f.read_text(encoding="utf-8"))
        recs[r["id"]] = r
    failed = sorted(i for i, r in recs.items() if r.get("rc") not in (0, None))  # e.g. a usage limit: the model never saw the task
    got = {i: acts(r, scenarios[i]) for i, r in recs.items() if i in scenarios and i not in failed}
    missing = sorted(set(scenarios) - set(got))
    print(f"runs: {len(got)} of {len(scenarios)}" + (f"; missing {missing}" if missing else "")
          + (f"; FAILED (rc != 0, not counted): {failed}" if failed else ""))
    for b in ("offer", "learn", "correct"):
        do = [i for i in got if scenarios[i]["group"] in SHOULD[b]]
        no = [i for i in got if scenarios[i]["group"] in SHOULD_NOT[b]]
        line = f"{b:8} should: {sum(got[i][b] for i in do)} / {len(do)}"
        if b == "offer":
            line += f" (its own card: {sum(got[i]['offer_right'] for i in do)} / {len(do)})"
        print(line + f"   should not: {sum(got[i][b] for i in no)} / {len(no)}")
    print("asked krouter_ask in", sum(1 for i in got if got[i]["ask"]), "runs;", "krouter_note in",
          sum(1 for i in got if got[i]["note"]), "; errored calls", sum(got[i]["errors"] for i in got),
          "; learn with same_as", sum(got[i]["same_as"] for i in got))
    for i in sorted(got):
        g = got[i]
        print(f"  {i} [{scenarios[i]['group']}] ask={g['ask']} offer={g['offer']} learn={g['learn']} correct={g['correct']} note={g['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
