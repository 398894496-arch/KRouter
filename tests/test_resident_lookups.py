"""The server's resident lookups answer exactly what a one-shot lookup answers, recover from a worker that hangs or
dies, see a write at once, and stay small; the literal fallback reads only the pages that can hold the question and
prints the same lines as reading every file."""

from __future__ import annotations

import contextlib
import io
import json
import os
import random
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter-obsidian/scripts"
sys.path.insert(0, str(SCRIPTS))
import mcp_server  # noqa: E402
import recall_index  # noqa: E402
import route_knowledge  # noqa: E402

QUESTIONS = ["what port does the api use", "发版流程现在用什么", "how do we name covers", "8080",
             "a question this vault has nothing on whatsoever", "status: active"]


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    v = tmp_path / "vault"
    shutil.copytree(REPO / "template", v)
    (v / "02 经验与方法" / "API port.md").write_text(
        "---\ntitle: API port\nstatus: active\nhow: The local API listens on 8080.\nverified_at: 2026-11-01\n---\n\n"
        "# API port\n\nThe local API listens on 8080; the staging API on 9090.\n", encoding="utf-8")
    (v / "02 经验与方法" / "发版流程.md").write_text(
        "---\ntitle: 发版流程\nstatus: active\n---\n\n# 发版流程\n\n- 发版只从 main 打 tag，CI 发布。\n", encoding="utf-8")
    monkeypatch.setenv("OBSIDIAN_VAULT", str(v))
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("KROUTER_NO_QUERY_LOG", "1")
    return v


def _one_shot(q: str) -> str:
    proc = subprocess.run([sys.executable, str(SCRIPTS / "route_knowledge.py"), "search", q], capture_output=True,
                          text=True, timeout=120, env=os.environ.copy())
    return proc.stdout


def _sans_time(text: str) -> str:
    # 收据里有时间戳和查询耗时：比的是答案，不是哪一秒答的
    return "\n".join(ln for ln in text.splitlines() if not ln.startswith("observed_at:"))


def test_a_resident_lookup_prints_what_a_one_shot_lookup_prints(vault):
    import route_worker

    for q in QUESTIONS:
        reply = route_worker.handle({"argv": ["search", q]})
        assert reply["code"] == 0, reply["err"]
        assert _sans_time(reply["out"]) == _sans_time(_one_shot(q)), q


