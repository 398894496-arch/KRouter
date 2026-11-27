"""`KROUTER_ASK_JUDGE=1` (sets 53, 54): the lookup's first five pages go to a reader with the question, and the receipt
cites the pages it names or says the memory does not have it. Off by default; needs a key; a failed, empty or late call, or a
used-up day, leaves the lookup as it is without the switch; sends the redacted question and each candidate's title and
at most 1,200 characters, nothing else; a page shown only in parts cannot be refused. No test calls a real model."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter/scripts"
sys.path.insert(0, str(SCRIPTS))
QUESTION = "How long do we keep backups of the customer database?"
KEYLIKE = "sk-" + "Abc123XyZ" * 4


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("askjudge")
    v = root / "vault"
    shutil.copytree(REPO / "bench/memory_honesty/vault3", v)
    env = {k: val for k, val in os.environ.items() if not k.endswith("_API_KEY") and not k.startswith("KROUTER_")}
    env.update(KROUTER_VAULT=str(v), OBSIDIAN_VAULT=str(v), KROUTER_CACHE_DIR=str(root / "cache"),
               KROUTER_STATE_DIR=str(root / "state0"), KROUTER_NO_QUERY_LOG="1", KROUTER_KEYS_ENV=str(root / "none.env"))
    subprocess.run([sys.executable, str(SCRIPTS / "recall_index.py"), "--vault", str(v), "--stats"], env=env,
                   capture_output=True, check=True, timeout=180)
    return {"vault": v, "root": root, "env": env}


@pytest.fixture()
def box(built, tmp_path, monkeypatch):
    import recollect

    for k in list(os.environ):
        if k.endswith("_API_KEY") or k.startswith("KROUTER_") or k == "OBSIDIAN_VAULT":
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(built["root"] / "cache"))
    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("KROUTER_KEYS_ENV", str(tmp_path / "keys.env"))
    monkeypatch.setenv("KROUTER_NO_QUERY_LOG", "1")
    asked: list[str] = []

    def reader(reply):
        def call(conf, prompt):
            asked.append(prompt)
            if isinstance(reply, Exception):
                raise reply
            return reply
        monkeypatch.setattr(recollect, "_judge_call", call)

    return {"vault": built["vault"], "asked": asked, "reader": reader, "state": tmp_path / "state"}


def on(monkeypatch, **more):
    monkeypatch.setenv("KROUTER_ASK_JUDGE", "1")
    monkeypatch.setenv("KROUTER_JUDGE_KEY", "test-key")
    for k, v in more.items():
        monkeypatch.setenv(k, v)


def cands(vault: Path) -> list[str]:
    import recall_index as ri

    return [h["rel"] for h in ri.recall(vault, QUESTION, "", gate=False)["hits"]][:5]


def test_off_by_default_and_without_a_key(box, monkeypatch):
    import ask_reader

    box["reader"]("1")
    assert ask_reader.decide(box["vault"], QUESTION) is None
    monkeypatch.setenv("KROUTER_ASK_JUDGE", "1")
    assert ask_reader.decide(box["vault"], QUESTION) is None  # 没有 key
    assert box["asked"] == []
    monkeypatch.setenv("KROUTER_RECALL_JUDGE", "1")
    monkeypatch.delenv("KROUTER_ASK_JUDGE")
    monkeypatch.setenv("KROUTER_JUDGE_KEY", "k")
    assert ask_reader.decide(box["vault"], QUESTION) is None  # 钩子的开关不打开查询的这一层
    assert box["asked"] == []


def test_short_pages_are_shown_whole_and_long_ones_in_parts(box, tmp_path):
    import ask_reader

    c = cands(box["vault"])
    assert c and all(not ask_reader.is_long(box["vault"], rel) for rel in c)  # vault3 的页都短：整页给看
    title, text = ask_reader.passage(box["vault"], c[0], QUESTION)
    assert text == " ".join(ask_reader._body(box["vault"], c[0])[1])
    v = tmp_path / "v"
    v.mkdir()
    filler = "\n".join(f"Line {i} about the weather and the office plants." for i in range(200))
    (v / "long.md").write_text("---\ntitle: Long chat\n---\n\n# Long chat\n\n" + filler +
                               "\nWe keep backups of the customer database for 35 days.\n" + filler, encoding="utf-8")
    assert ask_reader.is_long(v, "long.md")
    title, text = ask_reader.passage(v, "long.md", QUESTION)
    assert title == "Long chat" and len(text) <= ask_reader.FULL and "35 days" in text and text.startswith("Line 0")


def test_the_reader_may_not_refuse_a_page_it_saw_in_parts(box, tmp_path):
    import ask_reader

    v = tmp_path / "v"
    v.mkdir()
    (v / "short.md").write_text("A short rule.\n", encoding="utf-8")
    (v / "long.md").write_text("word " * 600, encoding="utf-8")
    s, lg = {"rel": "short.md"}, {"rel": "long.md"}
    assert ask_reader.outcome(v, [s, s], []) == []  # 全是整页看过的：可以说记忆里没有
    assert ask_reader.outcome(v, [s, lg], []) is None  # 有只看了片段的长页：照没开开关时查
    assert ask_reader.outcome(v, [s, lg], [1]) == [s, lg]  # 点名的在前，没点名的长页留在后面
    assert ask_reader.outcome(v, [lg, s], [2, 1]) == [s, lg]
    assert ask_reader.pick("2, 1, 2, 9", 3) == [2, 1] and ask_reader.pick("0", 3) == [] and ask_reader.pick("none", 3) == []


def test_the_page_named_is_cited_alone(box, monkeypatch):
    import ask_reader

    on(monkeypatch)
    c = cands(box["vault"])
    assert len(c) >= 2
    box["reader"]("2")
    res = ask_reader.decide(box["vault"], QUESTION)
    assert [h["rel"] for h in res["hits"]] == [c[1]] and res["confidence"] == "high" and res["judged"] == "picked"
    assert not res["assoc"] and not res["more"] and "deepseek-flash" in res["judge_note"]
    assert len(box["asked"]) == 1 and box["asked"][0].count("\n1. ") == 1 and f"\n{len(c)}. " in box["asked"][0]


def test_none_of_them_is_a_refusal(box, monkeypatch):
    import ask_reader

    on(monkeypatch)
    box["reader"]("0")
    res = ask_reader.decide(box["vault"], QUESTION)
    assert res["hits"] == [] and res["confidence"] == "none" and res["judged"] == "none"
    box["reader"]("I am not sure")
    assert ask_reader.decide(box["vault"], QUESTION)["judged"] == "none"  # 读不出数字也算都不是


@pytest.mark.parametrize("reply", [TimeoutError("slow"), ""])
def test_a_failed_or_empty_call_leaves_the_lookup_alone(box, monkeypatch, reply):
    import ask_reader

    on(monkeypatch)
    box["reader"](reply)
    assert ask_reader.decide(box["vault"], QUESTION) is None
    row = json.loads((box["state"] / "judge.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert row["route"] == "ask" and row["error"] in ("TimeoutError", "empty") and QUESTION not in json.dumps(row)


def test_the_days_cap_is_shared_with_the_hook(box, monkeypatch):
    import ask_reader

    on(monkeypatch, KROUTER_JUDGE_MAX="1")
    box["reader"]("1")
    assert ask_reader.decide(box["vault"], QUESTION) is not None
    assert ask_reader.decide(box["vault"], QUESTION) is None and len(box["asked"]) == 1


def test_only_the_redacted_question_and_the_excerpts_leave(box, monkeypatch):
    import ask_reader

    on(monkeypatch)
    box["reader"]("1")
    ask_reader.decide(box["vault"], QUESTION + " token " + KEYLIKE)
    sent = box["asked"][0]
    assert KEYLIKE not in sent and "<redacted>" in sent
    for line in sent.splitlines():
        if line[:2].rstrip(".").isdigit() and ". " in line:
            assert len(line.split(": ", 1)[1]) <= ask_reader.FULL


class _Fake(BaseHTTPRequestHandler):
    reply = "1"
    bodies: list = []

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", 0))
        _Fake.bodies.append(json.loads(self.rfile.read(n)))
        out = json.dumps({"choices": [{"message": {"content": _Fake.reply}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):  # noqa: D401
        pass


@pytest.fixture()
def fake_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _Fake.bodies.clear()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1/chat/completions"
    srv.shutdown()


def _route(built, tmp_path, url: str | None, reply: str) -> str:
    _Fake.reply = reply
    env = {**built["env"], "KROUTER_STATE_DIR": str(tmp_path / "s")}
    if url:
        env.update(KROUTER_ASK_JUDGE="1", KROUTER_JUDGE_KEY="test-key", KROUTER_JUDGE_URL=url)
    return subprocess.run([sys.executable, str(SCRIPTS / "route_knowledge.py"), "search", QUESTION], env=env,
                          capture_output=True, text=True, timeout=120).stdout


def test_the_receipt_says_who_decided(built, tmp_path, fake_server):
    off = _route(built, tmp_path, None, "1")
    picked = _route(built, tmp_path, fake_server, "1")
    none = _route(built, tmp_path, fake_server, "0")
    assert "recall_judge" not in off
    assert picked.splitlines()[0].startswith("memory: direct") and "recall_judge:" in picked.splitlines()[1]
    assert sum(1 for ln in picked.splitlines() if ln.startswith("- ") and " tier=" in ln) == 1  # 只引那一页
    assert none.splitlines()[0].startswith("memory: none") and "found none" in none and "recall: none" in none
    assert len(_Fake.bodies) == 2 and _Fake.bodies[0]["model"] == "deepseek-flash" and _Fake.bodies[0]["temperature"] == 0
