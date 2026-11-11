# KRouter in agent frameworks

[中文](FRAMEWORKS.zh.md)

Every framework below can use KRouter's MCP server, so one server gives each of them the same memory: the page that
answers, its one-line answer, and `recall: none` when the vault does not know. Set `KROUTER` to the server's path
once:

```python
KROUTER = "/Users/you/.agents/skills/krouter/scripts/mcp_server.py"   # after the one-line install
```

On Windows it is `C:\\Users\\you\\.agents\\skills\\krouter\\scripts\\mcp_server.py`, often with `python`
instead of `python3`. For a team server, use the framework's Streamable HTTP client with
`https://<host>/mcp/<memory>` and an `Authorization: Bearer <token>` header ([`TEAM.md`](TEAM.md)).

| | How | Status |
|---|---|---|
| [MCP Python SDK](#mcp-python-sdk) (`pip install mcp`) | stdio, or Streamable HTTP | tested: `tests/test_mcp_official_sdk.py` (mcp 1.27) |
| [LlamaIndex](#llamaindex) | `krouter.integrations.llamaindex.KRouterRetriever` | tested: `tests/test_sdk_llamaindex.py` (llama-index-core 0.14) |
| [JavaScript / TypeScript](#javascript--typescript) | `sdk/js`, no dependencies | tested: `sdk/js/test/krouter.test.js` (Node 22) |
| [LangChain / LangGraph](#langchain--langgraph) | `langchain-mcp-adapters` | tested, agent loop included (LangChain's fake chat model): `tests/test_frameworks.py` (langchain 1.4, langgraph 1.2, adapters 0.3) |
| [LangGraph store](#langgraph-store-long-term-memory) | `krouter.integrations.langgraph.KRouterStore`, a `BaseStore` (no MCP) | tested in real graphs, sync and async: `tests/test_langgraph_store.py` (langgraph 1.0.0 with langgraph-checkpoint 2.1.0, and 1.2.20 with 4.3.1) |
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

## LangGraph store (long-term memory)

LangGraph's own interface for long-term memory, without MCP: a `BaseStore` you pass to `compile(store=...)`, so your
nodes call `put`, `get`, `search`, `delete` and `list_namespaces` (and the `a...` versions) on KRouter. A namespace is
a folder (`("users", "ada")` is `users/ada/`), an item is one Markdown page in it, and a query search runs KRouter's
recall on that namespace alone.

```sh
pip install "krouter[langgraph]"           # once 2.0.0 is on PyPI; it is not there yet
pip install "./KRouter[langgraph]"         # until then, from a clone of this repository
python -m krouter.integrations.langgraph_demo   # the example below, no model and no key
```

The extra adds only `langgraph>=1.0,<2` (Python 3.10+); `pip install krouter` alone stays without dependencies.

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

def assistant(state: MessagesState, runtime: Runtime[Context]):   # scripted here; a model node works the same way
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
ask("ada", "thread-2", "Am I allergic to anything?")   # a new thread: the answer comes from the store, with its page
```

The demo prints, among its lines:

```
agent: I am allergic to peanuts, so no satay.  [from users/ada/fact-1.md]
agent: Nothing in my memory about that.        (ada: "Which car do I drive?")
agent: Nothing in my memory about that.        (ben, a different user, asks ada's question)
```

**The pages.** `users/ada/fact-1.md` is plain Markdown: a frontmatter (namespace, key, status, version, times) and
the text. A value that is one string field (`{"content": "..."}`) is the text itself, so editing it in any editor
changes the memory; any other value is kept as one JSON line (`value:`) with a readable list of its fields as the
text. A page you add to a namespace folder yourself is a memory too, read as `{"content": <its text>}`. The folder
can sit inside your KRouter vault (`KRouterStore("<vault>/LangGraph")`); its pages then also answer in your coding
apps. The search indexes live in `~/.cache/krouter/langgraph` (or `cache_dir=`), never in the folder.

**Changing a memory.** `put` on a key that has a page keeps the old page in `.history/` beside it, marked
`status: superseded` with `superseded_by` and `superseded_at`; the new page says what it replaced (`supersedes:`,
also `item.supersedes`) and counts `version`. `delete` keeps the last version there marked `retired`. Old versions
never answer a search. `store.history(ns, key)` reads them back; `store.purge(ns, key)` removes a key with its history
when it has to be gone. Writing the same value again is not a change: no new version.

**What a result carries.** `Item` and `SearchItem` as LangGraph defines them, plus `page` (the path in the folder),
`path`, `supersedes` and `version`; a query result also has `how` (the line recall matched) and `confidence`, and
`score` relative to the first result. An empty list means the namespace does not know.

| KRouter on this path | |
|---|---|
| Source page with every result | yes: `item.page` |
| Refusal when the namespace does not know | yes: `[]`; `min_confidence="medium"` or `"high"` is stricter |
| Change of mind (superseded, never answers) | yes, per key: `.history/`, `supersedes`, `history()` |
| Isolation between namespaces | yes: each query indexes only its namespace (and KRouter's two sample vaults, fixed pages that are never returned, so word statistics mean something in a namespace of two pages) |
| `filter`, `limit`/`offset`, `list_namespaces` with prefix, suffix, `*`, `max_depth` | yes, the semantics of LangGraph's `InMemoryStore` (a filter on a missing field does not match, where `InMemoryStore` raises) |
| `index=False`, `index=["field"]` | yes: kept out of query search, or only those fields searchable |
| Associations, conflict marks, experience digest, the alias lock, `krouter_correct`, the nightly jobs, the change ledger and git commits | not on this path (recall runs with associations off; the rest belong to the MCP server and the vault's nightly run) |
| Embeddings / semantic search, TTL | no: recall matches the question's words (no synonyms); `ttl=` raises `NotImplementedError` |
| LangGraph Platform (`langgraph.json` store config), langmem, Windows | not tested |

**How it searches, and what that costs.** Each query search runs KRouter's recall in its own Python process (about
0.06 s on a laptop; nothing is sent anywhere and no query is logged) over a per-namespace index of about 230 KB that it
keeps up to date from file times, so a page written or edited a moment ago is found. "The user" and "用户" in a
question are read as the namespace's owner, like "I" and "my". Tested with 300 users of 5 memories each
(`bench/scale/langgraph_store.py`): of 320 questions asked in one user's namespace, 100 of 129 answerable ones came
back with the right page first, all 191 the user never answered came back empty, and none came back with another
user's page; the 29 misses asked in words the page does not use ("what are the cats called" for "two cats named Miso
and Tofu"). A query over a broad prefix where the same kind of fact repeats across hundreds of users
(`("users",)`, "who plays the cello") can come back empty: KRouter's score floor assumes a fact is written once.
Writes take a lock file per key, so threads and processes can share one folder.

**Compared with the MCP route** (LangChain / LangGraph above): there, the model calls `krouter_ask` on your whole
vault, with everything the server does. Here, your graph's code reads and writes per-user and per-thread memories
through LangGraph's standard interface, and no server runs. They can share one folder.

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
