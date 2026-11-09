"""The MCP server over HTTP: bearer auth, health, a label on every receipt, bad requests, parallel calls, and an access
log that never holds the question."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "skill/krouter-obsidian/scripts/mcp_server.py"
TOKEN = "t0ken-for-tests-only-0123456789"


def _env(tmp: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.endswith(("_API_KEY", "_BASE_URL"))}
    env.update({"HOME": str(tmp / "home"), "KROUTER_CACHE_DIR": str(tmp / "cache"),
                "KROUTER_STATE_DIR": str(tmp / "state"), "KROUTER_VAULT_FILE": str(tmp / "no-vault-file"),
                "KROUTER_NO_QUERY_LOG": "1"})
    env.pop("OBSIDIAN_VAULT", None)
    (tmp / "home").mkdir(exist_ok=True)
    return env


@pytest.fixture()
def server(tmp_path):
    vault = tmp_path / "team-vault"
    shutil.copytree(REPO / "template", vault)
    token_file = tmp_path / "token"
    token_file.write_text(TOKEN + "\n", encoding="utf-8")
    token_file.chmod(0o600)
    proc = subprocess.Popen([sys.executable, str(SERVER), "--http", "127.0.0.1:0", "--vault", str(vault),
                             "--label", "team", "--token-file", str(token_file)],
                            env=_env(tmp_path), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    url = None
    for _ in range(50):
        line = proc.stderr.readline()
        if not line:
            break
        if line.startswith("{") and "listening" in line:
            url = json.loads(line)["listening"]
            break
    assert url, "server did not start"
    base = url.rsplit("/mcp", 1)[0]
    yield {"url": url, "base": base, "proc": proc, "vault": vault}
    proc.terminate()
    proc.wait(timeout=10)


def _post(url: str, body, token: str | None = TOKEN, ctype: str = "application/json", headers: dict | None = None):
    data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": ctype, **(headers or {})})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as err:
        raw = err.read()
        return err.code, (json.loads(raw) if raw else None)


def _get(url: str, method: str = "GET") -> int:
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as err:
        return err.code


def _ask(query: str, mid: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "method": "tools/call",
            "params": {"name": "krouter_ask", "arguments": {"query": query}}}


def test_bearer_token_is_required_and_checked(server):
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}
    assert _post(server["url"], init, token=None)[0] == 401
    assert _post(server["url"], init, token="wrong-token-but-long-enough")[0] == 401
    code, reply = _post(server["url"], init)
    assert code == 200 and reply["result"]["serverInfo"]["title"] == "KRouter (team)"
    assert "'team' vault" in reply["result"]["instructions"]


def test_every_receipt_names_its_vault(server):
    code, reply = _post(server["url"], _ask("发版流程怎么定的"))
    assert code == 200 and not reply["result"]["isError"]
    text = reply["result"]["content"][0]["text"]
    assert text.startswith("vault_label: team\n") and "receipt_version:" in text
    code, reply = _post(server["url"], _ask("量子火锅的配方是什么"))
    assert "recall: none" in reply["result"]["content"][0]["text"]  # still refuses what the vault does not hold


def test_health_and_methods(server):
    with urllib.request.urlopen(server["base"] + "/healthz", timeout=10) as resp:
        health = json.loads(resp.read())
    assert resp.status == 200 and health["ok"] and health["label"] == "team"
    assert "vault" not in health  # the path is not given out
    assert _get(server["url"]) == 405 and _get(server["url"], "DELETE") == 405
    assert _get(server["base"] + "/nope") == 404


def test_bad_requests_get_clear_codes(server):
    url = server["url"]
    assert _post(url, b"{not json")[0] == 400
    assert _post(url, _ask("x"), ctype="text/plain")[0] == 415
    assert _post(url, b"x" * 1_000_001)[0] == 413
    assert _post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"})[0] == 202
    assert _post(url, _ask("x"), headers={"Origin": "https://evil.example"})[0] == 403
    assert _post(url, {"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers={"Origin": "http://localhost:3000"})[0] == 200
    assert _post(url, {"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers={"MCP-Protocol-Version": "1999-01-01"})[0] == 400
    code, reply = _post(url, {"jsonrpc": "2.0", "id": 9, "method": "no/such"})
    assert code == 200 and reply["error"]["code"] == -32601


def test_parallel_calls_all_answer(server):
    # a git pull just brought a page in: the first calls update the index at the same time
    (server["vault"] / "01 项目" / "季度复盘节奏.md").write_text(
        "---\ntitle: 季度复盘节奏\nstatus: active\n---\n\n# 季度复盘节奏\n\n- 季度复盘改成每月最后一个周五（11-09）\n",
        encoding="utf-8")
    questions = ["季度复盘节奏是怎么定的", "封面标题用什么规则", "量子火锅的配方是什么", "备份放在哪里"] * 3
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda iq: _post(server["url"], _ask(iq[1], iq[0])), enumerate(questions)))
    assert all(code == 200 and not reply["result"]["isError"] for code, reply in results)
    assert sorted(reply["id"] for _, reply in results) == list(range(len(questions)))
    assert all("季度复盘节奏" in reply["result"]["content"][0]["text"] for _, reply in results[::4])


def test_access_log_holds_a_hash_not_the_question(server):
    secret = "客户甲的合同违约金是多少"
    assert _post(server["url"], _ask(secret))[0] == 200
    server["proc"].terminate()
    log = server["proc"].stderr.read()
    rows = [json.loads(line) for line in log.splitlines() if line.startswith("{") and '"status"' in line]
    calls = [r for r in rows if r.get("tool") == "krouter_ask"]
    assert calls and all(len(r["q_sha256"]) == 16 for r in calls)
    assert secret not in log


def test_refuses_a_public_address_without_a_token(tmp_path):
    res = subprocess.run([sys.executable, str(SERVER), "--http", "0.0.0.0:0", "--vault", str(REPO / "template")],
                         env=_env(tmp_path), capture_output=True, text=True, timeout=30)
    assert res.returncode == 2 and "refusing to listen on 0.0.0.0" in res.stderr


def test_short_token_is_refused(tmp_path):
    short = tmp_path / "token"
    short.write_text("abc", encoding="utf-8")
    res = subprocess.run([sys.executable, str(SERVER), "--http", "127.0.0.1:0", "--token-file", str(short)],
                         env=_env(tmp_path), capture_output=True, text=True, timeout=30)
    assert res.returncode == 2 and "at least 16" in res.stderr


def test_stdio_takes_the_label_too(tmp_path):
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            _ask("发版流程怎么定的", 2)]
    res = subprocess.run([sys.executable, str(SERVER), "--vault", str(REPO / "template"), "--label", "personal"],
                         input="\n".join(json.dumps(m) for m in msgs) + "\n", env=_env(tmp_path),
                         capture_output=True, text=True, timeout=60)
    replies = [json.loads(line) for line in res.stdout.splitlines()]
    assert replies[0]["result"]["serverInfo"]["title"] == "KRouter (personal)"
    assert replies[1]["result"]["content"][0]["text"].startswith("vault_label: personal\n")
