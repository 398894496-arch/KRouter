from pathlib import Path

import pytest

from canonical_lookup import lookup, near_score, suggestions

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "skill/krouter-obsidian/scripts/canonical_sources.psv"
VAULT = ROOT / "template"


@pytest.fixture(scope="module")
def rows():
    from canonical_lookup import load_rows

    return load_rows(MAP)


def test_exact_home(rows):
    hit = lookup("home", rows)
    assert hit is not None
    assert hit[0] == "Q01"
    assert hit[1] == "Agent第二大脑.md"


def test_clippings(rows):
    hit = lookup("clippings", rows)
    assert hit is not None
    assert hit[0] == "Q02"


def test_preference_alias(rows):
    hit = lookup("preference", rows)
    assert hit is not None
    assert hit[0] == "Q02"


def test_memory_alias(rows):
    hit = lookup("memory", rows)
    assert hit is not None
    assert hit[0] == "Q07"


def test_ambiguous_different_files_is_miss(tmp_path):
    from canonical_lookup import load_rows, lookup

    path = tmp_path / "map.psv"
    path.write_text("Q1|alpha|a.md|x\nQ2|alpha|b.md|y\n", encoding="utf-8")
    rows = load_rows(path)
    assert lookup("alpha", rows) is None


def test_same_file_tie_picks_lowest_id(tmp_path):
    from canonical_lookup import load_rows, lookup

    path = tmp_path / "map.psv"
    path.write_text("Q2|alpha|a.md|x\nQ1|alpha|a.md|y\n", encoding="utf-8")
    rows = load_rows(path)
    hit = lookup("alpha", rows)
    assert hit is not None
    assert hit[0] == "Q1"


def test_prefix_is_suggestion_not_hit(rows):
    assert lookup("homz", rows) is None
    ranked = suggestions("homz", rows, limit=3)
    ids = [item[1] for item in ranked]
    assert "Q01" in ids
    assert near_score("homz", "home") >= 40


def test_latin_fragment_of_an_alias_is_not_a_hit(rows):
    """`how` sits inside `how to handle clippings`. That is not a hit."""
    assert lookup("how", rows) is None
    assert lookup("how to deploy", rows) is None
    assert lookup("how do I add my own topic", rows) is None
    ranked = suggestions("how to deploy", rows, limit=3)
    assert ranked, "a miss still owes the caller hints"


def test_short_alias_inside_a_question_still_hits(rows):
    assert lookup("correction policy for my team", rows)[0] == "Q05"
    assert lookup("homepage", rows)[0] == "Q01"


def test_cjk_fragment_still_carries_the_alias(tmp_path):
    from canonical_lookup import load_rows, lookup

    path = tmp_path / "map.psv"
    path.write_text("Q1|唯一总入口|a.md|x\n", encoding="utf-8")
    rows = load_rows(path)
    assert lookup("入口", rows)[0] == "Q1"


def test_expired_page_dropped_when_vault_given(tmp_path):
    from datetime import date

    from canonical_lookup import load_rows, lookup

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "a.md").write_text("---\ninvalid_at: 2026-01-01\n---\n", encoding="utf-8")
    (vault / "b.md").write_text("---\nvalid_from: 2026-01-01\n---\n", encoding="utf-8")
    path = tmp_path / "map.psv"
    path.write_text("Q1|alpha|a.md|x\nQ2|beta|b.md|y\n", encoding="utf-8")
    rows = load_rows(path)
    assert lookup("alpha", rows) is not None
    assert lookup("alpha", rows, vault=vault, today=date(2026, 8, 22)) is None
    hit = lookup("beta", rows, vault=vault, today=date(2026, 8, 22))
    assert hit is not None
    assert hit[0] == "Q2"


def test_template_sources_exist(rows):
    for _case_id, _aliases, source, _anchor in rows:
        assert (VAULT / source).is_file(), source


def test_query_conflict_asks_when_two_pages_tie(tmp_path):
    from canonical_lookup import load_rows, lookup, query_conflict

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "a.md").write_text("---\nstatus: active\n---\n", encoding="utf-8")
    (vault / "b.md").write_text("---\nstatus: active\n---\n", encoding="utf-8")
    path = tmp_path / "map.psv"
    path.write_text(
        "Q21|每日进化自动化真的运行过了吗|a.md|x\n"
        "Q22|自动化什么时候运行|b.md|y\n",
        encoding="utf-8",
    )
    rows = load_rows(path)
    assert lookup("自动化", rows, vault=vault) is None
    conflict = query_conflict("自动化", rows, vault=vault)
    assert conflict is not None
    assert conflict["kind"] == "ambiguous-query"
    assert "选一个" in conflict["host_prompt"]
    assert "Q21" in conflict["host_prompt"]
    assert "Q22" in conflict["host_prompt"]


def test_weak_hint_is_not_a_host_choice(rows):
    from canonical_lookup import query_conflict

    assert query_conflict("how", rows, vault=VAULT) is None
    assert query_conflict("home", rows, vault=VAULT) is None


def test_hints_need_a_shared_content_pair_not_scattered_characters():
    """`剪辑` and `剪藏原件` share 剪 and 件; `标题有什么讲究` and `方法什么时候能进` share only 什么. Neither is a hint."""
    assert near_score("剪辑用什么软件", "剪藏原件") == 0
    assert near_score("标题有什么讲究", "方法什么时候能进") == 0
    assert near_score("剪藏的规矩", "剪藏原件") > 0
    assert near_score("发版流程改了吗", "上次的发版流程") > 0
