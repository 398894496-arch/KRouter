"""The public subconscious benchmark (bench/subconscious/public/) and the no-model reproduction table (bench/reproduce.py).

The KRouter adapter must give exactly the numbers registered for the hook alone (set 45 development half and the
development halves of sets 32 and 35), the plain BM25 baseline must keep working, and the sealed held-out halves must not
be reachable from the public scorer. bench/reproduce.py must match every registered value it prints.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PUBLIC = REPO / "bench/subconscious/public"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def score():
    return _load(PUBLIC / "score.py", "public_score")


def _run_in_a_fresh_process(adapter: str, cases: str) -> dict:
    """The way a user runs it. The KRouter hook is measured in its own process, as the hook runs: in a shared pytest process
    another test's earlier calls into the engine's modules (compile_subconscious.standing_index) change one message's result."""
    out = subprocess.run([sys.executable, "-X", "utf8", "-I", str(PUBLIC / "score.py"), "--adapter", adapter, "--cases", cases, "--json"],
                         capture_output=True, text=True, encoding="utf-8", cwd=REPO)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)[0]


def _run(score, adapter: str, cases: str, **opts) -> dict:
    if adapter == "krouter-hook":
        return _run_in_a_fresh_process(adapter, cases)
    rows = score.load_cases(cases)
    given = score.run_adapter(adapter, opts, rows, score.load_pages())
    return score.summary(rows, given)


def test_krouter_hook_adapter_reproduces_the_registered_development_numbers(score):
    s = _run(score, "krouter-hook", "set45dev")
    assert s["recall"] == [7, 48] and s["changed"] == [7, 24] and s["quiet_loud"] == [2, 48]
    assert s["wrong_pages"] == 0 and s["old_pages"] == 0
    assert s["recall_not_named"] == [1, 42] and s["recall_named"] == [6, 6]
    assert s["by_language"]["zh"]["recall"] == [5, 24] and s["by_language"]["en"]["recall"] == [2, 24]
    assert s["quiet_loud_by_kind"]["other_sense"] == [1, 8] and s["quiet_loud_by_kind"]["near_topic"] == [1, 8]
    s35 = _run(score, "krouter-hook", "set35dev")
    assert (s35["recall"], s35["changed"], s35["quiet_loud"]) == ([6, 24], [2, 12], [2, 24])
    s32 = _run(score, "krouter-hook", "set32dev")
    assert (s32["recall"], s32["changed"], s32["quiet_loud"]) == ([5, 24], [5, 12], [0, 24])


def test_bm25_baseline_rows_are_stable_and_the_always_speaking_one_is_loud(score):
    always = _run(score, "bm25-naive", "set45dev")
    assert always["quiet_loud"][0] >= 40 and always["old_pages"] > 0  # speaks on nearly everything, hands over replaced pages
    careful = _run(score, "bm25-naive", "set45dev", live_only=1, floor=22)
    assert careful["old_pages"] == 0
    assert (careful["recall"][0], careful["changed"][0], careful["quiet_loud"][0], careful["wrong_pages"]) == (4, 4, 2, 2)


def test_held_out_halves_are_not_reachable_from_the_public_scorer(score):
    for name in ("set45held", "set35held", "set32held", "heldout"):
        with pytest.raises(SystemExit):
            score.load_cases(name)


def test_adapter_contract_is_checked(score, tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("def setup(pages, **o): pass\ndef handle(m): return 'Handbook/X.md'\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        _run(score, str(bad), "set45dev")
    quiet = tmp_path / "quiet.py"
    quiet.write_text("def setup(pages, **o): pass\ndef handle(m): return []\n", encoding="utf-8")
    s = _run(score, str(quiet), "set45dev")
    assert s["recall"][0] == 0 and s["quiet_loud"][0] == 0 and s["wrong_pages"] == 0


def test_export_and_answers_round_trip(score, tmp_path):
    out = subprocess.run([sys.executable, "-X", "utf8", "-I", str(PUBLIC / "score.py"), "--export", str(tmp_path)],
                         capture_output=True, text=True, encoding="utf-8", cwd=REPO)
    assert out.returncode == 0, out.stderr
    pages = [json.loads(l) for l in (tmp_path / "pages.jsonl").read_text(encoding="utf-8").splitlines()]
    msgs = [json.loads(l) for l in (tmp_path / "messages.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(pages) == 110 and len(msgs) == 120 and set(msgs[0]) == {"id", "text"}  # no expected answers in what is handed out
    (tmp_path / "answers.jsonl").write_text("".join(json.dumps({"id": m["id"], "pages": []}) + "\n" for m in msgs), encoding="utf-8")
    res = subprocess.run([sys.executable, "-X", "utf8", "-I", str(PUBLIC / "score.py"), "--answers", str(tmp_path / "answers.jsonl"), "--json"],
                         capture_output=True, text=True, encoding="utf-8", cwd=REPO)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout)[0]["recall"] == [0, 48]


def test_reproduce_table_matches_every_registered_value():
    repro = _load(REPO / "bench/reproduce.py", "repro_table")
    table = repro.rows()
    assert len(table) >= 15
    bad = [(w, reg, got) for w, reg, got, _ in table if reg != got]
    import platform
    import sqlite3

    # print the recomputed values: a CI log that only names the row cannot be diagnosed
    assert not bad, ("recomputed values differ from the registered ones (Python %s, SQLite %s, %s %s):\n" % (
        platform.python_version(), sqlite3.sqlite_version, platform.system(), platform.machine())
        + "\n".join(f"- {w.strip()}\n    registered: {reg}\n    recomputed: {got}" for w, reg, got in bad))
