"""Observable, not approved: a capture run settles correction candidates on its own, commits exactly what it wrote,
lists it in the change ledger, and one command takes it back while the ledger keeps the record."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys

import pytest

from test_import_sessions import FOLDER, SCRIPTS, _claude_turns, _pages, _ts, env  # noqa: F401  env 是 fixture

HOOK = SCRIPTS / "session_hook.py"
LEDGER = "90 系统文件/自动化/记忆变更记录.md"
SID = "abcd1234-ledger"


def _git(vault, *args):
    return subprocess.run(["git", "-C", str(vault), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          capture_output=True, text=True, check=True).stdout


@pytest.fixture()
def box(env, monkeypatch):
    if not shutil.which("git"):
        pytest.skip("git not installed")
    vault = env["vault"]
    (vault / "笔记.md").write_text("# 笔记\n", encoding="utf-8")
    _git(vault, "init", "-q")
    _git(vault, "add", "-A")
    _git(vault, "commit", "-q", "-m", "init")
    state = env["env"]["KROUTER_STATE_DIR"]
    from pathlib import Path

    Path(state).mkdir(parents=True, exist_ok=True)
    (Path(state) / "import.json").write_text(json.dumps({"consent": True}), encoding="utf-8")
    for text in ("不对，发版以后一律走 CI 发布。", "配色改成蓝色主题。"):
        payload = {"prompt": text, "session_id": SID, "cwd": "/work/shop", "transcript_path": ""}
        hook_env = {k: v for k, v in env["env"].items() if k != "KROUTER_IN_DISTILL"}
        subprocess.run([sys.executable, str(HOOK), "prompt"], input=json.dumps(payload), env=hook_env,
                       capture_output=True, text=True, check=True, timeout=60)
    t = [_ts(0, 9), _ts(0, 10)]
    _claude_turns(env["claude"], SID, [(t[0], "发版怎么走？", "手动上传。"), (t[1], "不对，发版以后一律走 CI 发布。", "好，改成 CI。")])
    sys.path.insert(0, str(SCRIPTS))
    import import_sessions as imp
    import llm

    monkeypatch.setattr(llm, "complete", lambda prompt, vault=None: "- 原来手动上传 → 改成 发版一律走 CI 发布（10:05）")
    for k in ("OBSIDIAN_VAULT", "KROUTER_CLAUDE_PROJECTS", "KROUTER_CODEX_SESSIONS", "KROUTER_CURSOR_PROJECTS",
              "KROUTER_STATE_DIR"):
        monkeypatch.setenv(k, env["env"][k])
    return {"vault": vault, "imp": imp, "env": env, "monkeypatch": monkeypatch}


def _candidates(vault) -> str:
    page = next((vault / FOLDER).glob("*｜纠正候选.md"))
    return page.read_text(encoding="utf-8")


def _main(box, *args):
    box["monkeypatch"].setattr(sys, "argv", ["import_sessions.py", *args])
    return box["imp"].main()


def test_run_settles_candidates_commits_and_logs(box):
    vault = box["vault"]
    assert _main(box, "--distill", "--days", "1") == 0
    cands = _candidates(vault)
    assert "判定：成立 → [[05 时间日志/会话摘录/" in cands and "改成 发版一律走 CI 发布" in cands
    # 提炼里没有的那句（配色）按原话补记进提炼，不丢
    assert "判定：补记 → [[05 时间日志/会话摘录/" in cands and "待下次蒸馏判定" not in cands
    ledger = (vault / LEDGER).read_text(encoding="utf-8")
    assert "status: generated" in ledger and "撤销这一轮：`" in ledger and "--undo " in ledger
    assert f"会话 `claude-code:{SID[:8]}`" in ledger and "取代：原来手动上传 → 改成 发版一律走 CI 发布" in ledger
    assert "纠正候选判定：成立 1，补记 1，不成立 0" in ledger and "补记：「配色改成蓝色主题。」" in ledger
    log = _git(vault, "log", "--format=%s%n%b")
    assert re.search(r"\[krouter-run \d{8}T\d{6}\]", log) and "变更记录 run" in log
    page = next(iter(_pages(box["env"]).values()))
    assert "（模型提炼）" in page and "待你确认" not in page
    assert "- 你说：配色改成蓝色主题。（" in page and "当场记下的纠正，提炼里没有" in page
    assert _git(vault, "status", "--porcelain") == ""  # 这一轮写的全进了提交


def test_undo_takes_the_run_back_and_keeps_the_record(box):
    vault = box["vault"]
    assert _main(box, "--distill", "--days", "1") == 0
    rid = re.search(r"run (\d{8}T\d{6})", (vault / LEDGER).read_text(encoding="utf-8")).group(1)
    assert _main(box, "--undo", rid) == 0
    assert not [p for p in (vault / FOLDER).glob("*.md") if "纠正候选" not in p.name]  # 这一轮写的会话页没了
    assert _candidates(vault).count("待下次蒸馏判定") == 2  # 候选回到待判定
    ledger = (vault / LEDGER).read_text(encoding="utf-8")
    assert f"run {rid}" in ledger and f"撤销 run {rid}" in ledger  # 变更记录不跟着撤
    assert _main(box, "--undo", "19990101T000000") == 1


def test_a_run_that_changes_nothing_leaves_no_trace(box):
    vault = box["vault"]
    assert _main(box, "--distill", "--days", "1") == 0
    before = _git(vault, "rev-list", "--count", "HEAD")
    ledger = (vault / LEDGER).read_text(encoding="utf-8")
    assert _main(box, "--distill", "--days", "1") == 0  # 会话没变：不再提炼，也不再记一轮
    assert _git(vault, "rev-list", "--count", "HEAD") == before
    assert (vault / LEDGER).read_text(encoding="utf-8") == ledger
