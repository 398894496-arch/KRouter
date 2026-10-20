#!/usr/bin/env python3
"""Nightly upkeep runner: the five steps in order, each one's outcome written where the host can see it.

import_sessions → import_claude_mem → compile_subconscious → reconsolidate → consolidate_topics → answer_cards → checkup → backup.
The last writes an encrypted, restore-checked archive of the vault into the backup folder when one is set
(`backup.py init --dir`), and is `off` otherwise. The first one
imports yesterday's agent sessions only after the host said yes (`import_sessions.py --consent`), the second
re-imports claude-mem's memory the same way; until then they are `off`, which is not a problem to report. Each step is a
separate process; one failing does not stop the others. Outcomes (ran / skipped / partial / failed,
the reason, the model lane, how many model calls and how many characters left the machine) go to
`90 系统文件/自动化/夜间维护.md` and onto the health page (`nightly`, `nightly_at`), where `status`
reads them and raises `host_action` when the steps are skipped or failing.

`--dry-run` calls no model and writes nothing: it lists, per step, what would be sent, roughly how
many tokens, and which files would be written.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import llm  # noqa: E402
import notify  # noqa: E402
import zones  # noqa: E402

STEPS = ("import_sessions", "import_claude_mem", "compile_subconscious", "reconsolidate", "consolidate_topics", "answer_cards", "checkup",
         "backup")
MODEL_STEPS = {"import_sessions", "import_claude_mem", "reconsolidate", "consolidate_topics", "answer_cards"}
REPORT = "90 系统文件/自动化/夜间维护.md"
HEALTH = "90 系统文件/自动化/日更健康.md"


def classify(rc: int, out: str) -> tuple[str, str]:
    """(state, reason) from a step's exit code and output."""
    low = out.lower()
    if rc != 0:
        return "failed", (out.strip().splitlines() or [f"rc={rc}"])[-1][:200]
    if '"import": "off"' in out:
        return "off", "会话导入没开（import_sessions.py --consent 开启）"
    if '"backup": "partial"' in out:
        return "partial", "备份只写成了一部分位置：" + out.split('"errors": ', 1)[-1][:160]
    if '"backup": "off"' in out:
        return "off", "备份没开（backup.py init --dir <会同步到别处的文件夹> 开启）"
    if '"claude_mem": "off"' in out or '"claude_mem": "absent"' in out:
        return "off", "claude-mem 导入没开，或本机没有 claude-mem（import_claude_mem.py --consent 开启）"
    for line in out.splitlines():
        if "skipped" in line.lower():
            return "skipped", line.strip()[:200]
    if '"status": "failed"' in low or "batch failed" in low or "verify failed" in low:
        bad = [ln for ln in out.splitlines() if "failed" in ln.lower()]
        return "partial", bad[0].strip()[:200]
    return "ok", ""


def lane(vault: Path) -> str:
    steps = llm.plan(vault)  # detects once; the result is cached for this process
    if not steps:
        return "none"
    kind, detail = steps[0]
    return f"cli {Path(detail).name}" if kind == "cli" else kind


def set_frontmatter(path: Path, fields: dict[str, str]) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not text.startswith("---\n") or "\n---" not in text[4:]:
        return
    end = text.index("\n---", 4)
    lines = text[4:end].splitlines()
    for key, val in fields.items():
        for i, line in enumerate(lines):
            if line.startswith(key + ":"):
                lines[i] = f"{key}: {val}"
                break
        else:
            lines.append(f"{key}: {val}")
    path.write_text("---\n" + "\n".join(lines) + text[end:], encoding="utf-8")


def overall(results: list[dict]) -> str:
    states = {r["state"] for r in results}
    if "failed" in states:
        return "failed"
    if "skipped" in states:  # 有一步因为没有可用模型而没做：这是宿主要处理的事
        return "skipped"
    if states - {"ok", "off"}:
        return "degraded"
    return "ok"


