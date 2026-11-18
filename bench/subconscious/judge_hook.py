#!/usr/bin/env python3
"""Set 51, condition J (bench/memory_honesty/HELDOUT.md): the hook brings nothing, so it asks a model which of the
closest pages, if any, the message is about, and brings that one.

    DEEPSEEK_API_KEY=... python3 bench/subconscious/judge_hook.py --out DIR [--crowd N] [--dry]
    OPENROUTER_API_KEY=... python3 bench/subconscious/judge_hook.py --out DIR [--crowd N] --decider MODEL    # set 52

Set 45's dev half through `recollect.recollect()` as `session_hook.py prompt` runs it, on set 45's own vault (vault3
with the overlay; `--crowd N` adds the set 35 distractor pages). Where the hook brought nothing and `candidates.py`
gives candidates (up to K_JUDGE), one call to `deepseek-flash` (temperature 0, `candidates.ask`), and the page it
names counts as brought, by route `judge`. Scored as set 45 scores the hook alone. Writes DIR/judge.jsonl (each
message's candidates, the model's answer, the seconds the call took) and DIR/brought.jsonl. `--dry` makes no call and
prints how many messages would ask. The key is read from the environment and written nowhere.

Set 52: `--decider MODEL` asks a decision model through OpenRouter's Decisions API instead (`candidates.question`: one
`choice` question, an option per candidate and `none`); the option it picks is the page brought. `:free` models are
called one at a time, about three seconds apart; a 429 or a 5xx is retried up to five times. The seconds recorded are
the last attempt's, without the waiting.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
OPENROUTER = "https://openrouter.ai/api/alpha/decisions"


def answer_of(d: dict, name: str) -> dict | None:
    """The answer to question `name`, wherever the response keeps it (`answers`, `decisions`, `results`, or the top)."""
    for holder in (d.get("answers"), d.get("decisions"), d.get("results"), d.get("output"), d):
        if isinstance(holder, dict) and isinstance(holder.get(name), dict):
            return holder[name]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--crowd", type=int, default=0)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--decider", default="", help="an OpenRouter decision model id; empty: deepseek-flash (set 51)")
    ap.add_argument("--engine", action="store_true", help="ask through the engine (`recollect.judged`, "
                    "KROUTER_RECALL_JUDGE=1) instead of this script's own call: the tier as shipped")
    args = ap.parse_args()
    import set45  # puts skill/krouter/scripts (or SET45_SCRIPTS) on the path
    import run as set32
    import tool_host as th
    import candidates
    import recollect

    name = "OPENROUTER_API_KEY" if args.decider else "DEEPSEEK_API_KEY"
    key = os.environ.get(name, "")
    if not key and not args.dry:
        print(f"{name} is not set", file=sys.stderr)
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
        if args.engine and not args.dry:
            os.environ.update(KROUTER_RECALL_JUDGE="1", KROUTER_JUDGE_KEY=key)
            for r in rows:
                if not brought[r["id"]]:
                    brought[r["id"]] = recollect.judged(v, r["text"])
            log = Path(os.environ["KROUTER_STATE_DIR"]) / recollect.JUDGE_LOG
            asked = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []
            (args.out / "judge.jsonl").write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in asked), encoding="utf-8")
            (args.out / "brought.jsonl").write_text("".join(json.dumps(
                {"id": r["id"], "brought": [h["real"] for h in brought[r["id"]]], "routes": [h["route"] for h in brought[r["id"]]]},
                ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
            secs = sorted(a["seconds"] for a in asked) or [0.0]
            print(f"engine: questions asked {len(asked)}  named a page {sum(a['picked'] for a in asked)}  "
                  f"errors {dict((e, sum(1 for a in asked if a['error'] == e)) for e in sorted({a['error'] for a in asked} - {''}))}")
            print(f"seconds per call: median {statistics.median(secs):.2f}  p90 {secs[int(len(secs) * 0.9)]:.2f}  max {secs[-1]:.2f}")
            set45.report(rows, brought, f"hook + judge through the engine  crowd: {args.crowd}")
            return 0
    asking = [r for r in rows if cands[r["id"]]]
    print(f"cases: {len(rows)}  the hook brought a page for {sum(bool(b) for b in brought.values())}  "
          f"messages that ask the model: {len(asking)}")
    if args.dry:
        return 0

    def decide(r: dict) -> dict:
        c = cands[r["id"]]
        body = {"model": args.decider, "state": r["text"], "questions": {"page": candidates.question(c, r["lang"])}}
        d, took, err = {}, 0.0, ""
        for attempt in range(5):
            req = urllib.request.Request(OPENROUTER, data=json.dumps(body).encode(), headers={
                "Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "bench-client"})
            t = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    d = json.load(resp)
                took, err = time.perf_counter() - t, ""
                break
            except urllib.error.HTTPError as e:
                err = f"http {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
                if e.code not in (408, 429, 500, 502, 503, 504):
                    break
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                err = f"{type(e).__name__}: {str(getattr(e, 'reason', e))[:120]}"
            time.sleep(4 * (attempt + 1))
        ans = answer_of(d, "page")
        n, conf = candidates.chosen(ans, len(c))
        if args.decider.endswith(":free"):
            time.sleep(3.2)
        return {"id": r["id"], "candidates": [x["real"] for x in c], "reply": str((ans or {}).get("choice", ""))[:40],
                "pick": n, "page": c[n - 1]["real"] if n else "", "confidence": round(conf, 4),
                "seconds": round(took, 2), "model": str(d.get("model", args.decider)), "error": err,
                "tokens": (d.get("usage") or {}).get("input_tokens") or (d.get("usage") or {}).get("prompt_tokens") or 0}

    def one(r: dict) -> dict:
        if args.decider:
            return decide(r)
        c = cands[r["id"]]
        t = time.perf_counter()
        d = th.call([{"role": "user", "content": candidates.ask(r["text"], c, r["lang"])}], None, key)
        took = time.perf_counter() - t
        reply = d["choices"][0]["message"].get("content") or ""
        n = candidates.pick(reply, len(c))
        return {"id": r["id"], "candidates": [x["real"] for x in c], "reply": reply.strip()[:80], "pick": n,
                "page": c[n - 1]["real"] if n else "", "seconds": round(took, 2), "model": d.get("model", ""),
                "tokens": (d.get("usage") or {}).get("total_tokens", 0)}

    with ThreadPoolExecutor(max_workers=1 if args.decider.endswith(":free") else th.WORKERS) as pool:
        got = list(pool.map(one, asking))
    failed = [g for g in got if g.get("error")]
    if failed:
        print(f"calls that failed after retries: {len(failed)} (counted as no page); first: {failed[0]['error'][:160]}")
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
    set45.report(rows, brought, f"hook + judge ({args.decider or 'deepseek-flash'})  crowd: {args.crowd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
