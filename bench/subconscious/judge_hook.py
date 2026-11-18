#!/usr/bin/env python3
"""Set 51, condition J (bench/memory_honesty/HELDOUT.md): the hook brings nothing, so it asks a model which of the
closest pages, if any, the message is about, and brings that one.

    DEEPSEEK_API_KEY=... python3 bench/subconscious/judge_hook.py --out DIR [--crowd N] [--dry]

Set 45's dev half through `recollect.recollect()` as `session_hook.py prompt` runs it, on set 45's own vault (vault3
with the overlay; `--crowd N` adds the set 35 distractor pages). Where the hook brought nothing and `candidates.py`
gives candidates (up to K_JUDGE), one call to `deepseek-flash` (temperature 0, `candidates.ask`), and the page it
names counts as brought, by route `judge`. Scored as set 45 scores the hook alone. Writes DIR/judge.jsonl (each
message's candidates, the model's answer, the seconds the call took) and DIR/brought.jsonl. `--dry` makes no call and
prints how many messages would ask. The key is read from the environment and written nowhere.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--crowd", type=int, default=0)
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    import set45  # puts skill/krouter/scripts (or SET45_SCRIPTS) on the path
    import run as set32
    import tool_host as th
    import candidates
    import recollect

    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key and not args.dry:
        print("DEEPSEEK_API_KEY is not set", file=sys.stderr)
        return 2
    rows = set45.case_file("set45dev")
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["KROUTER_CACHE_DIR"] = str(Path(tmp) / "cache")
        os.environ["KROUTER_STATE_DIR"] = str(Path(tmp) / "state")
        os.environ["KROUTER_NO_QUERY_LOG"] = "1"
        v = set32.make_vault(Path(tmp))
        if args.crowd:
            import both

            both.add_crowd(v, args.crowd, newer=False)
        import recall_index

        recall_index.recall(v, "warm up the index")
        brought = {r["id"]: recollect.recollect(v, r["text"], recollect.DEFAULT_ROUTES) for r in rows}
        cands = {r["id"]: ([] if brought[r["id"]] else candidates.candidates(v, r["text"], set(), candidates.K_JUDGE))
                 for r in rows}
    asking = [r for r in rows if cands[r["id"]]]
    print(f"cases: {len(rows)}  the hook brought a page for {sum(bool(b) for b in brought.values())}  "
          f"messages that ask the model: {len(asking)}")
    if args.dry:
        return 0

    def one(r: dict) -> dict:
        c = cands[r["id"]]
        t = time.perf_counter()
        d = th.call([{"role": "user", "content": candidates.ask(r["text"], c, r["lang"])}], None, key)
        took = time.perf_counter() - t
        reply = d["choices"][0]["message"].get("content") or ""
        n = candidates.pick(reply, len(c))
        return {"id": r["id"], "candidates": [x["real"] for x in c], "reply": reply.strip()[:80], "pick": n,
                "page": c[n - 1]["real"] if n else "", "seconds": round(took, 2), "model": d.get("model", ""),
                "tokens": (d.get("usage") or {}).get("total_tokens", 0)}

    with ThreadPoolExecutor(max_workers=th.WORKERS) as pool:
        got = list(pool.map(one, asking))
    (args.out / "judge.jsonl").write_text("".join(json.dumps(g, ensure_ascii=False) + "\n" for g in got), encoding="utf-8")
    for g in got:
        if g["page"]:
            brought[g["id"]] = [{"real": g["page"], "rel": g["page"], "route": "judge", "word": "", "how": "", "notes": [],
                                 "related": []}]
    (args.out / "brought.jsonl").write_text("".join(json.dumps(
        {"id": r["id"], "brought": [h["real"] for h in brought[r["id"]]], "routes": [h["route"] for h in brought[r["id"]]]},
        ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    secs = sorted(g["seconds"] for g in got)
    print(f"model: {sorted({g['model'] for g in got})}  calls: {len(got)}  said a page: {sum(bool(g['page']) for g in got)}  "
          f"tokens: {sum(g['tokens'] for g in got)}")
    print(f"seconds per call: median {statistics.median(secs):.2f}  p90 {secs[int(len(secs) * 0.9)]:.2f}  max {secs[-1]:.2f}")
    set45.report(rows, brought, f"hook + judge  crowd: {args.crowd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
