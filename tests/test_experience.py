"""Experience cards (experimental, `KROUTER_EXPERIENCE=1`): written next to the distill, offered as suggestions apart
from the facts, quiet when nothing fits, off by default. Set 13's files are pinned (HELDOUT.md)."""

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


def _route(vault: Path, query: str, tmp_path: Path, on: bool) -> str:
    e = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_CACHE_DIR": str(tmp_path / "cache"),
         "KROUTER_NO_QUERY_LOG": "1"}
    e.pop("KROUTER_EXPERIENCE", None)
    if on:
        e["KROUTER_EXPERIENCE"] = "1"
    res = subprocess.run([sys.executable, str(SCRIPTS / "route_knowledge.py"), "search", query], env=e,
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    return res.stdout


def test_router_adds_suggestions_after_the_facts_only_when_switched_on(bench_vault, tmp_path):
    off = _route(bench_vault, C02_CASE, tmp_path, on=False)
    assert "experience_" not in off
    on = _route(bench_vault, C02_CASE, tmp_path, on=True)
    assert on.index("experience_suggestions:") > on.index("route: search")
    assert "experience_note: 建议（别的任务里的经验" in on and "C02｜" in on.split("experience_suggestions:", 1)[1]
    assert "experience_" not in _route(bench_vault, "用 Python 写一个快速排序", tmp_path, on=True)


def _prompt(vault: Path, agent: str, on: bool, text: str = C02_CASE) -> subprocess.CompletedProcess:
    e = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_NO_QUERY_LOG": "1"}
    e.pop("KROUTER_EXPERIENCE", None)
    if on:
        e["KROUTER_EXPERIENCE"] = "1"
    return subprocess.run([sys.executable, str(SCRIPTS / "session_hook.py"), "prompt", "--agent", agent],
                          input=json.dumps({"prompt": text, "session_id": "s1"}), env=e, capture_output=True,
                          text=True, timeout=60)


def test_prompt_hook_adds_suggestions_to_the_context(bench_vault):
    res = _prompt(bench_vault, "claude", on=True)
    ctx = json.loads(res.stdout)["hookSpecificOutput"]
    assert ctx["hookEventName"] == "UserPromptSubmit" and "C02｜" in ctx["additionalContext"]
    assert "建议（别的任务里的经验" in _prompt(bench_vault, "codex", on=True).stdout
    assert json.loads(_prompt(bench_vault, "cursor", on=True).stdout) == {"continue": True}
    assert _prompt(bench_vault, "claude", on=False).stdout == ""
    assert _prompt(bench_vault, "claude", on=True, text="用 Python 写一个快速排序").stdout == ""


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
    {**GOOD, "situation": "nginx 吃着发平", "when": ["nginx 发平", "nginx 寡淡", "层次"]},  # 触发语带题材
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
