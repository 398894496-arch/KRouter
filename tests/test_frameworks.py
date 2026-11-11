"""Each agent framework in docs/FRAMEWORKS.md, run against KRouter's real MCP server the way that page shows: it loads
the server over stdio, lists its tools, asks a question the vault knows (the cited page comes back) and one it does
not (`recall: none`). Where the framework ships a stand-in model, its agent loop runs too, with no model call and no
key. Each test is skipped when its framework is not installed; CI installs them in a job of their own.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SERVER = str(REPO / "skill/krouter/scripts/mcp_server.py")
KNOWN = "what port does the local api listen on"
UNKNOWN = "which espresso grinder setting do we use"


@pytest.fixture()
def env(tmp_path) -> dict:
    """The server's environment: a vault of its own, its own cache and state, and no query log (never the host's)."""
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template", vault)
    (vault / "02 经验与方法" / "API port.md").write_text(
        "---\ntitle: API port\nstatus: active\nhow: The local API listens on 8080.\n---\n\n# API port\n\n"
        "The local API listens on 8080.\n", encoding="utf-8")
    return {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_CACHE_DIR": str(tmp_path / "cache"),
            "KROUTER_STATE_DIR": str(tmp_path / "state"), "KROUTER_NO_QUERY_LOG": "1"}


def text_of(result) -> str:
    """Whatever a framework hands back from a tool call, as text: a string, MCP content blocks, a list of either,
    a (content, artifact) pair."""
    if isinstance(result, str):
        return result
    if isinstance(result, tuple):
        return text_of(result[0])
    if isinstance(result, dict):
        return str(result.get("text") or result.get("content") or result)
    if isinstance(result, list):
        return "\n".join(text_of(r) for r in result)
    content = getattr(result, "content", None)
    if content is not None and content is not result:
        return text_of(content)
    return str(getattr(result, "text", result))


def check_answers(known: str, unknown: str) -> None:
    assert "API port" in known and "8080" in known, known[-800:]
    assert "recall: none" in unknown, unknown[-800:]


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, 180))


def need(module: str):
    """The framework, or a skip when it is not installed; CI sets KROUTER_REQUIRE_FRAMEWORKS so a framework that failed
    to install fails the job instead of skipping it."""
    if os.environ.get("KROUTER_REQUIRE_FRAMEWORKS"):
        import importlib

        return importlib.import_module(module)
    return pytest.importorskip(module)


# ---------- LangChain / LangGraph（langchain-mcp-adapters） ----------

def test_langchain(env):
    need("langchain_mcp_adapters")
    from langchain_mcp_adapters.client import MultiServerMCPClient

    async def go():
        client = MultiServerMCPClient({"krouter": {"command": sys.executable, "args": [SERVER], "transport": "stdio",
                                                   "env": env}})
        tools = {t.name: t for t in await client.get_tools()}
        assert {"krouter_ask", "krouter_status"} <= set(tools)
        known = text_of(await tools["krouter_ask"].ainvoke({"query": KNOWN}))
        unknown = text_of(await tools["krouter_ask"].ainvoke({"query": UNKNOWN}))
        check_answers(known, unknown)
        return tools

    tools = run(go())
    # 整个 agent 跑一遍：LangChain 自带的假聊天模型先调 krouter_ask，再照工具结果回答
    need("langchain.agents")
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    class Fake(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    model = Fake(messages=iter([
        AIMessage(content="", tool_calls=[{"name": "krouter_ask", "args": {"query": KNOWN}, "id": "c1"}]),
        AIMessage(content="Port 8080, per the API port page."),
    ]))

    async def agent_run():
        agent = create_agent(model, list(tools.values()))
        return await agent.ainvoke({"messages": [{"role": "user", "content": "What port does the local API use?"}]})

    out = run(agent_run())
    tool_msgs = [m for m in out["messages"] if m.type == "tool"]
    assert tool_msgs and "8080" in text_of(tool_msgs[0].content)
    assert out["messages"][-1].content == "Port 8080, per the API port page."


# ---------- OpenAI Agents SDK ----------

def test_openai_agents(env):
    need("agents")
    from agents.mcp import MCPServerStdio

    async def go():
        async with MCPServerStdio(name="KRouter", params={"command": sys.executable, "args": [SERVER], "env": env},
                                  client_session_timeout_seconds=60) as krouter:
            names = {t.name for t in await krouter.list_tools()}
            assert {"krouter_ask", "krouter_status"} <= names
            known = text_of(await krouter.call_tool("krouter_ask", {"query": KNOWN}))
            unknown = text_of(await krouter.call_tool("krouter_ask", {"query": UNKNOWN}))
            check_answers(known, unknown)

    run(go())


# ---------- Pydantic AI ----------

def test_pydantic_ai(env):
    need("pydantic_ai")
    need("fastmcp")
    from fastmcp.client.transports import StdioTransport
    from pydantic_ai import Agent
    from pydantic_ai.mcp import MCPToolset
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    def model(messages, info: AgentInfo) -> ModelResponse:
        returned = [p for m in messages for p in getattr(m, "parts", []) if isinstance(p, ToolReturnPart)]
        if not returned:  # 第一步：调 krouter_ask
            assert "krouter_ask" in {t.name for t in info.function_tools}
            return ModelResponse(parts=[ToolCallPart("krouter_ask", {"query": KNOWN})])
        return ModelResponse(parts=[TextPart(text_of(returned[-1].content))])  # 第二步：照查回来的页回答

    toolset = MCPToolset(StdioTransport(command=sys.executable, args=[SERVER], env=env))
    agent = Agent(FunctionModel(model), toolsets=[toolset])

    async def go():
        async with agent:
            return (await agent.run("What port does the local API listen on?")).output

    out = run(go())
    assert "API port" in out and "8080" in out


# ---------- Google ADK ----------

def test_google_adk(env):
    need("google.adk")
    from google.adk.tools.mcp_tool import McpToolset
    from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
    from mcp import StdioServerParameters

    async def go():
        toolset = McpToolset(connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(command=sys.executable, args=[SERVER], env=env), timeout=60),
            tool_filter=["krouter_ask"])
        try:
            tools = {t.name: t for t in await toolset.get_tools()}
            assert set(tools) == {"krouter_ask"}  # tool_filter 只放进 krouter_ask
            ask = tools["krouter_ask"]
            known = text_of(await ask.run_async(args={"query": KNOWN}, tool_context=None))
            unknown = text_of(await ask.run_async(args={"query": UNKNOWN}, tool_context=None))
            check_answers(known, unknown)
        finally:
            await toolset.close()

    run(go())


# ---------- CrewAI ----------

def test_crewai(env):
    need("crewai")
    from crewai import Agent
    from crewai.mcp import MCPServerStdio

    agent = Agent(role="Engineer", goal="Follow the team's past decisions", backstory="Checks KRouter first",
                  mcps=[MCPServerStdio(command=sys.executable, args=[SERVER], env=env)], llm="gpt-4o-mini")
    tools = {t.name: t for t in agent.get_mcp_tools(agent.mcps)}
    ask = next(t for n, t in tools.items() if n.endswith("krouter_ask"))
    check_answers(text_of(ask.run(query=KNOWN)), text_of(ask.run(query=UNKNOWN)))
