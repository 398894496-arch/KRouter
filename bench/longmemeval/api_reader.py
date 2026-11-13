#!/usr/bin/env python3
"""Set 22, sixth amendment (bench/memory_honesty/HELDOUT.md): the same 500 reader prompts, read by another model through
its API (no agent in between). Only the reader changes.

    python3 bench/longmemeval/api_reader.py check   # rebuild the 500 prompts from set 22's pages; compare with the stored ones
    DEEPSEEK_API_KEY=... python3 bench/longmemeval/api_reader.py run --out bench/longmemeval/results/2026-11-14-deepseek-reader.set22.jsonl

The prompt is `qa.py`'s `reader_prompt` with the pages KRouter 2.1.1 handed over in set 22
(`~/.local/state/krouter-eval/lme-set22/outputs.krouter.jsonl`), sent as the only user message, temperature 0, one call
per question. The key is read from the environment and never written. A prompt the provider rejects as too long or
malformed (HTTP 400, 413, 422) is recorded as not answered and counted wrong; nothing is cut. A network error or a
server error (5xx) is resumed at least 30 s later, at most 5 times; a rate-limit or authentication refusal (401, 402,
403, 429) stops the run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import qa  # noqa: E402

DATA = Path(os.environ.get("KROUTER_LME_DATA") or Path.home() / ".cache/krouter-eval/lme-data/longmemeval_s_cleaned.json")
OUTPUTS = Path.home() / ".local/state/krouter-eval/lme-set22/outputs.krouter.jsonl"
STORED = Path.home() / ".cache/krouter-eval/set22/reader_jsonl"
URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"  # 只用 flash，写死；返回的 model 里出现 pro 就停
MAX_TOKENS = 8192
WORKERS = 4
NOT_ANSWERED = (400, 413, 422)
STOP = (401, 402, 403, 429)


def jsonl(path: Path) -> list[dict]:
    """JSON Lines split on "\\n" only: the prompts hold U+2028, which `str.splitlines` would split on."""
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").split("\n") if x.strip()]


def prompts() -> dict[str, str]:
    data = qa.load_data(DATA)
    outs = {o["id"]: o for o in jsonl(OUTPUTS)}
    return {q: qa.reader_prompt(it, [] if outs[q]["refused"] else outs[q]["cited"]) for q, it in data.items()}


def check(_args) -> int:
    p = prompts()
    stored = {r["qid"]: r["prompt"] for f in sorted(STORED.glob("*.jsonl")) for r in jsonl(f)}
    same = sum(p[q] == s for q, s in stored.items())
    reused = [r["qid"] for r in jsonl(STORED.parent / "reused.jsonl")]
    data = qa.load_data(DATA)
    earlier = jsonl(STORED.parent / "reuse_set11_12.jsonl")
    reused_same = sum(any(r["qid"] == q and p[q] == qa.reader_prompt(data[q], [] if r["refused"] else r["sessions"])
                          for r in earlier) for q in reused)
    print(json.dumps({"prompts": len(p), "stored": len(stored), "identical_to_stored": same,
                      "reused_from_sets_11_12": len(reused), "reused_identical_to_sets_11_12": reused_same, "not_stored_and_not_reused": sorted(set(p) - set(stored) - set(reused)),
                      "chars_max": max(len(x) for x in p.values()), "chars_total": sum(len(x) for x in p.values())}))
    return 0 if same == len(stored) and reused_same == len(reused) else 1


class Stop(Exception):
    pass


class Net(Exception):
    pass


def call(prompt: str, key: str) -> dict:
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0,
                       "max_tokens": MAX_TOKENS}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                                          "User-Agent": "bench-client"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8", "replace")).get("error", {}).get("message", "")[:300]
        except (ValueError, OSError, AttributeError):
            msg = ""
        if e.code in NOT_ANSWERED:
            return {"status": "not_answered", "http": e.code, "message": msg, "response": ""}
        if e.code in STOP:
            raise Stop(json.dumps({"http": e.code, "message": msg}))
        raise Net(f"http {e.code}: {msg}")
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise Net(f"{type(e).__name__}: {str(getattr(e, 'reason', e))[:200]}")
    model = d.get("model", "")
    if "pro" in model.lower():
        raise Stop(json.dumps({"unexpected_model": model}))
    ch = d["choices"][0]
    return {"status": "answered", "response": ch["message"].get("content") or "", "finish_reason": ch.get("finish_reason"),
            "model": model, "usage": {k: (d.get("usage") or {}).get(k) for k in ("prompt_tokens", "completion_tokens")}}


def run_once(out: Path, key: str) -> int:
    """0 done, 1 stopped (refusal), 2 network (resumable)."""
    p = prompts()
    done = {r["qid"] for r in jsonl(out)} if out.exists() else set()
    todo = [q for q in p if q not in done]
    lock, flag = threading.Lock(), {"stop": None, "net": None}

    def one(q: str) -> None:
        if flag["stop"] or flag["net"]:
            return
        try:
            rec = call(p[q], key)
        except Stop as e:
            flag["stop"] = f"{q} {e}"
            return
        except Net as e:
            flag["net"] = f"{q} {e}"
            return
        with lock:
            with out.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"qid": q, **rec}, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(one, todo))
    n = len({r["qid"] for r in jsonl(out)}) if out.exists() else 0
    if flag["stop"]:
        print(json.dumps({"stopped": flag["stop"], "done": n}), file=sys.stderr, flush=True)
        return 1
    if flag["net"]:
        print(json.dumps({"network": flag["net"], "done": n}), file=sys.stderr, flush=True)
        return 2
    print(json.dumps({"done": n}), file=sys.stderr, flush=True)
    return 0


def run(args) -> int:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY is not set")
    out = Path(args.out)
    for attempt in range(6):
        rc = run_once(out, key)
        if rc != 2:
            return rc
        if attempt < 5:
            print(json.dumps({"resume": attempt + 1}), file=sys.stderr, flush=True)
            time.sleep(30)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["check", "run"])
    ap.add_argument("--out")
    args = ap.parse_args()
    return check(args) if args.cmd == "check" else run(args)


if __name__ == "__main__":
    raise SystemExit(main())
