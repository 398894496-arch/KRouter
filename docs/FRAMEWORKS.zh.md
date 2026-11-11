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
| [LangGraph 存储](#langgraph-存储长期记忆) | `krouter.integrations.langgraph.KRouterStore`，一个 `BaseStore`（不走 MCP） | 已在真实的图里实测，同步和异步：`tests/test_langgraph_store.py`（langgraph 1.0.0 配 langgraph-checkpoint 2.1.0，1.2.20 配 4.3.1） |
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

## LangGraph 存储（长期记忆）

LangGraph 自己的长期记忆接口，不走 MCP：一个 `BaseStore`，交给 `compile(store=...)`，图里的节点就在 KRouter 上调
`put`、`get`、`search`、`delete`、`list_namespaces`（以及 `a` 开头的异步版本）。一个命名空间是一个文件夹
（`("users", "ada")` 就是 `users/ada/`），一条记忆是里面的一页 Markdown；带 `query` 的搜索只在这个命名空间里跑 KRouter
的召回。

```sh
pip install "krouter[langgraph]"           # 2.0.0 发到 PyPI 之后；现在还没有
pip install "./KRouter[langgraph]"         # 在那之前，从本仓库的克隆装
python -m krouter.integrations.langgraph_demo   # 下面这个例子，不调模型、不要 key
```

这个附加组只多装 `langgraph>=1.0,<2`（要 Python 3.10+）；只装 `pip install krouter` 照旧没有任何依赖。

```python
from dataclasses import dataclass
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.runtime import Runtime
from krouter.integrations.langgraph import KRouterStore

@dataclass
class Context:
    user_id: str

def assistant(state: MessagesState, runtime: Runtime[Context]):   # 这里是写死的节点；换成调模型的节点也一样用
    text, ns = state["messages"][-1].content, ("users", runtime.context.user_id)
    if text.lower().startswith("remember:"):
        runtime.store.put(ns, "fact-1", {"content": text.split(":", 1)[1].strip()})
        return {"messages": [AIMessage("Saved.")]}
    hits = runtime.store.search(ns, query=text, limit=1)
    return {"messages": [AIMessage(f"{hits[0].value['content']}  [from {hits[0].page}]" if hits
                                   else "Nothing in my memory about that.")]}

builder = StateGraph(MessagesState, context_schema=Context)
builder.add_node("assistant", assistant)
builder.add_edge(START, "assistant")
graph = builder.compile(checkpointer=InMemorySaver(), store=KRouterStore("./memory"))

ask = lambda user, thread, text: graph.invoke({"messages": [HumanMessage(text)]},
                                              {"configurable": {"thread_id": thread}}, context=Context(user))
ask("ada", "thread-1", "Remember: I am allergic to peanuts, so no satay.")
ask("ada", "thread-2", "Am I allergic to anything?")   # 换了一个线程：答案从存储里来，带出处页
```

例子的输出里有这几行：

```
agent: I am allergic to peanuts, so no satay.  [from users/ada/fact-1.md]
agent: Nothing in my memory about that.        （ada 问 "Which car do I drive?"）
agent: Nothing in my memory about that.        （另一个用户 ben 问 ada 那个问题）
```

**页面。** `users/ada/fact-1.md` 就是普通的 Markdown：frontmatter（命名空间、键、状态、版本、时间）加正文。值只有一个
字符串字段时（`{"content": "..."}`），正文就是这段字，在任何编辑器里改正文就是改这条记忆；别的值整个存成一行 JSON
（`value:`），正文是各字段的可读列表。你自己往命名空间文件夹里加的页也算记忆，读成 `{"content": <正文>}`。这个文件夹可以
放在你的 KRouter 库里（`KRouterStore("<库>/LangGraph")`），这样它的页在你的编程应用里也能查到。搜索索引放在
`~/.cache/krouter/langgraph`（或 `cache_dir=`），从不放进记忆文件夹。

**改一条记忆。** 对已经有页的键再 `put`，旧页会留在旁边的 `.history/` 里，标成 `status: superseded`，带
`superseded_by` 和 `superseded_at`；新页写明它取代了哪一页（`supersedes:`，也就是 `item.supersedes`），并记 `version`。
`delete` 把最后一版留在那里，标成 `retired`。旧版本永远不会回答搜索。`store.history(ns, key)` 读回旧版本；必须彻底删掉
时用 `store.purge(ns, key)`，连历史一起删。写入和原来一样的值不算改动，不多留一版。

**结果里有什么。** LangGraph 定义的 `Item` 和 `SearchItem`，多带 `page`（文件夹里的路径）、`path`、`supersedes` 和
`version`；带 query 的结果还有 `how`（召回对上的那一行）和 `confidence`，`score` 是相对第一条的分数。空列表就是这个命名
空间里没有。

| 这条路上的 KRouter 能力 | |
|---|---|
| 每条结果带出处页 | 有：`item.page` |
| 命名空间里没有时拒答 | 有：返回 `[]`；`min_confidence="medium"` 或 `"high"` 更严 |
| 改主意（被取代的不再回答） | 有，按键：`.history/`、`supersedes`、`history()` |
| 命名空间之间隔离 | 有：每次查询只给它自己的命名空间建索引（外加 KRouter 自带的两份样例库：固定的参照页，从不返回，让只有两页的命名空间里词的统计也有意义） |
| `filter`、`limit`/`offset`、带 prefix、suffix、`*`、`max_depth` 的 `list_namespaces` | 有，语义同 LangGraph 的 `InMemoryStore`（过滤一个不存在的字段算不匹配，`InMemoryStore` 会报错） |
| `index=False`、`index=["字段"]` | 有：不进 query 搜索，或只有这些字段可搜 |
| 联想、冲突标记、经验摘要、别名锁、`krouter_correct`、夜间任务、变更总账和 git 提交 | 这条路上没有（召回关了联想；其余属于 MCP 服务和库的夜间任务） |
| 向量 / 语义搜索、TTL | 没有：召回按问题里的词匹配（不认同义词）；传 `ttl=` 会抛 `NotImplementedError` |
| LangGraph Platform（`langgraph.json` 里配存储）、langmem、Windows | 没测过 |

**怎么搜、代价多少。** 每次带 query 的搜索在一个单独的 Python 进程里跑 KRouter 的召回（笔记本上约 0.06 秒；不往任何地方
发数据，不记查询日志），用的是每个命名空间一份、约 230 KB 的索引，按文件时间随时更新，所以刚写的、刚改过的页马上能搜到。
问句里的 "the user"、"用户" 当作命名空间的主人，和 "I"、"my"、"我" 一样不计。用 300 个用户、每人 5 条记忆测过
（`bench/scale/langgraph_store.py`）：在某个用户的命名空间里问 320 个问题，能答的 129 个里 100 个第一条就是对的页，这个
用户从没说过的 191 个全部返回空，没有一个返回别的用户的页；没答上的 29 个，问法用的词页里没有（问 "what are the cats
called"，页里写的是 "two cats named Miso and Tofu"）。中文同样适用，也同样按字面：问"他的狗叫什么名字"，而页里没有"名字"
这个词，就会拒答。在很宽的前缀上查、而同一类事实在几百个用户里重复出现时（`("users",)` 上问 "who plays the cello"），可能
返回空：KRouter 的分数下限假定一件事在库里只写一次。写入时每个键一个锁文件，多个线程、多个进程可以共用一个文件夹。

**和 MCP 那条路的区别**（上面的 LangChain / LangGraph）：那条路是模型对你整个库调 `krouter_ask`，服务的所有能力都在。这条
路是你的图的代码通过 LangGraph 的标准接口读写按用户、按线程分的记忆，不用跑服务。两条路可以共用一个文件夹。

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
