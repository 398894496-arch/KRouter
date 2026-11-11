"""In an English vault the standing index and the prompt hook's note name pages by the vault's own paths
(`02 Methods/…`), not the default layout's (`02 经验与方法/…`): the host reads `{vault}/[page]`."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CJK = re.compile(r"[一-鿿]")


@pytest.fixture()
def english(tmp_path, monkeypatch):
    import zones

    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    vault = tmp_path / "en"
    zones.lay_out(REPO / "template", vault, alias_sample=REPO / "skill/krouter/scripts/canonical_sources.psv")
    from test_session_start import own_row

    own_row(vault)  # a vault in use: the index lists its topics
    return vault


def test_the_index_names_real_paths(english):
    import compile_subconscious

    text = compile_subconscious.standing_index(english)
    pages = re.findall(r"\[([^\]]+\.md)\]", text)
    assert pages and not CJK.search(text)
    assert all((english / p).is_file() for p in pages), [p for p in pages if not (english / p).is_file()]


def test_the_hook_note_names_the_real_path(english):
    import recall_index
    import recollect

    recall_index.recall(english, "home")  # the hook reads the recall cache as it is and never builds it itself
    hits = recollect.recollect(english, "Going to move the clippings originals into the archive folder this afternoon.")
    note = recollect.render(hits)
    assert "[02 Methods/Agent/User preferences.md, alias]" in note and not CJK.search(note)
    assert hits[0]["rel"].startswith("02 经验与方法/")  # recalled.jsonl keeps the default-layout path, as before
