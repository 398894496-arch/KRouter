#!/usr/bin/env python3
"""What automatic capture changed, where you can see it, and one command to take a run back.

Capture writes memory without asking (session digests, judged corrections). In place of a yes/no gate, every run
that changes something leaves two traces: a section in `90 系统文件/自动化/记忆变更记录.md` (what was added, what a
change of mind replaced, which session it came from, how each correction candidate was judged) and, when the vault
is a git repository, one commit holding exactly the files that run wrote, tagged `[krouter-run <id>]`; the ledger
entry is committed separately, so undoing a run keeps its record. `import_sessions.py --undo <id>` reverts the run.
"""

from __future__ import annotations

import re
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


_REPOS: set[str] = set()  # 已确认是 git 仓库的库：团队服务每次写入不再多起一个 git 进程去问


def is_repo(vault: Path) -> bool:
    if not (vault / ".git").exists():
        return False
    if str(vault) in _REPOS:
        return True
    try:
        ok = _git(vault, "rev-parse", "--is-inside-work-tree").returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
    if ok:
        _REPOS.add(str(vault))
    return ok


def _link(vault: Path, path: Path) -> str:
    rel = zones.canon(vault, str(path.relative_to(vault)).replace("\\", "/"))
    return f"[[{rel.removesuffix('.md')}]]"


def section(vault: Path, rid: str, pages: list[dict], verdicts: list[dict], removed: list[Path], undo: str,
            sha: str = "", superseded: list | None = None) -> str:
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
        added = sum(1 for v in verdicts if v.get("kind") == "补记")
        ok = sum(1 for v in verdicts if v["ok"]) - added
        out.append(f"- 纠正候选判定：成立 {ok}，补记 {added}，不成立 {len(verdicts) - ok - added}")
        for v in verdicts:
            said = v["said"] if len(v["said"]) <= 80 else v["said"][:80] + " …"
            if v.get("kind") == "补记":
                out.append(f"  - 补记：「{said}」→ {v['link']}（提炼里没有，按原话补进）")
            elif v["ok"]:
                out.append(f"  - 成立：「{said}」→ {v['link']}：{v['line']}")
            else:
                out.append(f"  - 不成立：「{said}」：{v['why'] or '模型判定不是改主意或新规则'}")
    for path, by in superseded or []:
        out.append(f"- 取代 {_link(vault, path)} → {by}（这一页定下的事都被后来的改主意改掉了，整页标为 superseded）")
    for path in removed:
        out.append(f"- 删除 `{path.name}`（标了 #不记、是无头调用，或被另一个会话完整包含）")
    return "\n".join(out) + "\n"


ROTATE_AT = 256 * 1024   # 变更记录超过这么大就整页挪进 记忆变更记录/：每次写入都要重建这一页的索引，页越大越慢
ARCHIVE = "90 系统文件/自动化/记忆变更记录"
_ROTATED: dict[str, list[Path]] = {}  # 挪走、还没提交的旧页：下一次 commit() 一并提交


def _header(earlier: str = "") -> str:
    return ("---\ntitle: 记忆变更记录\ntype: automation-log\nstatus: generated\nsource: krouter-capture\n---\n\n"
            "# 记忆变更记录\n\n自动沉淀每一轮改了什么：新增的决定、被取代的旧决定、来源会话、纠正候选的判定。"
            "机器写，不需要你批；不对就用每轮下面那条命令撤销。新的在下面。\n\n"
            + (f"更早的记录：{earlier}\n\n" if earlier else ""))


def append(vault: Path, text: str) -> Path:
    path = zones.path(vault, LEDGER)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        big = path.stat().st_size > ROTATE_AT
    except OSError:
        big = False
    if big:  # 整页原样挪走（一条不丢），新页开头链到它；团队服务一天能写上千条
        old = path.read_text(encoding="utf-8")
        stamp = datetime.now().strftime("%Y-%m-%d %H%M%S")
        dest = zones.path(vault, f"{ARCHIVE}/{stamp}.md")
        n = 1
        while dest.exists():
            n += 1
            dest = dest.with_name(f"{stamp}-{n}.md")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(old.replace("title: 记忆变更记录\n", f"title: 记忆变更记录（到 {stamp}）\n", 1), encoding="utf-8")
        link = _link(vault, dest) + ("（再早的，那一页开头链着）" if re.search(r"^更早的记录：", old, re.M) else "")
        path.write_text(_header(link), encoding="utf-8")
        _ROTATED.setdefault(str(vault), []).append(dest)
    elif not path.exists():
        path.write_text(_header(), encoding="utf-8")
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n" + text)
    return path


def commit(vault: Path, rid: str, paths: list[Path], summary: str, tagged: bool = True, author: str = "",
           need_sha: bool = True) -> str:
    """Commit exactly `paths` (written or deleted by this run); other changes in the vault stay as they are. `author`
    (a team server's user) is the commit's author, so `git log` says who; the committer stays krouter-capture."""
    if not is_repo(vault):
        return ""
    if zones.path(vault, LEDGER) in paths:  # 挪走的旧页跟变更记录同一个提交，不进某一轮的提交（撤销一轮不会把它撤回）
        paths = [*paths, *_ROTATED.pop(str(vault), [])]
    rels = sorted({str(p.relative_to(vault)) for p in paths})
    try:
        # 删掉的页只有被跟踪过才能提交；从没进过 git 的就不用管
        rels = [r for r in rels if (vault / r).exists() or _git(vault, "ls-files", "--", r).stdout.strip()]
        if not rels:
            return ""
        who = ["--author", f"{author} <{re.sub(r'[^A-Za-z0-9._-]', '-', author)}@krouter.invalid>"] if author else []
        argv = ["-c", "user.name=krouter-capture", "-c", "user.email=krouter@local", "commit", "-q", *who,
                "-m", f"KRouter 自动沉淀 {summary}" + (f"\n\n{TAG.format(rid)}" if tagged else ""), "--only", "--", *rels]
        # 都是已跟踪、还在的文件时 commit --only 自己就收它们，省一次 git add；有新文件（git 不认得）会整个失败，再走老路
        res = _git(vault, *argv) if all((vault / r).exists() for r in rels) else None
        if res is None or res.returncode != 0:
            _git(vault, "add", "-A", "--", *rels)
            res = _git(vault, *argv)
        if res.returncode != 0:
            return ""
        return _git(vault, "rev-parse", "HEAD").stdout.strip() if need_sha else "committed"
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
