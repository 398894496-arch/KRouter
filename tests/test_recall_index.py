from pathlib import Path

import pytest

import recall_index as r
from canonical_lookup import alias_score, lookup


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    psv = tmp_path / "map.psv"
    psv.write_text("# id|aliases|source|anchor\nQ01|主入口;总入口|Agent第二大脑.md|唯一总入口\n", encoding="utf-8")
    monkeypatch.setenv("KROUTER_MAP", str(psv))
    v = tmp_path / "vault"
    write(v, "Agent第二大脑.md", "---\ntitle: Agent第二大脑\nstatus: active\n---\n\n整个知识库只从这里进入。\n")
    write(
        v,
        "02 经验与方法/短视频/包装排版准纠错.md",
        "---\ntitle: 包装排版准纠错\nstatus: provisional\n---\n\n"
        "1. **排版形态和动画要多变，内容要丰富。** 每一页换一种版式。\n",
    )
    write(
        v,
        "02 经验与方法/准经验/旧排版规则.md",
        "---\ntitle: 旧排版规则\nstatus: superseded\n---\n\n排版形态统一用左侧标题，动画固定。\n",
    )
    write(
        v,
        "02 经验与方法/搜索与知识库/封账先看时间日志文件.md",
        "---\ntitle: 封账先看时间日志文件\nstatus: active\n---\n\n时间日志文件存在且不是待总结，这一天就已封账。\n",
    )
    write(v, "05 时间日志/2026-10/01｜日常.md", "---\ntitle: 01｜日常\n---\n\n今天整理了排版，也看了时间日志。\n")
    write(v, "Clippings/剪藏.md", "排版 封账 时间日志 全都在这里\n")
    return v


def hits(res):
    return [h["rel"] for h in res["hits"]] if res["confidence"] != "none" else []


def test_tokens_split_cjk_bigrams_and_latin():
    assert r.tokens("日更健康 Groq whisper") == ["日更", "更健", "健康", "groq", "whisper"]


def test_rule_page_ranks_first(vault):
    res = r.recall(vault, "封账要看时间日志吗")
    assert hits(res)[0] == "02 经验与方法/搜索与知识库/封账先看时间日志文件.md"
    assert res["hits"][0]["tier"] == "rule"


def test_clippings_are_not_indexed(vault):
    res = r.recall(vault, "封账 时间日志 排版", limit=10)
    assert all(not h["rel"].startswith("Clippings/") for h in res["hits"])


def test_superseded_page_ranks_below_live_one(vault):
    rels = [h["rel"] for h in r.recall(vault, "排版形态 动画", limit=5)["hits"]]
    assert rels.index("02 经验与方法/短视频/包装排版准纠错.md") < rels.index("02 经验与方法/准经验/旧排版规则.md")


def test_unknown_question_is_refused(vault):
    res = r.recall(vault, "比特币现在多少钱")
    assert res["confidence"] == "none"


def test_sidecar_triggers_bridge_paraphrase(vault):
    before = r.recall(vault, "画面太单调被骂了")
    assert "02 经验与方法/短视频/包装排版准纠错.md" not in hits(before)
    write(vault, "90 系统文件/Claude Code协作/下意识触发词.psv",
          "02 经验与方法/短视频/包装排版准纠错.md|画面太单调;版式单调;动画不够多变\n")
    after = r.recall(vault, "画面太单调被骂了")
    assert hits(after)[0] == "02 经验与方法/短视频/包装排版准纠错.md"


def test_scope_restricts_hits(vault):
    res = r.recall(vault, "封账 时间日志", scope="05 时间日志", limit=5)
    assert res["hits"] and all(h["rel"].startswith("05 时间日志/") for h in res["hits"])


def test_incremental_refresh_picks_up_edits(vault):
    con = r.connect(r.cache_path(vault))
    assert r.refresh(vault, con)["added"] == 5
    assert r.refresh(vault, con) == {"added": 0, "changed": 0, "removed": 0, "docs": 5}
    write(vault, "Agent第二大脑.md", "---\ntitle: Agent第二大脑\n---\n\n入口改了。\n")
    assert r.refresh(vault, con)["changed"] == 1


