"""The associative path (edges in the recall cache, spreading from the direct hits) and the no-model tie-break for a
vault that changed its mind (newer page first, the conflict named)."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter-obsidian/scripts"
IMPORT = SCRIPTS / "import_sessions.py"
ROUTE = SCRIPTS / "route_knowledge.py"


@pytest.fixture()
def ri(tmp_path, monkeypatch):
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("KROUTER_NO_QUERY_LOG", "1")
    monkeypatch.delenv("KROUTER_ASSOC", raising=False)
    monkeypatch.delenv("KROUTER_CONFLICT", raising=False)
    import recall_index

    return importlib.reload(recall_index)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


FILLER = ["Office plants are watered on Fridays.", "Parking spots rotate every quarter.",
          "The coffee machine is cleaned weekly.", "Team lunch is on the first Monday.",
          "Holiday requests go through the HR portal.", "The printer on floor two jams often.",
          "Visitors sign in at the front desk.", "Bike racks are behind the building."]


def _filler(v: Path) -> None:
    for i, text in enumerate(FILLER):
        _write(v, f"99 杂项/Note {i}.md", f"# Note {i}\n\n{text}\n")


def _vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    _write(v, "01 项目/Billing/Invoice retries.md",
           "---\ntitle: Invoice retries\n---\n# Invoice retries\n\nFailed invoice charges retry three times, "
           "then the account is flagged for review. See [[Dunning emails]] for what the customer is told.\n")
    _write(v, "01 项目/Billing/Dunning emails.md",
           "---\ntitle: Dunning emails\n---\n# Dunning emails\n\nThe customer gets a reminder on day one and a "
           "final notice on day seven; templates live in the mailer repo.\n")
    _write(v, "01 项目/Billing/Index.md",
           "---\ntitle: Billing index\n---\n# Billing index\n\n" + "".join(f"- [[Page {i}]]\n" for i in range(14))
           + "- [[Invoice retries]]\n")
    for i in range(14):
        _write(v, f"01 项目/Billing/Page {i}.md", f"---\ntitle: Page {i}\n---\n# Page {i}\n\nUnrelated note {i} "
               f"about office plants and parking spot {i}.\n")
    _write(v, "01 项目/Billing/Retry policy (old).md",
           "---\ntitle: Retry policy (old)\nstatus: superseded\n---\n# Retry policy (old)\n\nInvoices retried five "
           "times.\n")
    _write(v, "01 项目/Billing/Retry policy.md",
           "---\ntitle: Retry policy\nsupersedes: \"[[Retry policy (old)]]\"\n---\n# Retry policy\n\nSee "
           "[[Invoice retries]].\n")
    return v


def test_edges_are_in_the_rebuildable_cache(ri, tmp_path):
    v = _vault(tmp_path)
    con = ri.connect(ri.cache_path(v))
    ri.refresh(v, con)
    kinds = {k for (k,) in con.execute("SELECT DISTINCT kind FROM edges")}
    assert {"link", "supersedes"} <= kinds
    links = ri.associate._resolved_links(con, ["01 项目/Billing/Invoice retries.md"])
    assert ("01 项目/Billing/Invoice retries.md", "01 项目/Billing/Dunning emails.md", "link") in links
    con.close()
    ri.cache_path(v).unlink()  # the cache can go at any time; the next lookup rebuilds the edges
    res = ri.recall(v, "how many times do failed invoice charges retry", limit=3, assoc=True)
    assert res["assoc"][0]["rel"] == "01 项目/Billing/Dunning emails.md"


def test_associated_pages_are_separate_say_their_edge_and_fit_the_page_budget(ri, tmp_path):
    v = _vault(tmp_path)
    q = "how many times do failed invoice charges retry"
    off = ri.recall(v, q, limit=3)
    assert "assoc" not in off and off["hits"][0]["rel"] == "01 项目/Billing/Invoice retries.md"
    on = ri.recall(v, q, limit=3, assoc=True)
    assert on["hits"][0]["rel"] == off["hits"][0]["rel"]  # the direct path is untouched
    assert len(ri.page_list(on, 3)) <= 3 and len(on["assoc"]) <= ri.associate.slots(3)
    a = on["assoc"][0]
    assert a["rel"] == "01 项目/Billing/Dunning emails.md"  # it shares no word with the question
    assert {"kind": "link", "from": "01 项目/Billing/Invoice retries.md"} in a["via"]
    shown = {h["rel"] for h in on["hits"]} | {x["rel"] for x in on["assoc"]}
    assert "01 项目/Billing/Index.md" not in shown  # a hub page (14+ links, "index") is never offered
    assert "01 项目/Billing/Retry policy (old).md" not in shown  # nor a replaced page


def test_associative_path_off_by_default_and_env_switch(ri, monkeypatch):
    assert ri.associate.enabled() is ri.associate.DEFAULT_ON
    monkeypatch.setenv("KROUTER_ASSOC", "1")
    assert ri.associate.enabled() is True
    monkeypatch.setenv("KROUTER_ASSOC", "0")
    assert ri.associate.enabled() is False


def test_co_citation_strengthens_an_edge_from_a_state_file(ri, tmp_path):
    v = tmp_path / "vault"
    _filler(v)
    _write(v, "a/Deploy window.md", "---\ntitle: Deploy window\n---\nDeploys go out on Tuesday mornings only.\n")
    _write(v, "a/Pager rota.md", "---\ntitle: Pager rota\n---\nThe on-call engineer changes every Monday.\n")
    _write(v, "a/Other.md", "---\ntitle: Other\n---\nCoffee order for the offsite.\n")
    q = "when do deploys go out"
    assert "assoc" not in ri.recall(v, q, limit=3, assoc=True)
    assert ri.associate.reinforce(v, ["a/Deploy window.md", "a/Pager rota.md"], 5.0) == 1
    res = ri.recall(v, q, limit=3, assoc=True)
    assert [x["rel"] for x in res["assoc"]] == ["a/Pager rota.md"]
    assert res["assoc"][0]["via"][0]["kind"] == "cocite"
    assert ri.associate.cocite_file(v).parent == tmp_path / "state"  # outside the vault and the cache


def test_route_prints_associated_block_after_hits(tmp_path):
    v = _vault(tmp_path)
    env = {**os.environ, "OBSIDIAN_VAULT": str(v), "KROUTER_CACHE_DIR": str(tmp_path / "c"),
           "KROUTER_STATE_DIR": str(tmp_path / "s"), "KROUTER_NO_QUERY_LOG": "1", "KROUTER_ASSOC": "1"}
    out = subprocess.run([sys.executable, str(ROUTE), "search", "how many times do failed invoice charges retry"],
                         env=env, capture_output=True, text=True, timeout=60).stdout
    recall_block, _, assoc_block = out.partition("\nassociated: ")
    assert "\nrecall:\n- 01 项目/Billing/Invoice retries.md" in recall_block
    assert assoc_block and "- 01 项目/Billing/Dunning emails.md" in assoc_block
    assert "  via: linked with 01 项目/Billing/Invoice retries.md; shares words with" in assoc_block
    sys.path.insert(0, str(REPO / "sdk"))
    import krouter

    hits = krouter.Answer(text=out).hits  # the SDK reads only the direct hits
    assert [h["page"] for h in hits][0] == "01 项目/Billing/Invoice retries.md"
    assert "01 项目/Billing/Dunning emails.md" not in [h["page"] for h in hits]


# ---- the vault changed its mind, no model, nothing distilled (audit B5/B6) ----

def _ts(days_ago: int, hour: int) -> str:
    day = datetime.now().astimezone() - timedelta(days=days_ago)
    return day.replace(hour=hour, minute=5, second=0, microsecond=0).astimezone(timezone.utc).isoformat()


def _session(root: Path, sid: str, turns: list[tuple[str, str, str]]) -> None:
    rows = []
    for ts, ask, answer in turns:
        rows.append({"type": "user", "entrypoint": "claude-desktop", "cwd": "/work/demo", "timestamp": ts,
                     "origin": {"kind": "human"}, "message": {"role": "user", "content": ask}})
        rows.append({"type": "assistant", "entrypoint": "claude-desktop", "timestamp": ts,
                     "message": {"content": [{"type": "text", "text": answer}]}})
    path = root / "-work-demo" / f"{sid}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


@pytest.fixture()
def changed_mind(tmp_path):
    """Monday: the demo app gets PostgreSQL. Wednesday: switched to SQLite. Imported into a fresh install's vault (the
    bundled template), never distilled, no key: the audit's B5."""
    import shutil

    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template", vault)
    claude = tmp_path / "claude"
    _session(claude, "aaaa1111-monday", [
        (_ts(9, 10), "Let's set up the database for the demo app. Which database should the demo app use?",
         "Decided: the demo app uses PostgreSQL 16. I added a docker-compose service for the PostgreSQL database "
         "and the demo app connects with DATABASE_URL."),
        (_ts(9, 11), "Add a seed script for the demo app database.",
         "Done: scripts/seed.sql loads 20 rows into the PostgreSQL database of the demo app.")])
    _session(claude, "bbbb2222-wednesday", [
        (_ts(7, 15), "PostgreSQL is too heavy for the demo app. Switch the demo app database to SQLite instead.",
         "Switched: the demo app now uses SQLite (demo.db). The docker-compose database service is gone."),
        (_ts(7, 16), "Does the seed script still work?", "Yes, seed.sql runs against SQLite now.")])
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_CLAUDE_PROJECTS": str(claude),
           "KROUTER_CODEX_SESSIONS": str(tmp_path / "codex"), "KROUTER_CURSOR_PROJECTS": str(tmp_path / "cursor"),
           "KROUTER_STATE_DIR": str(tmp_path / "state"), "KROUTER_CACHE_DIR": str(tmp_path / "cache"),
           "KROUTER_NO_QUERY_LOG": "1"}
    for k in [k for k in env if k.endswith("_API_KEY")]:
        env.pop(k)
    res = subprocess.run([sys.executable, str(IMPORT), "--days", "14"], env=env, capture_output=True, text=True,
                         timeout=120)
    assert res.returncode == 0, res.stderr
    pages = sorted((vault / "05 时间日志/会话摘录").glob("*.md"))
    assert len(pages) == 2 and all("还没提炼" in p.read_text(encoding="utf-8") for p in pages)
    return {"vault": vault, "env": env, "monday": next(p for p in pages if "aaaa1111" in p.name),
            "wednesday": next(p for p in pages if "bbbb2222" in p.name)}


