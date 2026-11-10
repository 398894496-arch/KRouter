"""Experience cards (experimental, `KROUTER_EXPERIENCE=1`): written next to the distill, given to the host model as one
digest at session start, never among the facts, off by default. Sets 13 and 15's files are pinned (HELDOUT.md)."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter-obsidian/scripts"
BENCH = REPO / "bench/transfer"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(BENCH))
import experience  # noqa: E402
import run as transfer_bench  # noqa: E402
from test_import_sessions import _claude_session, _pages, _ts, env  # noqa: E402,F401

CARDS_SHA = "df0cfe6acbc01c48f47b08ecc9983f61aa46269444cb679994037add5d6f191e"
HELDOUT_SHA = "3a7f625c2c370e08bca7de5a843a286d2d3486a7b516e96ca5142e89a3361f33"
C02_CASE = "每次打开这个网页都要重新加载一大堆图片，等得很烦"  # development case C02-p2


@pytest.fixture()
def bench_vault(tmp_path):
    return transfer_bench.build_vault(tmp_path)


def test_set_13_files_are_frozen():
    cards = b"".join(p.read_bytes() for p in sorted((BENCH / "cards").glob("*.md")))
    assert hashlib.sha256(cards).hexdigest() == CARDS_SHA
    with gzip.open(BENCH / "heldout.jsonl.gz", "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest() == HELDOUT_SHA
    dev = transfer_bench.load("dev")
    assert len(dev) == 28 and sum(1 for c in dev if c["expect"]) == 14


def test_development_numbers_are_the_logged_ones(bench_vault):
    """HELDOUT.md set 13 log: recalled 3 / 14, no quiet case suggested, 1 wrong card, at the frozen threshold."""
    r = transfer_bench.score(transfer_bench.load("dev"), bench_vault)
    assert (r["recalled"], r["quiet_cases_with_suggestion"], r["transfer_wrong_cards"]) == (3, 0, 1)


def test_quiet_on_the_cards_own_subject_and_on_unrelated_tasks(bench_vault):
    for q in ("nginx 的 server_name 支持通配符吗", "红烧肉用五花肉还是前腿肉", "用 Python 写一个快速排序"):
        assert experience.suggest(bench_vault, q) == []
    got = experience.suggest(bench_vault, C02_CASE)
    assert got and transfer_bench.card_id(got[0]["rel"]) == "C02" and len(got) <= experience.MAX_SUGGESTIONS
    lines = experience.render(got, bench_vault)
    assert lines[0].startswith("建议（别的任务里的经验") and "出处 [[05 时间日志/会话摘录/示例｜C02]]" in lines[1]


def test_cards_never_come_back_as_facts(bench_vault, tmp_path):
    import recall_index as ri

    os.environ.setdefault("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    res = ri.recall(bench_vault, "红烧肉炖好了吃着发平，加一小勺糖")
    assert not any("经验卡" in h["rel"] for h in res["hits"])
    own = ri.recall(bench_vault, "红烧肉炖好了吃着发平，加一小勺糖", scope=experience.FOLDER)
    assert own["hits"] and "经验卡" in own["hits"][0]["rel"]  # 只在明确查经验卡目录时才出现


SET15_DEV = 28
SET15_HELDOUT_SHA = "88bec1675873250db2db32202fff959db12ac9d06154e961f721d00821e854b5"
DISTRACTORS_SHA = "8860fc6d3805b465ce0c50be9664211276fb02a2626ca6f209616f0c99125a48"


def test_set_15_files_are_frozen():
    import host

    with gzip.open(BENCH / "set15_heldout.jsonl.gz", "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest() == SET15_HELDOUT_SHA
    noise = b"".join(p.read_bytes() for p in sorted((BENCH / "distractors").glob("*.md")))
    assert hashlib.sha256(noise).hexdigest() == DISTRACTORS_SHA
    dev = host.load("dev")
    assert len(dev) == SET15_DEV and sum(1 for c in dev if c["expect"]) == 14


def test_digest_is_one_subject_free_line_per_card_with_its_id_and_a_cap(bench_vault):
    d = experience.digest(bench_vault)
    lines = [ln for ln in d.splitlines() if ln.startswith("- ")]
    assert len(lines) == 14 and all(ln.endswith("〕") for ln in lines)
    assert "整体发平、缺一点层次 → 不要再加同一种东西" in d and "〔C08〕" in d
    assert "红烧肉" not in d and "nginx" not in d  # 只有通用说法，没有题材
    assert d.splitlines()[-1].startswith("用法：") and "最多两条" in d and "一个字都不要提" in d
    short = experience.digest(bench_vault, max_lines=5)
    assert sum(1 for ln in short.splitlines() if ln.startswith("- ")) == 5 and "还有 9 张没列出" in short
    card = next((bench_vault / experience.FOLDER).glob("C03｜*.md"))
    card.write_text(card.read_text(encoding="utf-8").replace("date: 2026-01-01", "date: 2026-01-01\nadopted_at: 2026-11-01"),
                    encoding="utf-8")
    first = [ln for ln in experience.digest(bench_vault, max_lines=5).splitlines() if ln.startswith("- ")][0]
    assert first.endswith("〔C03〕")  # 最近被采纳的排最前
    assert 0 < experience.token_estimate(d) <= len(d)


def _start(vault: Path, tmp_path: Path, agent: str = "claude", **env) -> subprocess.CompletedProcess:
    e = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_STATE_DIR": str(tmp_path / "no-consent"),
         "KROUTER_NO_QUERY_LOG": "1", **env}
    for k in ("KROUTER_EXPERIENCE", "KROUTER_INJECT"):
        if k not in env:
            e.pop(k, None)
    return subprocess.run([sys.executable, str(SCRIPTS / "session_hook.py"), "start", "--agent", agent],
                          input=json.dumps({"cwd": str(tmp_path), "session_id": "s1"}), env=e, capture_output=True,
                          text=True, timeout=60)


def test_session_start_gives_the_digest_only_when_switched_on(bench_vault, tmp_path):
    assert _start(bench_vault, tmp_path).stdout == ""  # 默认关
    ctx = json.loads(_start(bench_vault, tmp_path, KROUTER_EXPERIENCE="1").stdout)["hookSpecificOutput"]
    assert ctx["hookEventName"] == "SessionStart" and ctx["additionalContext"].startswith("KRouter 经验摘要")
    cursor = json.loads(_start(bench_vault, tmp_path, "cursor", KROUTER_EXPERIENCE="1").stdout)
    assert "〔C08〕" in cursor["additional_context"]
    assert _start(bench_vault, tmp_path, KROUTER_EXPERIENCE="1", KROUTER_INJECT="0").stdout == ""


def test_host_scoring_reads_cited_ids_and_never_shows_the_answer():
    import host

    cases = host.load("dev")
    assert all(c["expect"] not in host.opaque(c["id"]) for c in cases if c["expect"])
    t = next(c for c in cases if c["expect"])
    q = next(c for c in cases if not c["expect"])
    replies = {t["id"]: f"别的任务里的经验，可以试试：……〔{t['expect']}〕和〔D07〕", q["id"]: "好的，我先看看。"}
    r = host.score_rows([t, q], replies)
    assert (r["recalled"], r["transfer_wrong_cards"], r["quiet_cases_with_suggestion"]) == (1, 1, 0)


EXCERPT = "- **问**（10:05）：红烧肉炖好了，咸是够了，但吃着发平怎么办\n  **答**：最后加一小勺糖，味道一下子有了层次\n"
GOOD = {"title": "整体发平时加一点点反差的东西", "situation": "红烧肉炖好了，咸是够了，但吃着发平",
        "action": "最后加了一小勺糖", "result": "味道有了层次", "lesson": "东西整体发平、缺一点层次时，加一点点相反的元素",
        "when": ["发平", "没有层次", "寡淡", "缺点什么"]}


def _entry() -> dict:
    return {"day": date(2026, 1, 2), "project": "kitchen"}


def test_extract_writes_a_readable_card_and_skips_a_repeat(tmp_path, monkeypatch):
    import llm

    vault = tmp_path / "v"
    vault.mkdir()
    monkeypatch.setattr(llm, "complete", lambda prompt, vault=None: "好的：\n" + json.dumps([GOOD], ensure_ascii=False))
    written, chars = experience.extract(_entry(), EXCERPT, vault, "[[05 时间日志/会话摘录/x]]")
    assert len(written) == 1 and chars > len(EXCERPT)
    text = written[0].read_text(encoding="utf-8")
    assert "type: experience-card" in text and "status: provisional" in text and "- 通用说法：" in text
    assert experience.load_cards(vault)[0]["when"] == GOOD["when"]
    again, _ = experience.extract(_entry(), EXCERPT, vault, "[[05 时间日志/会话摘录/y]]")
    assert again == []  # 同一条经验已经在库里


@pytest.mark.parametrize("bad", [
    {**GOOD, "result": ""},                                            # 字段不全
    {**GOOD, "action": "填上 api_key=" + "sk-" + "Abc123XyZ" * 4},       # 像密钥
    {**GOOD, "situation": "部署服务失败", "action": "重启容器"},          # 摘录里没有
])
def test_extract_drops_cards_that_do_not_hold_up(tmp_path, monkeypatch, bad):
    import llm

    monkeypatch.setattr(llm, "complete", lambda prompt, vault=None: json.dumps([bad], ensure_ascii=False))
    assert experience.extract(_entry(), EXCERPT, tmp_path, "[[x]]")[0] == []


def test_extract_without_a_model_lane_does_nothing(tmp_path, monkeypatch):
    import llm

    def none(prompt, vault=None):
        raise llm.NoModel("no lane")

    monkeypatch.setattr(llm, "complete", none)
    assert experience.extract(_entry(), EXCERPT, tmp_path, "[[x]]") == ([], 0)
    assert not (tmp_path / experience.FOLDER).exists()


def test_distill_writes_an_experience_card_only_when_switched_on(env, monkeypatch):  # noqa: F811
    path = _claude_session(env["claude"], "aaaa1111-s", 1, title="发版流程")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "user", "timestamp": _ts(1, 11),
                             "message": {"role": "user", "content": "那就这么定"}}) + "\n")
    import import_sessions as imp
    import llm

    card = {"title": "规则说不清时先定一条唯一的入口", "situation": "发版流程怎么定一直没说清",
            "action": "定了发版只从 main 打 tag", "result": "之后照这条做", "lesson": "流程说不清时，先定一个唯一入口",
            "when": ["流程说不清", "没有统一做法", "各做各的"]}
    sent = []

    def fake(prompt, vault=None):
        sent.append(prompt)
        if "经验卡" in prompt:
            return json.dumps([card], ensure_ascii=False)
        return "- 发版只从 main 打 tag（10:05）"

    monkeypatch.setattr(llm, "complete", fake)
    for k in ("OBSIDIAN_VAULT", "KROUTER_CLAUDE_PROJECTS", "KROUTER_CODEX_SESSIONS", "KROUTER_CURSOR_PROJECTS",
              "KROUTER_STATE_DIR"):
        monkeypatch.setenv(k, env["env"][k])
    monkeypatch.delenv("KROUTER_EXPERIENCE", raising=False)
    monkeypatch.setattr(sys, "argv", ["import_sessions.py", "--distill"])
    assert imp.main() == 0
    folder = env["vault"] / experience.FOLDER
    assert len(sent) == 2 and not folder.exists()  # 默认关：不多发一次，也不写卡
    shutil.rmtree(env["vault"] / "05 时间日志/会话摘录")
    sent.clear()
    monkeypatch.setenv("KROUTER_EXPERIENCE", "1")
    monkeypatch.setattr(sys, "argv", ["import_sessions.py", "--distill"])
    assert imp.main() == 0
    assert len(sent) == 3 and "经验卡" in sent[-1]
    cards = list(folder.glob("*.md"))
    assert len(cards) == 1 and "[[05 时间日志/会话摘录/" in cards[0].read_text(encoding="utf-8")
    ledger = (env["vault"] / "90 系统文件/自动化/记忆变更记录.md").read_text(encoding="utf-8")
    assert "经验卡：规则说不清时先定一条唯一的入口" in ledger
    assert _pages(env)  # 会话页照常写


# ---------- 第三轮：使用记录、宿主自己写卡、英文 ----------

IDS = {"C02", "C08", "C11"}


def _turns(*pairs):
    return [{"ask": a, "answer": b, "ts": f"2026-11-0{i + 1}T10:00:00"} for i, (a, b) in enumerate(pairs)]


def test_offered_is_recorded_and_adopted_only_on_a_clear_yes():
    offer = "先看第一条报错。别的任务里的经验，可以试试：只解决最前面那一条〔C11〕"
    ev = experience.uses_in(_turns(("编译报了一屏", offer), ("按你说的只改了第一个，果然全好了", "好")), IDS)
    assert [(e["card"], e["kind"]) for e in ev] == [("C11", "offered"), ("C11", "adopted")]
    assert "按你说的" in ev[1]["why"]
    for reply in ("好的", "不用，这次不是这个问题", "按你说的试了，没用", "嗯，然后呢"):  # 拿不准、或明说不是：只记提出
        ev = experience.uses_in(_turns(("编译报了一屏", offer), (reply, "")), IDS)
        assert [e["kind"] for e in ev] == ["offered"], reply
    two = "可以试试〔C11〕，或者〔C02〕"
    assert [e["kind"] for e in experience.uses_in(_turns(("x", two), ("有用", "")), IDS)] == ["offered", "offered"]
    named = experience.uses_in(_turns(("x", two), ("C02 那条有用", "")), IDS)
    assert ("C02", "adopted") in [(e["card"], e["kind"]) for e in named]  # 提了两条、你点了名：记被点名的那条
    en = experience.uses_in(_turns(("x", "A lesson from another task you could try: … [C08]"), ("That worked, thanks", "")), IDS)
    assert [(e["card"], e["kind"]) for e in en] == [("C08", "offered"), ("C08", "adopted")]
    assert experience.uses_in(_turns(("x", "see C08 for details"), ("that worked", "")), IDS) == []  # 不带括号不算


def test_use_records_are_kept_once_and_rank_the_digest(bench_vault):
    turns = _turns(("x", "可以试试〔C02〕"), ("按你说的做了，管用", ""))
    assert experience.record_uses(bench_vault, "claude:s1", turns) == 2
    assert experience.record_uses(bench_vault, "claude:s1", turns) == 0  # 每轮都会重新导入：同一条不记两次
    for n in range(3):  # C05 提了三次，一次都没人采纳
        experience.record_uses(bench_vault, f"claude:s{n + 2}", _turns(("y", "可以试试〔C05〕"), ("嗯", "")))
    u = experience.usage(bench_vault)
    assert u["C02"]["adopted"] == 1 and u["C05"] == {**u["C05"], "offered": 3, "adopted": 0}
    lines = [ln for ln in experience.digest(bench_vault).splitlines() if ln.startswith("- ")]
    assert lines[0].endswith("〔C02〕") and lines[-1].endswith("〔C05〕")  # 被采纳的最前，屡提不用的沉底


EN_CARD = {"situation": "Our nginx config change did nothing after three reloads",
           "action": "Ran nginx -T and found a second file with the same server block being loaded",
           "result": "Deleting the stale file made the change take effect at once",
           "lesson": "When a change has no effect, first check that the system reads the copy you changed",
           "when": ["changed it but nothing happened", "still the old behaviour", "nginx did not reload"]}


def test_host_written_card_needs_no_model_and_reads_back_in_english(tmp_path):
    vault = tmp_path / "v"
    vault.mkdir()
    path, why = experience.learn(vault, EN_CARD, "[[Journal/session]]")
    assert path and not why and path.name.startswith("Lesson - ")
    text = path.read_text(encoding="utf-8")
    assert "- Lesson: When a change has no effect" in text and "nginx did not reload" not in text  # 带题材名的短语去掉
    card = experience.load_cards(vault)[0]
    assert card["lesson"].startswith("When a change") and len(card["when"]) == 2
    d = experience.digest(vault)
    assert d.startswith("KRouter experience digest") and "How to use:" in d
    assert f"- When a change has no effect, first check that the system reads the copy you changed [{card['id']}]" in d
    assert experience.learn(vault, EN_CARD, "x") == (None, "not written: a card with the same lesson is already there")
    assert experience.learn(vault, {**EN_CARD, "result": ""}, "x")[0] is None


def test_learn_from_the_command_line(tmp_path):
    vault = tmp_path / "v"
    vault.mkdir()
    res = subprocess.run([sys.executable, str(SCRIPTS / "experience.py"), "--vault", str(vault), "learn"],
                         input=json.dumps(EN_CARD), capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout)["written"].startswith("02 经验与方法/经验卡/Lesson - ")


def _mcp(env: dict, *msgs: dict) -> list[dict]:
    data = "\n".join(json.dumps(m, ensure_ascii=False) for m in msgs) + "\n"
    res = subprocess.run([sys.executable, str(SCRIPTS / "mcp_server.py")], input=data, env=env, capture_output=True,
                         text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    return [json.loads(line) for line in res.stdout.splitlines() if line.strip()]


def test_mcp_learn_writes_a_card_into_the_ledger(tmp_path):
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template", vault)
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_NO_QUERY_LOG": "1", "KROUTER_CACHE_DIR": str(tmp_path / "c"),
           "KROUTER_EXPERIENCE": "1"}
    out = _mcp(env, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
               {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
               {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "krouter_learn", "arguments": EN_CARD}})
    assert "krouter_learn" in out[0]["result"]["instructions"]
    assert "krouter_learn" in [t["name"] for t in out[1]["result"]["tools"]]
    assert out[2]["result"]["isError"] is False and "learned: 02 经验与方法/经验卡/Lesson - " in out[2]["result"]["content"][0]["text"]
    assert "经验卡：" in (vault / "90 系统文件/自动化/记忆变更记录.md").read_text(encoding="utf-8")
    off = _mcp({**env, "KROUTER_EXPERIENCE": "0"}, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert "krouter_learn" not in [t["name"] for t in off[0]["result"]["tools"]]


def test_session_import_records_uses_without_a_model(env, tmp_path):  # noqa: F811
    from test_import_sessions import _jsonl, _run

    folder = env["vault"] / experience.FOLDER
    folder.mkdir(parents=True)
    shutil.copy(next((BENCH / "cards").glob("C02｜*.md")), folder)
    ts = _ts(1)
    rows = [{"type": "user", "cwd": "/work/shop", "timestamp": ts, "origin": {"kind": "human"},
             "message": {"role": "user", "content": "每次跑报表都要重新下载那份数据，太慢"}},
            {"type": "assistant", "timestamp": ts, "message": {"content": [{"type": "text", "text":
             "别的任务里的经验，可以试试：把这一步的结果存起来〔C02〕"}]}},
            {"type": "user", "timestamp": _ts(1, 11), "origin": {"kind": "human"},
             "message": {"role": "user", "content": "按你说的加了缓存，管用"}},
            {"type": "assistant", "timestamp": _ts(1, 11), "message": {"content": [{"type": "text", "text": "好。"}]}}]
    _jsonl(env["claude"] / "-work-shop" / "s1.jsonl", rows)
    env["env"]["KROUTER_EXPERIENCE"] = "1"
    out = _run(env)
    assert out["experience_uses"] == 2
    u = experience.usage(env["vault"])
    assert u["C02"]["offered"] == 1 and u["C02"]["adopted"] == 1
    assert _run(env).get("experience_uses") is None  # 再导入一遍不重复记


SET16_HELDOUT_SHA = "d939c2cacc24c9ece6e7c104dd99bacd30d6bf246c4f1d71a9dee4745b24ba8a"
CARDS_EN_SHA = "b27d45a3fe439e86e99a8e9225c467eb4f57b89c27c0e693c4c25af0f59f03bc"
SET17_SHA = "7ccda4641f7a2dd651708b68196cf0043c86bd174e405a2580bfea723c4ba2de"
SET19_SHA = "b137cc968d0bb7cfe0ebf54f63ea4f774d9ea56daf17db64fe58cc9a07c85caf"
SET20_SHA = "56ad0b0c0b2d2cc87f984a6a0ee856d1c2b935ba962e480b10acc1258aabb780"


def test_sets_16_and_17_are_frozen():
    import host

    with gzip.open(BENCH / "set16_heldout.jsonl.gz", "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest() == SET16_HELDOUT_SHA
    cards = b"".join(p.read_bytes() for p in sorted((BENCH / "cards_en").glob("*.md")))
    assert hashlib.sha256(cards).hexdigest() == CARDS_EN_SHA
    assert hashlib.sha256((BENCH / "set17_sessions.jsonl").read_bytes()).hexdigest() == SET17_SHA
    assert hashlib.sha256((BENCH / "set19_sessions.jsonl").read_bytes()).hexdigest() == SET19_SHA
    assert hashlib.sha256((BENCH / "set20_sessions.jsonl").read_bytes()).hexdigest() == SET20_SHA
    assert len(host.load("dev", "16")) == 28


def test_english_vault_gets_an_english_digest_at_session_start(tmp_path):
    import host

    host.SET = "16"
    try:
        vault = host.build_vault(tmp_path)
    finally:
        host.SET = "15"
    ctx = json.loads(_start(vault, tmp_path, KROUTER_EXPERIENCE="1").stdout)["hookSpecificOutput"]["additionalContext"]
    assert ctx.startswith("KRouter experience digest") and "[C08]" in ctx and "How to use:" in ctx and "经验" not in ctx.split("\n", 1)[1]


def test_extraction_scorer_counts_written_subject_free_and_duplicates():
    import extract

    sessions = {s["id"]: s for s in extract.load()}
    good = [{"situation": "写正则匹配日期，改来改去总有漏的", "action": "先列 10 条该匹配和 10 条不该匹配的例子当测试",
             "result": "20 条全部通过", "lesson": "规则改来改去总有漏的时，先写一组正反例当测试，每改一次全跑一遍",
             "when": ["改来改去总漏", "顾此失彼", "老是漏掉"],
             "quotes": ["10 条应该匹配的、10 条不该匹配的", "现在 20 条全部通过"]}]
    r = extract.score_one(sessions["S01"], json.dumps(good, ensure_ascii=False))
    assert [{k: w[k] for k in ("subject_free", "faithful")} for w in r["written"]] == [{"subject_free": True, "faithful": True}]
    leaky = [{**good[0], "lesson": "正则改来改去总有漏的时，先写正反例", "title": "写正则先写例子"}]
    assert extract.score_one(sessions["S01"], json.dumps(leaky, ensure_ascii=False))["written"][0]["subject_free"] is False
    dup = [{"situation": "cargo build 报了 80 多个错误", "action": "只改第一个错误", "result": "剩下的七十多个都没了",
            "lesson": "报错一大片时，后面的多半是被第一个错误连带出来的，先只解决最前面那一条", "when": ["满屏报错", "一大堆错误"]}]
    assert extract.score_one(sessions["D01"], json.dumps(dup, ensure_ascii=False))["written"] == []
    assert extract.score_one(sessions["N01"], "[]")["proposed"] == 0


def test_when_phrases_are_optional_and_subject_names_are_dropped(tmp_path, monkeypatch):
    import llm

    item = {**GOOD, "situation": "nginx 吃着发平", "when": ["nginx 发平", "层次不够"]}
    monkeypatch.setattr(llm, "complete", lambda prompt, vault=None: json.dumps([item], ensure_ascii=False))
    written, _ = experience.extract(_entry(), EXCERPT + "nginx", tmp_path, "[[x]]")
    assert experience.load_cards(tmp_path)[0]["when"] == ["层次不够"]  # 带题材名的短语去掉，卡照写
    bare = {k: v for k, v in GOOD.items() if k != "when"}
    path, why = experience.learn(tmp_path / "v2", bare, "x") if (tmp_path / "v2").mkdir() is None else (None, "")
    assert path and "适用于" not in path.read_text(encoding="utf-8") and "when:" not in path.read_text(encoding="utf-8")


def test_a_lesson_that_still_names_its_own_subject_is_sent_back(tmp_path):
    item = {**EN_CARD, "subject": ["nginx", "server block"], "lesson": "When an nginx change has no effect, check the file"}
    path, why = experience.learn(tmp_path, item, "x")
    assert path is None and "names the subject (nginx)" in why
    ok = {**EN_CARD, "subject": ["nginx", "server block"]}
    assert experience.learn(tmp_path, ok, "x")[0] is not None


def test_numbers_in_a_card_must_come_from_the_session(tmp_path):
    card = {**EN_CARD, "subject": ["nginx"], "result": "Deleting the stale file made all 24 reloads work"}
    path, why = experience.learn(tmp_path, card, "x")
    assert path is None and "not in quotes: 24" in why
    quoted = {**card, "quotes": ["after that, all 24 reloads worked"]}
    assert experience.learn(tmp_path, quoted, "x")[0] is not None
    assert experience.unsupported_figures({"result": "20 of 24"}, "confirmed 20 batches in 2026") == ["24"]
    assert experience.unsupported_figures({"result": "3,000 files"}, "renamed 3000 files") == []
    assert experience.unsupported_figures({"result": "1.4 m"}, "it is 1.1 by 1.4") == []
    assert experience.unsupported_figures({"result": "1.1 m"}, "width 21.1") == ["1.1"]
