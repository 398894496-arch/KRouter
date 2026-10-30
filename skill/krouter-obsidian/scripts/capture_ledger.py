#!/usr/bin/env python3
"""What automatic capture changed, where you can see it, and one command to take a run back.

Capture writes memory without asking (session digests, judged corrections). In place of a yes/no gate, every run
that changes something leaves two traces: a section in `90 系统文件/自动化/记忆变更记录.md` (what was added, what a
change of mind replaced, which session it came from, how each correction candidate was judged) and, when the vault
is a git repository, one commit holding exactly the files that run wrote, tagged `[krouter-run <id>]`; the ledger
entry is committed separately, so undoing a run keeps its record. `import_sessions.py --undo <id>` reverts the run.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

import zones

LEDGER = "90 系统文件/自动化/记忆变更记录.md"
TAG = "[krouter-run {}]"


def run_id(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y%m%dT%H%M%S")


def _git(vault: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(vault), *args], capture_output=True, text=True, timeout=60,
                          stdin=subprocess.DEVNULL)


def is_repo(vault: Path) -> bool:
    try:
        return (vault / ".git").exists() and _git(vault, "rev-parse", "--is-inside-work-tree").returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _link(vault: Path, path: Path) -> str:
    rel = zones.canon(vault, str(path.relative_to(vault)).replace("\\", "/"))
    return f"[[{rel.removesuffix('.md')}]]"


def section(vault: Path, rid: str, pages: list[dict], verdicts: list[dict], removed: list[Path], undo: str,
            sha: str = "") -> str:
    """One run's entry. `pages`: [{path, agent, session, added: [line]}]; `verdicts`: [{said, ok, line, why, link}]."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    where = f"提交 `{sha[:10]}`；" if sha else "库不是 git 仓库，没有提交可撤；"
    out = [f"## {now} · run {rid}", "", f"{where}撤销这一轮：`{undo}`", ""]
    for p in pages:
        out.append(f"- 新增 {_link(vault, p['path'])}（会话 `{p['agent']}:{p['session'][:8]}`）")
        for ln in p["added"]:
            text = ln.lstrip("-* ").strip()
            out.append(f"  - {'取代：' if '→' in text else ''}{text}")
    if verdicts:
        ok = sum(1 for v in verdicts if v["ok"])
        out.append(f"- 纠正候选判定：成立 {ok}，不成立 {len(verdicts) - ok}")
        for v in verdicts:
            said = v["said"] if len(v["said"]) <= 80 else v["said"][:80] + " …"
            if v["ok"]:
                out.append(f"  - 成立：「{said}」→ {v['link']}：{v['line']}")
            else:
                out.append(f"  - 不成立：「{said}」：{v['why'] or '模型判定不是改主意或新规则'}")
    for path in removed:
        out.append(f"- 删除 `{path.name}`（标了 #不记，或被另一个会话完整包含）")
    return "\n".join(out) + "\n"


def append(vault: Path, text: str) -> Path:
    path = zones.path(vault, LEDGER)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("---\ntitle: 记忆变更记录\ntype: automation-log\nstatus: generated\nsource: krouter-capture\n---\n\n"
                        "# 记忆变更记录\n\n自动沉淀每一轮改了什么：新增的决定、被取代的旧决定、来源会话、纠正候选的判定。"
                        "机器写，不需要你批；不对就用每轮下面那条命令撤销。新的在下面。\n\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n" + text)
    return path


def commit(vault: Path, rid: str, paths: list[Path], summary: str, tagged: bool = True) -> str:
    """Commit exactly `paths` (written or deleted by this run); other changes in the vault stay as they are."""
    if not is_repo(vault):
        return ""
    rels = sorted({str(p.relative_to(vault)) for p in paths})
    try:
        # 删掉的页只有被跟踪过才能提交；从没进过 git 的就不用管
        rels = [r for r in rels if (vault / r).exists() or _git(vault, "ls-files", "--", r).stdout.strip()]
        if not rels:
            return ""
        _git(vault, "add", "-A", "--", *rels)
        res = _git(vault, "-c", "user.name=krouter-capture", "-c", "user.email=krouter@local", "commit", "-q",
                   "-m", f"KRouter 自动沉淀 {summary}" + (f"\n\n{TAG.format(rid)}" if tagged else ""), "--only", "--",
                   *rels)
        if res.returncode != 0:
            return ""
        return _git(vault, "rev-parse", "HEAD").stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def undo(vault: Path, rid: str) -> dict:
    """Revert the commit of run `rid`, and say so in the ledger (that line is committed too)."""
    if not is_repo(vault):
        return {"undo": "failed", "reason": "the vault is not a git repository"}
    found = _git(vault, "log", "--format=%H", "-F", "--grep", TAG.format(rid)).stdout.split()
    if not found:
        return {"undo": "failed", "reason": f"no commit tagged {TAG.format(rid)}"}
    res = _git(vault, "-c", "user.name=krouter-capture", "-c", "user.email=krouter@local", "revert", "--no-edit",
               found[0])
    if res.returncode != 0:
        _git(vault, "revert", "--abort")
        return {"undo": "failed", "reason": (res.stderr or res.stdout).strip()[-300:]}
    ledger = append(vault, f"## {datetime.now().strftime('%Y-%m-%d %H:%M')} · 撤销 run {rid}\n\n"
                           f"- 已用 `git revert {found[0][:10]}` 撤回这一轮的全部改动。\n")
    commit(vault, run_id(), [ledger], f"变更记录：撤销 run {rid}", tagged=False)
    return {"undo": "done", "run": rid, "reverted": found[0]}
