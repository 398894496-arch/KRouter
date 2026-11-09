"""One HTTP server, several isolated vaults ("banks") at /mcp/NAME, each with its own token, and Prometheus metrics."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from test_mcp_http import SERVER, _env, _post

REPO = Path(__file__).resolve().parents[1]
TEAM, OPS = "team-token-for-tests-0123456789", "ops-token-for-tests-0123456789"


@pytest.fixture()
def banks(tmp_path):
    team, ops = tmp_path / "team", tmp_path / "ops"
    shutil.copytree(REPO / "template", team)
    shutil.copytree(REPO / "template", ops)
    (ops / "02 经验与方法" / "On-call handover.md").write_text(
        "---\ntitle: On-call handover\nstatus: active\n---\n\n# On-call handover\n\n"
        "The on-call handover happens every Monday at 10:00; the handover note is pinned in the on-call channel.\n",
        encoding="utf-8")
    files = {}
    for name, tok in (("team", TEAM), ("ops", OPS)):
        f = tmp_path / f"{name}.token"
        f.write_text(tok + "\n", encoding="utf-8")
        f.chmod(0o600)
        files[name] = f
    proc = subprocess.Popen([sys.executable, str(SERVER), "--http", "127.0.0.1:0",
                             "--bank", f"team={team}", "--bank", f"ops={ops}",
                             "--bank-token", f"team={files['team']}", "--bank-token", f"ops={files['ops']}"],
                            env=_env(tmp_path), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    info = None
    for _ in range(50):
        line = proc.stderr.readline()
        if not line:
            break
        if line.startswith("{") and "listening" in line:
            info = json.loads(line)
            break
    assert info and set(info["banks"]) == {"team", "ops"}, "server did not start"
    yield {"base": info["listening"].rsplit("/mcp", 1)[0], "banks": info["banks"], "proc": proc}
    proc.terminate()
    proc.wait(timeout=10)


def _ask(url: str, token: str, q: str):
    return _post(url, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "krouter_ask", "arguments": {"query": q}}}, token=token)


def _get(url: str, token: str | None = None):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8")


def test_each_bank_answers_from_its_own_vault_with_its_own_token(banks):
    q = "when is the on-call handover"
    code, body = _ask(banks["banks"]["ops"], OPS, q)
    text = body["result"]["content"][0]["text"]
    assert code == 200 and text.startswith("vault_label: ops") and "On-call handover" in text, text[-600:]
    code, body = _ask(banks["banks"]["team"], TEAM, q)  # team 库里没有这页
    text = body["result"]["content"][0]["text"]
    assert text.startswith("vault_label: team") and "On-call handover" not in text
    assert _ask(banks["banks"]["ops"], TEAM, q)[0] == 401  # 别的库的 token 进不来
    assert _ask(banks["base"] + "/mcp", TEAM, "x")[0] == 404  # 有库时没有不带名字的 /mcp
    assert _ask(banks["base"] + "/mcp/nope", TEAM, "x")[0] == 404


def test_health_lists_banks_and_metrics_count_calls_without_question_text(banks):
    code, body = _get(banks["base"] + "/healthz")
    assert code == 200 and json.loads(body)["banks"] == {"team": True, "ops": True}
    _ask(banks["banks"]["ops"], OPS, "when is the on-call handover")
    _ask(banks["banks"]["team"], TEAM, "how do we deploy the quantum toaster on mars")
    assert _get(banks["base"] + "/metrics")[0] == 401
    code, text = _get(banks["base"] + "/metrics", OPS)
    assert code == 200 and "krouter_up 1" in text
    assert 'krouter_tool_calls_total{vault="ops",tool="krouter_ask",outcome="ok"} 1' in text
    assert 'krouter_request_seconds_count{vault="team"} 1' in text
    assert 'krouter_index_build_seconds{vault="ops"}' in text
    assert "handover" not in text and "toaster" not in text


def test_a_bank_without_a_token_is_refused_off_loopback(tmp_path):
    res = subprocess.run([sys.executable, str(SERVER), "--http", "0.0.0.0:0", "--bank", f"a={tmp_path}"],
                         env=_env(tmp_path), capture_output=True, text=True, timeout=60)
    assert res.returncode == 2 and "the vaults a" in res.stderr
    res = subprocess.run([sys.executable, str(SERVER), "--bank", f"a={tmp_path}"], env=_env(tmp_path),
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 2 and "--bank needs --http" in res.stderr
