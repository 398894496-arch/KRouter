"""`KROUTER_RECALL_JUDGE=1` (sets 51 and 52): when the per-message hook brings nothing and holds candidate pages, it asks
a reader which one, if any, the message is about, and brings that page. Off by default; needs a key; says nothing when
the reader says none, fails or is slow; never asks for a light message, a `#不记` session or past the day's cap; sends the
redacted message and the candidates' names and one line each, nothing else. No test calls a real model."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter/scripts"
sys.path.insert(0, str(SCRIPTS))
SYSTEM = "90 系统文件"
MENTION = "drop that old field in 3.2?"  # set 45 dev, en-001: the hook alone says nothing, the page is a candidate
EXPECT = "Handbook/API deprecation.md"
KEYLIKE = "sk-" + "Abc123XyZ" * 4


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """vault3 with the bench alias table, indexed once for the module."""
    root = tmp_path_factory.mktemp("judge")
    v = root / "vault"
    shutil.copytree(REPO / "bench/memory_honesty/vault3", v)
    (v / SYSTEM).mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / "bench/subconscious/overlay/canonical_sources.psv", v / SYSTEM / "canonical_sources.psv")
    env = {k: val for k, val in os.environ.items() if not k.endswith("_API_KEY") and not k.startswith("KROUTER_")}
    env.update(KROUTER_VAULT=str(v), KROUTER_CACHE_DIR=str(root / "cache"), KROUTER_STATE_DIR=str(root / "state0"),
               KROUTER_NO_QUERY_LOG="1", KROUTER_KEYS_ENV=str(root / "none.env"))
    subprocess.run([sys.executable, str(SCRIPTS / "recall_index.py"), "--vault", str(v), "--stats"], env=env,
                   capture_output=True, check=True, timeout=180)
    return {"vault": v, "root": root, "env": env}


@pytest.fixture()
def box(built, tmp_path, monkeypatch):
    import recollect

    for k in list(os.environ):
        if k.endswith("_API_KEY") or k.startswith("KROUTER_") or k == "OBSIDIAN_VAULT":
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("KROUTER_VAULT", str(built["vault"]))
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(built["root"] / "cache"))
    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("KROUTER_KEYS_ENV", str(tmp_path / "keys.env"))
    monkeypatch.setenv("KROUTER_NO_QUERY_LOG", "1")
    recollect._PAGES.clear()
    asked: list[str] = []

    def reader(reply):
        def call(conf, prompt):
            asked.append(prompt)
            if isinstance(reply, Exception):
                raise reply
            return reply(conf, prompt) if callable(reply) else reply
        monkeypatch.setattr(recollect, "_judge_call", call)

    return {"vault": built["vault"], "asked": asked, "reader": reader, "state": tmp_path / "state", "tmp": tmp_path}


def on(monkeypatch, **more):
    monkeypatch.setenv("KROUTER_RECALL_JUDGE", "1")
    monkeypatch.setenv("KROUTER_JUDGE_KEY", "test-key")
    for k, v in more.items():
        monkeypatch.setenv(k, v)


def number_of(prompt: str, title: str) -> str:
    for line in prompt.splitlines():
        if ". " in line and line.split(". ", 1)[1].startswith(title):
            return line.split(".", 1)[0]
    return "0"


def test_off_by_default_and_off_without_a_key(box, monkeypatch):
    import recollect

    box["reader"]("1")
    assert recollect.recollect(box["vault"], MENTION) == []  # 前提：钩子自己不递
    assert recollect.judged(box["vault"], MENTION) == []
    monkeypatch.setenv("KROUTER_RECALL_JUDGE", "1")  # 开了但没有 key
    assert recollect.judge_conf() is None and recollect.judged(box["vault"], MENTION) == []
    assert box["asked"] == [] and not (box["state"] / recollect.JUDGE_LOG).exists()


def test_the_page_the_reader_names_is_brought_and_marked_as_judged(box, monkeypatch):
    import recollect

    on(monkeypatch)
    box["reader"](lambda conf, prompt: number_of(prompt, "API deprecation"))
    hits = recollect.judged(box["vault"], MENTION)
    assert [h["rel"] for h in hits] == [EXPECT] and hits[0]["route"] == "judge" and hits[0]["how"]
    note = recollect.render(hits)
    assert EXPECT in note and "model-judged" in note
    assert len(box["asked"]) == 1 and MENTION in box["asked"][0] and "API deprecation" in box["asked"][0]
    row = json.loads((box["state"] / recollect.JUDGE_LOG).read_text(encoding="utf-8").splitlines()[0])
    assert row["picked"] is True and row["error"] == "" and 1 <= row["candidates"] <= recollect.JUDGE_K
    assert MENTION not in json.dumps(row) and "API deprecation" not in json.dumps(row)  # 只记元数据


@pytest.mark.parametrize("reply", ["0", "none of them", "", "9", "7 or maybe 2"])
def test_none_or_an_answer_that_names_no_candidate_brings_nothing(box, monkeypatch, reply):
    import recollect

    on(monkeypatch)
    box["reader"](reply)
    assert recollect.judged(box["vault"], MENTION) == [] and len(box["asked"]) == 1


def test_an_empty_answer_is_logged_as_one(box, monkeypatch):
    import recollect

    on(monkeypatch)
    box["reader"]("  ")
    assert recollect.judged(box["vault"], MENTION) == []
    assert json.loads((box["state"] / recollect.JUDGE_LOG).read_text(encoding="utf-8").splitlines()[0])["error"] == "empty"


def test_a_reader_that_fails_or_is_slow_is_as_if_nobody_asked(box, monkeypatch):
    import recollect

    on(monkeypatch, KROUTER_JUDGE_TIMEOUT="0.5")
    box["reader"](OSError("connection refused"))
    assert recollect.judged(box["vault"], MENTION) == []

    def slow(conf, prompt):
        time.sleep(3)
        return "1"

    box["reader"](slow)
    t = time.perf_counter()
    assert recollect.judged(box["vault"], MENTION) == []
    assert time.perf_counter() - t < 2.0  # 等到超时就走，不等它答完
    errs = [json.loads(x)["error"] for x in (box["state"] / recollect.JUDGE_LOG).read_text(encoding="utf-8").splitlines()]
    assert errs == ["OSError", "timeout"]


def test_the_timeout_is_five_seconds_unless_set(box, monkeypatch):
    import recollect

    on(monkeypatch)
    assert recollect.JUDGE_TIMEOUT == 5.0 and recollect.judge_conf()["timeout"] == 5.0
    assert recollect.judge_conf()["url"].startswith("https://api.deepseek.com") and recollect.judge_conf()["model"] == "deepseek-flash"


@pytest.mark.parametrize("light", ["好的", "go on", "装吧", "is that right?", "PR review SLA?"])
def test_a_light_message_is_never_sent(box, monkeypatch, light):
    import recollect

    on(monkeypatch)
    box["reader"]("1")
    assert recollect.judged(box["vault"], light) == [] and box["asked"] == []


def test_the_days_questions_have_a_cap(box, monkeypatch):
    import recollect

    on(monkeypatch, KROUTER_JUDGE_MAX="1")
    box["reader"]("0")
    recollect.judged(box["vault"], MENTION)
    recollect.judged(box["vault"], "who sends receipts now?")
    assert len(box["asked"]) == 1


def test_the_message_goes_out_redacted(box, monkeypatch):
    import recollect

    on(monkeypatch)
    box["reader"]("0")
    recollect.judged(box["vault"], f"drop that old field in 3.2? my key is {KEYLIKE} by the way")
    assert len(box["asked"]) == 1 and KEYLIKE not in box["asked"][0] and "old field" in box["asked"][0]


def test_the_key_can_be_the_deepseek_one_or_come_from_the_keys_file(box, monkeypatch):
    import recollect

    monkeypatch.setenv("KROUTER_RECALL_JUDGE", "1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key")
    assert recollect.judge_conf()["key"] == "ds-key"
    monkeypatch.setenv("KROUTER_JUDGE_KEY", "own-key")
    assert recollect.judge_conf()["key"] == "own-key"
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    monkeypatch.delenv("KROUTER_JUDGE_KEY")
    (box["tmp"] / "keys.env").write_text("KROUTER_JUDGE_KEY=file-key-0123456789\nKROUTER_JUDGE_MODEL=some-model\n", encoding="utf-8")
    conf = recollect.judge_conf()
    assert conf["key"] == "file-key-0123456789" and conf["model"] == "some-model"


def test_the_engine_asks_what_the_registered_bench_script_asked(box, monkeypatch):
    """Sets 51 and 52 were run with bench/subconscious/candidates.py: same candidates, same question."""
    import recollect

    sys.path.insert(0, str(REPO / "bench/subconscious"))
    import candidates as bench

    assert (recollect.JUDGE_K, recollect.JUDGE_MIN_WEIGHT) == (bench.K_JUDGE, bench.MIN_WEIGHT)
    rows = [json.loads(x) for x in (REPO / "bench/subconscious/set45_dev.jsonl").read_text(encoding="utf-8").splitlines()]
    some = 0
    for r in rows[:60]:
        theirs = bench.candidates(box["vault"], r["text"], set(), bench.K_JUDGE)
        ours = recollect.candidates(box["vault"], recollect.prose(r["text"]), set())
        assert [(c["real"], c["title"], c["how"]) for c in ours] == [(c["real"], c["title"], c["how"]) for c in theirs], r["id"]
        if ours:
            some += 1
            assert recollect.judge_prompt(r["text"], ours, r["lang"]) == bench.ask(r["text"], theirs, r["lang"])
    assert some >= 20
    for reply in ("2", "0", "", "none", "12", "the answer is 3"):
        assert recollect.judge_pick(reply, 5) == bench.pick(reply, 5)


class Reader(BaseHTTPRequestHandler):
    got: list[dict] = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Reader.got.append({"auth": self.headers.get("Authorization"), **body})
        prompt = body["messages"][0]["content"]
        out = json.dumps({"choices": [{"message": {"content": number_of(prompt, "API deprecation")}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


@pytest.fixture()
def server():
    Reader.got = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Reader)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/chat/completions"
    srv.shutdown()


def say(built, tmp_path, url, text, sid="s1"):
    env = dict(built["env"], KROUTER_STATE_DIR=str(tmp_path / "state"), KROUTER_RECALL_JUDGE="1", KROUTER_JUDGE_KEY="test-key",
               KROUTER_JUDGE_URL=url, KROUTER_RECALL_PROMPT="1")
    res = subprocess.run([sys.executable, str(SCRIPTS / "session_hook.py"), "prompt", "--agent", "claude"],
                         input=json.dumps({"prompt": text, "session_id": sid, "cwd": str(tmp_path)}), env=env,
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    return res.stdout


def test_through_the_hook_over_http(built, tmp_path, server):
    out = say(built, tmp_path, server, MENTION)
    note = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert EXPECT in note and "model-judged" in note
    assert len(Reader.got) == 1 and Reader.got[0]["auth"] == "Bearer test-key" and Reader.got[0]["model"] == "deepseek-flash"
    assert Reader.got[0]["temperature"] == 0 and MENTION in Reader.got[0]["messages"][0]["content"]
    # deepseek-flash 先想再答：给 16 个 token 时回来是空的，81 句一页都没点（引擎第一次重跑时发现）
    assert Reader.got[0]["max_tokens"] >= 1000
    row = json.loads((tmp_path / "state/recalled.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["route"] == "judge" and row["page"] == EXPECT


def test_the_hook_does_not_ask_when_it_brought_a_page_itself_or_the_session_says_no_capture(built, tmp_path, server):
    out = say(built, tmp_path, server, "do we add the Sunset header?")  # 别名对上了：钩子自己递
    assert "API deprecation" in out and Reader.got == []
    assert say(built, tmp_path, server, MENTION + " #不记", sid="s2") == "" and Reader.got == []
    assert say(built, tmp_path, server, MENTION, sid="s2") == "" and Reader.got == []  # 这个会话后面的话也不问
