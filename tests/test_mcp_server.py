"""The MCP server speaks JSON-RPC over stdio and finds the vault the installer recorded, with no env var."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter-obsidian/scripts"


def _talk(env: dict, *msgs: dict) -> list[dict]:
    data = "\n".join(json.dumps(m, ensure_ascii=False) for m in msgs) + "\n"
    res = subprocess.run([sys.executable, str(SCRIPTS / "mcp_server.py")], input=data, env=env,
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    return [json.loads(line) for line in res.stdout.splitlines() if line.strip()]


def test_initialize_list_and_ask(tmp_path):
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template", vault)
    vault_file = tmp_path / "config/krouter/vault"
    vault_file.parent.mkdir(parents=True)
    vault_file.write_text(str(vault) + "\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "OBSIDIAN_VAULT"}
    env.update({"KROUTER_VAULT_FILE": str(vault_file), "KROUTER_NO_QUERY_LOG": "1", "KROUTER_CACHE_DIR": str(tmp_path / "c")})
    replies = _talk(env,
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                     "params": {"name": "krouter_ask", "arguments": {"query": "Agent second brain"}}},
                    {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                     "params": {"name": "krouter_ask", "arguments": {"query": "x", "route": "rm -rf"}}},
                    {"jsonrpc": "2.0", "id": 5, "method": "nope"})
    assert [r["id"] for r in replies] == [1, 2, 3, 4, 5]  # 通知不回
    assert replies[0]["result"]["protocolVersion"] == "2025-06-18" and "recall: none" in replies[0]["result"]["instructions"]
    assert {t["name"] for t in replies[1]["result"]["tools"]} == {"krouter_ask", "krouter_status", "krouter_note", "krouter_correct"}
    ask = replies[2]["result"]
    assert ask["isError"] is False and "receipt_version:" in ask["content"][0]["text"]
    assert str(vault) in ask["content"][0]["text"]
    assert replies[3]["result"]["isError"] is True
    assert replies[4]["error"]["code"] == -32601


def test_no_vault_is_said_plainly(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "OBSIDIAN_VAULT"}
    env["KROUTER_VAULT_FILE"] = str(tmp_path / "missing")
    replies = _talk(env, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": "krouter_status", "arguments": {}}})
    res = replies[0]["result"]
    assert res["isError"] is True and "one-line install" in res["content"][0]["text"]


def test_router_scripts_find_the_recorded_vault(tmp_path):
    vault = tmp_path / "v"
    shutil.copytree(REPO / "template", vault)
    vf = tmp_path / "vault-file"
    vf.write_text(str(vault) + "\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "OBSIDIAN_VAULT"}
    env.update({"KROUTER_VAULT_FILE": str(vf), "KROUTER_NO_QUERY_LOG": "1"})
    for argv in ([sys.executable, str(SCRIPTS / "route_knowledge.py"), "status"],
                 *([["/bin/sh", str(SCRIPTS / "route_knowledge.sh"), "status"]] if os.name != "nt" else [])):
        res = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=120)
        assert res.returncode == 0 and "route: status" in res.stdout, res.stderr


def test_note_writes_a_line_the_ledger_and_one_commit(tmp_path):
    if not shutil.which("git"):
        import pytest
        pytest.skip("git not installed")
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template", vault)
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"]):
        subprocess.run(["git", "-C", str(vault), *args], check=True, capture_output=True)
    env = {k: v for k, v in os.environ.items() if k != "OBSIDIAN_VAULT"}
    env.update({"OBSIDIAN_VAULT": str(vault), "KROUTER_NO_QUERY_LOG": "1", "KROUTER_CACHE_DIR": str(tmp_path / "c")})
    key = "sk-" + "Abc123XyZ" * 4
    replies = _talk(env,
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2025-06-18", "clientInfo": {"name": "test-client"}}},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                     "params": {"name": "krouter_note", "arguments": {"text": f"发版只从 main 打 tag，密钥 {key} 不进库",
                                                                       "kind": "decision"}}},
                    {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                     "params": {"name": "krouter_note", "arguments": {"text": "x" * 501}}},
                    {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                     "params": {"name": "krouter_note", "arguments": {"text": "ok", "kind": "rule"}}})
    assert "krouter_note" in {t["name"] for t in replies[1]["result"]["tools"]}
    done = replies[2]["result"]
    assert done["isError"] is False and "noted: 05 时间日志/会话摘录/" in done["content"][0]["text"]
    assert "undo: " in done["content"][0]["text"] and "--undo " in done["content"][0]["text"]
    page = next((vault / "05 时间日志/会话摘录").glob("*｜agent 记下.md")).read_text(encoding="utf-8")
    assert "[决定] 发版只从 main 打 tag" in page and "来自 MCP（test-client）" in page and key not in page
    assert "status: provisional" in page  # 线索，不是规则页
    ledger = (vault / "90 系统文件/自动化/记忆变更记录.md").read_text(encoding="utf-8")
    assert "MCP 记下（test-client）" in ledger
    log = subprocess.run(["git", "-C", str(vault), "log", "--format=%s"], capture_output=True, text=True).stdout
    assert "MCP 记下 1 条" in log
    assert replies[3]["result"]["isError"] is True and replies[4]["result"]["isError"] is True


def test_http_server_is_read_only_unless_asked(tmp_path):
    sys.path.insert(0, str(SCRIPTS))
    import mcp_server as m
    saved = m.WRITE
    try:
        m.WRITE = False  # what main() sets for --http without --allow-write
        names = {t["name"] for t in m.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]}
        assert names == {"krouter_ask", "krouter_status"}
        res = m.call("krouter_note", {"text": "x"})
        assert res["isError"] is True and "unknown tool" in res["content"][0]["text"]
    finally:
        m.WRITE = saved
