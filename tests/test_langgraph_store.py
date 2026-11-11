"""KRouter as a LangGraph store (krouter.integrations.langgraph): the BaseStore interface, sync and async; namespace
isolation; the superseded trail; refusals; a real graph. Skipped when langgraph is not installed, unless
KROUTER_REQUIRE_LANGGRAPH=1 (CI's langgraph job), where a missing install fails instead. No model is called."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if os.environ.get("KROUTER_REQUIRE_LANGGRAPH") != "1":
    pytest.importorskip("langgraph.store.base")
sys.path.insert(0, str(REPO / "sdk"))

from langgraph.store.base import GetOp, InvalidNamespaceError, PutOp, SearchOp  # noqa: E402
from langgraph.store.memory import InMemoryStore  # noqa: E402

from krouter.integrations.langgraph import KRouterStore, _decode, _encode  # noqa: E402

A = ("users", "alice", "memories")
B = ("users", "bob", "memories")


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("KROUTER_NO_QUERY_LOG", "1")
    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path / "state"))
    return KRouterStore(tmp_path / "memory", cache_dir=tmp_path / "cache")


def facts(store):
    store.put(A, "diet", {"content": "Alice is vegetarian and never eats fish."})
    store.put(A, "pet", {"content": "Alice has a dog called Biscuit who is afraid of thunder."})
    store.put(B, "diet", {"content": "Bob is allergic to peanuts and loves spicy ramen."})
    store.put(B, "car", {"content": "Bob drives an old red Volvo estate."})


# -- the interface --------------------------------------------------------------------------------------------------


def test_put_get_round_trip_and_timestamps(store):
    store.put(A, "diet", {"content": "Alice is vegetarian."})
    first = store.get(A, "diet")
    assert first.value == {"content": "Alice is vegetarian."} and first.key == "diet" and first.namespace == A
    assert first.page == "users/alice/memories/diet.md" and Path(first.path).is_file() and first.version == 1
    store.put(A, "diet", {"content": "Alice eats fish again."})
    second = store.get(A, "diet")
    assert second.value == {"content": "Alice eats fish again."} and second.version == 2
    assert second.created_at == first.created_at and second.updated_at > first.updated_at
    assert store.get(A, "nope") is None and store.get(("users", "nobody"), "diet") is None


def test_values_that_are_not_one_text_field_round_trip(store):
    values = {
        "profile": {"name": "Alice", "city": "Lyon", "langs": ["fr", "en"], "age": 41, "vip": True, "x": None},
        "nested": {"a": {"b": [1, {"c": "deep"}]}, "empty": {}},
        "padded": {"content": "  leading and trailing spaces  "},
        "multi": {"content": "line one\nline two\n\n- a bullet"},
        "empty": {},
        "number": {"content": 3},
        "unicode": {"content": "爱丽丝不吃鱼 🐟"},
    }
    for k, v in values.items():
        store.put(A, k, v)
    for k, v in values.items():
        assert store.get(A, k).value == v, k
    with pytest.raises(TypeError):
        store.put(A, "bad", {"when": object()})
    assert store.get(A, "bad") is None


def test_the_page_is_plain_markdown_a_person_can_edit(store):
    store.put(A, "diet", {"content": "Alice is vegetarian and never eats fish."})
    store.put(A, "profile", {"name": "Alice", "city": "Lyon"})
    page = Path(store.get(A, "diet").path)
    text = page.read_text(encoding="utf-8")
    assert text.startswith("---\n") and 'key: "diet"' in text and "status: active" in text
    assert text.rstrip().endswith("Alice is vegetarian and never eats fish.")
    assert "- city: Lyon" in Path(store.get(A, "profile").path).read_text(encoding="utf-8")
    # 人在编辑器里改了正文：存储读到的就是改过的
    page.write_text(text.replace("never eats fish", "eats fish on Fridays"), encoding="utf-8")
    assert store.get(A, "diet").value == {"content": "Alice is vegetarian and eats fish on Fridays."}
    assert [i.key for i in store.search(A, query="does she eat fish on Fridays")] == ["diet"]


def test_a_page_added_by_hand_is_a_memory(store):
    folder = store.root / "users" / "alice" / "memories"
    folder.mkdir(parents=True)
    (folder / "Weekend plans.md").write_text("Alice goes climbing in Fontainebleau most weekends.\n", encoding="utf-8")
    item = store.get(A, "Weekend plans")
    assert item.value == {"content": "Alice goes climbing in Fontainebleau most weekends."}
    assert store.get(A, "weekend plans") is None  # 大小写不同就是另一个键，即使磁盘不分大小写
    assert [i.key for i in store.search(A, query="where does she go climbing")] == ["Weekend plans"]
    store.put(A, "Weekend plans", {"content": "Alice stopped climbing; she runs now."})
    assert store.get(A, "Weekend plans").value == {"content": "Alice stopped climbing; she runs now."}
    assert not (folder / "Weekend plans.md").exists()  # 交给存储自己的页接替，原页进了历史
    assert [h.value for h in store.history(A, "Weekend plans")] == [
        {"content": "Alice goes climbing in Fontainebleau most weekends."}]


def test_search_without_query_filter_limit_offset(store):
    for i in range(7):
        store.put(A, f"k{i}", {"kind": "even" if i % 2 == 0 else "odd", "n": i})
    got = store.search(A, limit=100)
    assert [i.key for i in got] == [f"k{i}" for i in reversed(range(7))]  # 最近更新的在前
    assert [i.key for i in store.search(A, limit=2, offset=1)] == ["k5", "k4"]
    assert {i.key for i in store.search(A, filter={"kind": "odd"})} == {"k1", "k3", "k5"}
    assert {i.key for i in store.search(A, filter={"n": {"$gte": 5}})} == {"k5", "k6"}
    assert {i.key for i in store.search(A, filter={"kind": "even", "n": {"$lt": 3, "$ne": 0}})} == {"k2"}
    assert store.search(A, filter={"missing": "x"}) == []


def test_list_namespaces(store):
    facts(store)
    store.put(("users", "alice", "threads", "t1"), "summary", {"content": "Planned the Lyon trip."})
    store.put(("teams", "red"), "rule", {"content": "Deploy on Tuesdays."})
    assert store.list_namespaces() == [("teams", "red"), ("users", "alice", "memories"),
                                       ("users", "alice", "threads", "t1"), ("users", "bob", "memories")]
    assert store.list_namespaces(prefix=("users",), max_depth=2) == [("users", "alice"), ("users", "bob")]
    assert store.list_namespaces(prefix=("users", "*", "memories")) == [A, B]
    assert store.list_namespaces(suffix=("memories",)) == [A, B]
    assert store.list_namespaces(limit=1, offset=1) == [A]
    store.delete(("teams", "red"), "rule")
    assert ("teams", "red") not in store.list_namespaces()


def test_matches_langgraphs_own_in_memory_store(store):
    """The same writes on both stores give the same reads (search without a query; with one, embeddings and KRouter
    rank differently by design)."""
    ref = InMemoryStore()
    ops = [(A, "a", {"content": "one"}), (A, "b", {"n": 2, "tags": ["x", "y"]}), (B, "a", {"content": "two"}),
           (("users", "alice", "threads", "t1"), "s", {"content": "three"}), (A, "a", {"content": "one, again"}),
           (B, "a", None), (A, "c", {"n": 5})]
    for ns, key, value in ops:
        for s in (store, ref):
            s.delete(ns, key) if value is None else s.put(ns, key, value)
    for ns, key in [(A, "a"), (A, "b"), (B, "a"), (A, "zzz")]:
        mine, theirs = store.get(ns, key), ref.get(ns, key)
        assert (mine and (mine.value, mine.key, mine.namespace)) == (theirs and (theirs.value, theirs.key,
                                                                                  theirs.namespace))
    for prefix, flt in [(A, None), (("users",), None), (A, {"n": 5}), (A, {"tags": ["x", "y"]}),
                        (("users",), {"content": "three"})]:
        mine = {(i.namespace, i.key, str(i.value)) for i in store.search(prefix, filter=flt, limit=100)}
        theirs = {(i.namespace, i.key, str(i.value)) for i in ref.search(prefix, filter=flt, limit=100)}
        assert mine == theirs, (prefix, flt)
    # InMemoryStore 删到空的命名空间还会列出来；KRouterStore 只列还有记忆的命名空间
    assert set(store.list_namespaces()) <= set(ref.list_namespaces())


def test_namespace_and_key_validation(store):
    for bad in [("users", "a.b"), ("users", ""), ("", "x")]:
        with pytest.raises(InvalidNamespaceError):
            store.put(bad, "k", {"content": "x"})
        with pytest.raises(InvalidNamespaceError):
            store.search(bad)
    with pytest.raises(InvalidNamespaceError):
        store.put((), "k", {"content": "x"})
    with pytest.raises(InvalidNamespaceError):
        store.put(("langgraph", "x"), "k", {"content": "x"})
    with pytest.raises(InvalidNamespaceError):  # 直接交给 batch 的操作也检查，一个不合法就一个都不做
        store.batch([PutOp(A, "ok", {"content": "x"}), PutOp(("a.b",), "k", {"content": "x"})])
    assert store.get(A, "ok") is None
    with pytest.raises(NotImplementedError):
        store.put(A, "k", {"content": "x"}, ttl=5)
    with pytest.raises(NotImplementedError):
        store.batch([PutOp(A, "first", {"content": "x"}), PutOp(A, "k", {"content": "x"}, ttl=5.0)])
    assert store.get(A, "first") is None


def test_keys_and_labels_that_are_awkward_file_names(store):
    keys = ["a/b", "", ".env", "CON", "nul.txt", "x%y~z", "trailing.", " spaced ", "q?*:<>|\"\\", "#tag^[1]",
            "Alice", "alice", "ALICE", "é", "é", "k" * 300, "爱丽丝", "a@b.com"]
    for i, k in enumerate(keys):
        store.put(A, k, {"content": f"value {i}"})
    for i, k in enumerate(keys):
        assert store.get(A, k).value == {"content": f"value {i}"}, repr(k)
    assert sorted(i.key for i in store.search(A, limit=100)) == sorted(keys)
    names = [p.name for p in (store.root / "users/alice/memories").iterdir() if p.suffix == ".md"]
    assert len(names) == len(keys) and len({n.lower() for n in names}) == len(keys)  # 不分大小写的磁盘上也不撞
    assert all(len(n.encode()) < 200 and not n.startswith(".") for n in names)
    labels = ["Alice", "alice", "a/b", "CON", "爱丽丝", "x%~y"]
    for lab in labels:
        store.put(("users", lab), "k", {"content": lab})
    assert set(store.list_namespaces(prefix=("users",), max_depth=2)) == {("users", lab) for lab in labels}
    for lab in labels:
        assert store.get(("users", lab), "k").value == {"content": lab}
        assert _decode(_encode(lab, 10**6)) == lab


# -- KRouter's part: sources, refusals, the superseded trail -----------------------------------------------------------


def test_search_returns_the_page_it_came_from(store):
    facts(store)
    hits = store.search(A, query="what is the dog called")
    assert [h.key for h in hits] == ["pet"]
    assert hits[0].page == "users/alice/memories/pet.md" and Path(hits[0].path).is_file()
    assert hits[0].score == 1.0 and hits[0].confidence in ("low", "medium", "high") and "Biscuit" in hits[0].how
    assert hits[0].dict()["page"] == "users/alice/memories/pet.md"


def test_empty_when_the_namespace_does_not_know(store):
    facts(store)
    for q in ["which car does she drive", "what is her favourite football team", "is she allergic to peanuts",
              "kubernetes cluster upgrade"]:
        assert store.search(A, query=q) == [], q
    assert store.search(("users", "carol"), query="does she eat fish") == []  # 没有这个命名空间
    assert [h.key for h in store.search(B, query="is the user allergic to peanuts")] == ["diet"]


def test_one_namespace_never_answers_for_another(store):
    facts(store)
    store.put(("users", "alice", "threads", "t1"), "note", {"content": "Booked the cello lesson for Monday."})
    for q, owner in [("is the user allergic to peanuts", B), ("which car does the user drive", B),
                     ("does the user eat fish", A), ("what is the dog called", A)]:
        other = A if owner == B else B
        assert store.search(owner, query=q), q
        assert store.search(other, query=q) == [], q
        assert all(h.namespace == owner for h in store.search(owner, query=q))
    # 线程也是命名空间：线程里的记忆不出现在用户的 memories 里，前缀 ("users", "alice") 能同时看到两个
    assert store.search(A, query="when is the cello lesson") == []
    hits = store.search(("users", "alice"), query="when is the cello lesson")
    assert [h.namespace for h in hits] == [("users", "alice", "threads", "t1")]
    # 前缀 ("users",) 看得到所有人的
    assert {h.namespace for h in store.search(("users",), query="is the user allergic to peanuts")} == {B}
    assert {i.namespace for i in store.search(A, limit=100)} == {A}


def test_chinese_memories(store):
    wang, li = ("用户", "小王"), ("用户", "老李")
    store.put(wang, "饮食", {"content": "小王对花生过敏，点菜时要避开沙爹。"})
    store.put(wang, "宠物", {"content": "小王养了一只叫饼干的狗，怕打雷。"})
    store.put(li, "出行", {"content": "老李每天骑自行车上班。"})
    assert store.search(wang, query="小王对什么过敏")[0].page == "用户/小王/饮食.md"
    assert [h.key for h in store.search(li, query="老李怎么上班")] == ["出行"]
    assert store.search(wang, query="用户开什么车") == []
    assert store.search(wang, query="老李怎么上班") == [] and store.search(li, query="用户对什么过敏") == []


def test_namespaces_differing_only_in_case_stay_apart(store):
    store.put(("users", "Alice"), "diet", {"content": "This Alice never eats fish."})
    store.put(("users", "alice"), "pet", {"content": "This alice has a parrot called Kiwi."})
    assert store.search(("users", "alice"), query="does she eat fish") == []
    assert [h.key for h in store.search(("users", "Alice"), query="does she eat fish")] == ["diet"]
    assert [i.key for i in store.search(("users", "alice"))] == ["pet"]


def test_writing_a_key_again_keeps_what_it_replaced(store):
    store.put(A, "diet", {"content": "Alice is vegetarian and never eats fish."})
    store.put(A, "diet", {"content": "Alice eats fish again but still no red meat."})
    cur = store.get(A, "diet")
    old = store.history(A, "diet")
    assert len(old) == 1 and old[0].value == {"content": "Alice is vegetarian and never eats fish."}
    assert old[0].status == "superseded" and cur.supersedes == old[0].page and old[0].page.startswith(
        "users/alice/memories/.history/diet@")
    text = Path(old[0].path).read_text(encoding="utf-8")
    assert "status: superseded" in text and 'superseded_by: "../diet.md"' in text and "superseded_at:" in text
    # 被取代的说法不再回答问题；新的说法回答
    assert store.search(A, query="is she vegetarian") == []
    assert [h.key for h in store.search(A, query="does she eat red meat")] == ["diet"]
    # 再写一次同样的内容：不是改主意，不多留一版
    store.put(A, "diet", {"content": "Alice eats fish again but still no red meat."})
    assert len(store.history(A, "diet")) == 1 and store.get(A, "diet").version == 2
    store.put(A, "diet", {"content": "Alice is vegan now."})
    assert [h.value["content"] for h in store.history(A, "diet")] == [
        "Alice eats fish again but still no red meat.", "Alice is vegetarian and never eats fish."]
    assert [i.key for i in store.search(A, limit=100)] == ["diet"]  # 旧版本不算条目


def test_delete_retires_the_page_and_purge_removes_it(store):
    store.put(A, "diet", {"content": "Alice is vegetarian and never eats fish."})
    store.put(A, "diet", {"content": "Alice eats fish again."})
    store.delete(A, "diet")
    assert store.get(A, "diet") is None and store.search(A) == [] and store.search(A, query="does she eat fish") == []
    assert [h.status for h in store.history(A, "diet")] == ["retired", "superseded"]
    store.delete(A, "diet")  # 删不存在的键：什么也不做
    store.put(A, "diet", {"content": "Alice is pescatarian."})
    assert store.purge(A, "diet") == 3
    assert store.get(A, "diet") is None and store.history(A, "diet") == []
    assert not list((store.root / "users/alice/memories").rglob("*.md"))
    page = store.root / "users/alice/memories/note.md"  # 人把页标成了失效：purge 也删它
    page.write_text("---\nstatus: superseded\n---\n\nOld note.\n", encoding="utf-8")
    assert store.get(A, "note") is None and store.purge(A, "note") == 1 and not page.exists()
    assert store.purge(("users", "nobody"), "x") == 0 and not (store.root / "users/nobody").exists()


def test_index_false_and_index_fields(store):
    store.put(A, "secret-plan", {"content": "Surprise party for Alice on Saturday."}, index=False)
    store.put(A, "trip", {"title": "Lyon trip", "notes": "Book the train to Lyon", "budget": 400}, index=["notes"])
    assert store.get(A, "secret-plan").value == {"content": "Surprise party for Alice on Saturday."}
    assert store.search(A, query="when is the surprise party") == []
    assert [i.key for i in store.search(A, filter={"budget": 400})] == ["trip"]
    body = Path(store.get(A, "trip").path).read_text(encoding="utf-8").split("\n---\n", 1)[1]
    assert "notes: Book the train to Lyon" in body and "budget" not in body
    assert [h.key for h in store.search(A, query="book the train")] == ["trip"]


def test_min_confidence(tmp_path):
    strict = KRouterStore(tmp_path / "memory", cache_dir=tmp_path / "cache", min_confidence="high")
    facts(strict)
    assert strict.search(A, query="does she eat fish") == []  # 低于 high 的结果不给
    with pytest.raises(ValueError):
        KRouterStore(tmp_path / "m2", min_confidence="sure")
    with pytest.raises(ValueError):
        KRouterStore(tmp_path / "m3", cache_dir=tmp_path / "m3" / "cache")


# -- async, threads, processes ------------------------------------------------------------------------------------


def test_async_methods_match_the_sync_ones(store):
    async def run():
        await store.aput(A, "diet", {"content": "Alice is vegetarian and never eats fish."})
        await store.aput(B, "diet", {"content": "Bob is allergic to peanuts."})
        await store.aput(A, "diet", {"content": "Alice eats fish again."})
        got = await store.aget(A, "diet")
        hits = await store.asearch(A, query="does she eat fish")
        none = await store.asearch(A, query="is she allergic to peanuts")
        spaces = await store.alist_namespaces()
        hist = await store.ahistory(A, "diet")
        await store.adelete(B, "diet")
        gone = await store.aget(B, "diet")
        results = await store.abatch([GetOp(A, "diet"), SearchOp(A, query="does she eat fish")])
        return got, hits, none, spaces, hist, gone, results

    got, hits, none, spaces, hist, gone, results = asyncio.run(run())
    assert got.value == {"content": "Alice eats fish again."} and [h.key for h in hits] == ["diet"] and none == []
    assert spaces == [A, B] and len(hist) == 1 and gone is None
    assert results[0].value == got.value and [h.key for h in results[1]] == ["diet"]


def test_concurrent_writers_keep_every_version(store):
    def write(i):
        store.put(A, "counter", {"n": i})
        store.put(A, f"own-{i}", {"n": i})

    threads = [threading.Thread(target=write, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(store.history(A, "counter")) == 11
    assert store.get(A, "counter").value["n"] in range(12)
    assert len(store.search(A, limit=100)) == 13
    assert not [p for p in (store.root / "users/alice/memories").iterdir() if p.name.endswith((".lock", ".tmp"))]


def test_two_processes_share_one_folder(store, tmp_path):
    code = ("import sys; sys.path.insert(0, sys.argv[1]); from krouter.integrations.langgraph import KRouterStore; "
            "s = KRouterStore(sys.argv[2], cache_dir=sys.argv[3]); "
            "[s.put(('users', 'alice', 'memories'), 'shared', {'n': i, 'by': sys.argv[4]}) for i in range(10)]")
    procs = [subprocess.Popen([sys.executable, "-c", code, str(REPO / "sdk"), str(store.root), str(tmp_path / "c2"),
                               w]) for w in ("p1", "p2")]
    assert all(p.wait(timeout=120) == 0 for p in procs)
    assert len(store.history(A, "shared")) == 19 and store.get(A, "shared").value["n"] == 9


# -- in a real LangGraph graph ----------------------------------------------------------------------------------


def test_a_graph_remembers_across_threads(store):
    from dataclasses import dataclass

    from langchain_core.messages import AIMessage, HumanMessage
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import START, MessagesState, StateGraph
    from langgraph.runtime import Runtime

    @dataclass
    class Ctx:
        user_id: str

    def node(state: MessagesState, runtime: Runtime[Ctx]):
        text = state["messages"][-1].content
        ns = ("users", runtime.context.user_id, "memories")
        if text.startswith("remember "):
            runtime.store.put(ns, "fact", {"content": text[len("remember "):]})
            return {"messages": [AIMessage("saved")]}
        hits = runtime.store.search(ns, query=text, limit=1)
        return {"messages": [AIMessage(f"{hits[0].value['content']} | {hits[0].page}" if hits else "unknown")]}

    builder = StateGraph(MessagesState, context_schema=Ctx)
    builder.add_node("node", node)
    builder.add_edge(START, "node")
    graph = builder.compile(checkpointer=InMemorySaver(), store=store)

    def say(user, thread, text):
        out = graph.invoke({"messages": [HumanMessage(text)]}, {"configurable": {"thread_id": thread}},
                           context=Ctx(user_id=user))
        return out["messages"][-1].content

    assert say("ada", "t1", "remember Ada is allergic to peanuts.") == "saved"
    assert say("ada", "t2", "is she allergic to anything?") == (
        "Ada is allergic to peanuts. | users/ada/memories/fact.md")
    assert say("ada", "t2", "which car does she drive?") == "unknown"
    assert say("ben", "t3", "is she allergic to anything?") == "unknown"

    async def async_graph():  # 异步图走 aput / asearch
        async def anode(state: MessagesState, runtime: Runtime[Ctx]):
            hits = await runtime.store.asearch(("users", runtime.context.user_id, "memories"),
                                               query=state["messages"][-1].content, limit=1)
            return {"messages": [AIMessage(hits[0].page if hits else "unknown")]}

        b = StateGraph(MessagesState, context_schema=Ctx)
        b.add_node("anode", anode)
        b.add_edge(START, "anode")
        g = b.compile(store=store)
        out = await g.ainvoke({"messages": [HumanMessage("is she allergic to anything?")]}, context=Ctx("ada"))
        return out["messages"][-1].content

    assert asyncio.run(async_graph()) == "users/ada/memories/fact.md"


def test_the_demo_runs(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    env["KROUTER_NO_QUERY_LOG"] = "1"
    env["KROUTER_CACHE_DIR"] = str(tmp_path / "cache")
    env["PYTHONPATH"] = str(REPO / "sdk")
    out = subprocess.run([sys.executable, "-m", "krouter.integrations.langgraph_demo", str(tmp_path / "memory")],
                         env=env, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr
    lines = out.stdout.splitlines()
    assert "agent: I am allergic to peanuts, so no satay.  [from users/ada/fact-1.md]" in lines
    assert lines.count("agent: Nothing in my memory about that.") == 2
    assert (tmp_path / "memory" / "users" / "ada" / "fact-1.md").is_file()


def test_a_long_key_works_where_the_disk_refuses_long_names(store, monkeypatch):
    """Linux (ext4) answers a file name over 255 bytes with ENAMETOOLONG instead of "no such file"; CI found it.
    Simulated here so it is caught on any disk."""
    import errno
    from pathlib import Path as _P

    real = _P.is_file

    def is_file(self):
        if len(self.name.encode("utf-8")) > 255:
            raise OSError(errno.ENAMETOOLONG, "File name too long", str(self))
        return real(self)

    monkeypatch.setattr(_P, "is_file", is_file)
    key = "k" * 300
    store.put(A, key, {"content": "long"})
    assert store.get(A, key).value == {"content": "long"}
    store.put(A, key, {"content": "longer"})
    assert store.get(A, key).value == {"content": "longer"} and store.purge(A, key) >= 1


def test_a_knowledge_base_in_the_memory_folder_changes_no_search(store, tmp_path):
    """2.1's knowledge base (kb.py): reference material declared in the same folder neither enters a namespace's
    search nor changes what it returns."""
    facts(store)
    before = {q: [(h.key, h.confidence) for h in store.search(A, query=q)]
              for q in ("what is the dog called", "does alice eat fish", "which car does she drive")}
    root = tmp_path / "memory"
    (root / "Research").mkdir()
    (root / "Research" / "Dogs.md").write_text("# Dogs afraid of thunder\n\nSource: https://example.org/dogs\n\nMany a dog "
                                               "called Biscuit is afraid of thunder; vegetarian owners never feed fish.\n",
                                               encoding="utf-8")
    (root / "krouter-kb.txt").write_text("Research\n", encoding="utf-8")
    after = {q: [(h.key, h.confidence) for h in store.search(A, query=q)] for q in before}
    assert after == before