def test_how_skips_status_line_and_prefers_bold_rule():
    body = "provisional（准纠错）\n\n背景说明一段文字在这里。\n\n1. **英文证据一律截翻译后的页面。** 原话略。\n"
    assert r.first_rule_line(body).startswith("英文证据一律截翻译后的页面")


def test_short_alias_inside_long_question_does_not_lock():
    assert alias_score("日更能不能交给云端自动化跑", "日更") < 100
    assert alias_score("日更", "日更") >= 1000
    assert alias_score("每日进化运行状态怎么看", "每日进化运行状态") >= 500


def test_lookup_refuses_short_alias_lock():
    rows = [("Q21", ["日更", "日更健康"], "90 系统文件/自动化/日更健康.md", "当前健康以本页为准")]
    assert lookup("日更能不能交给云端自动化跑", rows) is None
    assert lookup("日更健康", rows)[0] == "Q21"


def test_token_fallback_fragment_does_not_lock():
    rows = [("Q05", ["纠错优先级", "最新纠正"], "AGENTS.md", "用户当前指令和最新纠正优先")]
    assert lookup("Claude Code 纠错", rows) is None
    assert lookup("纠错优先级", rows)[0] == "Q05"


def test_rejected_source_is_not_locked(tmp_path):
    from canonical_lookup import lookup as lk

    v = tmp_path / "v"
    write(v, "old.md", "---\nstatus: rejected\n---\n")
    write(v, "new.md", "---\nstatus: active\n---\n")
    rows = [("Q18", ["项目阶段诊断"], "old.md", "x"), ("Q19", ["真实任务"], "new.md", "y")]
    assert lk("项目阶段诊断", rows, vault=v) is None
    assert lk("真实任务", rows, vault=v)[0] == "Q19"


def test_single_keyword_query_is_answered(vault):
    res = r.recall(vault, "封账")
    assert res["confidence"] != "none"
    assert hits(res)[0] == "02 经验与方法/搜索与知识库/封账先看时间日志文件.md"


def test_bare_number_is_not_a_content_term(vault):
    res = r.recall(vault, "2026")
    assert res["confidence"] == "none"


def test_route_widens_from_single_file_scope(vault, monkeypatch, tmp_path):
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1] / "skill/krouter-obsidian/scripts/route_knowledge.py"
    write(vault, "02 经验与方法/Agent/用户偏好与工作约束.md", "---\ntitle: 用户偏好\n---\n\n名称要能看懂。\n")
    env = {**__import__("os").environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_STATE_DIR": str(tmp_path / "state"),
           "KROUTER_NO_QUERY_LOG": "0"}
    out = subprocess.run([sys.executable, str(root), "preference", "封账 时间日志"], capture_output=True, text=True, env=env).stdout
    assert "scope_widened: vault" in out
    assert "封账先看时间日志文件.md" in out
    log = (tmp_path / "state" / "queries.jsonl").read_text(encoding="utf-8")
    assert "ranked-recall-complete+widened" in log


def test_reconsolidate_reads_only_weak_queries(tmp_path):
    import json

    import reconsolidate as rc

    log = tmp_path / "q.jsonl"
    log.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in [
        {"ts": "2026-10-01T00:00:00Z", "q": "没答好", "status": "bounded-literal-search-complete"},
        {"ts": "2026-10-01T00:00:01Z", "q": "低置信", "status": "ranked-recall-complete", "confidence": "low"},
        {"ts": "2026-10-01T00:00:02Z", "q": "答好了", "status": "ranked-recall-complete", "confidence": "high"},
        {"ts": "2026-09-01T00:00:00Z", "q": "游标之前", "status": "bounded-literal-search-complete"},
    ]), encoding="utf-8")
    got = [row["q"] for row in rc.load_misses(log, "2026-09-30T00:00:00Z")]
    assert got == ["没答好", "低置信"]


