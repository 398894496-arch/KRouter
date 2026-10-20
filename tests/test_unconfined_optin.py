"""A CLI KRouter cannot confine is never picked on its own: only grok and claude are used without asking.

opencode, kimi, pi, vibe, antigravity and cursor-agent run with no sandbox or allow-list KRouter can set, and the
vault holds untrusted text (clipped pages, pasted chats). A logged-in one is skipped unless the host says
`KROUTER_ALLOW_UNCONFINED=1` (environment or keys file); a confined CLI further down the list wins instead.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="the fake CLIs are shell scripts")


def _fake(path: Path) -> Path:
    """A CLI whose every login probe succeeds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture()
def llm(monkeypatch, tmp_path):
    import llm as mod

    for k in list(os.environ):
        if k.endswith(("_API_KEY", "_BASE_URL", "_MODEL")) or k in ("KROUTER_LEARN_CLI", "KROUTER_WRITER",
                                                                    "KROUTER_ALLOW_UNCONFINED", "KROUTER_ALLOW_CODEX"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("KROUTER_KEYS_ENV", str(tmp_path / "keys.env"))
    mod._CLI.clear()
    yield mod
    mod._CLI.clear()


def test_unconfined_cli_is_skipped_for_a_confined_one(llm, monkeypatch, tmp_path):
    opencode, claude = _fake(tmp_path / "bin/opencode"), _fake(tmp_path / "bin/claude")
    monkeypatch.setattr(llm, "detect_candidates", lambda: [opencode, claude])
    assert llm.detect_writer() == (str(claude), "claude:ok")


def test_unconfined_cli_alone_is_reported_not_used(llm, monkeypatch, tmp_path):
    kimi = _fake(tmp_path / "bin/kimi")
    monkeypatch.setattr(llm, "detect_candidates", lambda: [kimi])
    path, result = llm.detect_writer()
    assert (path, result) == (str(kimi), "kimi:unconfined") and not llm.writer_ok(result)
    assert llm.logged_in_cli() == "" and llm.plan(None) == []


def test_pinned_unconfined_cli_still_needs_the_opt_in(llm, tmp_path):
    vibe = _fake(tmp_path / "bin/vibe")
    assert llm.detect_writer(str(vibe)) == (str(vibe), "vibe:unconfined")


def test_opt_in_from_env_or_keys_file(llm, monkeypatch, tmp_path):
    opencode = _fake(tmp_path / "bin/opencode")
    monkeypatch.setattr(llm, "detect_candidates", lambda: [opencode])
    monkeypatch.setenv("KROUTER_ALLOW_UNCONFINED", "1")
    assert llm.detect_writer() == (str(opencode), "opencode:ok")
    monkeypatch.delenv("KROUTER_ALLOW_UNCONFINED")
    (tmp_path / "keys.env").write_text("KROUTER_ALLOW_UNCONFINED=1\n", encoding="utf-8")
    assert llm.detect_writer() == (str(opencode), "opencode:ok")


def test_named_learn_cli_follows_the_same_rule(llm, monkeypatch, tmp_path):
    opencode, claude = _fake(tmp_path / "bin/opencode"), _fake(tmp_path / "bin/claude")
    monkeypatch.setattr(llm, "detect_candidates", lambda: [])
    monkeypatch.setenv("KROUTER_LEARN_CLI", str(opencode))
    assert ("cli", str(opencode)) not in llm.plan(None)
    monkeypatch.setenv("KROUTER_LEARN_CLI", str(claude))
    assert llm.plan(None)[0] == ("cli", str(claude))


def test_codex_is_not_picked_on_its_own(llm, monkeypatch, tmp_path):
    """Codex writes only the vault but reads the whole account: a confined lane further down wins; alone, it is
    reported as `codex:reads-account` and not used."""
    codex = _fake(tmp_path / "bin/codex")
    claude = _fake(tmp_path / "bin/claude")
    monkeypatch.setattr(llm, "detect_candidates", lambda: [codex, claude])
    assert llm.detect_writer() == (str(claude), "claude:ok")
    monkeypatch.setattr(llm, "detect_candidates", lambda: [codex])
    path, result = llm.detect_writer()
    assert (path, result) == (str(codex), "codex:reads-account") and not llm.writer_ok(result)


def test_codex_is_used_when_named_or_allowed(llm, monkeypatch, tmp_path):
    codex = _fake(tmp_path / "bin/codex")
    assert llm.detect_writer(str(codex)) == (str(codex), "codex:ok")  # KROUTER_WRITER 点名
    monkeypatch.setattr(llm, "detect_candidates", lambda: [codex])
    (tmp_path / "keys.env").write_text("KROUTER_ALLOW_CODEX=1\n", encoding="utf-8")
    assert llm.detect_writer() == (str(codex), "codex:ok")


def test_claude_writer_tools_are_all_scoped_to_the_vault(tmp_path):
    """A bare `Glob` or `Grep` in the allow-list lets the claude writer read any file in the account (a bare Grep
    printed a canary line from outside the vault). Every file tool carries the vault path."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extras/host-daily-evolution"))
    import resolve

    vault = tmp_path / "vault"
    allow = resolve.claude_allow(vault, tmp_path / "route_knowledge.sh")
    for tool in ("Read", "Edit", "Glob", "Grep"):
        assert tool not in allow, f"bare {tool} in the claude allow-list"
        assert f"{tool}(/{vault}/**)" in allow
    assert all(a.startswith(("Read(", "Edit(", "Glob(", "Grep(", "Bash(")) for a in allow)