def _route(env: dict, q: str, **extra: str) -> str:
    return subprocess.run([sys.executable, str(ROUTE), "search", q], env={**env, **extra}, capture_output=True,
                          text=True, timeout=60).stdout


def _hits(out: str) -> list[str]:
    block = out.split("\nrecall:\n", 1)[1].split("\nassociated: ", 1)[0]
    return [ln[2:].split(" tier=")[0] for ln in block.splitlines() if ln.startswith("- ")]


def test_newer_page_first_and_conflict_named_without_any_model(changed_mind):
    q = "which database does the demo app use?"
    vault = changed_mind["vault"]
    old = changed_mind["monday"].relative_to(vault).as_posix()
    new = changed_mind["wednesday"].relative_to(vault).as_posix()
    before = _route(changed_mind["env"], q, KROUTER_CONFLICT="0")
    assert _hits(before)[0] == old and "recall_conflict" not in before  # what the audit saw (B6)
    out = _route(changed_mind["env"], q)
    assert _hits(out)[:2] == [new, old]
    assert "recall_conflict: an earlier page says otherwise." in out
    assert f"{new} (" in out and f"changes what {old} (" in out
    assert f"- {new} tier=log status=imported conflict=newer" in out
    assert f"- {old} tier=log status=imported conflict=older" in out


