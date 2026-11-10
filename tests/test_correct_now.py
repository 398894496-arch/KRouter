"""A correction holds in the same turn, with no key: the agent calls krouter_correct (or corrections.py apply), the
vault's own supersede rule does the rest, and the next lookup no longer puts the old answer first."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter-obsidian/scripts"
sys.path.insert(0, str(SCRIPTS))
import corrections  # noqa: E402

OLD_PAGE = "01 项目/示例项目/数据库选型.md"


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template-zh", vault)
    (vault / OLD_PAGE).write_text("---\ntitle: 数据库选型\nstatus: active\n---\n\n# 数据库选型\n\n"
                                  "- 本地开发数据库用 Postgres 16，端口 5432。\n", encoding="utf-8")
    return vault


def _ask(vault: Path, tmp_path: Path, q: str) -> str:
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_NO_QUERY_LOG": "1",
           "KROUTER_CACHE_DIR": str(tmp_path / "cache")}
    res = subprocess.run([sys.executable, str(SCRIPTS / "route_knowledge.py"), "search", q], env=env,
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    block = res.stdout.split("recall:", 1)[1] if "recall:\n" in res.stdout else ""
    return next((ln[2:].split(" tier=")[0] for ln in block.splitlines() if ln.startswith("- ")), "")


def _mcp(vault: Path, tmp_path: Path, *msgs: dict) -> list[dict]:
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_NO_QUERY_LOG": "1",
           "KROUTER_CACHE_DIR": str(tmp_path / "cache")}
    data = "\n".join(json.dumps(m, ensure_ascii=False) for m in msgs) + "\n"
    res = subprocess.run([sys.executable, str(SCRIPTS / "mcp_server.py")], input=data, env=env, capture_output=True,
                         text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    return [json.loads(line) for line in res.stdout.splitlines() if line.strip()]


def test_correct_in_session_puts_the_new_answer_before_the_old(tmp_path):
    vault = _vault(tmp_path)
    q = "本地开发用什么数据库"
    assert _ask(vault, tmp_path, q) == OLD_PAGE  # 改之前：旧答案排第一
    out = _mcp(vault, tmp_path,
               {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
               {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "krouter_correct", "arguments": {
                   "new": "本地开发数据库以后改用 SQLite", "old": "本地开发数据库用 Postgres 16，端口 5432。",
                   "page": OLD_PAGE}}})
    assert "krouter_correct" in out[0]["result"]["instructions"]
    text = out[1]["result"]["content"][0]["text"]
    assert out[1]["result"]["isError"] is False and "(page)" in text
    old = (vault / OLD_PAGE).read_text(encoding="utf-8")
    assert "status: superseded" in old and "superseded_by:" in old and "Postgres 16" in old  # 不删原文，只标取代
    top = _ask(vault, tmp_path, q)
    # 改之后：旧页不再排第一，排第一的那页写着新答案（纠正页，或记下了这条取代的纠错与取代记录），不等夜间、不要模型
    assert top != OLD_PAGE and "SQLite" in (vault / top).read_text(encoding="utf-8")
    written = text.split("corrected: ", 1)[1].split("\n", 1)[0]
    new = (vault / written).read_text(encoding="utf-8")
    assert "supersedes:" in new and "原来 本地开发数据库用 Postgres 16" in new and "→ 改成" in new
    log = (vault / "90 系统文件/Agent记忆/纠错与取代记录.md").read_text(encoding="utf-8")
    assert "改成 本地开发数据库以后改用 SQLite" in log
    assert "会话内纠正" in (vault / "90 系统文件/自动化/记忆变更记录.md").read_text(encoding="utf-8")


def test_a_page_with_other_facts_is_annotated_not_superseded(tmp_path):
    vault = _vault(tmp_path)
    page = vault / OLD_PAGE
    page.write_text(page.read_text(encoding="utf-8") + "".join(f"- 其他约定 {i}：保持不变。\n" for i in range(14)),
                    encoding="utf-8")
    res = corrections.apply_now(vault, "本地开发数据库以后改用 SQLite", "本地开发数据库用 Postgres 16", OLD_PAGE, "test")
    assert res["mode"] == "line"
    text = page.read_text(encoding="utf-8")
    assert "status: active" in text and "⚠ 已改" in text and text.index("⚠ 已改") > text.index("Postgres 16")


def test_refuses_what_it_cannot_ground_and_settles_todays_candidate(tmp_path):
    vault = _vault(tmp_path)
    assert "error" in corrections.apply_now(vault, "改用 SQLite", "用 MySQL 8", OLD_PAGE, "t")  # 旧页上没有这句
    assert "error" in corrections.apply_now(vault, "改用 SQLite", "x", "../outside.md", "t")
    assert "error" in corrections.apply_now(vault, "", "", "", "t")
    folder = vault / "05 时间日志/会话摘录"
    folder.mkdir(parents=True, exist_ok=True)
    cand = folder / f"{date.today().isoformat()}｜纠正候选.md"
    cand.write_text("# x\n\n- （10:00）不对，本地开发数据库以后改用 SQLite — 项目 shop，会话 `claude:0123abcd`，命中「改用」，"
                    "待下次蒸馏判定\n", encoding="utf-8")
    res = corrections.apply_now(vault, "本地开发数据库以后改用 SQLite", "", "", "t")
    assert res["settled"] == 1 and res["mode"] == "recorded"
    assert "判定：成立 → [[05 时间日志/会话摘录/" in cand.read_text(encoding="utf-8")  # 夜间提炼不用再判一次


def test_command_line_twin(tmp_path):
    vault = _vault(tmp_path)
    res = subprocess.run([sys.executable, str(SCRIPTS / "corrections.py"), "--vault", str(vault), "apply",
                          "--new", "Use SQLite for local development from now on",
                          "--old", "本地开发数据库用 Postgres 16", "--page", OLD_PAGE],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout)["mode"] == "page"


def _session_page(folder: Path, name: str, root: str, lines: list[str], day: str) -> Path:
    path = folder / f"{day}｜{name}.md"
    path.write_text(f"---\ntype: session-excerpt\nsource: krouter-import\nstatus: imported\ndate: {day}\nproject: shop\n"
                    f"project_root: {root}\nhow: {lines[0]}\n---\n\n# {name}\n\n## 定了什么、改了什么（模型提炼）\n\n"
                    + "\n".join(f"- {ln}" for ln in lines) + "\n\n## 摘录\n\n- **问**：…\n", encoding="utf-8")
    return path


def test_distilled_change_of_mind_supersedes_the_page_it_replaced(tmp_path):
    """The audit's case through the distill path: decided PostgreSQL, later changed to SQLite. The old session page
    is marked superseded at import (no model), so the new answer comes first; a page with another live decision
    is left alone."""
    import import_sessions

    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template-zh", vault)
    folder = vault / "05 时间日志/会话摘录"
    folder.mkdir(parents=True, exist_ok=True)
    day = date.today().isoformat()
    old = _session_page(folder, "本地开发数据库用什么？（aaaa0001）", "/work/shop", ["本地开发数据库用 PostgreSQL 16（10:20）"], day)
    keep = _session_page(folder, "部署（cccc0003）", "/work/shop",
                         ["本地开发数据库用 PostgreSQL 16（09:00）", "发版只从 main 打 tag（09:05）"], day)
    _session_page(folder, "改主意（bbbb0002）", "/work/shop", ["本地开发数据库原来用 PostgreSQL → 改成 SQLite（16:05）"], day)
    q = "本地开发数据库用什么"
    assert "aaaa0001" in _ask(vault, tmp_path, q)
    done = import_sessions.supersede_replaced(vault, {"/work/shop"})
    assert [p.name for p, _ in done] == [old.name]
    text = old.read_text(encoding="utf-8")
    assert "status: superseded" in text and "superseded_by:" in text and "bbbb0002" in text
    assert "status: imported" in keep.read_text(encoding="utf-8")  # 还有一条决定没被改掉：整页不动
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_NO_QUERY_LOG": "1", "KROUTER_CACHE_DIR": str(tmp_path / "cache")}
    out = subprocess.run([sys.executable, str(SCRIPTS / "route_knowledge.py"), "search", q], env=env,
                         capture_output=True, text=True, timeout=120).stdout
    hits = [ln for ln in out.split("recall:", 1)[1].splitlines() if ln.startswith("- ")]
    assert any("aaaa0001" in h and "status=superseded" in h and "tier=dead" in h for h in hits)  # 回执里写明已被取代
    assert any("bbbb0002" in h for h in hits)
    # 新旧两页都还在时谁排第一，是 recall_index 的事（另一个会话在做「新页在前」的兜底），这里不断言顺序
