"""Ten people, each with their own token and agent, on one team server at once: asks, notes, concurrent corrections
of one page and contradicting corrections of one decision. Nothing acknowledged may go missing, no page may break,
every change must name the token that made it, each contested decision must end with the last correction in force
and the others superseded in arrival order, and every answer must name its vault and a page.

The same harness, at 10,000 and 50,000 pages and for 30 minutes, is `bench/team/load.py` (numbers in docs/TEAM.md)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("team_load", REPO / "bench/team/load.py")
load = importlib.util.module_from_spec(spec)
sys.modules["team_load"] = load
spec.loader.exec_module(load)


@pytest.fixture(scope="module", params=[20261110, 7])
def run(request, tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp(f"team{request.param}")
    vault, people, users = load.prepare(tmp_path, None, 10)
    proc, url, _ready = load.start(tmp_path, vault, users)
    results: list[dict] = []
    try:
        phases = load.run(url, people, 8, 0, request.param, results)
        final = load.final_answer(url, people[0]["token"], vault, results)
    finally:
        load.stop(proc)  # the server's log is drained on a thread: read it only once that thread is done
    log = (tmp_path / "server.log").read_text(encoding="utf-8")
    return {"vault": vault, "people": people, "results": results, "phases": phases, "final": final, "log": log,
            "env": load.clean_env(tmp_path)}


def test_ten_concurrent_agents_lose_nothing_and_converge(run):
    checks = load.verify(run["vault"], run["results"], run["env"])
    failed = {k: v for k, v in checks.items() if not v["ok"]}
    assert not failed, failed
    writes = checks["journal_complete"]["acked_writes"]
    assert writes >= 40 and checks["conflicts_converge"]["conflict_replies"] >= 9 + 9  # the two bursts alone
    assert run["final"]["ok"], run["final"]


def test_every_person_was_seen_and_no_token_was_logged(run):
    whos = {r["who"] for r in run["results"] if r["ok"] and r["tool"] != "krouter_ask"}
    assert whos == {p["name"] for p in run["people"]}
    assert not any(p["token"] in run["log"] for p in run["people"])
    assert '"who": "dev00"' in run["log"]  # the access log names the person instead
    journal = (run["vault"] / load.team.JOURNAL).read_text(encoding="utf-8")
    assert not any(p["token"] in journal for p in run["people"])
