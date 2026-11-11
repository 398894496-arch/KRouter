"""`session_hook.py prompt` with `KROUTER_RECALL_PROMPT=1`: mention it and it comes to mind (`recollect.py`).

The contract since 2.0: when the message names nothing in the vault the hook prints nothing at all (Claude Code and
Codex add any output to the context, so silence is the default); when it names a page it prints one JSON object,
`hookSpecificOutput.additionalContext`, holding at most two pages, each with its conclusion, its path and a mark that
this is memory, not the user's words. On by default since set 35 (the hook plus the standing index passed with both hosts); `KROUTER_RECALL_PROMPT=0` off."""

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


def test_on_by_default_and_off_by_switch(box):
    # 第 35 套两个宿主都过线：钩子和下意识索引默认打开；开关照样能关
    env = {k: v for k, v in box["env"].items() if k != "KROUTER_RECALL_PROMPT"}
    assert "团队手册/测试环境.md" in _note(_say(box, "测试环境的数据有没有办法留下来，我下周要演示", env=env, sid="d1"))
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


# ---------- 2.0 second round: the standing index and learning from what the agent fetched ----------

sys.path.insert(0, str(SCRIPTS))
import compile_subconscious  # noqa: E402
import learn_mentions  # noqa: E402


def test_the_standing_index_lists_live_topics_with_a_how_to_fetch_line(box):
    text = compile_subconscious.standing_index(box["vault"])
    assert text.startswith("KRouter 下意识索引")
    assert "测试环境" in text and "〔团队手册/测试环境.md〕" in text
    assert "〔团队手册/代码托管.md〕" in text and "代码托管（旧）" not in text  # 旧页的那一行算在新页名下
    assert "短信通道" not in text and "部署钥匙" not in text  # 退役的、机密的不列
    assert "krouter_ask" in text and "route_knowledge.sh" in text and str(box["vault"]) in text  # 不假设宿主看得到工具说明


def test_the_standing_index_keeps_to_its_budget_and_says_how_many_are_left(box):
    # 主题多于整行的预算：排在前面的给整行，其余的只列名字；名字也放不下了才说「还有几件没列出」
    text = compile_subconscious.standing_index(box["vault"], lines=2)
    assert text.count("\n- ") == 2 and "也记着" in text and "没列出" not in text
    names = text.split("也记着", 1)[1].split("\n", 1)[0]
    assert sum(n in names for n in ("测试环境", "代码托管", "周会", "status page")) == 2
    tight = compile_subconscious.standing_index(box["vault"], lines=1, chars=40)
    assert "没列出" in tight and len(tight.split("用法：", 1)[0]) <= 40 + 60


def test_session_start_hands_over_the_index_only_when_on(box):
    def start(env):
        return subprocess.run([sys.executable, str(HOOK), "start"], input=json.dumps({"cwd": str(box["tmp"])}), env=env,
                              capture_output=True, text=True, timeout=60).stdout
    env = {k: v for k, v in box["env"].items() if k not in ("KROUTER_RECALL_PROMPT",)}
    assert "下意识索引" in json.loads(start({**env, "KROUTER_RECALL_INDEX": "1"}))["hookSpecificOutput"]["additionalContext"]
    assert start({**env, "KROUTER_RECALL_INDEX": "0"}) == ""
    out = start({**env, "KROUTER_RECALL_INDEX": "1"})
    assert len(json.loads(out)["hookSpecificOutput"]["additionalContext"]) < 9400


