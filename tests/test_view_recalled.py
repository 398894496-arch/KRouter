"""`krouter view` and `krouter why` read the data the subconscious and skills write: the prompt hook's deliveries
(`recalled.jsonl`), the skills folder and its use counts. Missing data shows as empty, never as an error."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "sdk"))
SEALED = "02 经验与方法/自动化/按日志文件判断封账.md"


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    for k in ("KROUTER_RECALL_PROMPT", "KROUTER_RECALL_INDEX", "KROUTER_SKILLS"):
        monkeypatch.delenv(k, raising=False)
    v = tmp_path / "vault"
    shutil.copytree(REPO / "template-zh", v)
    from test_session_start import own_row

    own_row(v)  # a vault in use: the session-start index lists its topics
    return v


def _store(vault):
    from krouter.viewdata import Store

    return Store(vault)


def test_no_recalled_file_is_an_empty_list(vault):
    out = _store(vault).recalled()
    assert out["rows"] == [] and out["on"] is True


def test_recalled_rows_newest_first_and_bad_lines_skipped(vault, tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    rows = [{"ts": "2026-11-09T08:00:00Z", "agent": "codex", "session": "11112222", "route": "trigger", "word": "封账",
             "sentence": "封账那个", "page": SEALED},
            {"ts": "2026-11-10T12:45:07Z", "agent": "claude", "session": "abcd1234", "route": "alias", "word": "昨天封账了吗",
             "sentence": "昨天封账了吗", "page": SEALED, "notes": [["older", "x.md"]]}]
    (state / "recalled.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\nnot json\n{}\n",
                                          encoding="utf-8")
    out = _store(vault).recalled()
    assert out["total"] == 2 and [r["agent"] for r in out["rows"]] == ["claude", "codex"]
    assert out["rows"][0]["page"] == SEALED and out["rows"][0]["notes"] == [["older", "x.md"]]


def test_skills_with_counts_and_none_when_there_is_no_folder(vault):
    import skills

    store = _store(vault)
    assert store.experience()["skills"] == [] and store.experience()["drafts"] == []
    folder = vault / skills.FOLDER
    folder.mkdir(parents=True)
    for sid, status in (("S01", "active"), ("S02", "draft")):
        (folder / f"技能｜{sid}.md").write_text(
            f"---\ntitle: \"技能｜{sid}\"\ntype: {skills.TYPE}\nstatus: {status}\nskill_id: {sid}\nuse_when: \"改了不生效时\"\n"
            "cards: C01\ndrafted: 2026-10-01\n---\n\n# 技能\n\n## 做法\n\n1. 看读的是哪一份\n\n## 出处\n\n- 测试\n", encoding="utf-8")
    x = _store(vault).experience()
    assert [s["id"] for s in x["skills"]] == ["S01"] and [s["id"] for s in x["drafts"]] == ["S02"]
    assert x["skills"][0]["offered"] == 0 and x["skills"][0]["use_when"] == "改了不生效时"


def test_why_says_whether_the_hook_brings_it_or_the_host_reads_the_index(vault, tmp_path):
    from krouter import why

    brought = why.explain(vault, "昨天封账了吗，我得先确认日志文件")
    assert [h["rel"] for h in brought["mention"]["hook"]] == [SEALED]
    text = why.render(brought)
    assert "提问钩子会自己把 " + SEALED in text and "这句话钩子会先递过去" in text
    quiet = why.explain(vault, "昨天那个封账我还没看")
    assert quiet["mention"]["hook"] == [] and quiet["mention"]["pages"][0]["indexed"]
    assert "agent 看了索引自己取的" in why.render(quiet)
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    (state / "recalled.jsonl").write_text(json.dumps({"ts": "2026-11-10T12:45:07Z", "agent": "claude", "session": "a",
                                                      "route": "alias", "word": "封账", "sentence": "", "page": SEALED},
                                                     ensure_ascii=False) + "\n", encoding="utf-8")
    assert "钩子以前递过它：2026-11-10T12:45:07Z" in why.render(why.explain(vault, "昨天那个封账我还没看"))


def test_why_with_the_hook_and_index_off(vault, monkeypatch):
    from krouter import why

    monkeypatch.setenv("KROUTER_RECALL_PROMPT", "0")
    monkeypatch.setenv("KROUTER_RECALL_INDEX", "0")
    text = why.render(why.explain(vault, "昨天封账了吗"))
    assert "KROUTER_RECALL_PROMPT=0" in text and "KROUTER_RECALL_INDEX=0" in text