def run_step(step: str, vault: Path, extra: list[str], dry: bool) -> dict:
    path = HERE / f"{step}.py"
    if not path.is_file():
        return {"step": step, "state": "missing", "reason": "script not found"}
    argv = [sys.executable, str(path), "--vault", str(vault)]
    if step in ("import_sessions", "import_claude_mem"):
        argv.append("--nightly")
    if step in MODEL_STEPS:
        argv += extra
    if dry:
        if step not in MODEL_STEPS:
            if step == "backup":
                return {"step": step, "state": "dry-run", "sends": "nothing (no model)",
                        "writes": ["an encrypted archive in the backup folder, if one is set"]}
            return {"step": step, "state": "dry-run", "sends": "nothing (no model)",
                    "writes": ["90 系统文件/自动化/下意识.md" if step == "compile_subconscious"
                               else "90 系统文件/自动化/下意识体检.md"]}
        argv.append("--dry-run")
    with tempfile.NamedTemporaryFile("r", suffix=".jsonl", delete=False) as fh:
        usage_log = fh.name
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_USAGE_LOG": usage_log}
    start = time.time()
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=3 * 3600)
        rc, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        rc, out = 124, "timed out after 3 h"
    calls = []
    try:
        calls = [json.loads(x) for x in Path(usage_log).read_text(encoding="utf-8").splitlines() if x.strip()]
    finally:
        Path(usage_log).unlink(missing_ok=True)
    if dry:
        chars = 0
        writes: list[str] = []
        for line in out.splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                chars += int(row.get("chars") or 0)
                writes += [w for w in row.get("writes") or [] if w not in writes]
        return {"step": step, "state": "dry-run", "chars": chars, "est_tokens": round(chars / 1.6),
                "writes": writes, "detail": out.strip()[-600:]}
    state, reason = classify(rc, out)
    sys.stderr.write(out)
    tok = [c.get("tokens_in", 0) + c.get("tokens_out", 0) for c in calls if "tokens_in" in c]
    return {"step": step, "state": state, "reason": reason, "seconds": round(time.time() - start),
            "model_calls": len(calls), "chars_sent": sum(c.get("chars_in", 0) for c in calls),
            **({"tokens": sum(tok)} if tok else {})}


def write_report(vault: Path, results: list[dict], state: str, lane_name: str, at: str) -> None:
    rows = []
    for r in results:
        cost = f"{r.get('model_calls', 0)} 次 / {r.get('chars_sent', 0)} 字" + (f" / {r['tokens']} tokens" if "tokens" in r else "")
        rows.append(f"| {r['step']} | {r['state']} | {cost} | {r.get('seconds', '')} | {r.get('reason', '').replace('|', '／')} |")
    text = "\n".join([
        "---", "title: 夜间维护", "status: generated", f"nightly_at: {at}", f"nightly: {state}", f"lane: {lane_name}", "---", "",
        "# 夜间维护", "",
        "机器生成，每晚覆盖。只记元数据（步骤、结果、调用次数、发出的字数），不记内容。", "",
        f"结果：**{state}**（通道：{lane_name}）", "",
        "| 步骤 | 结果 | 模型调用 / 发出 | 秒 | 原因 |", "|---|---|---|---|---|", *rows, "",
        "发出的内容：规则页 / 主题页全文（问答卡）、主题证据（主题档案）、路由器没答好的查询原文（夜间学习）；"
        "开了会话导入并选了提炼时，还有昨天会话的脱敏摘录。"
        "`KROUTER_NIGHTLY=0` 关掉；`run.sh --dry-run` 先看会发什么。", "",
    ])
    out = zones.path(vault, REPORT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT", ""))
    ap.add_argument("--cli", default="", help="pick a CLI explicitly for the model steps")
    ap.add_argument("--model", default="")
    ap.add_argument("--steps", default=",".join(STEPS))
    ap.add_argument("--dry-run", action="store_true", help="no model call, no write: list what would be sent")
    args = ap.parse_args()
    if not args.vault:
        print("set OBSIDIAN_VAULT", file=sys.stderr)
        return 2
    vault = Path(args.vault)
    extra = (["--cli", args.cli] if args.cli else []) + (["--model", args.model] if args.model else [])
    if args.cli:
        os.environ["KROUTER_LEARN_CLI"] = args.cli
    lane_name = lane(vault)
    steps = llm.plan(vault)
    if steps and steps[0][0] == "cli" and not args.cli:
        os.environ["KROUTER_WRITER"] = steps[0][1]  # 子进程不必再逐个探测 CLI 登录
    results = [run_step(s, vault, extra, args.dry_run) for s in args.steps.split(",") if s]
    if args.dry_run:
        total = sum(r.get("chars", 0) for r in results)
        print(json.dumps({"lane": lane_name, "est_tokens_total": round(total / 1.6), "steps": results},
                         ensure_ascii=False, indent=1))
        return 0
    state = overall(results)
    at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    write_report(vault, results, state, lane_name, at)
    set_frontmatter(zones.path(vault, HEALTH), {"nightly": state, "nightly_at": at})
    if state in notify.NIGHTLY:
        notify.send(notify.NIGHTLY[state], kind=f"nightly-{state}")
    print(json.dumps({"nightly": state, "lane": lane_name, "steps": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
