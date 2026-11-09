# KRouter in agent frameworks

[中文](FRAMEWORKS.zh.md)

Every framework below can use KRouter's MCP server, so one server gives each of them the same memory: the page that
answers, its one-line answer, and `recall: none` when the vault does not know. Set `KROUTER` to the server's path
once:

```python
KROUTER = "/Users/you/.agents/skills/krouter-obsidian/scripts/mcp_server.py"   # after the one-line install
```

On Windows it is `C:\\Users\\you\\.agents\\skills\\krouter-obsidian\\scripts\\mcp_server.py`, often with `python`
instead of `python3`. For a team server, use the framework's Streamable HTTP client with
`https://<host>/mcp/<memory>` and an `Authorization: Bearer <token>` header ([`TEAM.md`](TEAM.md)).

| | How | Status |
|---|---|---|
| [MCP Python SDK](#mcp-python-sdk) (`pip install mcp`) | stdio, or Streamable HTTP | tested: `tests/test_mcp_official_sdk.py` (mcp 1.27) |
| [LlamaIndex](#llamaindex) | `krouter.integrations.llamaindex.KRouterRetriever` | tested: `tests/test_sdk_llamaindex.py` (llama-index-core 0.14) |
| [JavaScript / TypeScript](#javascript--typescript) | `sdk/js`, no dependencies | tested: `sdk/js/test/krouter.test.js` (Node 22) |
| [LangChain / LangGraph](#langchain--langgraph) | `langchain-mcp-adapters` | tested, agent loop included (LangChain's fake chat model): `tests/test_frameworks.py` (langchain 1.4, langgraph 1.2, adapters 0.3) |
| [OpenAI Agents SDK](#openai-agents-sdk) | `agents.mcp.MCPServerStdio` | tested: `tests/test_frameworks.py` (openai-agents 0.24) |
| [Pydantic AI](#pydantic-ai) | `pydantic_ai.mcp.MCPToolset` | tested, agent loop included (Pydantic AI's `FunctionModel`): `tests/test_frameworks.py` (pydantic-ai-slim 2.66, fastmcp 4.1) |
| [Google ADK](#google-adk) | `McpToolset` | tested: `tests/test_frameworks.py` (google-adk 2.14 with the `mcp` extra) |
| [CrewAI](#crewai) | the agent's `mcps=` field | tested: `tests/test_frameworks.py` (crewai 1.15) |
| [Vercel AI SDK](#vercel-ai-sdk) | `createMCPClient` from `@ai-sdk/mcp` | tested, with the SDK's mock model: `tests/frameworks/vercel/` (ai 7.0, @ai-sdk/mcp 2.0) |

Every row is run against KRouter's real server on 2026-11-09, with the versions in brackets: the framework loads
the server over stdio the way its snippet below shows, lists the tools, gets the cited page for a question the vault
knows and `recall: none` for one it does not. Where a framework ships a stand-in model (LangChain, Pydantic AI, the
Vercel AI SDK), its whole agent loop runs too: the model calls `krouter_ask` and answers from the page. No model is
called and no key is needed. CI runs each framework in its own environment (`.github/workflows/ci.yml`, jobs
`frameworks` and `vercel-ai-sdk`). The tested clients carry two major versions of the MCP SDK (1.30 and 2.3).

Whatever the framework, tell the model what the tool is for, as KRouter's own server instructions do: ask the vault
before answering a question about how the user does things or what was decided; answer from the `how` line and cite
the page; say "not in the vault" on `recall: none` instead of guessing.

## MCP Python SDK

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    async with stdio_client(StdioServerParameters(command="python3", args=[KROUTER])) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool("krouter_ask", {"query": "how do we ship a release?"})
            print(res.content[0].text)

asyncio.run(main())
```

## LlamaIndex

A retriever, so it goes anywhere LlamaIndex takes one (query engines, chat engines, agent tools). The answering page
comes back as one node with its source; nothing comes back when the vault does not know, so the engine has no weak
match to make an answer from.

```python
# pip install "krouter[llamaindex] @ git+https://github.com/398894496-arch/KRouter"
from krouter.integrations.llamaindex import KRouterRetriever
from llama_index.core.query_engine import RetrieverQueryEngine

retriever = KRouterRetriever()                         # the installed vault, or vault="/path/to/vault"
nodes = retriever.retrieve("how do we ship a release?")
nodes[0].node.text, nodes[0].node.metadata["page"]     # the one-line answer, the page
engine = RetrieverQueryEngine.from_args(retriever, llm=your_llm)
```

## JavaScript / TypeScript

No dependencies (Node 18+): it starts the local server over stdio, or talks to a team server over Streamable HTTP.

```js
import { KRouter } from "./sdk/js/index.js";          // the npm package is not published yet

const kr = KRouter.local();
const a = await kr.ask("how do we ship a release?");
console.log(a.page, a.how, a.refused);
await kr.close();

const team = KRouter.remote("https://krouter.example/mcp/team", { token: process.env.KROUTER_TOKEN });
```

## LangChain / LangGraph

```python
# pip install langchain-mcp-adapters langgraph "langchain[openai]"
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent

client = MultiServerMCPClient({"krouter": {"command": "python3", "args": [KROUTER], "transport": "stdio"}})
tools = await client.get_tools()                      # krouter_ask, krouter_status, krouter_note
agent = create_agent("openai:gpt-4.1", tools)
```

The adapter's README now says it is no longer actively maintained and points to `langchain[mcp]`; the server side
does not change.

## OpenAI Agents SDK

```python
# pip install openai-agents
from agents import Agent, Runner
from agents.mcp import MCPServerStdio

async with MCPServerStdio(name="KRouter", params={"command": "python3", "args": [KROUTER]}) as krouter:
    agent = Agent(name="Assistant", instructions="Ask KRouter before answering about past decisions.",
                  mcp_servers=[krouter])
    result = await Runner.run(agent, "How do we ship a release?")
```

## Pydantic AI

```python
# pip install "pydantic-ai-slim[mcp]" fastmcp
from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset

agent = Agent("openai:gpt-6.1-sol", toolsets=[MCPToolset(StdioTransport(command="python3", args=[KROUTER]))])
async with agent:
    result = await agent.run("How do we ship a release?")
```

## Google ADK

```python
# pip install "google-adk[mcp]"     (since 2.x MCP support is the `mcp` extra; plain google-adk has no McpToolset)
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

root_agent = LlmAgent(
    model="gemini-flash-latest", name="assistant", instruction="Ask KRouter before answering about past decisions.",
    tools=[McpToolset(connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(command="python3", args=[KROUTER])),
        tool_filter=["krouter_ask"])],
)
```

## CrewAI

```python
# pip install crewai
from crewai import Agent
from crewai.mcp import MCPServerStdio

agent = Agent(role="Engineer", goal="Follow the team's past decisions", backstory="Checks KRouter first",
              mcps=[MCPServerStdio(command="python3", args=[KROUTER])])
```

## Vercel AI SDK

```ts
// npm install ai @ai-sdk/mcp @modelcontextprotocol/sdk
import { generateText } from "ai";
import { createMCPClient } from "@ai-sdk/mcp";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const krouter = await createMCPClient({ transport: new StdioClientTransport({ command: "python3", args: [KROUTER] }) });
try {
  const { text } = await generateText({ model: "anthropic/claude-sonnet-5.5", tools: await krouter.tools(),
    prompt: "How do we ship a release?" });
} finally {
  await krouter.close();
}
```
