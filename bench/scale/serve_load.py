#!/usr/bin/env python3
"""Scale over HTTP: the MCP server under load, the way a team uses it.

Starts `mcp_server.py --http` on loopback for a vault (one bank, or the same vault as several banks), then asks
`krouter_ask` questions: first one caller at a time, then C callers at once, and reports p50 / p95 latency, answers
per second, failures, and the server's memory (its process and its workers: the peak while under load, which
includes `rg` reading files, and what stays resident afterwards).

    python3 bench/scale/gen.py 10000 /tmp/v10000
    python3 bench/scale/serve_load.py /tmp/v10000 --concurrency 1,8,32 --calls 200

Nothing is sent anywhere: the server listens on 127.0.0.1 only and the cache goes to a temporary folder.
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
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "skill/krouter-obsidian/scripts/mcp_server.py"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen import EN, ZH  # noqa: E402


def questions(n: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        if i % 2:
            out.append(f"{rng.choice(ZH)}{rng.choice(ZH)}现在用什么？")
        else:
            out.append(f"what did we decide about {rng.choice(EN)} {rng.choice(EN)}")
    return out


def rss_mb(pid: int) -> float:
    """Resident size of a process and its children, in MB (ps; 0 when ps is missing)."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,rss="], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return 0.0
    rows = [tuple(int(x) for x in ln.split()) for ln in out.splitlines() if len(ln.split()) == 3]
    kids, total, todo = {}, 0, [pid]
    for p, pp, _ in rows:
        kids.setdefault(pp, []).append(p)
    rss = {p: r for p, _, r in rows}
    while todo:
        p = todo.pop()
        total += rss.get(p, 0)
        todo += kids.get(p, [])
    return total / 1024


def ask(url: str, q: str) -> tuple[float, bool]:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "krouter_ask", "arguments": {"query": q}}}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json",
                                                         "Accept": "application/json, text/event-stream"})
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ok = not data.get("result", {}).get("isError") and "content" in data.get("result", {})
    except Exception:  # noqa: BLE001
        ok = False
    return time.perf_counter() - t, ok


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("vault")
    ap.add_argument("--concurrency", default="1,8,32", help="comma-separated caller counts")
    ap.add_argument("--calls", type=int, default=200, help="calls per concurrency level")
    ap.add_argument("--banks", type=int, default=1, help="serve the vault as this many banks and spread the calls")
    ap.add_argument("--seed", type=int, default=20261109)
    ap.add_argument("--server-arg", action="append", default=[], help="extra argument for mcp_server.py (repeat)")
    ap.add_argument("--server", default=str(SERVER), help="the mcp_server.py to run (to compare with another version)")
    args = ap.parse_args()
    vault = Path(args.vault).resolve()
    cache = tempfile.mkdtemp(prefix="krouter-scale-cache-")
    state = tempfile.mkdtemp(prefix="krouter-scale-state-")
    env = {**os.environ, "KROUTER_CACHE_DIR": cache, "KROUTER_STATE_DIR": state, "KROUTER_NO_QUERY_LOG": "1",
           "OBSIDIAN_VAULT": str(vault)}
    argv = [sys.executable, args.server, "--http", "127.0.0.1:0", *args.server_arg]
    if args.banks > 1:
        for i in range(args.banks):
            argv += ["--bank", f"b{i}={vault}"]
    t0 = time.perf_counter()
    proc = subprocess.Popen(argv, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    info = None
    while True:
        line = proc.stderr.readline()
        if not line:
            break
        if line.startswith("{") and "listening" in line:
            info = json.loads(line)
            break
    if not info:
        print("server did not start", file=sys.stderr)
        return 1
    ready = time.perf_counter() - t0
    urls = list((info.get("banks") or {}).values()) or [info["listening"]]
    qs = questions(max(args.calls, 50), args.seed)
    report = {"vault": str(vault), "pages": sum(1 for _ in vault.rglob("*.md")), "banks": len(urls),
              "server_args": args.server_arg, "ready_s": round(ready, 2), "levels": []}
    peak = rss_mb(proc.pid)
    try:
        for c in [int(x) for x in args.concurrency.split(",")]:
            jobs = [(urls[i % len(urls)], qs[i % len(qs)]) for i in range(args.calls)]
            t = time.perf_counter()
            with ThreadPoolExecutor(max_workers=c) as pool:
                res = list(pool.map(lambda j: ask(*j), jobs))
            wall = time.perf_counter() - t
            peak = max(peak, rss_mb(proc.pid))
            lat = [r[0] for r in res]
            report["levels"].append({"callers": c, "calls": len(res), "failed": sum(1 for r in res if not r[1]),
                                     "p50_ms": round(1000 * statistics.median(lat)), "p95_ms": round(1000 * pct(lat, 0.95)),
                                     "max_ms": round(1000 * max(lat)), "per_second": round(len(res) / wall, 1)})
        time.sleep(1)
        report["resident_mb"] = round(rss_mb(proc.pid))  # 压完以后：服务器加常驻查询进程，不含跑完的 rg
    finally:
        proc.terminate()
        proc.wait(timeout=20)
    report["peak_mb"] = round(peak)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
