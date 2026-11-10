#!/usr/bin/env python3
"""Set 34 speed (bench/memory_honesty/HELDOUT.md): the whole prompt hook process, as the app runs it.

    python3 bench/subconscious/speed.py --vault V --hit "message that names a page" --miss "message that does not"

Builds the recall index first (as the router, the MCP server or the hook's own detached refresh would have). Cold:
the first run in a new state folder with the scripts' bytecode cache deleted (as right after install) and the phrase
table not yet compiled; the OS file cache is not flushed (that needs root). Warm: the rest, each with a new session id
so nothing is skipped as a repeat. (`PYTHONPYCACHEPREFIX` is not used: it adds about 90 ms to every run.)
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "skill/krouter/scripts/session_hook.py"


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def once(env: dict, text: str, sid: str) -> tuple[float, str]:
    t = time.perf_counter()
    r = subprocess.run([sys.executable, str(HOOK), "prompt"], input=json.dumps({"prompt": text, "session_id": sid}),
                       env=env, capture_output=True, text=True)
    return (time.perf_counter() - t) * 1000, r.stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True)
    ap.add_argument("--hit", required=True)
    ap.add_argument("--miss", required=True)
    ap.add_argument("--warm", type=int, default=200)
    ap.add_argument("--cold", type=int, default=20)
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp())
    base = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    base.update(KROUTER_VAULT=a.vault, KROUTER_CACHE_DIR=str(tmp / "cache"), KROUTER_NO_QUERY_LOG="1",
                KROUTER_RECALL_PROMPT=os.environ.get("ROUTES", "1"))
    t = time.perf_counter()
    subprocess.run([sys.executable, str(REPO / "skill/krouter/scripts/recall_index.py"), "--vault", a.vault, "--stats"],
                   env=base, capture_output=True, check=True)
    print(f"index build: {(time.perf_counter() - t):.1f} s")
    for name, text in (("hit", a.hit), ("miss", a.miss)):
        cold = []
        import glob
        import shutil

        for i in range(a.cold):
            shutil.rmtree(HOOK.parent / "__pycache__", ignore_errors=True)
            for f in glob.glob(str(tmp / "cache" / "mentions-*")):
                os.unlink(f)
            env = {**base, "KROUTER_STATE_DIR": str(tmp / f"cold-{name}-{i}")}
            ms, out = once(env, text, f"c{i}")
            cold.append(ms)
        env = {**base, "KROUTER_STATE_DIR": str(tmp / f"warm-{name}")}
        once(env, text, "prime")
        warm, outs = [], set()
        for i in range(a.warm):
            ms, out = once(env, text, f"w{i}")
            warm.append(ms)
            outs.add(bool(out.strip()))
        print(f"{name}: printed={sorted(outs)}  cold p50 {statistics.median(cold):.0f} ms p95 {pct(cold, 95):.0f} ms (n={len(cold)})"
              f"  warm p50 {statistics.median(warm):.0f} ms p95 {pct(warm, 95):.0f} ms (n={len(warm)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