def test_checkup_flags_dead_lock_and_tenure(vault, tmp_path):
    import subprocess
    import sys

    write(vault, "02 经验与方法/准经验/新排版规则.md",
          "---\ntitle: 新排版规则\nstatus: active\nsupersedes:\n  - \"[[02 经验与方法/准经验/旧排版规则]]\"\n---\n\n排版形态和动画要多变。\n")
    psv = tmp_path / "m2.psv"
    psv.write_text("Q09|旧规则|02 经验与方法/准经验/旧排版规则.md|x\n", encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "skill/krouter-obsidian/scripts/checkup.py"
    env = {**__import__("os").environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_STATE_DIR": str(tmp_path / "s")}
    subprocess.run([sys.executable, str(script), "--map", str(psv), "--days", "1"], check=True, env=env, capture_output=True)
    page = (vault / "90 系统文件/自动化/下意识体检.md").read_text(encoding="utf-8")
    assert "Q09 →" in page and "superseded" in page
    assert "tenure: \"1/1\"" in page


def test_function_bigram_does_not_carry_a_refusal(vault):
    assert r.recall(vault, "帮我写一首关于秋天的诗")["confidence"] == "none"


def test_unknown_latin_term_is_refused(vault):
    assert r.recall(vault, "Kubernetes的排版怎么扩容")["confidence"] == "none"


def test_topic_page_needs_to_be_named(vault):
    write(vault, "02 经验与方法/主题档案/主题｜Grok 订阅.md",
          "---\ntitle: 主题｜Grok 订阅\ntopic_terms: grok-fixed;Grok订阅\n---\n\n排版 排版 排版 时间日志 封账 时间日志 封账。\n")
    unnamed = r.recall(vault, "封账要看时间日志吗", limit=5)
    assert unnamed["hits"][0]["rel"] != "02 经验与方法/主题档案/主题｜Grok 订阅.md"
    named = r.recall(vault, "grok-fixed 封账", limit=5)
    assert named["hits"][0]["rel"] == "02 经验与方法/主题档案/主题｜Grok 订阅.md"
    assert named["hits"][0]["tier"] == "topic"


def test_consolidate_topics_writes_cited_provisional_page(vault, monkeypatch):
    import consolidate_topics as ct

    write(vault, "05 时间日志/2026-10/02｜修补丁.md", "---\ntitle: 02｜修补丁\n---\n\n中文补丁又掉了，用户要求重装。\n")
    write(vault, ct.LIST, "cn|中文补丁|中文补丁|\n")
    seen = {}

    def fake(v, prompt):
        seen["prompt"] = prompt
        return ("## 一句话\n补丁反复掉。[[05 时间日志/2026-10/02｜修补丁]]\n## 当前状态\n截至 2026-10-02 未修好。[[不存在的页]]\n"
                "## 关键事实\n- x\n## 用户纠错与踩过的坑\n- y\n## 时间线\n- z\n## 未决与不确定\n- w\n## 相关页面\n- v\nTRIGGERS: 中文又丢了;汉化补丁")

    monkeypatch.setattr(ct, "call_model", fake)
    res = ct.build(vault, ct.load_list(vault)[0], False)
    assert res["status"] == "written" and res["bad_links"] == 1 and not res["missing_sections"]
    page = (vault / ct.OUT_DIR / "主题｜中文补丁.md").read_text(encoding="utf-8")
    assert "status: provisional" in page and "topic_terms: 中文补丁" in page
    assert "triggers: 中文补丁;中文又丢了;汉化补丁" in page
    assert "`不存在的页`（未找到此页）" in page and "[[05 时间日志/2026-10/02｜修补丁]]" in page
    assert "05 时间日志/2026-10/02｜修补丁.md" in seen["prompt"]
    assert ct.build(vault, ct.load_list(vault)[0], False)["status"] == "unchanged"


def test_single_concept_detection():
    assert r.is_single_concept("DSH") and r.is_single_concept("发版") and r.is_single_concept("grok-fixed")
    assert not r.is_single_concept("DSH 桌面端") and not r.is_single_concept("封账要看时间日志吗")


def test_title_hit_and_single_keyword(vault):
    res = r.recall(vault, "封账", limit=3)
    assert res["confidence"] != "none"
    assert hits(res)[0] == "02 经验与方法/搜索与知识库/封账先看时间日志文件.md"


def test_answer_card_is_attached_and_expires_with_its_page(vault):
    import hashlib
    import json

    rel = "02 经验与方法/搜索与知识库/封账先看时间日志文件.md"
    sha = hashlib.sha1((vault / rel).read_bytes()).hexdigest()[:16]
    write(vault, "90 系统文件/自动化/下意识问答.jsonl", json.dumps(
        {"rel": rel, "sha": sha, "q": "怎么判断哪天封账了", "a": "那天的时间日志存在且不叫待总结就算封账。"},
        ensure_ascii=False) + "\n")
    res = r.recall(vault, "怎么判断哪天封账了", limit=3)
    top = res["hits"][0]
    assert top["rel"] == rel and top["answer"].startswith("那天的时间日志存在")
    write(vault, rel, "---\ntitle: 封账先看时间日志文件\nstatus: active\n---\n\n规则改了。\n")
    res = r.recall(vault, "怎么判断哪天封账了", limit=3)
    assert all("answer" not in h for h in res["hits"])


def _card(vault, rel, q, a, sha=None):
    import hashlib
    import json

    sha = sha or hashlib.sha1((vault / rel).read_bytes()).hexdigest()[:16]
    path = vault / "90 系统文件/自动化/下意识问答.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"rel": rel, "sha": sha, "q": q, "a": a}, ensure_ascii=False) + "\n")


def test_stale_card_question_stops_ranking_its_page(vault):
    rel = "02 经验与方法/搜索与知识库/封账先看时间日志文件.md"
    _card(vault, rel, "封账以后燃料配比怎么算", "时间日志存在就算封账。")
    fresh = [h["rel"] for h in r.recall(vault, "燃料配比", limit=5, gate=False)["hits"]]
    assert rel in fresh  # the card question is a live trigger
    write(vault, rel, "---\ntitle: 封账先看时间日志文件\nstatus: active\n---\n\n规则改了，现在看健康页。\n")
    stale = [h["rel"] for h in r.recall(vault, "燃料配比", limit=5, gate=False)["hits"]]
    assert rel not in stale  # page changed: the old card no longer ranks it


def test_faithful_matches_whole_tokens_not_substrings():
    page = "日志保留 30 天，端口 8080，版本 v0.9.2，倍率 1.3。"
    assert r.faithful("保留 30 天，端口 8080", page) and r.faithful("版本 0.9.2", page)
    for wrong in ("保留 3 天", "保留 0 天", "端口 80", "端口 808", "倍率 3"):
        assert not r.faithful(wrong, page), wrong


def test_off_page_card_neither_ranks_nor_answers(vault):
    rel = "02 经验与方法/搜索与知识库/封账先看时间日志文件.md"
    _card(vault, rel, "咖啡机除垢周期是多少", "时间日志存在就算封账。")  # answer faithful, question not about the page
    res = r.recall(vault, "咖啡机除垢周期是多少", limit=5, gate=False)
    assert rel not in [h["rel"] for h in res["hits"]]
    assert r.recall(vault, "咖啡机除垢周期是多少", limit=5)["confidence"] == "none"


def test_faithful_requires_specifics_verbatim():
    page = "日更用本机 09:10（上海 00:10）+ `automations/obsidian-daily-evolution/run.sh`。Codex cron 保持 PAUSED。"
    assert r.faithful("本机 09:10 跑 `automations/obsidian-daily-evolution/run.sh`。", page)
    assert not r.faithful("本机 08:00 跑。", page)
    assert not r.faithful("用 launchd 每天跑。", page)
    assert r.faithful("Codex 那边暂停了。", page)


def test_faithful_joined_words_pass_but_derived_numbers_do_not():
    page = "原来 32px 文案配 104px 主标题。打开 TUN（utun1、utun7）。push 和 release 之前实测。用 /opt/homebrew/bin/claude。"
    assert r.faithful("utun1/utun7", page) and r.faithful("push/release 前实测", page)
    assert r.faithful("TUN：/opt/homebrew/bin/claude", page)  # full-width colon is punctuation
    assert not r.faithful("Opus：/opt/homebrew/bin/claude", page)  # "Opus" is not in the page
    assert not r.faithful("约 1:3.3", page)  # a ratio the model computed is not in the page


def test_unfaithful_card_is_not_printed_as_answer(vault):
    rel = "02 经验与方法/搜索与知识库/封账先看时间日志文件.md"
    _card(vault, rel, "怎么判断哪天封账了", "看 `05 时间日志/2099` 目录。")
    top = r.recall(vault, "怎么判断哪天封账了", limit=3)["hits"][0]
    assert top["rel"] == rel and "answer" not in top


def test_answer_cards_generation_filters_and_remembers_empty_pages(vault, monkeypatch):
    import json
    import re

    import answer_cards as ac
    import llm

    asked, verified = [], []

    def fake(prompt, v=None):
        rels = re.findall(r"### 页面路径: (.+)", prompt)
        if prompt.startswith(ac.VERIFY_PROMPT[:20]):
            verified.extend(rels)
            # the checker rejects a card whose answer is another question's
            return json.dumps({rel: [{"id": int(n), "ok": "跑" not in q} for n, q in re.findall(r"卡 (\d+)：问：(\S+)", prompt)]
                               for rel in rels}, ensure_ascii=False)
        asked.extend(rels)
        out = {}
        for rel in rels:
            if rel.endswith("封账先看时间日志文件.md"):
                out[rel] = [
                    {"q": "怎么算封账", "a": "时间日志文件存在且不是待总结就算封账。"},
                    {"q": "几点跑", "a": "每天 03:00 跑。"},
                    {"q": "key 是什么", "a": "api_key=abc 写在页里。"},
                ]
            else:
                out[rel] = []
        return json.dumps(out, ensure_ascii=False)

    monkeypatch.setattr(llm, "complete", fake)
    monkeypatch.setattr("sys.argv", ["answer_cards.py", "--vault", str(vault), "--jobs", "1"])
    assert ac.main() == 0
    rows = [json.loads(x) for x in (vault / ac.CARDS).read_text(encoding="utf-8").splitlines()]
    real = [x for x in rows if not x.get("empty")]
    assert [x["q"] for x in real] == ["怎么算封账"]  # 03:00 not in page; api_key line dropped
    assert real[0].get("v") == 1 and verified  # the second pass checked it
    assert any(x.get("empty") for x in rows)  # nav pages remembered
    first = len(asked)
    asked.clear()
    verified.clear()
    assert ac.main() == 0
    assert asked == [] and verified == [] and first > 0  # nothing changed: nothing re-asked or re-checked


def test_answer_cards_verify_drops_what_lexical_checks_cannot_see(vault, monkeypatch):
    """A half-off-topic or flipped card passes every lexical check; the second pass drops it."""
    import json
    import re

    import answer_cards as ac
    import llm

    rel = "02 经验与方法/搜索与知识库/封账先看时间日志文件.md"

    def fake(prompt, v=None):
        if prompt.startswith(ac.VERIFY_PROMPT[:20]):
            return json.dumps({rel: [{"id": int(n), "ok": "咖啡" not in q} for n, q in re.findall(r"卡 (\d+)：问：(\S+)", prompt)]},
                              ensure_ascii=False)
        return json.dumps({r: ([{"q": "怎么算封账", "a": "时间日志文件存在且不是待总结就算封账。"},
                                {"q": "咖啡机封账多久除垢", "a": "时间日志文件存在且不是待总结就算封账。"}] if r == rel else [])
                           for r in re.findall(r"### 页面路径: (.+)", prompt)}, ensure_ascii=False)

    monkeypatch.setattr(llm, "complete", fake)
    monkeypatch.setattr("sys.argv", ["answer_cards.py", "--vault", str(vault), "--jobs", "1"])
    page = (vault / rel).read_text(encoding="utf-8")
    assert r.grounded({"q": "咖啡机封账多久除垢", "a": "时间日志文件存在且不是待总结就算封账。"}, page)  # lexical: passes
    assert ac.main() == 0
    rows = [json.loads(x) for x in (vault / ac.CARDS).read_text(encoding="utf-8").splitlines()]
    assert [x["q"] for x in rows if x.get("rel") == rel and not x.get("empty")] == ["怎么算封账"]


def test_llm_plan_order(monkeypatch, tmp_path):
    import llm

    for k in list(__import__("os").environ):
        if k.endswith(("_API_KEY", "_BASE_URL", "_MODEL")) or k == "KROUTER_LEARN_CLI":
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("KROUTER_KEYS_ENV", str(tmp_path / "none.env"))
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(llm, "detect_candidates", lambda: [])
    llm._CLI.clear()
    assert llm.plan(None) == []
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "y")
    # the writer's table and order (api_writer imports it from llm): every provider, flagship locked at call time
    assert [k for k, _ in llm.plan(None)] == ["api:DEEPSEEK_API_KEY", "api:OPENAI_API_KEY", "api:GEMINI_API_KEY"]
    monkeypatch.setenv("KROUTER_LEARN_MODEL", "pinned-model")
    assert {d for _, d in llm.plan(None)} == {"pinned-model"}
    monkeypatch.delenv("KROUTER_LEARN_MODEL")
    import api_writer
    assert api_writer.CHAT_SPECS is not None and api_writer.CHAT_SPECS == llm.CHAT_SPECS
    assert llm.lock_flagship(["claude-opus-4-20250514", "claude-opus-5-5", "claude-haiku-5-5"]) == "claude-opus-5-5"
    cli = tmp_path / "claude"
    cli.write_text("#!/bin/sh\necho ok\n")
    cli.chmod(0o755)
    monkeypatch.setenv("KROUTER_LEARN_CLI", str(cli))
    assert llm.plan(None)[0] == ("cli", str(cli))  # the host's explicit pick goes first
    monkeypatch.delenv("KROUTER_LEARN_CLI")
    for k in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(k)
    with pytest.raises(llm.NoModel):
        monkeypatch.setenv("PATH", str(tmp_path / "empty"))
        llm.complete("hi")


@pytest.mark.skipif(__import__("os").name == "nt", reason="the fake CLI is a shell script")
def test_llm_no_key_uses_the_writers_cli_detection(monkeypatch, tmp_path):
    """Only grok installed, no key: the nightly lane finds what the writer finds and gets text back."""
    import llm

    for k in list(__import__("os").environ):
        if k.endswith(("_API_KEY", "_BASE_URL", "_MODEL")) or k in ("KROUTER_LEARN_CLI", "KROUTER_WRITER"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("KROUTER_KEYS_ENV", str(tmp_path / "none.env"))
    grok = tmp_path / "bin" / "grok"
    grok.parent.mkdir()
    grok.write_text('#!/bin/sh\n[ "$1" = models ] && exit 0\n'
                    'while [ $# -gt 0 ]; do [ "$1" = --prompt-file ] && { printf "echo:"; cat "$2"; exit 0; }; shift; done\n'
                    'exit 2\n')
    grok.chmod(0o755)
    monkeypatch.setattr(llm, "detect_candidates", lambda: [tmp_path / "missing" / "claude", grok])
    llm._CLI.clear()
    assert llm.plan(None) == [("cli", str(grok))]
    assert llm.complete("你好") == "echo:你好"
    llm._CLI.clear()


def test_frontmatter_edit_keeps_a_card_but_a_body_edit_stales_it(vault):
    """A card is about the page's content: `status` / `verified_at` / `nightly_at` edits must not stale it."""
    rel = "02 经验与方法/搜索与知识库/封账先看时间日志文件.md"
    path = vault / rel
    _card(vault, rel, "封账以后燃料配比怎么算", "时间日志存在就算封账。", sha=r.body_hash(path.read_bytes()))
    assert rel in [h["rel"] for h in r.recall(vault, "燃料配比", limit=5, gate=False)["hits"]]
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("status: active", "status: active\nverified_at: 2026-10-11\nnightly_at: x", 1),
                    encoding="utf-8")
    assert rel in [h["rel"] for h in r.recall(vault, "燃料配比", limit=5, gate=False)["hits"]]  # still live
    path.write_text(path.read_text(encoding="utf-8") + "\n正文改了一句。\n", encoding="utf-8")
    assert rel not in [h["rel"] for h in r.recall(vault, "燃料配比", limit=5, gate=False)["hits"]]  # body changed


def test_cards_written_against_the_whole_page_stay_valid(vault):
    """Cards from before 0.11.1 carry the whole-page hash; they stay valid until the page changes."""
    rel = "02 经验与方法/搜索与知识库/封账先看时间日志文件.md"
    _card(vault, rel, "封账以后燃料配比怎么算", "时间日志存在就算封账。")  # whole-page hash
    assert rel in [h["rel"] for h in r.recall(vault, "燃料配比", limit=5, gate=False)["hits"]]


def test_health_page_gets_no_cards(vault):
    import answer_cards as ac

    health = "90 系统文件/自动化/日更健康.md"
    write(vault, health, "---\ntitle: 日更健康\nstatus: active\n---\n\n# 日更健康\n\n每天 09:10 跑。\n")
    assert health not in ac.targets(vault)


def test_cli_env_carries_the_long_lived_token(monkeypatch, tmp_path):
    """`claude setup-token` in the keys file reaches every CLI call; the keychain login is no longer needed."""
    import llm

    keys = tmp_path / "keys.env"
    keys.write_text("DEEPSEEK_API_KEY=sk-x\nCLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-test\n", encoding="utf-8")
    monkeypatch.setenv("KROUTER_KEYS_ENV", str(keys))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    env = llm.cli_env()
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat01-test"
    assert "DEEPSEEK_API_KEY" not in env or env["DEEPSEEK_API_KEY"] != "sk-x"  # only the CLI token is added
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "from-env")
    assert llm.cli_env()["CLAUDE_CODE_OAUTH_TOKEN"] == "from-env"  # an explicit env value wins


