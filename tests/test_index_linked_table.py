"""The session-start index when the alias table next to the code is a link to the vault's own table.

A host that keeps its table in the vault and links the install directory's copy to it (so an upgrade never overwrites
it) used to get an empty index: the table was taken for the shipped sample, twice over (same resolved file, same
content). Found on a real machine on 2026-11-15."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skill/krouter/scripts"))


def make_vault(root: Path) -> Path:
    """vault3 with the bench's alias table laid in, as bench/subconscious/run.py does (not imported: its module names
    collide with other benches' on sys.path)."""
    import shutil

    v = root / "vault"
    shutil.copytree(REPO / "bench/memory_honesty/vault3", v)
    (v / "90 系统文件").mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / "bench/subconscious/overlay/canonical_sources.psv", v / "90 系统文件/canonical_sources.psv")
    return v


def test_index_is_not_empty_when_the_install_table_links_to_the_vaults(tmp_path, monkeypatch):
    import compile_subconscious as cs

    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("KROUTER_NO_QUERY_LOG", "1")
    monkeypatch.delenv("KROUTER_MAP", raising=False)
    v = make_vault(tmp_path)
    table = v / "90 系统文件/canonical_sources.psv"
    plain = len(cs.index_topics(v))
    assert plain > 0
    install = tmp_path / "install"
    install.mkdir()
    link = install / "canonical_sources.psv"
    link.symlink_to(table)
    monkeypatch.setattr(cs, "sample_path", lambda: link)
    assert cs.sample_table(v, table) is False
    assert len(cs.index_topics(v)) == plain
    assert cs.standing_index(v)


def test_the_shipped_sample_is_still_recognised(tmp_path, monkeypatch):
    import compile_subconscious as cs

    monkeypatch.delenv("KROUTER_MAP", raising=False)
    sample = cs.sample_path()
    assert not sample.is_symlink()
    v = tmp_path / "vault"
    (v / "90 系统文件").mkdir(parents=True)
    (v / "90 系统文件/canonical_sources.psv").write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")
    assert cs.sample_table(v, v / "90 系统文件/canonical_sources.psv") is True
    assert cs.index_topics(v) == []