def _transcript(path: Path, prompt_text: str, tool_result: str, answer: str) -> None:
    import datetime as dt
    ts = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=1)).isoformat()
    rows = [
        {"type": "user", "timestamp": ts, "message": {"role": "user", "content": prompt_text}},
        {"type": "assistant", "timestamp": ts, "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "mcp__krouter__krouter_ask", "input": {"query": "测试环境"}}]}},
        {"type": "user", "timestamp": ts, "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": tool_result}]}},
        {"type": "assistant", "timestamp": ts, "message": {"content": [{"type": "text", "text": answer}]}},
    ]
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def test_a_page_the_agent_fetched_and_used_after_the_hook_said_nothing_is_learned(box):
    box["env"]["KROUTER_RECALL_LEARN"] = "1"  # 第 36 套没过线：默认关
    said = "演示前那台机器的数据会不会被清掉，老秦说夜里会洗一遍"
    assert _say(box, said, sid="L1") == ""  # 钩子没认出来
    t = box["tmp"] / "t.jsonl"
    receipt = f"route: canonical\ncanonical_source: {box['vault']}/团队手册/测试环境.md\nhow: 每天凌晨 3 点重置"
    _transcript(t, said, receipt, "会的：测试环境每天凌晨 3 点重置数据，要保留就先申请快照（团队手册/测试环境.md）。")
    res = subprocess.run([sys.executable, str(HOOK), "turn"], input=json.dumps({"session_id": "L1", "transcript_path": str(t)}),
                         env=box["env"], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    rows = [json.loads(x) for x in (box["state"] / "recall-learn.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows == [{**rows[0], "kind": "learn", "page": "团队手册/测试环境.md", "sentence": said}]
    out = learn_mentions.run(box["vault"], box["state"])
    assert out["added"] and out["added"][0]["page"] == "团队手册/测试环境.md"
    psv = box["vault"] / learn_mentions.OUT
    assert "待验证" in psv.read_text(encoding="utf-8")
    assert learn_mentions.run(box["vault"], box["state"])["events"] == 0  # 读过的不再读


def test_nothing_is_learned_when_the_agent_did_not_use_the_page(box):
    box["env"]["KROUTER_RECALL_LEARN"] = "1"
    said = "演示前那台机器的数据会不会被清掉"
    _say(box, said, sid="L2")
    t = box["tmp"] / "t2.jsonl"
    _transcript(t, said, f"canonical_source: {box['vault']}/团队手册/测试环境.md", "我不确定，问一下运维吧。")
    subprocess.run([sys.executable, str(HOOK), "turn"], input=json.dumps({"session_id": "L2", "transcript_path": str(t)}),
                   env=box["env"], capture_output=True, text=True, timeout=60)
    assert not (box["state"] / "recall-learn.jsonl").exists()


def test_a_contradicted_provisional_phrase_is_removed(box):
    psv = box["vault"] / learn_mentions.OUT
    psv.parent.mkdir(parents=True, exist_ok=True)
    psv.write_text(learn_mentions.HEADER + "团队手册/测试环境.md|夜里洗库\n", encoding="utf-8")
    (box["state"]).mkdir(parents=True, exist_ok=True)
    (box["state"] / "recall-learn.jsonl").write_text(json.dumps(
        {"kind": "contradict", "phrase": "夜里洗库", "page": "团队手册/测试环境.md", "instead": "团队手册/发布流程.md"},
        ensure_ascii=False) + "\n", encoding="utf-8")
    out = learn_mentions.run(box["vault"], box["state"])
    assert out["removed"] and "夜里洗库" not in psv.read_text(encoding="utf-8")


def test_learned_phrases_skip_everyday_words_and_other_pages_names(box):
    picks = learn_mentions.pick(box["vault"], "帮我把这个函数改成异步的，顺便看下 GitLab 那边", "团队手册/测试环境.md")
    assert all("GitLab" not in p for p in picks)  # 别的页的名字不能学给这一页
    assert learn_mentions.pick(box["vault"], "好的谢谢，那就这样吧", "团队手册/测试环境.md") == []


def test_learning_is_off_by_default_and_keeps_no_words(box):
    said = "演示前那台机器的数据会不会被清掉"
    _say(box, said, sid="L3")
    assert not list((box["state"] / "recalled").glob("*.last.json")) if (box["state"] / "recalled").exists() else True


def test_a_page_fetched_with_a_windows_path_is_found(tmp_path):
    """Windows receipts name pages with backslashes; they were hidden by the JSON escaping the patterns ran on."""
    import recollect

    vault = tmp_path / "vault"
    (vault / "团队手册").mkdir(parents=True)
    (vault / "团队手册/测试环境.md").write_text("# 测试环境\n\n每天凌晨 3 点重置\n", encoding="utf-8")
    win = str(vault).replace("/", "\\")
    rows = [{"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1",
                                                      "content": f"route: canonical\ncanonical_source: {win}\\团队手册\\测试环境.md"}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t2",
                                                      "content": "recall:\n- 团队手册\\测试环境.md tier=rule score=3"}]}}]
    assert recollect.fetched_pages(vault, rows) == ["团队手册/测试环境.md"]