@pytest.mark.skipif(__import__("os").name == "nt", reason="flock")
def test_one_cli_at_a_time(monkeypatch, tmp_path):
    import threading
    import time

    import llm

    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path))
    inside, peak = [0], [0]

    def work():
        with llm._CliLock():
            inside[0] += 1
            peak[0] = max(peak[0], inside[0])
            time.sleep(0.05)
            inside[0] -= 1

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak[0] == 1


def test_a_question_that_names_something_the_vault_never_mentions_is_refused(tmp_path, monkeypatch):
    """`Porsche` is in no page: however many other words match, the vault cannot say when that project started.
    Sentence-initial capitals, `OK`, and month or day names are not names."""
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    v = tmp_path / "vault"
    write(v, "Projects/Models.md", "---\ntitle: Models\nstatus: active\n---\n\n"
          "I started the Ferrari model project in March and finished the Ferrari model in May.\n")
    for i in range(6):
        write(v, f"Journal/day{i}.md", f"---\ntitle: day {i}\n---\n\nWorked on the garden and a model kit, day {i}.\n")
    assert r.recall(v, "When did I start the Ferrari model project?")["confidence"] != "none"
    assert r.recall(v, "When did I start the Porsche model project?")["confidence"] == "none"
    assert r.absent_names("Is it OK to start the model project?", {}) == []
    assert r.absent_names("Which project did I start in December?", {}) == []
    assert r.absent_names("Porsche project start?", {}) == []  # 句首