def test_the_pool_answers_many_callers_at_once(vault, monkeypatch):
    monkeypatch.setattr(mcp_server, "WORKERS", 3)
    monkeypatch.setattr(mcp_server, "POOLS", {})
    want = {q: _sans_time(_one_shot(q)) for q in QUESTIONS}
    got: dict[int, tuple[str, str]] = {}

    def call(i: int) -> None:
        q = QUESTIONS[i % len(QUESTIONS)]
        text, err = mcp_server._route("search", q, None)
        got[i] = (q, _sans_time(text) if not err else "ERROR " + text)

    threads = [threading.Thread(target=call, args=(i,)) for i in range(24)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert len(got) == 24 and all(text == want[q] for q, text in got.values())
    assert 1 <= mcp_server.POOLS[str(vault)].count() <= 3


def test_a_worker_that_dies_is_replaced(vault, monkeypatch):
    monkeypatch.setattr(mcp_server, "WORKERS", 1)
    monkeypatch.setattr(mcp_server, "POOLS", {})
    assert "API port" in mcp_server._route("search", "what port does the api use", None)[0]
    pool = mcp_server.POOLS[str(vault)]
    pool.started[0].proc.kill()
    pool.started[0].proc.wait(timeout=10)
    text, err = mcp_server._route("search", "what port does the api use", None)  # 这次退回一次性进程
    assert not err and "API port" in text
    text, err = mcp_server._route("search", "what port does the api use", None)  # 槽位里换上新的常驻进程
    assert not err and "API port" in text and pool.count() == 1


def test_a_lookup_that_hangs_times_out_and_frees_its_slot(vault, monkeypatch, tmp_path):
    hang = tmp_path / "hang_worker.py"
    hang.write_text("import sys, time\nfor line in sys.stdin:\n    time.sleep(60)\n", encoding="utf-8")
    real = mcp_server.Worker.__init__

    def slow(self, v):  # 一个读了请求就不回的常驻进程
        import queue

        self.proc = subprocess.Popen([sys.executable, str(hang)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, bufsize=1)
        self.replies, self.stale = queue.Queue(), False
        threading.Thread(target=self._read, daemon=True).start()

    monkeypatch.setattr(mcp_server, "WORKERS", 1)
    monkeypatch.setattr(mcp_server, "POOLS", {})
    monkeypatch.setattr(mcp_server, "LOOKUP_TIMEOUT", 1)
    monkeypatch.setattr(mcp_server.Worker, "__init__", slow)
    text, err = mcp_server._route("search", "what port does the api use", None)
    assert err and "timed out" in text
    monkeypatch.setattr(mcp_server.Worker, "__init__", real)
    text, err = mcp_server._route("search", "what port does the api use", None)  # 槽位空出来了，换上正常的
    assert not err and "API port" in text


def test_a_note_is_found_by_the_very_next_lookup(vault, monkeypatch):
    monkeypatch.setattr(mcp_server, "WORKERS", 1)
    monkeypatch.setattr(mcp_server, "POOLS", {})
    monkeypatch.setattr(mcp_server, "REFRESH_EVERY", 3600.0)  # 不靠时间窗：写了就要马上查得到
    assert "recall: none" in mcp_server._route("search", "which espresso grinder setting do we use", None)[0]
    text, err = mcp_server.note({"text": "The espresso grinder setting we use is 14 on the Niche.", "kind": "decision"})
    assert not err, text
    found, err = mcp_server._route("search", "which espresso grinder setting do we use", None)
    assert not err and "14 on the Niche" in found


def test_lookups_re_check_the_vault_at_most_once_per_window(vault, monkeypatch):
    monkeypatch.setenv("KROUTER_REFRESH_EVERY", "3600")
    recall_index.forget_refresh()
    recall_index.recall(vault, "api port")
    page = vault / "02 经验与方法" / "Kettle.md"
    page.write_text("---\ntitle: Kettle\nstatus: active\n---\n\n# Kettle\n\nThe kettle descales monthly.\n",
                    encoding="utf-8")
    assert not any("Kettle" in h["rel"] for h in recall_index.recall(vault, "kettle descales")["hits"])
    recall_index.forget_refresh()
    assert any("Kettle" in h["rel"] for h in recall_index.recall(vault, "kettle descales")["hits"])
    monkeypatch.delenv("KROUTER_REFRESH_EVERY")  # 默认（命令行、一次性进程）：每次都先检查
    page.write_text(page.read_text(encoding="utf-8").replace("monthly", "weekly"), encoding="utf-8")
    hit = recall_index.recall(vault, "kettle descales weekly")["hits"][0]
    assert "Kettle" in hit["rel"]


def test_recall_closes_its_connection(vault):
    import gc
    import sqlite3

    gc.collect()
    gc.disable()
    try:
        before = sum(1 for o in gc.get_objects() if isinstance(o, sqlite3.Connection))
        for q in QUESTIONS:
            recall_index.recall(vault, q)
        after = [o for o in gc.get_objects() if isinstance(o, sqlite3.Connection)]
        open_ = 0
        for con in after:
            try:
                con.execute("SELECT 1")
                open_ += 1
            except sqlite3.ProgrammingError:  # 已关闭
                pass
        assert open_ <= before
    finally:
        gc.enable()


def _literal(needle: str, scope: Path, vault: Path | None) -> list[str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        route_knowledge.md_search(needle, scope, max_lines=10**6, vault=vault)
    return sorted(out.getvalue().splitlines())


def test_the_literal_fallback_reads_only_pages_that_can_hold_the_question_and_prints_the_same(vault):
    recall_index.recall(vault, "warm up")
    rng = random.Random(20261109)
    pages = [p for p in vault.rglob("*.md") if ".obsidian" not in p.parts]
    needles = ["The local API listens", "listens on 8080; the staging", "verified_at: 2026-11-01", "Status: Active",
               "发版只从 main 打 tag", "只从 main", "no page has this sentence in it at all", "8080", "api"]
    for _ in range(120):
        lines = [ln for ln in rng.choice(pages).read_text(encoding="utf-8").splitlines() if ln.strip()] or ["x"]
        line = rng.choice(lines)
        a = rng.randrange(len(line))
        needles.append(line[a:a + rng.randint(3, 50)])
    narrowed = 0
    for n in needles:
        if not n.strip():
            continue
        for scope in (vault, vault / "02 经验与方法"):
            cand = route_knowledge.literal_candidates(n, scope, vault)
            narrowed += cand is not None
            assert _literal(n, scope, vault) == _literal(n, scope, None), (n, scope.name)
    assert narrowed > 50
    assert route_knowledge.literal_candidates("no page has this sentence in it at all", vault, vault) == []
    assert route_knowledge.literal_candidates("8080", vault, vault) is None  # 一个词：没有可筛的，照旧全读


def test_server_flags_set_the_pool(monkeypatch):
    seen = {}
    monkeypatch.setattr(mcp_server, "serve_stdio", lambda: seen.setdefault("mode", "stdio") and 0)
    monkeypatch.delenv("KROUTER_WORKERS", raising=False)
    monkeypatch.delenv("KROUTER_REFRESH_EVERY", raising=False)
    mcp_server.main([])
    assert (mcp_server.WORKERS, mcp_server.REFRESH_EVERY) == (1, 2.0)
    mcp_server.main(["--workers", "0", "--refresh-every", "0"])
    assert (mcp_server.WORKERS, mcp_server.REFRESH_EVERY) == (0, 0.0)


def test_processes_that_find_the_same_changes_at_once_index_each_page_once(vault, tmp_path):
    import sqlite3

    recall_index.recall(vault, "warm up")
    for i in range(150):
        (vault / "02 经验与方法" / f"Change {i}.md").write_text(
            f"---\ntitle: Change {i}\nstatus: active\n---\n\n# Change {i}\n\nPort {9000 + i} is for service {i}.\n",
            encoding="utf-8")
    code = ("import sys; sys.path.insert(0, sys.argv[1]); from pathlib import Path; import recall_index as ri; "
            "ri.recall(Path(sys.argv[2]), 'which port is for service 7')")
    procs = [subprocess.Popen([sys.executable, "-c", code, str(SCRIPTS), str(vault)], env=os.environ.copy())
             for _ in range(6)]
    assert all(p.wait(timeout=120) == 0 for p in procs)
    con = sqlite3.connect(recall_index.cache_path(vault))
    docs = con.execute("SELECT count(*), count(DISTINCT rel) FROM docs").fetchone()
    files = con.execute("SELECT count(*) FROM files").fetchone()[0]
    assert docs[0] == docs[1] == files, (docs, files)  # 一页一条：没有谁把同一页又索引了一遍
