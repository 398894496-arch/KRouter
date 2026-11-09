#!/usr/bin/env python3
"""Scale: how long the first lookup (index build) and later lookups take on a vault of N pages, and peak memory.

Each lookup runs `route_knowledge.py search <question>` in its own process, as the MCP server and the agent rules do,
so the times include interpreter start. The first lookup builds the full-text index in an empty cache; later ones
walk the vault to check file times and update nothing. Peak memory is the largest resident size of any lookup process.

    python3 bench/scale/gen.py 10000 /tmp/v10000            # a synthetic vault (template + N pages)
    python3 bench/scale/run.py /tmp/v10000 --queries 30

Nothing is sent anywhere; the cache goes to a temporary folder unless KROUTER_CACHE_DIR is set.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROUTER = REPO / "skill/krouter-obsidian/scripts/route_knowledge.py"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen import EN, ZH  # noqa: E402

try:
    import resource
except ImportError:  # Windows
    resource = None


def peak_children_mb() -> float:
    if resource is None:
        return float("nan")
    rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024  # bytes on macOS, KiB on Linux


def lookup(vault: Path, env: dict, question: str) -> tuple[float, str]:
    t = time.perf_counter()
    out = subprocess.run([sys.executable, str(ROUTER), "search", question], env={**env, "OBSIDIAN_VAULT": str(vault)},
                         capture_output=True, text=True, timeout=1800).stdout
    refused = any(ln.startswith("recall: none") for ln in out.splitlines())
    return time.perf_counter() - t, "refused" if refused else "answered"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("vault")
    ap.add_argument("--queries", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20261109)
    args = ap.parse_args()
    vault = Path(args.vault).resolve()
    pages = sum(1 for p in vault.rglob("*.md"))
    rnd = random.Random(args.seed)
    questions = []
    for i in range(args.queries):  # two in three should match some page, one in three asks about nothing in the vault
        if i % 3 == 2:
            questions.append(f"{rnd.choice(['量子火锅', '月球签证', 'zebra quota'])}怎么定的？")
        else:
            questions.append(f"{rnd.choice(ZH)}{rnd.choice(ZH)} {rnd.choice(EN)} 是怎么定的？")
    with tempfile.TemporaryDirectory() as tmp:
        env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
        env.update(KROUTER_NO_QUERY_LOG="1", KROUTER_CACHE_DIR=os.environ.get("KROUTER_CACHE_DIR") or tmp,
                   KROUTER_STATE_DIR=str(Path(tmp) / "state"))
        first, _ = lookup(vault, env, questions[0])
        times, statuses = [], []
        for q in questions:
            dt, st = lookup(vault, env, q)
            times.append(dt)
            statuses.append(st)
        cache_mb = sum(p.stat().st_size for p in Path(env["KROUTER_CACHE_DIR"]).rglob("*") if p.is_file()) / 1e6
    times.sort()
    p95 = times[min(len(times) - 1, int(round(0.95 * len(times))) - 1)]
    print(json.dumps({"pages": pages, "vault_mb": round(sum(p.stat().st_size for p in vault.rglob("*.md")) / 1e6, 1),
                      "first_lookup_s": round(first, 2), "lookups": len(times),
                      "p50_s": round(statistics.median(times), 3), "p95_s": round(p95, 3),
                      "peak_rss_mb": round(peak_children_mb(), 1), "index_mb": round(cache_mb, 1),
                      "python": sys.version.split()[0], "platform": sys.platform,
                      "answered": statuses.count("answered"), "refused": statuses.count("refused")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
