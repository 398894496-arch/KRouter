"""Skills grown from experience cards (`skills.py`): drafted nightly through the host lane (quietly skipped with none),
offered as drafts apart from the facts, promoted or withdrawn on their use records, each change one commit that one
command takes back; the host fetches the full text (`krouter_skill`); export only when asked. Also: an English vault's
session pages carry English turn labels, and both kinds are parsed."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter/scripts"
BENCH = REPO / "bench/transfer"
sys.path.insert(0, str(SCRIPTS))
import experience  # noqa: E402
import llm  # noqa: E402
import skills  # noqa: E402


def _git(vault: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(vault), *args], capture_output=True, text=True, check=True).stdout


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    v = tmp_path / "vault"
    shutil.copytree(REPO / "template-zh", v)
    folder = v / experience.FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    for card in sorted((BENCH / "cards").glob("*.md")):
        shutil.copy(card, folder / card.name)
    _git(v, "init", "-q")
    _git(v, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    _git(v, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    monkeypatch.setenv("KROUTER_SKILLS", "1")
    monkeypatch.delenv("KROUTER_EXPERIENCE", raising=False)
    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("KROUTER_NO_QUERY_LOG", "1")
    return v


def _uses(vault: Path, rows: list[tuple[str, str]]) -> None:
    path = vault / experience.USES
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for i, (cid, kind) in enumerate(rows):
            fh.write(json.dumps({"at": f"2026-11-0{1 + i % 8}T10:00:00", "card": cid, "kind": kind,
                                 "session": f"claude:s{i:07d}", "turn": f"t{i}"}, ensure_ascii=False) + "\n")


C02_DRAFT = {"cards": ["C02"], "name": "慢活的结果存起来复用", "use_when": "当同一件耗时的事每次都要从头做一遍时",
             "steps": ["先确认每次重做的这一步输入有没有变", "把这一步的结果存起来", "输入没变就直接复用存下的结果"]}


def _model(monkeypatch, reply, calls=None):
    def fake(prompt, vault=None):
        if calls is not None:
            calls.append(prompt)
        return reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
    monkeypatch.setattr(llm, "complete", fake)


def test_a_card_borne_out_repeatedly_is_drafted_with_its_sources_as_one_commit(vault, monkeypatch):
    _uses(vault, [("C02", "adopted"), ("C02", "again"), ("C02", "adopted")])
    calls: list[str] = []
    _model(monkeypatch, [C02_DRAFT], calls)
    row = skills.nightly(vault)
    assert row["skills"] == "done" and row["drafting"] == "ran" and len(calls) == 1
    assert "〔C02〕" in calls[0] and "被反复证实的卡（可以单独起草）：C02" in calls[0]
    d = row["drafted"][0]
    assert d["cards"] == ["C02"] and d["evidence"]["C02"] == {"adopted": 2, "again": 1} and d["commit"]
    page = (vault / d["rel"]).read_text(encoding="utf-8")
    assert "status: draft" in page and "**什么时候用**：当同一件耗时的事每次都要从头做一遍时" in page
    assert "1. 先确认" in page and "经验卡〔C02〕[[02 经验与方法/经验卡/C02｜" in page and "claude:s0000000" in page
    log = _git(vault, "log", "--format=%s%n%b", "-3")
    assert "技能草稿：「慢活的结果存起来复用」（一张卡被反复证实；〔C02〕采纳 2、又遇到 1）" in log and "[krouter-run " in log
    # 摘要里：和经验分开，标明是草稿
    text = skills.digest(vault)
    assert text.startswith("KRouter 技能") and "技能草稿（还没转正" in text and f"慢活的结果存起来复用：当同一件耗时的事每次都要从头做一遍时〔{d['id']}〕" in text
    full = skills.show(vault, d["id"])
    assert full.startswith("（这是草稿") and "## 做法" in full and f"skill_id: {d['id']}" in full
    # 同一批卡，第二晚不再调模型
    again = skills.nightly(vault)
    assert again["drafting"] in ("unchanged since the last attempt", "nothing to draft") and len(calls) == 1


def test_no_draft_without_evidence_or_a_second_card_and_no_call_for_nothing(vault, monkeypatch):
    calls: list[str] = []
    _model(monkeypatch, [C02_DRAFT], calls)
    row = skills.nightly(vault)  # 14 张卡，没有一张被反复证实：模型可以提合并，单张的草稿被代码挡下
    assert row["drafting"] == "ran" and row["drafted"] == [] and len(calls) == 1
    assert any("not been borne out" in why for why in row["dropped"])
    for card in (vault / experience.FOLDER).glob("*.md"):
        if not card.name.startswith("C02"):
            card.unlink()
    assert skills.draft_step(vault, force=True) == {"drafting": "nothing to draft", "drafted": [], "calls": 0}


@pytest.mark.parametrize("bad, why", [
    ({**C02_DRAFT, "cards": ["C99", "C02"]}, "unknown card"),
    ({**C02_DRAFT, "steps": ["等 12 分钟以上就缓存", "把结果存起来", "输入没变就复用"]}, None),
    ({**C02_DRAFT, "steps": ["等 45 分钟以上就缓存", "把结果存起来", "输入没变就复用"]}, "numbers not in the cards"),
    ({**C02_DRAFT, "steps": ["一步"]}, "steps"),
    ({**C02_DRAFT, "steps": ["喝口水", "出去走走"]}, "share no words"),
    ({**C02_DRAFT, "name": ""}, "name"),
])
def test_drafts_are_checked_by_the_code(vault, bad, why):
    cards = {c["id"]: {**c, "path": vault / c["rel"]} for c in experience.load_cards(vault)}
    d, reason = skills.check(bad, cards, {"C02"}, set())
    if why is None:
        assert d and reason == ""  # 12 在卡里有
    else:
        assert d is None and why in reason
    d, reason = skills.check(C02_DRAFT, cards, {"C02"}, {"C02"})
    assert d is None and "already in a skill" in reason


def test_without_a_model_lane_drafting_is_skipped_quietly_and_reported(vault, monkeypatch):
    def none(prompt, vault=None):
        raise llm.NoModel("no lane")
    monkeypatch.setattr(llm, "complete", none)
    _uses(vault, [("C02", "adopted")] * 3)
    row = skills.nightly(vault)
    assert row["drafting"].startswith("skipped") and row["drafted"] == []
    assert not (vault / skills.FOLDER).exists()
    lines = "\n".join(skills.report_lines(row))
    assert "起草：跳过，没有可用的模型通道" in lines
    import nightly

    assert nightly.classify(0, json.dumps(row, ensure_ascii=False)) == ("ok", "起草跳过：没有模型通道")


def _draft(vault, monkeypatch, day: str = "") -> dict:
    _uses(vault, [("C02", "adopted")] * 3)
    cards = experience.load_cards(vault)
    for c in cards:
        c["path"] = vault / c["rel"]
    d, _ = skills.check(C02_DRAFT, {c["id"]: c for c in cards}, {"C02"}, set())
    return skills.write_draft(vault, d, cards, experience.usage(vault), day=day)


def test_adopted_enough_times_a_draft_is_promoted_in_its_own_commit_and_one_command_reverts_it(vault, monkeypatch):
    d = _draft(vault, monkeypatch)
    _uses(vault, [(d["id"], "offered"), (d["id"], "adopted")])
    assert skills.lifecycle(vault)["promoted"] == []  # 一次还不够
    _uses(vault, [(d["id"], "offered"), (d["id"], "adopted")])
    res = skills.lifecycle(vault)
    p = res["promoted"][0]
    assert p["adopted"] == skills.PROMOTE_ADOPTED and p["commit"]
    page = vault / d["rel"]
    assert "status: active" in page.read_text(encoding="utf-8")
    head = _git(vault, "log", "--format=%B", "-2")
    assert f"技能转正：「慢活的结果存起来复用」（被采纳 2 次，门槛 {skills.PROMOTE_ADOPTED}；提出 2 次）" in head
    ledger = (vault / "90 系统文件/自动化/记忆变更记录.md").read_text(encoding="utf-8")
    rid = next(ln.split("undo ")[-1].rstrip("`") for ln in ledger.splitlines() if "-promote-" in ln and "undo" in ln)
    text = skills.digest(vault)
    assert "技能草稿" not in text and f"〔{d['id']}〕" in text  # 转正后不再在草稿里
    out = subprocess.run([sys.executable, str(SCRIPTS / "skills.py"), "--vault", str(vault), "undo", rid],
                         capture_output=True, text=True, env={**os.environ})
    assert out.returncode == 0, out.stderr
    assert "status: draft" in page.read_text(encoding="utf-8") and "promoted:" not in page.read_text(encoding="utf-8")
    assert "撤销 run " + rid in (vault / "90 系统文件/自动化/记忆变更记录.md").read_text(encoding="utf-8")


def test_a_draft_nobody_adopts_is_withdrawn_and_sinks_first(vault, monkeypatch):
    old = (date.today() - timedelta(days=skills.WITHDRAW_DAYS)).isoformat()
    d = _draft(vault, monkeypatch, day=old)
    other = {**C02_DRAFT, "cards": ["C01", "C03"], "name": "改了不生效先查读的是哪份",
             "use_when": "当改了东西却没有效果时", "steps": ["先查实际读的是哪一份", "确认改的就是那一份"]}
    cards = experience.load_cards(vault)
    for c in cards:
        c["path"] = vault / c["rel"]
    d2 = skills.write_draft(vault, skills.check(other, {c["id"]: c for c in cards}, set(), set())[0], cards, {})
    _uses(vault, [(d2["id"], "offered")] * skills.SINK_OFFERED)
    order = [s["id"] for s in skills.rank(skills.load(vault), experience.usage(vault))]
    assert order[-1] == d2["id"]  # 提了几次没人采纳：沉底
    res = skills.lifecycle(vault)
    assert [w["id"] for w in res["withdrawn"]] == [d["id"]] and "一次没被采纳" in res["withdrawn"][0]["why"]
    assert "status: retired" in (vault / d["rel"]).read_text(encoding="utf-8")
    assert d["id"] not in skills.digest(vault) and skills.show(vault, d["id"]).startswith("（已撤回")
    assert "技能草稿撤回：「慢活的结果存起来复用」" in _git(vault, "log", "--format=%s", "-2")
    _uses(vault, [(d2["id"], "offered")] * (skills.WITHDRAW_OFFERED - skills.SINK_OFFERED))
    assert [w["id"] for w in skills.lifecycle(vault)["withdrawn"]] == [d2["id"]]


def test_use_records_count_skill_ids_like_card_ids(vault, monkeypatch):
    d = _draft(vault, monkeypatch)
    turns = [{"ts": "2026-11-09T10:00:00", "ask": "每次跑这个都要等很久",
              "answer": f"按技能〈慢活的结果存起来复用〉来〔{d['id']}〕：先看输入有没有变。"},
             {"ts": "2026-11-09T10:05:00", "ask": "按你说的做了，管用", "answer": "好。"}]
    assert experience.record_uses(vault, "claude:abc", turns) == 2
    u = experience.usage(vault)[d["id"]]
    assert u["offered"] == 1 and u["adopted"] == 1
    monkeypatch.setenv("KROUTER_SKILLS", "0")
    assert skills.ids(vault) == set() and skills.digest(vault) == ""


def _mcp(env: dict, *msgs: dict) -> list[dict]:
    data = "\n".join(json.dumps(m, ensure_ascii=False) for m in msgs) + "\n"
    res = subprocess.run([sys.executable, str(SCRIPTS / "mcp_server.py")], input=data, env=env, capture_output=True,
                         text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    return [json.loads(line) for line in res.stdout.splitlines() if line.strip()]


def test_mcp_lists_skills_and_returns_the_full_text(vault, monkeypatch, tmp_path):
    d = _draft(vault, monkeypatch)
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_CACHE_DIR": str(tmp_path / "c")}
    out = _mcp(env, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
               {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
               {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "krouter_skill", "arguments": {"id": d["id"]}}},
               {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "krouter_skill", "arguments": {"id": "S0000"}}})
    assert "krouter_skill" in out[0]["result"]["instructions"]
    tool = next(t for t in out[1]["result"]["tools"] if t["name"] == "krouter_skill")
    assert f"{d['id']} = 慢活的结果存起来复用 (draft): 当同一件耗时的事每次都要从头做一遍时" in tool["description"]
    assert out[2]["result"]["isError"] is False and "## 做法" in out[2]["result"]["content"][0]["text"]
    assert out[3]["result"]["isError"] is True and d["id"] in out[3]["result"]["content"][0]["text"]
    assert experience.usage(vault)[d["id"]].get("offered", 0) == 0  # 取全文记为 fetched，不算提出或采纳
    assert '"kind": "fetched"' in (vault / experience.USES).read_text(encoding="utf-8")
    off = _mcp({**env, "KROUTER_SKILLS": "0"}, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert "krouter_skill" not in [t["name"] for t in off[0]["result"]["tools"]]


def test_session_start_lists_skills_after_the_experience_digest(vault, monkeypatch, tmp_path):
    d = _draft(vault, monkeypatch)
    e = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_STATE_DIR": str(tmp_path / "no-consent")}
    res = subprocess.run([sys.executable, str(SCRIPTS / "session_hook.py"), "start", "--agent", "claude"],
                         input=json.dumps({"cwd": str(tmp_path), "session_id": "s1"}), env=e, capture_output=True,
                         text=True, timeout=60)
    ctx = json.loads(res.stdout)["hookSpecificOutput"]["additionalContext"]
    assert ctx.startswith("KRouter 经验摘要") and "\n\nKRouter 技能" in ctx and f"〔{d['id']}〕" in ctx
    assert "## 做法" not in ctx  # 只列名字和什么时候用，全文要取


def test_skills_never_come_back_as_facts(vault, monkeypatch, tmp_path):
    _draft(vault, monkeypatch)
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_CACHE_DIR": str(tmp_path / "c")}
    res = subprocess.run(["sh", str(SCRIPTS / "route_knowledge.sh"), "search", "慢活的结果存起来复用"], env=env,
                         capture_output=True, text=True, timeout=120)
    assert "02 经验与方法/技能/" not in res.stdout.replace("[[02 经验与方法/技能/", "")  # 变更记录里的链接不算


def test_export_only_when_asked_and_only_its_own_files(vault, monkeypatch, tmp_path):
    d = _draft(vault, monkeypatch)
    dest = tmp_path / "skills-out"
    (dest / "mine").mkdir(parents=True)
    (dest / "mine" / "SKILL.md").write_text("someone else's", encoding="utf-8")
    assert skills.export(vault, "agent-skills", dest)["written"] == []  # 草稿默认不导出
    res = skills.export(vault, "agent-skills", dest, drafts=True)
    rel = res["written"][0]
    text = (dest / rel).read_text(encoding="utf-8")
    assert rel == f"krouter-skill-{d['id'].lower()}/SKILL.md" and text.startswith(f"---\nname: krouter-skill-{d['id'].lower()}\n")
    assert "description: \"当同一件耗时的事每次都要从头做一遍时（KRouter 技能" in text and "## 做法" in text
    cur = skills.export(vault, "cursor-rule", tmp_path / "rules", drafts=True)
    assert (tmp_path / "rules" / cur["written"][0]).read_text(encoding="utf-8").count("alwaysApply: false") == 1
    page = vault / d["rel"]
    page.write_text(page.read_text(encoding="utf-8").replace("status: draft", "status: retired"), encoding="utf-8")
    again = skills.export(vault, "agent-skills", dest, drafts=True)
    assert again["removed"] == [rel] and not (dest / rel).exists()
    assert (dest / "mine" / "SKILL.md").read_text(encoding="utf-8") == "someone else's"


def test_nightly_runs_the_step_and_reports_counts(vault, monkeypatch, tmp_path):
    import nightly

    row = {"skills": "done", "drafting": "ran", "calls": 1,
           "drafted": [{"id": "S1", "name": "n", "rel": "02 经验与方法/技能/技能｜n.md", "cards": ["C02"],
                        "evidence": {"C02": {"adopted": 2, "again": 1}}}],
           "promoted": [{"id": "S2", "name": "m", "adopted": 2, "offered": 3}],
           "withdrawn": [{"id": "S3", "name": "k", "why": "起草 45 天，一次没被采纳（门槛 45 天）"}]}
    lines = "\n".join(nightly.skill_lines([{"step": "skills", "skills": row}]))
    assert "新起草〔S1〕[[02 经验与方法/技能/技能｜n]]：依据 〔C02〕采纳 2、又遇到 1" in lines
    assert "转正〔S2〕「m」：被采纳 2 次" in lines and "撤回〔S3〕「k」：起草 45 天" in lines
    assert "skills" in nightly.STEPS and "skills" in nightly.MODEL_STEPS
    env = {**os.environ, "KROUTER_HOST_CLI": "0", "KROUTER_KEYS_ENV": str(tmp_path / "none.env")}
    for k in list(env):
        if k.endswith("_API_KEY"):
            env.pop(k)
    res = subprocess.run([sys.executable, str(SCRIPTS / "nightly.py"), "--vault", str(vault), "--steps", "skills"],
                         env=env, capture_output=True, text=True, timeout=120)
    out = json.loads(res.stdout.splitlines()[-1])
    assert out["steps"][0]["step"] == "skills" and out["steps"][0]["state"] == "ok"
    assert "技能" in (vault / "90 系统文件/自动化/夜间维护.md").read_text(encoding="utf-8")


# ---------- 英文库的会话页：英文标签，两种都能解析 ----------

def _entry() -> dict:
    return {"day": date(2026, 11, 9), "agent": "claude", "id": "abcdef1234", "project": "shop", "title": "Release flow",
            "turns": [{"ts": "2026-11-09T10:05:00+00:00", "ask": "How do we release?", "answer": "Tag from main only."},
                      {"ts": "2026-11-09T10:07:00+00:00", "ask": "And hotfixes?", "answer": "Same rule."}]}


def test_an_english_vault_writes_english_turn_labels_and_both_kinds_parse(monkeypatch):
    import import_sessions as imp

    monkeypatch.setattr(imp, "PAGE_LANG", "en")
    page = imp.render(_entry())
    assert "## Excerpt (2026-11-09 · shop · claude · 2 turns)" in page and "**问**" not in page and "**答**" not in page
    assert "- **Q** (" in page and "  **A**: Tag from main only." in page
    body = imp.excerpt_of(page)
    assert len(imp.TURN_MARK.findall(body)) == 2 and imp.from_turn(body, 1).count("**Q**") == 1
    monkeypatch.setattr(imp, "PAGE_LANG", "zh")
    zh = imp.render(_entry())
    assert "## 摘录（2026-11-09 · shop · claude · 2 轮）" in zh and "- **问**（" in zh and "  **答**：" in zh
    assert len(imp.TURN_MARK.findall(imp.excerpt_of(zh))) == 2
    # 已有的英文库：页里还是中文标签，照样按轮切
    legacy = zh.replace("## 摘录", "## 摘录", 1)
    assert imp.segments(imp.excerpt_of(legacy))[0].count("**问**") == 2
    sys.path.insert(0, str(REPO / "bench/real_questions"))
    import capture_bench

    assert [t for t, _ in capture_bench.turns_of(body)] == [t for t, _ in capture_bench.turns_of(imp.excerpt_of(zh))]
    assert len(capture_bench.turns_of(body)) == 2


def test_an_english_vault_keeps_skills_in_an_english_folder_and_digest(tmp_path, monkeypatch):
    monkeypatch.setenv("KROUTER_SKILLS", "1")
    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path / "state"))
    v = tmp_path / "vault"
    shutil.copytree(REPO / "template", v)
    (v / "krouter-zones.psv").write_text("@lang|en\n02 经验与方法|02 Methods\n", encoding="utf-8")  # 没有 Skills 那一行的旧库
    folder = v / "02 Methods/经验卡"
    folder.mkdir(parents=True)
    for card in sorted((BENCH / "cards_en").glob("C02*.md")):
        shutil.copy(card, folder / card.name)
    _uses(v, [("C02", "adopted")] * 3)
    _model(monkeypatch, [{"cards": ["C02"], "name": "Keep the result of slow repeated work",
                          "use_when": "When the same slow step is redone from scratch every time",
                          "steps": ["Check whether the step's input changed", "Store the step's result",
                                    "Reuse the stored result while the input is unchanged"]}])
    row = skills.nightly(v)
    assert row["drafted"] and row["drafted"][0]["rel"].startswith("02 Methods/Skills/Skill - ")
    text = skills.digest(v)
    assert text.startswith("KRouter skills") and "Skill drafts" in text and "\"02 Methods/Skills\"" in text
    assert not any("一" <= ch <= "鿿" for ch in text)
    assert "## Steps" in skills.show(v, row["drafted"][0]["id"])


SETS = {"24": ("c0dd8f8e4008b02a54e00a22d5b754c5fa3a2da22079e49ceeb984611919ef10",
               "f8d39268b1a968bf6676009bfdc7068335bc6d335c32ef92371f216b8bc20430"),
        "25": ("6f74995dc70125a35c16a94296e188a525e55603a8b7795b6feb5e39ebcfd710",
               "7625411fdd80dd4b58bcd6f326160ebf0f4802a3449b2d3cc29686fab6e79406"),
        "26": ("8a10dcbfde311e2308e66bd6bc419bd83680e8e2d6bb576104038ea429c20a3d",
               "ca1edc8c5516c444210186ff76c854ee69b22d04afddca52b04f9cf12f3fc49b")}


def test_sets_24_to_26_are_frozen():
    import gzip
    import hashlib

    folder = REPO / "bench/skills"
    for n, (dev, held) in SETS.items():
        assert hashlib.sha256((folder / f"set{n}_dev.jsonl").read_bytes()).hexdigest() == dev
        with gzip.open(folder / f"set{n}_heldout.jsonl.gz", "rb") as fh:
            assert hashlib.sha256(fh.read()).hexdigest() == held
    skills_file = (folder / "set25_skills.json").read_bytes()
    assert hashlib.sha256(skills_file).hexdigest() == "a093d11d59434e7c97a0a1291539b680c818ab9dfb51da3ad7e9bc6be47905d2"


def test_the_bench_scores_drafts_through_the_codes_own_checks(tmp_path):
    sys.path.insert(0, str(REPO / "bench/skills"))
    import run as bench

    s = {"id": "x", "kind": "group", "lang": "zh", "expect": [["a", "b"]], "cards": [
        {"key": "a", "situation": "网页加载慢", "action": "把图片缓存起来", "result": "快了", "lesson": "同一件慢事每次重做时，把结果存起来复用", "adopted": 0, "again": 0},
        {"key": "b", "situation": "每天手抄报表", "action": "把上次结果存起来复用", "result": "省了时间", "lesson": "反复做同样的慢活时，存下结果", "adopted": 1, "again": 0},
        {"key": "c", "situation": "汤太咸", "action": "加水", "result": "好了", "lesson": "味道过头时，加一点中和的东西", "adopted": 0, "again": 0}]}
    ids = bench.card_ids(s)
    with tempfile.TemporaryDirectory() as tmp:
        vault = bench.build24(Path(tmp), s)
        pool, singles, used, covered = bench.state24(vault)
        reply = json.dumps([{"cards": [ids["a"], ids["b"]], "name": "慢活结果存起来", "use_when": "当同样的慢活反复做时",
                             "steps": ["把结果存起来", "下次直接复用"]}], ensure_ascii=False)
        drafts, _ = skills.parse(reply, {c["id"]: c for c in pool}, {c["id"] for c in singles}, covered)
    assert drafts and set(drafts[0]["cards"]) == {ids["a"], ids["b"]} and not singles
    assert bench.called('CALL krouter_skill {"id": "Sca77"}') == "Sca77" and bench.called("好的，我们先看看") == ""
