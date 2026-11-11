#!/usr/bin/env python3
"""Lay out a set for a Claude Code subagent host: per scenario a project folder, a throwaway memory folder, a `kr`
wrapper (KROUTER_VAULT and the call log pointed at that scenario) and the host's session context (`kr_cli.py --context`).

    python3 bench/behavior/prep_claude.py SET.json WORKDIR [--only ID,ID]
Then one fresh subagent per scenario, given WORKDIR/<id>/prompt.txt; `finish_claude.py` turns the call log and the
subagent's last message into record.json for judge.py.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 宿主不许碰的、用户真实的知识库。公开版本里不写这台机器的路径；第 30、31 套测量时的提示词里是本机的真实路径，
# 也就是这里在那台机器上算出来的值（HELDOUT.md 第 30、31 套日志）
REAL_VAULT = os.environ.get("KROUTER_BENCH_REAL_VAULT") or str(Path.home() / "KnowledgeArchive")
sys.path.insert(0, str(HERE))
from make_fixture import build  # noqa: E402
from run_codex import write_project  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("set_json")
    ap.add_argument("workdir")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    work = Path(a.workdir).resolve()
    scenarios = json.loads(Path(a.set_json).read_text(encoding="utf-8"))
    if a.only:
        scenarios = [s for s in scenarios if s["id"] in a.only.split(",")]
    base = work / "_base"
    work.mkdir(parents=True, exist_ok=True)
    if not base.exists():
        build(base)
    for sc in scenarios:
        d = work / sc["id"]
        if d.exists():
            shutil.rmtree(d)
        mem, proj = d / "mem", d / "proj"
        proj.mkdir(parents=True)
        shutil.copytree(base, mem, symlinks=True)
        write_project(proj, sc["files"])
        kr = d / "kr"
        kr.write_text(f"#!/bin/sh\nexec env KROUTER_VAULT='{mem}' KROUTER_STATE_DIR='{d}/state' KROUTER_NO_QUERY_LOG=1 "
                      f"XDG_CONFIG_HOME='{d}/xdg' KR_CALL_LOG='{d}/calls.jsonl' python3 '{HERE}/kr_cli.py' \"$@\"\n")
        kr.chmod(kr.stat().st_mode | stat.S_IXUSR)
        ctx = subprocess.run([str(kr), "--context"], capture_output=True, text=True).stdout
        (d / "context.md").write_text(ctx, encoding="utf-8")
        (d / "prompt.txt").write_text(
            f"The context below was added to your session when it started (it comes from the user's memory integration).\n\n"
            f"{ctx}\n\n---\nShell helper for the tools above: `{kr}` (use it as $KR).\n"
            f"Your project folder is {proj}; work only inside it (and call the helper), and do not read or write anything "
            f"under {REAL_VAULT} or ~/.claude.\n\nThe user's message:\n\n{sc['prompt']}\n", encoding="utf-8")
        print(sc["id"], d / "prompt.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
