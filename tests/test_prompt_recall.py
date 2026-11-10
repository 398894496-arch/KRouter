"""`session_hook.py prompt` with `KROUTER_RECALL_PROMPT=1`: mention it and it comes to mind (`recollect.py`).

The contract since 2.0: when the message names nothing in the vault the hook prints nothing at all (Claude Code and
Codex add any output to the context, so silence is the default); when it names a page it prints one JSON object,
`hookSpecificOutput.additionalContext`, holding at most two pages, each with its conclusion, its path and a mark that
this is memory, not the user's words. Off by default (set 32 failed its registered line on recall)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter/scripts"
HOOK = SCRIPTS / "session_hook.py"
sys.path.insert(0, str(SCRIPTS))
import recollect  # noqa: E402

KEY = "sk-" + "Abc123XyZ" * 4


def _page(v: Path, rel: str, meta: str, body: str) -> None:
    p = v / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{meta}\n---\n\n# {Path(rel).stem}\n\n{body}\n", encoding="utf-8")


@pytest.fixture()
def box(tmp_path):
    v = tmp_path / "vault"
    _page(v, "团队手册/测试环境.md", "title: 测试环境\nstatus: active",
          "测试环境每天凌晨 3 点自动重置数据；需要保留的数据要提前在工单里申请快照。另见 [[发布流程]]。")
    _page(v, "团队手册/发布流程.md", "title: 发布流程\nstatus: active", "发布只从 main 打 tag，发布前跑完整测试。")
    _page(v, "团队手册/代码托管（旧）.md", "title: 代码托管（旧）\nstatus: superseded\nsuperseded_by: \"[[代码托管]]\"",
          "代码放在自建的 GitLab。")
    _page(v, "团队手册/代码托管.md", "title: 代码托管\nstatus: active\nsupersedes: \"[[代码托管（旧）]]\"",
          "代码统一迁到公司的 GitHub 企业版，自建 GitLab 只读到明年三月；新建仓库默认私有。本页取代 [[代码托管（旧）]]。")
    _page(v, "团队手册/短信通道（旧）.md", "title: 短信通道（旧）\nstatus: retired", "验证码短信只用一家供应商。")
    _page(v, "团队手册/部署钥匙.md", "title: 部署钥匙\nstatus: active", "部署用的密钥放在保险箱里，轮换周期 90 天。")
    _page(v, "Handbook/Status page.md", "title: Status page\nstatus: active\nhow: Update the status page within 15 "
          "minutes of a confirmed incident, then every 30 minutes",
          "The status page is updated within 15 minutes of a confirmed customer-facing incident, then every 30 minutes "
          "until it is resolved.")
    _page(v, "团队手册/团队周会.md", "title: 团队周会\nstatus: active", "团队周会在每周二上午 10 点，半小时，只同步风险。")
    (v / "90 系统文件").mkdir(parents=True, exist_ok=True)
    (v / "90 系统文件/canonical_sources.psv").write_text(
        "Z22|测试环境|团队手册/测试环境.md|测试环境每天凌晨 3 点重置数据；要保留先在工单申请快照\n"
        "Z03|代码托管;GitLab|团队手册/代码托管（旧）.md|代码放在自建的 GitLab\n"
        "Z24|短信通道|团队手册/短信通道（旧）.md|验证码短信只用一家供应商\n"
        "Z99|部署钥匙|团队手册/部署钥匙.md|密钥放保险箱\n"
        "Z07|周会|团队手册/团队周会.md|每周二上午 10 点\n"
        "E25|status page|Handbook/Status page.md|Update within 15 minutes\n", encoding="utf-8")
    env = {k: val for k, val in os.environ.items() if not k.endswith("_API_KEY")}
    env.update(KROUTER_VAULT=str(v), KROUTER_STATE_DIR=str(tmp_path / "state"), KROUTER_CACHE_DIR=str(tmp_path / "cache"),
               KROUTER_NO_QUERY_LOG="1", KROUTER_RECALL_PROMPT="1")
    for k in ("KROUTER_IN_DISTILL", "KROUTER_INJECT", "KROUTER_MAP", "OBSIDIAN_VAULT"):
        env.pop(k, None)
    subprocess.run([sys.executable, str(SCRIPTS / "recall_index.py"), "--vault", str(v), "--stats"], env=env,
                   capture_output=True, check=True, timeout=120)
    return {"vault": v, "env": env, "state": tmp_path / "state", "tmp": tmp_path}


def _say(box: dict, text: str, agent: str = "claude", sid: str = "s1", env: dict | None = None) -> str:
    payload = {"prompt": text, "session_id": sid, "cwd": str(box["tmp"])}
    if agent == "cursor":
        payload = {"prompt": text, "conversation_id": sid, "workspace_roots": [str(box["tmp"])]}
    res = subprocess.run([sys.executable, str(HOOK), "prompt", "--agent", agent], input=json.dumps(payload),
                         env=env or box["env"], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    return res.stdout


def _note(out: str, event: str = "UserPromptSubmit") -> str:
    data = json.loads(out)
    assert set(data) == {"hookSpecificOutput"} and data["hookSpecificOutput"]["hookEventName"] == event
    return data["hookSpecificOutput"]["additionalContext"]


def test_a_named_page_comes_with_its_conclusion_its_path_and_a_memory_mark(box):
    note = _note(_say(box, "测试环境的数据有没有办法留下来，我下周要演示"))
    assert "KRouter 记忆提示" in note and "不是用户这句话里说的" in note
    assert "凌晨 3 点重置数据" in note and "团队手册/测试环境.md" in note and "「测试环境」" in note
    assert "相关页：发布流程" in note  # 联想页只给标题
    assert "发布只从 main 打 tag" not in note


def test_nothing_named_prints_nothing(box):
    assert _say(box, "帮我把这个函数改成异步的，顺便加个超时") == ""


def test_off_by_default_and_by_switch(box):
    env = {k: v for k, v in box["env"].items() if k != "KROUTER_RECALL_PROMPT"}
    assert _say(box, "测试环境的数据有没有办法留下来，我下周要演示", env=env) == ""
    assert _say(box, "测试环境的数据有没有办法留下来，我下周要演示", env={**env, "KROUTER_RECALL_PROMPT": "0"}) == ""
    assert _say(box, "测试环境的数据有没有办法留下来，我下周要演示", env={**box["env"], "KROUTER_INJECT": "0"}) == ""


def test_codex_gets_the_same_json_and_cursor_only_its_receipt(box):
    note = _note(_say(box, "测试环境的数据有没有办法留下来，我下周要演示", agent="codex"))
    assert "团队手册/测试环境.md" in note
    # Cursor 的 beforeSubmitPrompt 文档里只有 continue / user_message：加不了上下文，所以这一步在 Cursor 上不跑
    assert json.loads(_say(box, "测试环境的数据有没有办法留下来，我下周要演示", agent="cursor")) == {"continue": True}


def test_an_old_page_brings_the_page_that_replaced_it_and_says_so(box):
    note = _note(_say(box, "新项目的仓库我就建在公司自己的 GitLab 上吧"))
    assert "团队手册/代码托管.md" in note and "GitHub 企业版" in note
    assert "更早的一页说法不同（团队手册/代码托管（旧）.md）" in note
    assert "代码放在自建的 GitLab" not in note  # 旧页的锚点说的是旧结论


def test_a_retired_page_with_no_successor_never_comes(box):
    assert _say(box, "短信通道这块我准备重写一下发送逻辑，验证码短信供应商那边的接口") == ""


def test_a_secret_page_never_comes(box):
    assert _say(box, "部署钥匙轮换周期是多少，保险箱里那个") == ""


def test_the_same_page_comes_once_per_session_unless_its_conclusion_changed(box):
    assert _say(box, "测试环境的数据有没有办法留下来，我下周要演示", sid="a")
    assert _say(box, "测试环境的数据有没有办法留下来，我下周要演示", sid="a") == ""
    assert _say(box, "测试环境的数据有没有办法留下来，我下周要演示", sid="b")  # 另一个会话照常
    psv = box["vault"] / "90 系统文件/canonical_sources.psv"
    psv.write_text(psv.read_text(encoding="utf-8").replace("要保留先在工单申请快照", "要保留先申请快照，保留 7 天"),
                   encoding="utf-8")
    assert "保留 7 天" in _note(_say(box, "测试环境的数据有没有办法留下来，我下周要演示", sid="a"))


def test_pasted_code_and_logs_are_not_matched(box):
    fenced = "这个报错帮我看看：\n```\n2026-11-10 12:00:01 ERROR 测试环境 reset failed\n```\n顺便把超时改长点"
    raw = ("docker compose up 卡住了\nweb_1  | waiting for db...\nstatus_1  | status page check failed\n"
           "2026-11-10T12:00:01Z ERROR GitLab mirror timeout")
    for text in (fenced, raw):
        assert _say(box, text) == ""


def test_a_short_name_inside_a_long_message_is_not_a_mention(box):
    assert _say(box, "下午我先去周会，回来以后你帮我把登录页的表单校验补上，再把按钮颜色统一一下") == ""


def test_a_name_inside_a_message_about_something_else_fails_the_second_key(box):
    assert _say(box, "Can you make the status page of my photography portfolio a dark banner with my logo on it?") == ""


def test_what_was_brought_is_recorded_redacted_with_word_page_and_route(box):
    _say(box, f"测试环境的数据有没有办法留下来，key 是 {KEY}。下周演示", sid="rec-1")
    rows = [json.loads(ln) for ln in (box["state"] / "recalled.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert row["page"] == "团队手册/测试环境.md" and row["word"] == "测试环境" and row["route"] == "alias"
    assert row["agent"] == "claude" and row["session"] == "rec-1"
    assert KEY not in row["sentence"] and "测试环境的数据" in row["sentence"] and "下周演示" not in row["sentence"]


def test_a_session_marked_no_capture_still_recalls_but_records_no_words(box):
    out = _say(box, "#不记 测试环境的数据有没有办法留下来，我下周要演示", sid="nc")
    assert "团队手册/测试环境.md" in _note(out)
    row = json.loads((box["state"] / "recalled.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert row["sentence"] == ""


def test_per_session_cap(box, monkeypatch):
    monkeypatch.setenv("KROUTER_STATE_DIR", str(box["state"]))
    hits = [{"rel": f"p{i}.md", "how": "x", "notes": []} for i in range(recollect.PER_SESSION + 3)]
    assert len(recollect.keep_new(hits, "claude", "cap")) == recollect.PER_SESSION
    assert recollect.keep_new([{"rel": "new.md", "how": "y", "notes": []}], "claude", "cap") == []


def test_no_index_brings_nothing_and_starts_a_refresh(box):
    env = {**box["env"], "KROUTER_CACHE_DIR": str(box["tmp"] / "empty-cache")}
    assert _say(box, "测试环境的数据有没有办法留下来，我下周要演示", env=env) == ""
    assert list(box["state"].glob("recall-refresh-*.stamp"))


def test_the_correction_candidate_is_still_written_and_nothing_else_changes(box):
    (box["state"]).mkdir(parents=True, exist_ok=True)
    (box["state"] / "import.json").write_text(json.dumps({"consent": True}), encoding="utf-8")
    out = _say(box, "不对，以后一律用 pnpm，不要再用 npm。")
    assert out == ""  # 没提到库里的事：照旧一个字不输出
    assert list((box["vault"] / "05 时间日志/会话摘录").glob("*纠正候选.md"))


@pytest.mark.parametrize("line,code", [
    ("if 明天还挂就回滚", False),
    ("terraform plan failed again, can you look?", False),
    ("go ahead and fix the status page", False),
    ("Note: the hackathon is next week.", False),
    ("我们的测试环境又挂了", False),
    ("status: active", True),
    ("2026-11-10 12:00:01 ERROR kafka down", True),
    ('  File "x.py", line 3, in <module>', True),
    ("kubectl get pods -n prod", True),
    ("if (x) {", True),
    ("SELECT * FROM refunds WHERE id = 3", True),
    ("terraform-runner_1  | Error: Failed to load plugin schemas", True),
    ("<<<<<<< HEAD", True),
    ("  GPU hours: 8", True),
    ("- openapi: 3.0.1", True),
])
def test_what_counts_as_pasted(line, code):
    assert recollect.code_like(line) is code


def test_latin_names_match_whole_words_only():
    s, _where, cuts = recollect.squash("we need to import the report")
    assert recollect.spans(recollect.norm("port"), s, cuts) == []
    s, _where, cuts = recollect.squash("check the status page, please")
    assert recollect.spans(recollect.norm("status page"), s, cuts)
