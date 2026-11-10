# 在智能体框架里用 KRouter

[English](FRAMEWORKS.md)

下面每个框架都能加载 KRouter 的 MCP 服务，所以一个服务就让它们共用同一份记忆：答案所在的页、一句话答案；库里没有时回 `recall: none`。先把服务的路径记一次：

```python
KROUTER = "/Users/you/.agents/skills/krouter/scripts/mcp_server.py"   # 一行安装之后就在这里
```

Windows 上是 `C:\\Users\\you\\.agents\\skills\\krouter\\scripts\\mcp_server.py`，命令常常是 `python` 而不是 `python3`。连团队服务的话，用框架自带的 Streamable HTTP 客户端，地址是 `https://<主机>/mcp/<记忆名>`，带上 `Authorization: Bearer <token>` 请求头（见 [`TEAM.md`](TEAM.md)）。

| | 怎么接 | 状态 |
|---|---|---|
| [MCP Python SDK](#mcp-python-sdk)（`pip install mcp`） | stdio，或 Streamable HTTP | 已实测：`tests/test_mcp_official_sdk.py`（mcp 1.27） |
| [LlamaIndex](#llamaindex) | `krouter.integrations.llamaindex.KRouterRetriever` | 已实测：`tests/test_sdk_llamaindex.py`（llama-index-core 0.14） |
| [JavaScript / TypeScript](#javascript--typescript) | `sdk/js`，不依赖任何包 | 已实测：`sdk/js/test/krouter.test.js`（Node 22） |
| [LangChain / LangGraph](#langchain--langgraph) | `langchain-mcp-adapters` | 已实测，含完整 agent 流程（LangChain 自带的假聊天模型）：`tests/test_frameworks.py`（langchain 1.4、langgraph 1.2、适配器 0.3） |
| [OpenAI Agents SDK](#openai-agents-sdk) | `agents.mcp.MCPServerStdio` | 已实测：`tests/test_frameworks.py`（openai-agents 0.24） |
| [Pydantic AI](#pydantic-ai) | `pydantic_ai.mcp.MCPToolset` | 已实测，含完整 agent 流程（Pydantic AI 的 `FunctionModel`）：`tests/test_frameworks.py`（pydantic-ai-slim 2.66、fastmcp 4.1） |
| [Google ADK](#google-adk) | `McpToolset` | 已实测：`tests/test_frameworks.py`（google-adk 2.14，带 `mcp` 扩展） |
| [CrewAI](#crewai) | agent 的 `mcps=` 字段 | 已实测：`tests/test_frameworks.py`（crewai 1.15） |
| [Vercel AI SDK](#vercel-ai-sdk) | `@ai-sdk/mcp` 的 `createMCPClient` | 已实测，用 SDK 自带的假模型：`tests/frameworks/vercel/`（ai 7.0、@ai-sdk/mcp 2.0） |

每一行都在 2026-11-09 对着 KRouter 真实的服务跑过，版本写在括号里：框架照下面的写法通过 stdio 加载服务、列出工具，库里有的问题拿回带出处的页，库里没有的拿回 `recall: none`。自带假模型的框架（LangChain、Pydantic AI、Vercel AI SDK）还把整个 agent 流程跑了一遍：模型调 `krouter_ask`，再照查回来的页作答。全程不调任何模型，也不用 key。CI 里每个框架各装在自己的环境里跑（`.github/workflows/ci.yml` 的 `frameworks` 和 `vercel-ai-sdk` 两个任务）。测过的客户端带的是两个大版本的 MCP SDK（1.30 和 2.3）。

不管用哪个框架，都要告诉模型这个工具是干什么的，就像 KRouter 自己的服务说明那样：用户问到做事的习惯、以前定过什么，先查库；用 `how` 那一行回答并注明出处页；遇到 `recall: none` 就直说库里没有，不要猜。

## MCP Python SDK

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    async with stdio_client(StdioServerParameters(command="python3", args=[KROUTER])) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool("krouter_ask", {"query": "我们怎么发版？"})
            print(res.content[0].text)

asyncio.run(main())
```

## LlamaIndex

这是一个检索器，LlamaIndex 能放检索器的地方都能放（查询引擎、聊天引擎、agent 工具）。答案所在的页作为一个带出处的节点返回；库里没有时什么都不返回，引擎也就拿不到勉强凑上的结果去编答案。

```python
# pip install "krouter[llamaindex] @ git+https://github.com/398894496-arch/KRouter"
from krouter.integrations.llamaindex import KRouterRetriever
from llama_index.core.query_engine import RetrieverQueryEngine

retriever = KRouterRetriever()                         # 一行安装记下的那个库；也可以 vault="/path/to/vault"
nodes = retriever.retrieve("我们怎么发版？")
nodes[0].node.text, nodes[0].node.metadata["page"]     # 一句话答案、出处页
engine = RetrieverQueryEngine.from_args(retriever, llm=your_llm)
```

## JavaScript / TypeScript

不依赖任何包（Node 18+）：可以在本机用 stdio 启动服务，也可以走 Streamable HTTP 连团队服务。

```js
import { KRouter } from "./sdk/js/index.js";          // npm 包还没发布

const kr = KRouter.local();
const a = await kr.ask("我们怎么发版？");
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
tools = await client.get_tools()                      # krouter_ask、krouter_status、krouter_note
agent = create_agent("openai:gpt-4.1", tools)
```

这个适配器的 README 现在写着它不再积极维护，建议改用 `langchain[mcp]`；服务这一端不用改。

## OpenAI Agents SDK

```python
# pip install openai-agents
from agents import Agent, Runner
from agents.mcp import MCPServerStdio

async with MCPServerStdio(name="KRouter", params={"command": "python3", "args": [KROUTER]}) as krouter:
    agent = Agent(name="Assistant", instructions="回答以前定过的事之前，先问 KRouter。",
                  mcp_servers=[krouter])
    result = await Runner.run(agent, "我们怎么发版？")
```

## Pydantic AI

```python
# pip install "pydantic-ai-slim[mcp]" fastmcp
from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset

agent = Agent("openai:gpt-6.1-sol", toolsets=[MCPToolset(StdioTransport(command="python3", args=[KROUTER]))])
async with agent:
    result = await agent.run("我们怎么发版？")
```

## Google ADK

```python
# pip install "google-adk[mcp]"     （2.x 起 MCP 支持放进了 mcp 扩展；只装 google-adk 没有 McpToolset）
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

root_agent = LlmAgent(
    model="gemini-flash-latest", name="assistant", instruction="回答以前定过的事之前，先问 KRouter。",
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

agent = Agent(role="工程师", goal="按团队以前的决定做事", backstory="动手前先查 KRouter",
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
    prompt: "我们怎么发版？" });
} finally {
  await krouter.close();
}
```
