#!/usr/bin/env python3
"""Set 22, third amendment (bench/memory_honesty/HELDOUT.md): the same 500 stored replies graded again by a judge from
another model family. Only the judge changes; no question is read again.

    GROQ_API_KEY=... python3 bench/longmemeval/second_judge.py run \
        --data ~/.cache/krouter-eval/lme-data/longmemeval_s_cleaned.json \
        --replies bench/longmemeval/results/2026-11-13-sonnet-qa.set22.jsonl \
        --out bench/longmemeval/results/2026-11-13-gptoss-judge.set22.jsonl
    python3 bench/longmemeval/second_judge.py report --data ... --replies ... --out ...

The prompt is `qa.py`'s `judge_prompt` (LongMemEval's templates), sent as the only user message, temperature 0. What is
sent: the question, the benchmark's answer and the stored reply. The key is read from the environment and never written.
The verdict is the reply's first word (`yes` / `no`, case and punctuation ignored); anything else is `unparsed`. Calls
are paced by the provider's rate-limit headers; an HTTP error or a rate-limit refusal stops the run (rerunning `run`
skips the questions already in `--out`, but the registration says a stop is reported, not retried until the quota is
gone).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import qa  # noqa: E402
import lme  # noqa: E402

URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"


def parse(reply: str) -> str:
    words = re.findall(r"[a-z]+", reply.strip().lower())
    return words[0] if words and words[0] in ("yes", "no") else "unparsed"


def _seconds(raw: str) -> float:
    """'2m59.5s' / '7.66s' / '120ms' -> seconds."""
    total = 0.0
    for num, unit in re.findall(r"([\d.]+)(ms|s|m|h)", raw or ""):
        total += float(num) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
    return total


def call(prompt: str, key: str) -> tuple[str, dict]:
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0,
                       "max_completion_tokens": 4096}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                                          "User-Agent": "bench-client"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
        return d["choices"][0]["message"].get("content") or "", {k.lower(): v for k, v in r.headers.items()}


def run(args) -> int:
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        raise SystemExit("GROQ_API_KEY is not set")
    data = qa.load_data(Path(args.data))
    replies = qa.read_jsonl([Path(args.replies)])
    out = Path(args.out)
    done = {json.loads(x)["qid"] for x in out.read_text().splitlines() if x.strip()} if out.exists() else set()
    n = 0
    for row in replies:
        if row["qid"] in done:
            continue
        prompt = qa.judge_prompt(data[row["qid"]], row["response"])
        try:
            reply, h = call(prompt, key)
        except urllib.error.HTTPError as e:
            print(json.dumps({"stopped": row["qid"], "http": e.code, "done": len(done) + n}), file=sys.stderr)
            return 1
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
            print(json.dumps({"stopped": row["qid"], "error": type(e).__name__, "reason": str(getattr(e, "reason", e))[:200],
                              "done": len(done) + n}), file=sys.stderr)
            return 1
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"qid": row["qid"], "reply": reply, "verdict": parse(reply),
                                 "sonnet": "yes" if qa.correct(str(row["verdict"])) else "no"}, ensure_ascii=False) + "\n")
        n += 1
        # 按限流头放慢：剩余请求数或 token 数见底就等到重置，不去撞 429
        if int(h.get("x-ratelimit-remaining-requests", "99") or 99) < 2:
            time.sleep(_seconds(h.get("x-ratelimit-reset-requests", "")) + 1)
        if int(h.get("x-ratelimit-remaining-tokens", "99999") or 99999) < 3000:
            time.sleep(_seconds(h.get("x-ratelimit-reset-tokens", "")) + 1)
        if n % 50 == 0:
            print(f"{len(done) + n} judged", file=sys.stderr, flush=True)
    print(json.dumps({"judged_now": n, "total": len(done) + n}), file=sys.stderr)
    return 0


def report(args) -> int:
    data = qa.load_data(Path(args.data))
    rows = [{"id": q, "abs": "_abs" in q} for q in data]
    split = lme.split_of(rows)
    got = {r["qid"]: r for r in qa.read_jsonl([Path(args.out)])}
    sonnet = {r["qid"]: qa.correct(str(r["verdict"])) for r in qa.read_jsonl([Path(args.replies)])}
    second = {q: got.get(q, {}).get("verdict") == "yes" for q in data}
    held = [q for q in data if split[q] == "heldout"]
    flags = [second[q] for q in data]
    agree = sum(second[q] == sonnet[q] for q in data if q in got)
    out = {"judged": len(got), "unparsed": sorted(q for q, r in got.items() if r["verdict"] == "unparsed"),
           "all": {"right": sum(flags), "of": len(flags), "pct": round(100 * sum(flags) / len(flags), 1),
                   "ci95": qa.interval(flags, 20261113)},
           "heldout": {"right": sum(second[q] for q in held), "of": len(held),
                       "pct": round(100 * sum(second[q] for q in held) / len(held), 1),
                       "ci95": qa.interval([second[q] for q in held], 20261113)},
           "dev": sum(second[q] for q in data if split[q] == "dev"), "abs": sum(second[q] for q in data if split[q] == "abs"),
           "agree": agree, "sonnet_yes_second_no": sorted(q for q in got if sonnet[q] and not second[q]),
           "sonnet_no_second_yes": sorted(q for q in got if not sonnet[q] and second[q])}
    by = {}
    for q, it in data.items():
        t = "abstention" if "_abs" in q else it["question_type"]
        by.setdefault(t, [0, 0]); by[t][0] += second[q]; by[t][1] += 1
    out["by_type"] = by
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "report"])
    ap.add_argument("--data", required=True)
    ap.add_argument("--replies", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    return run(args) if args.cmd == "run" else report(args)


if __name__ == "__main__":
    raise SystemExit(main())
