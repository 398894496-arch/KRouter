"""The official MCP Python SDK (`pip install mcp`) talks to KRouter over stdio and over Streamable HTTP: initialize,
list the tools, ask a question, get the page back. Skipped when the SDK is not installed."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

mcp = pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "skill/krouter-obsidian/scripts/mcp_server.py"
TOKEN = "sdk-test-token-0123456789abcdef"


@pytest.fixture()
def env(tmp_path):
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template", vault)
    (vault / "02 经验与方法" / "API port.md").write_text(
        "---\ntitle: API port\nstatus: active\nhow: The local API listens on 8080.\n---\n\n# API port\n\n"
        "The local API listens on 8080.\n", encoding="utf-8")
    return {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_CACHE_DIR": str(tmp_path / "cache"),
            "KROUTER_STATE_DIR": str(tmp_path / "state"), "KROUTER_NO_QUERY_LOG": "1"}


async def _session_checks(session: ClientSession) -> None:
    init = await session.initialize()
    assert init.serverInfo.name.lower().startswith("krouter")
    names = {t.name for t in (await session.list_tools()).tools}
    assert {"krouter_ask", "krouter_status"} <= names
    res = await session.call_tool("krouter_ask", {"query": "what port does the local api listen on"})
    text = res.content[0].text
    assert not res.isError and "API port" in text and "8080" in text
    none = await session.call_tool("krouter_ask", {"query": "which espresso grinder setting do we use"})
    assert "recall: none" in none.content[0].text


def test_official_sdk_over_stdio(env):
    async def run():
        params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await _session_checks(session)

    asyncio.run(asyncio.wait_for(run(), 120))


def test_official_sdk_over_streamable_http(env, tmp_path):
    try:
        from mcp.client.streamable_http import streamable_http_client as http_client  # 1.2x 以后的名字
        import httpx

        def connect(url):
            return http_client(url, http_client=httpx.AsyncClient(headers={"Authorization": f"Bearer {TOKEN}"}))
    except ImportError:
        from mcp.client.streamable_http import streamablehttp_client

        def connect(url):
            return streamablehttp_client(url, headers={"Authorization": f"Bearer {TOKEN}"})

    token = tmp_path / "token"
    token.write_text(TOKEN, encoding="utf-8")
    token.chmod(0o600)
    proc = subprocess.Popen([sys.executable, str(SERVER), "--http", "127.0.0.1:0", "--token-file", str(token)],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        url = ""
        for _ in range(200):
            line = proc.stderr.readline()
            if line.startswith("{") and "listening" in line:
                url = json.loads(line)["listening"]
                break
        assert url, "server did not start"

        async def run():
            async with connect(url) as (read, write, *_):
                async with ClientSession(read, write) as session:
                    await _session_checks(session)

        asyncio.run(asyncio.wait_for(run(), 120))
    finally:
        proc.terminate()
        proc.wait(timeout=10)
