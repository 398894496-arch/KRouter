"""A question you asked before, recorded with no answer, is not evidence the next time you ask it.

Found on the maintainer's own vault (not a registered set): asked once, the session was imported as an excerpt page
whose only matching line was the question itself; asked again, that page came back `medium`. Now such a page is left
out, and when nothing else covers the question the receipt says `recall: none` and that it was asked before. A page
where you stated something, or where the answer has the content, still counts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter/scripts"
IMPORT = SCRIPTS / "import_sessions.py"
ROUTE = SCRIPTS / "route_knowledge.py"


def _ts(days_ago: int, hour: int) -> str:
    day = datetime.now().astimezone() - timedelta(days=days_ago)
    return day.replace(hour=hour, minute=5, second=0, microsecond=0).astimezone(timezone.utc).isoformat()


def _session(root: Path, sid: str, turns: list[tuple[str, str]]) -> None:
    rows = []
    for n, (ask, answer) in enumerate(turns):
        ts = _ts(2, 10 + n)
        rows.append({"type": "user", "cwd": "/work/demo", "timestamp": ts, "origin": {"kind": "human"},
                     "message": {"role": "user", "content": ask}})
        rows.append({"type": "assistant", "timestamp": ts, "message": {"content": [{"type": "text", "text": answer}]}})
    path = root / "-work-demo" / f"{sid}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _vault(tmp_path: Path, template: str, sessions: dict[str, list[tuple[str, str]]]) -> tuple[Path, dict]:
    vault = tmp_path / "vault"
    if template == "en":
        sys.path.insert(0, str(SCRIPTS))
        import zones

        zones.lay_out(REPO / "template", vault, alias_sample=SCRIPTS / "canonical_sources.psv")
    else:
        shutil.copytree(REPO / "template-zh", vault)
    claude = tmp_path / "claude"
    for sid, turns in sessions.items():
        _session(claude, sid, turns)
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_CLAUDE_PROJECTS": str(claude),
           "KROUTER_CODEX_SESSIONS": str(tmp_path / "codex"), "KROUTER_CURSOR_PROJECTS": str(tmp_path / "cursor"),
           "KROUTER_STATE_DIR": str(tmp_path / "state"), "KROUTER_CACHE_DIR": str(tmp_path / "cache"),
           "KROUTER_NO_QUERY_LOG": "1"}
    for k in [k for k in env if k.endswith("_API_KEY")]:
        env.pop(k)
    res = subprocess.run([sys.executable, str(IMPORT), "--days", "7"], env=env, capture_output=True, text=True,
                         timeout=120)
    assert res.returncode == 0, res.stderr
    return vault, env


def _ask(env: dict, q: str) -> str:
    return subprocess.run([sys.executable, str(ROUTE), "search", q], env=env, capture_output=True, text=True,
                          timeout=60).stdout


@pytest.mark.parametrize("lang,q,answer", [
    ("en", "What is the production database password of the billing service?",
     "The vault has nothing on that; recall: none."),
    ("zh", "账单服务的生产数据库密码是什么？", "库里没有这方面的记录。"),
])
def test_your_own_earlier_question_is_not_an_answer(tmp_path, lang, q, answer):
    vault, env = _vault(tmp_path, lang, {"aaaa1111-asked": [(f"look it up: {q}" if lang == "en" else f"用 krouter 查一下：{q}",
                                                              answer)]})
    out = _ask(env, q)
    assert "recall: none" in out, out
    assert "recall_note: you asked this before" in out and "aaaa1111" in out, out
    assert "\nrecall:\n" not in out  # no page offered as an answer


def test_an_answer_that_has_the_content_still_counts(tmp_path):
    q = "Which port does the billing service listen on?"
    vault, env = _vault(tmp_path, "en", {"bbbb2222-answered": [(q, "The billing service listens on port 8443, set in deploy/billing.yaml.")]})
    out = _ask(env, q)
    assert "\nrecall:\n" in out and "bbbb2222" in out.split("\nrecall:\n", 1)[1], out
    assert "you asked this before" not in out


def test_what_you_stated_yourself_still_counts(tmp_path):
    vault, env = _vault(tmp_path, "en", {"cccc3333-stated": [
        ("From now on the billing service deploys from the release branch only.", "Noted.")]})
    out = _ask(env, "Which branch does the billing service deploy from?")
    assert "\nrecall:\n" in out and "cccc3333" in out.split("\nrecall:\n", 1)[1], out
    assert "you asked this before" not in out


def test_a_manual_distill_with_no_model_lane_says_so_and_exits_normally(tmp_path):
    """The backfill's third step on a machine with no key and no logged-in CLI: one clear line, the excerpts written,
    exit 0 (it used to fail once per session)."""
    vault, env = _vault(tmp_path, "en", {"eeee5555-port": [("Which port does the api use?", "Port 8443.")]})
    env = {k: v for k, v in env.items() if not k.endswith("_API_KEY")}
    env.update({"PATH": "/usr/bin:/bin", "KROUTER_KEYS_ENV": str(tmp_path / "no-keys.env"), "HOME": str(tmp_path / "h"),
                "USERPROFILE": str(tmp_path / "h")})
    env.pop("KROUTER_LEARN_CLI", None)
    res = subprocess.run([sys.executable, str(IMPORT), "--days", "3650", "--distill", "--distill-max", "40"], env=env,
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    assert res.stderr.count("distill skipped: no model lane") == 1, res.stderr
    row = json.loads([ln for ln in res.stdout.splitlines() if ln.startswith("{")][-1])
    assert row["pages"] == 1 and row["distilled"] == 0 and row["distill_failed"] == 0 and row["distill_skipped"]
