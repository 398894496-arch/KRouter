from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from verify_canonical_map import verify  # noqa: E402


def _clone_25():
    path = ROOT / "tests/fixtures/clone_25/run.py"
    spec = importlib.util.spec_from_file_location("clone_25_run", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


clone_25 = _clone_25()


def test_clone_25_mechanical_map():
    result = clone_25.run()
    mech = result["mechanical"]
    assert mech["ok"], mech["failures"]
    assert mech["topics"] == 25
    assert mech["aliases"] >= 25


def test_clone_25_paraphrase_misses_and_noun_hits():
    result = clone_25.run()
    rw = result["rewrite"]
    assert rw["n"] == 25
    assert rw["paraphrase_miss"] == 25
    assert rw["noun_hit"] == 25
    assert rw["ok"]


def test_shipped_template_map_still_mechanically_clean():
    """Product sample map (ten nouns) must stay unique-hit on template/."""
    mech = verify(
        ROOT / "skill/krouter/scripts/canonical_sources.psv",
        ROOT / "template",
    )
    assert mech["ok"], mech["failures"]
    assert mech["topics"] == 10
