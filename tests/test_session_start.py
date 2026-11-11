"""What a session starts with (`session_hook.start_text`): this project's decisions, the experience digest, the skills
list, the standing index and one tools line, in that order, under one length cap, each tool explained once."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def hook(monkeypatch):
    import session_hook

    for k in ("KROUTER_RECALL_INDEX", "KROUTER_EXPERIENCE", "KROUTER_SKILLS", "KROUTER_INJECT"):
        monkeypatch.delenv(k, raising=False)
    return session_hook


def _vault(tmp_path: Path, cards: int = 14, skills: int = 3, en_cards: bool = False) -> Path:
    """The Chinese template with experience cards (set 13's), a few skills and the template's alias table."""
    import experience
    import skills as sk

    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template-zh", vault)
    folder = vault / experience.FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    src = sorted((REPO / ("bench/transfer/cards_en" if en_cards else "bench/transfer/cards")).glob("*.md"))
    src += sorted((REPO / "bench/transfer/distractors").glob("*.md"))
    for card in src[:cards]:
        shutil.copy(card, folder / card.name)
    folder = vault / sk.FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(skills):
        (folder / f"技能｜检查第 {i} 步.md").write_text(
            f"---\ntitle: \"技能｜检查第 {i} 步\"\ntype: {sk.TYPE}\nstatus: active\nskill_id: S{i:02d}\n"
            f"use_when: \"改完配置却不生效、需要逐项核对第 {i} 类设置时\"\ncards: C01\ndrafted: 2026-10-01\n---\n\n"
            f"# 技能｜检查第 {i} 步\n\n**什么时候用**：改完配置却不生效时\n\n## 做法\n\n1. 先看读的是哪一份\n\n## 出处\n\n- 测试\n",
            encoding="utf-8")
    own_row(vault)
    return vault


def own_row(vault: Path) -> None:
    """One alias row of the user's own: a vault in use, not one that still holds only the template's examples."""
    for rel in ("90 系统文件/canonical_sources.psv", "90 System/canonical_sources.psv"):
        table = vault / rel
        if table.is_file():
            line = next(ln for ln in table.read_text(encoding="utf-8").splitlines() if ln.startswith("Q01|"))
            with table.open("a", encoding="utf-8") as fh:
                fh.write("Q98|my own entrance|" + line.split("|", 2)[2] + "\n")
            return
    raise AssertionError("no alias table")


def _decisions(monkeypatch, hook, text: str) -> None:
    monkeypatch.setattr(hook, "decisions_text", lambda payload, vault, mode, tail=True: text)


def test_order_and_each_tool_said_once(hook, tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    _decisions(monkeypatch, hook, "KRouter：这个仓库（demo）最近 30 天在你的库里记下的决定：\n- 数据库用 SQLite 〔05 时间日志/x.md〕")
    text = hook.start_text({}, vault)
    parts = text.split(hook.SEP)
    assert parts[0].startswith("KRouter：这个仓库")
    assert parts[1].startswith(("经验卡", "KRouter")) and "〔C" in parts[1]  # the experience digest
    assert "krouter_skill" in parts[2]  # the skills list
    assert parts[3].startswith("KRouter 下意识索引")
    assert parts[-1].startswith("KRouter 的两个写入工具") and len(parts) == 5
    for tool in ("krouter_ask", "krouter_correct", "krouter_learn", "krouter_skill"):
        assert text.count(tool) == 1, (tool, text.count(tool))  # how to call each one: said once
    assert text.count("recall: none") == 1
    assert "其他问题先用 krouter_ask" not in text  # the decisions' old closing line is not repeated
    assert len(text) <= hook.START_MAX


def test_without_the_index_the_tools_line_names_krouter_ask(hook, tmp_path, monkeypatch):
    monkeypatch.setenv("KROUTER_RECALL_INDEX", "0")
    vault = _vault(tmp_path)
    text = hook.start_text({}, vault)
    assert "下意识索引" not in text
    assert text.split(hook.SEP)[-1].startswith("KRouter 工具（MCP 服务 krouter")
    assert text.count("krouter_ask") == 1 and text.count("recall: none") == 1


def test_budgets_hold_and_the_index_gives_way_first(hook, tmp_path, monkeypatch):
    vault = _vault(tmp_path, cards=54, skills=20, en_cards=True)
    full = hook.start_text({}, vault)
    index_alone = hook.index_text(vault, hook.START_MAX)
    _decisions(monkeypatch, hook, "D" * hook.MAX_CHARS)
    text = hook.start_text({}, vault)
    assert len(text) <= hook.START_MAX
    parts = text.split(hook.SEP)
    exp, skl = hook.experience_text(vault), hook.skills_text(vault)
    assert len(exp) <= hook.EXPERIENCE_MAX and len(skl) <= hook.SKILLS_MAX
    assert parts[0] == "D" * hook.MAX_CHARS and parts[1] == exp and parts[2] == skl  # higher parts are never cut for the index
    if len(index_alone) > len(parts[3]):  # the index took what was left
        assert len(full) > len(text) - hook.MAX_CHARS


def test_each_part_stays_under_its_own_cap(hook, tmp_path, monkeypatch):
    vault = _vault(tmp_path, cards=54, skills=20, en_cards=True)
    monkeypatch.setattr(hook, "EXPERIENCE_MAX", 600)
    monkeypatch.setattr(hook, "SKILLS_MAX", 300)
    exp = hook.experience_text(vault, hook.EXPERIENCE_MAX)
    skl = hook.skills_text(vault, hook.SKILLS_MAX)
    assert 0 < len(exp) <= 600 and exp.rstrip().endswith((".", "。", "）", ")"))  # fewer card lines, the usage line kept
    assert 0 < len(skl) <= 300 and "krouter_skill" in skl


def test_no_room_for_the_index_drops_it_and_says_krouter_ask_in_the_tools_line(hook, tmp_path, monkeypatch):
    vault = _vault(tmp_path)
    head = len(hook.experience_text(vault)) + len(hook.skills_text(vault)) + 2 * len(hook.SEP)
    tools = max(len(hook.TOOLS["zh"]), len(hook.TOOLS_WRITE["zh"])) + len(hook.NONE_LINE["zh"]) + 1 + len(hook.SEP)
    cap = head + tools + hook.INDEX_MIN - 1  # one character short of room for the index
    monkeypatch.setattr(hook, "START_MAX", cap)
    text = hook.start_text({}, vault)
    assert "下意识索引" not in text and "krouter_ask" in text.split(hook.SEP)[-1]
    assert len(text) <= cap


def test_a_vault_with_nothing_to_say_starts_with_nothing(hook, tmp_path, monkeypatch):
    monkeypatch.setenv("KROUTER_RECALL_INDEX", "0")
    vault = tmp_path / "empty"
    shutil.copytree(REPO / "template", vault)
    assert hook.start_text({}, vault) == ""

