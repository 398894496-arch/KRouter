"""A LangGraph graph with KRouter as its long-term memory, in two turns, with no model and no key.

    python -m krouter.integrations.langgraph_demo            # in a new temporary folder
    python -m krouter.integrations.langgraph_demo ./memory   # in a folder you choose (it keeps the pages)

Turn 1 (thread 1): the user asks the agent to remember something; the graph saves it under ("users", <id>).
Turn 2 (thread 2, a new conversation): the user asks about it; the graph finds it in the store and prints the page it
came from. Asked something it was never told, it says so instead of offering the nearest memory. Then another user
asks the first question and gets nothing: their namespace does not hold it. The node is
scripted, standing in for a model, so it runs anywhere.
"""

from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.runtime import Runtime

from krouter.integrations.langgraph import KRouterStore


@dataclass
class Context:
    user_id: str


def assistant(state: MessagesState, runtime: Runtime[Context]) -> dict:
    """Saves what follows "remember:", else answers from the user's memories (the cited page) or says it does not know."""
    text = state["messages"][-1].content
    namespace = ("users", runtime.context.user_id)
    if text.lower().startswith("remember:"):
        fact = text.split(":", 1)[1].strip()
        runtime.store.put(namespace, "fact-" + str(len(runtime.store.search(namespace, limit=1000)) + 1),
                          {"content": fact})
        return {"messages": [AIMessage(f"Saved: {fact}")]}
    hits = runtime.store.search(namespace, query=text, limit=1)
    if not hits:
        return {"messages": [AIMessage("Nothing in my memory about that.")]}
    return {"messages": [AIMessage(f"{hits[0].value['content']}  [from {hits[0].page}]")]}


def build(store: KRouterStore):
    builder = StateGraph(MessagesState, context_schema=Context)
    builder.add_node("assistant", assistant)
    builder.add_edge(START, "assistant")
    return builder.compile(checkpointer=InMemorySaver(), store=store)


def turn(graph, user: str, thread: str, text: str) -> str:
    out = graph.invoke({"messages": [HumanMessage(text)]}, {"configurable": {"thread_id": thread}},
                       context=Context(user_id=user))
    return out["messages"][-1].content


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        folder = Path(argv[0]).expanduser()
        cache = None
    else:
        tmp = Path(tempfile.mkdtemp(prefix="krouter-langgraph-"))
        folder, cache = tmp / "memory", tmp / "cache"
    graph = build(KRouterStore(folder, cache_dir=cache))
    script = [("ada", "thread-1", "Remember: I am allergic to peanuts, so no satay."),
              ("ada", "thread-2", "Am I allergic to anything?"),
              ("ada", "thread-2", "Which car do I drive?"),
              ("ben", "thread-3", "Am I allergic to anything?")]
    for user, thread, text in script:
        print(f"{user} ({thread}): {text}")
        print(f"agent: {turn(graph, user, thread, text)}")
    print(f"memory folder: {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
