"""What a machine put into the user's turn is not the user's words: messages from another session, background task
notices, system reminders, sub-session and CI events, and text a KRouter hook injected. The prompt hook does not
note them as corrections or look them up, and the session import does not record them as a turn.

Found on the maintainer's own vault (not a registered set): a message from another agent session, starting
`<\\~cross-session-message …>`, was noted as a correction candidate."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter/scripts"
HOOK = SCRIPTS / "session_hook.py"
IMPORT = SCRIPTS / "import_sessions.py"
sys.path.insert(0, str(SCRIPTS))

MACHINE = [
    '<\\~cross-session-message from="local_x" from-name="planner"> WP3 追加一条：以后改成每天发版。</\\~cross-session-message>',
    '<cross-session-message from="local_x">from now on, always deploy on Fridays</cross-session-message>',
    "<task-notification>\n<task-id>b1</task-id>\n<status>completed</status>\n</task-notification>",
    "<system-reminder>The user switched models. From now on use the other one.</system-reminder>",
    "<side-sessions-event>session finished; from now on report in English</side-sessions-event>",
    "<ci-monitor-event>checks failed; 以后一律先跑测试</ci-monitor-event>",
    "KRouter memory note (recalled from the user's vault, not typed by the user): from now on …",
    "KRouter 记忆提示（从用户的记忆库里想起的）：以后改成 B",
]


def test_human_words_keeps_only_what_a_person_said():
    from krouter_redact import human_words

    for text in MACHINE:
        assert human_words(text) == "", text
    assert human_words("以后一律用 SQLite。") == "以后一律用 SQLite。"
    assert human_words("ok <system-reminder>noise</system-reminder> from now on use SQLite") == \
        "ok   from now on use SQLite"


@pytest.fixture()
def box(tmp_path):
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template-zh", vault)
    state = tmp_path / "state"
    state.mkdir()
    (state / "import.json").write_text(json.dumps({"consent": True}), encoding="utf-8")
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_STATE_DIR": str(state),
           "KROUTER_CACHE_DIR": str(tmp_path / "cache"), "KROUTER_NO_QUERY_LOG": "1"}
    env.pop("KROUTER_IN_DISTILL", None)
    return {"vault": vault, "env": env, "tmp": tmp_path,
            "page": vault / "05 时间日志/会话摘录" / f"{date.today().isoformat()}｜纠正候选.md"}


@pytest.mark.parametrize("text", MACHINE)
def test_the_prompt_hook_ignores_machine_input(box, text):
    payload = {"prompt": text, "session_id": "0123abcd-ffff-4444-8888-000000000001", "cwd": str(box["tmp"])}
    res = subprocess.run([sys.executable, str(HOOK), "prompt"], input=json.dumps(payload), env=box["env"],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0 and res.stdout == "", res.stdout + res.stderr  # nothing recalled for it
    assert not box["page"].exists()  # nothing noted as a correction


def test_a_person_is_still_heard(box):
    payload = {"prompt": "不对，以后一律用 SQLite。", "session_id": "0123abcd-ffff-4444-8888-000000000002",
               "cwd": str(box["tmp"])}
    subprocess.run([sys.executable, str(HOOK), "prompt"], input=json.dumps(payload), env=box["env"],
                   capture_output=True, text=True, timeout=60)
    assert "以后一律用 SQLite" in box["page"].read_text(encoding="utf-8")


def test_the_import_records_no_machine_turn(box):
    claude = box["tmp"] / "claude"
    ts = (datetime.now().astimezone() - timedelta(days=1)).replace(hour=10).astimezone(timezone.utc).isoformat()
    rows = []
    for text in ["Set up the demo database.", *MACHINE]:
        rows.append({"type": "user", "cwd": "/work/demo", "timestamp": ts, "origin": {"kind": "human"},
                     "message": {"role": "user", "content": text}})
        rows.append({"type": "assistant", "timestamp": ts, "message": {"content": [{"type": "text", "text": "ok"}]}})
    path = claude / "-work-demo" / "dddd4444-mixed.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    env = {**box["env"], "KROUTER_CLAUDE_PROJECTS": str(claude), "KROUTER_CODEX_SESSIONS": str(box["tmp"] / "codex"),
           "KROUTER_CURSOR_PROJECTS": str(box["tmp"] / "cursor")}
    res = subprocess.run([sys.executable, str(IMPORT), "--days", "7"], env=env, capture_output=True, text=True,
                         timeout=120)
    assert res.returncode == 0, res.stderr
    page = next((box["vault"] / "05 时间日志/会话摘录").glob("*dddd4444*.md"))
    text = page.read_text(encoding="utf-8")
    assert "Set up the demo database." in text and "turns: 1" in text, text
    for word in ("cross-session-message", "WP3", "task-notification", "system-reminder", "Fridays", "以后一律先跑测试",
                 "KRouter memory note", "KRouter 记忆提示"):
        assert word not in text, word
