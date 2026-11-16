"""`KROUTER_INDEX_PAGES=1` (set 49): the standing index also lists, by title, the pages in force that the alias table does
not name. Off by default; with it off, or with a table that names every such page, the index is the shipped one."""

import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skill/krouter/scripts"))

SYSTEM = "90 系统文件"


def page(path: Path, title: str, body: str, extra: str = "status: active\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: {title}\n{extra}date: 2026-10-01\n---\n\n# {title}\n\n{body}\n", encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    import recollect

    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("KROUTER_NO_QUERY_LOG", "1")
    monkeypatch.delenv("KROUTER_MAP", raising=False)
    monkeypatch.delenv("KROUTER_INDEX_PAGES", raising=False)
    monkeypatch.delenv("KROUTER_TOPICS", raising=False)
    recollect._PAGES.clear()
    return tmp_path


def bench_vault(root: Path, keep_every: int = 1) -> Path:
    """vault3 with the bench's alias table (every `keep_every`-th row), as bench/subconscious/tool_host.py lays it."""
    v = root / "vault"
    shutil.copytree(REPO / "bench/memory_honesty/vault3", v)
    (v / SYSTEM).mkdir(parents=True, exist_ok=True)
    lines = (REPO / "bench/subconscious/overlay/canonical_sources.psv").read_text(encoding="utf-8").splitlines()
    head = [x for x in lines if not x.strip() or x.startswith("#")]
    own = [x for x in lines if x.strip() and not x.startswith("#")]
    (v / SYSTEM / "canonical_sources.psv").write_text("\n".join(head + own[::keep_every]) + "\n", encoding="utf-8")
    return v


def warm(v: Path) -> None:
    import recall_index

    recall_index.recall(v, "warm up")


def names(index: str) -> list[str]:
    import compile_subconscious as cs

    for line in index.splitlines():
        for head in cs.INDEX_NAMES_HEAD.values():
            if line.startswith(head):
                return re_split(line[len(head):])
    return []


def re_split(text: str) -> list[str]:
    import re

    return [x.strip() for x in re.split(r"[、;]", text) if x.strip()]


def test_off_by_default_and_listed_when_on(env, monkeypatch):
    import compile_subconscious as cs

    v = bench_vault(env, keep_every=8)
    warm(v)
    shipped = cs.standing_index(v)
    assert "Access reviews" not in shipped
    monkeypatch.setenv("KROUTER_INDEX_PAGES", "1")
    on = cs.standing_index(v)
    listed = names(on)
    assert "Access reviews" in listed and "出差标准" in listed
    # 被取代的旧页不列，日志不列，别名表点了名的不重复列
    assert not [n for n in listed if "old" in n.lower() or "旧" in n]
    assert not [n for n in listed if n.startswith("2026-")]
    assert "Hackathon" not in listed and on.count("Hackathon.md") == 1
    # 别名表点了名的那几行原样在前
    assert on.splitlines()[:9] == shipped.splitlines()[:9]


def test_a_table_that_names_every_page_gives_the_shipped_index(env, monkeypatch):
    import compile_subconscious as cs

    v = bench_vault(env)
    warm(v)
    shipped = cs.standing_index(v)
    monkeypatch.setenv("KROUTER_INDEX_PAGES", "1")
    assert cs.standing_index(v) == shipped


def test_rule_pages_are_listed_and_other_folders_are_not_once_there_are_enough(env, monkeypatch):
    import compile_subconscious as cs

    v = env / "vault"
    for i in range(cs.INDEX_PAGES_MIN):
        page(v / f"02 经验与方法/规矩{i:02d}.md", f"规矩{i:02d}", f"第 {i} 条规矩：周五不发版。")
    page(v / "02 经验与方法/主题档案/主题｜发版.md", "主题｜发版", "发版的来龙去脉。")
    page(v / "02 经验与方法/旧规矩.md", "旧规矩", "作废了。", extra="status: superseded\n")
    page(v / "02 经验与方法/机器汇总.md", "机器汇总", "自动生成的。", extra="status: generated\n")
    page(v / "随手记/买菜.md", "买菜", "周末买菜。")
    page(v / "01 项目/某项目/进度.md", "某项目进度", "做到一半。")
    page(v / "05 时间日志/2026-10-01.md", "2026-10-01", "今天开会。", extra="type: log\n")
    (v / SYSTEM).mkdir(parents=True, exist_ok=True)
    (v / SYSTEM / "canonical_sources.psv").write_text(
        "R00|规矩零|02 经验与方法/规矩00.md|周五不发版\n", encoding="utf-8")
    warm(v)
    monkeypatch.setenv("KROUTER_INDEX_PAGES", "1")
    listed = names(cs.standing_index(v))
    assert "规矩01" in listed and "主题｜发版" in listed
    assert listed.index("规矩01") < listed.index("主题｜发版")  # 规则页在前，主题页在后
    assert "规矩00" not in listed  # 别名表点了名，已经有整行
    for absent in ("旧规矩", "机器汇总", "买菜", "某项目进度", "2026-10-01"):
        assert absent not in listed


def test_other_folders_stand_in_when_the_vault_is_not_laid_out_the_templates_way(env, monkeypatch):
    import compile_subconscious as cs

    v = env / "vault"
    page(v / "notes/报销.md", "报销", "打车费当月报。")
    page(v / "notes/值班.md", "值班", "周末轮流值班。")
    page(v / SYSTEM / "说明.md", "系统说明", "系统文件夹里的页不列。")
    (v / SYSTEM / "canonical_sources.psv").write_text("N01|报销|notes/报销.md|打车费当月报\n", encoding="utf-8")
    warm(v)
    monkeypatch.setenv("KROUTER_INDEX_PAGES", "1")
    listed = names(cs.standing_index(v))
    assert listed == ["值班"]


def test_no_table_of_its_own_still_lists_and_the_template_sample_does_not(env, monkeypatch):
    import compile_subconscious as cs

    v = env / "vault"
    page(v / "notes/报销.md", "报销", "打车费当月报。")
    warm(v)
    assert cs.table_state(v) == "none"
    assert cs.standing_index(v) == ""
    monkeypatch.setenv("KROUTER_INDEX_PAGES", "1")
    assert names(cs.standing_index(v)) == ["报销"]
    (v / SYSTEM).mkdir(parents=True, exist_ok=True)
    (v / SYSTEM / "canonical_sources.psv").write_text(cs.sample_path().read_text(encoding="utf-8"), encoding="utf-8")
    assert cs.table_state(v) == "sample"
    assert cs.standing_index(v) == ""


def test_titles_share_the_budget_and_the_rest_are_counted(env, monkeypatch):
    import compile_subconscious as cs

    v = bench_vault(env, keep_every=8)
    warm(v)
    monkeypatch.setenv("KROUTER_INDEX_PAGES", "1")
    whole = cs.standing_index(v)
    tight = cs.standing_index(v, chars=900)
    body = "\n".join(tight.splitlines()[1:-1])
    assert len(body) <= 900
    assert 0 < len(names(tight)) < len(names(whole))
    assert "没列出" in tight.splitlines()[-1] or "not listed" in tight.splitlines()[-1]


def test_no_recall_index_yet_means_no_titles_and_no_error(env, monkeypatch):
    import compile_subconscious as cs

    v = bench_vault(env, keep_every=8)
    monkeypatch.setenv("KROUTER_INDEX_PAGES", "1")
    assert cs.index_pages(v, set()) == []
    assert not (env / "cache").exists() or not list((env / "cache").glob("*.sqlite"))