def test_conflict_flag_only_when_the_change_does_not_name_the_subject(ri, tmp_path):
    """Two dated pages on the same question, the newer one says something changed but not about this: flagged,
    order kept."""
    v = tmp_path / "vault"
    _filler(v)
    _write(v, "05 时间日志/2026-11-02 cache.md", "---\ndate: 2026-11-02\n---\nThe report cache expires after "
           "ten minutes for the report cache of the dashboard. The report cache expires nightly too.\n")
    _write(v, "05 时间日志/2026-11-04 cache.md", "---\ndate: 2026-11-04\n---\nThe report cache of the dashboard "
           "expires after one hour.\nUnrelated: we switched the lunch order to pizza.\n")
    res = ri.recall(v, "when does the dashboard report cache expire", limit=3)
    c = res.get("conflict")
    assert c and not c["sure"] and not c["reorder"]
    assert res["hits"][0]["rel"] == "05 时间日志/2026-11-02 cache.md"  # not reordered
    assert {h.get("conflict") for h in res["hits"][:2]} == {"possible"}
    assert "recall_conflict: possible." in ri.associate.conflict_note(c)


def test_no_conflict_when_pages_are_undated_or_about_different_things(ri, tmp_path):
    v = tmp_path / "vault"
    _filler(v)
    _write(v, "a/Cache A.md", "The report cache of the dashboard expires after ten minutes.\n")
    _write(v, "a/Cache B.md", "We switched the report cache of the dashboard to expire after one hour.\n")
    assert "conflict" not in ri.recall(v, "when does the dashboard report cache expire", limit=3)
    w = tmp_path / "vault2"
    _filler(w)
    _write(w, "05 时间日志/2026-11-02 a.md", "---\ndate: 2026-11-02\n---\nThe dashboard report cache expires "
           "after ten minutes.\n")
    _write(w, "05 时间日志/2026-11-04 b.md", "---\ndate: 2026-11-04\n---\nThe login page moved to a new "
           "domain; we switched DNS to the new provider.\n")
    assert "conflict" not in ri.recall(w, "when does the dashboard report cache expire", limit=3)


def test_conflict_tie_break_can_be_turned_off(ri, tmp_path, monkeypatch):
    v = tmp_path / "vault"
    _filler(v)
    _write(v, "05 时间日志/2026-11-02 db.md", "---\ndate: 2026-11-02\n---\nThe demo app database is PostgreSQL. "
           "The demo app database runs in docker for the demo app.\n")
    _write(v, "05 时间日志/2026-11-04 db.md", "---\ndate: 2026-11-04\n---\nWe switched the demo app database "
           "to SQLite.\n")
    on = ri.recall(v, "which database does the demo app use", limit=3)
    assert on["hits"][0]["rel"] == "05 时间日志/2026-11-04 db.md" and on["conflict"]["sure"]
    monkeypatch.setenv("KROUTER_CONFLICT", "0")
    off = ri.recall(v, "which database does the demo app use", limit=3)
    assert "conflict" not in off and off["hits"][0]["rel"] == "05 时间日志/2026-11-02 db.md"