def test_a_question_that_matches_one_word_is_answered_as_low_and_says_so(tmp_path, monkeypatch, capsys):
    """A 20-page vault: `小红书的笔记几点发？` meets only 笔记 on a page about sealing days. Recall may still show the
    page, but at low confidence, with a note, and without a generated answer."""
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    v = tmp_path / "vault"
    write(v, "02 经验与方法/自动化/按日志文件判断封账.md",
          "---\ntitle: 按日志文件判断封账\nstatus: active\n---\n\n已经有真笔记的，只补缺的部分。笔记存在就算封账。\n")
    write(v, "02 经验与方法/短视频/封面标题规则.md",
          "---\ntitle: 封面标题规则\nstatus: active\n---\n\n封面标题直接给结论，最多 10 个字，不用问句。\n")
    for i in range(18):
        write(v, f"05 时间日志/2026-10/{i:02d}｜日常.md", f"---\ntitle: {i:02d}｜日常\n---\n\n今天剪了第 {i} 条视频的笔记。\n")
    res = r.recall(v, "小红书的笔记几点发？")
    assert res["confidence"] in ("none", "low")
    if res["confidence"] == "low":
        assert res["partial"] and not any(h.get("answer") for h in res["hits"])
    full = r.recall(v, "封面标题现在怎么写？")
    assert full["confidence"] in ("high", "medium") and not full["partial"]
    assert full["hits"][0]["rel"].endswith("封面标题规则.md")
    assert "recall_note" in r.PARTIAL_NOTE
