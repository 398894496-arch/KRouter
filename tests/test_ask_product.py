from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skill/krouter/scripts"
sys.path.insert(0, str(SCRIPTS))

from ask_product import (  # noqa: E402
    ask_once,
    coverage,
    load_catalog,
    match_trigger,
    vault_root,
)

TEMPLATE = ROOT / "template"


def test_template_catalog_has_triggers():
    os.environ["OBSIDIAN_VAULT"] = str(TEMPLATE)
    cat = load_catalog(TEMPLATE)
    cov = coverage(cat)
    assert cov["ok"], cov["missing"]
    assert cov["provisional_n"] >= 1


def test_timer_provisional_asks_on_trigger():
    os.environ["OBSIDIAN_VAULT"] = str(TEMPLATE)
    cat = load_catalog(TEMPLATE)
    hit = match_trigger("did the scheduled job run", cat)
    assert hit.get("ask") == "A timer that fired is not a product.md"
    miss = match_trigger("what is the weather", cat)
    assert miss.get("ask") is None


def test_exact_caret_and_ambiguous_refuse():
    cat = [
        {
            "file": "a.md",
            "title": "A",
            "next_ask": "",
            "status": "provisional",
            "triggers": ["^ship"],
        },
        {
            "file": "b.md",
            "title": "B",
            "next_ask": "",
            "status": "provisional",
            "triggers": ["ship it"],
        },
    ]
    assert match_trigger("ship", cat).get("ask") == "a.md"
    assert match_trigger("please ship it now", cat).get("ask") == "b.md"
    tied = [
        {**cat[0], "triggers": ["alpha"]},
        {**cat[1], "file": "c.md", "triggers": ["alpha"]},
    ]
    out = match_trigger("alpha", tied)
    assert out.get("ask") is None
    assert out.get("reason") == "trigger-ambiguous"


def test_ask_once_does_not_write_active(tmp_path):
    os.environ["OBSIDIAN_VAULT"] = str(tmp_path)
    vault = tmp_path
    prov = vault / "02 经验与方法" / "准经验"
    prov.mkdir(parents=True)
    (prov / "Sample.md").write_text(
        "---\ntitle: Sample\nstatus: provisional\ntriggers: sample trigger\nnext_ask: adopt sample?\n---\n",
        encoding="utf-8",
    )
    cat = load_catalog(vault)
    out = ask_once("please do the sample trigger now", cat, vault)
    assert out["trigger"]["ask"] == "Sample.md"
    assert "active" not in (out["trigger"].get("prompt") or "").lower()
    assert vault_root() == vault.resolve()


def test_promote_after_adopt_only(tmp_path):
    os.environ["OBSIDIAN_VAULT"] = str(tmp_path)
    vault = tmp_path
    prov = vault / "02 经验与方法" / "准经验"
    prov.mkdir(parents=True)
    page = prov / "Sample.md"
    page.write_text(
        "---\ntitle: Sample\nstatus: provisional\ntriggers: sample trigger\n---\n",
        encoding="utf-8",
    )
    from ask_product import append_ledger, load_catalog, match_trigger, promote

    assert promote(vault, "Sample.md")["reason"] == "need-adopt-first"
    append_ledger(
        vault,
        {"kind": "record", "file": "Sample.md", "decision": "adopt", "adopt": "adopt"},
    )
    out = promote(vault, "Sample.md")
    assert out["active"] is True
    assert "status: active" in page.read_text()
    cat = load_catalog(vault)
    assert match_trigger("sample trigger", cat).get("ask") is None


if __name__ == "__main__":
    os.environ["OBSIDIAN_VAULT"] = str(TEMPLATE)
    test_template_catalog_has_triggers()
    test_timer_provisional_asks_on_trigger()
    test_exact_caret_and_ambiguous_refuse()
    import tempfile
    from pathlib import Path as P

    with tempfile.TemporaryDirectory() as d:
        test_ask_once_does_not_write_active(P(d))
        test_promote_after_adopt_only(P(d) / "promo")
    print("ok ask_product tests")
