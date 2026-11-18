"""The host lane (llm.py): with no key, KRouter borrows the agent the user already has through its official CLI,
at most so many calls a day, each one recorded where the user can see it, and off with one switch. A shell-script
stand-in plays the CLI: no test spends a subscription."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="the fake CLI is a shell script")


@pytest.fixture()
def lane(monkeypatch, tmp_path):
    import llm

    for k in list(os.environ):
        if k.endswith(("_API_KEY", "_BASE_URL", "_MODEL")) or k in ("KROUTER_LEARN_CLI", "KROUTER_WRITER",
                                                                       "KROUTER_HOST_CLI", "KROUTER_HOST_CLI_MAX"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("KROUTER_KEYS_ENV", str(tmp_path / "none.env"))
    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path / "state"))
    cli = tmp_path / "bin/claude"
    cli.parent.mkdir()
    cli.write_text("#!/bin/sh\necho \"reply from the stand-in\"\n")
    cli.chmod(0o755)
    monkeypatch.setattr(llm, "detect_candidates", lambda: [cli])
    llm._CLI.clear()
    vault = tmp_path / "vault"
    vault.mkdir()
    yield llm, vault, tmp_path
    llm._CLI.clear()


def test_no_key_borrows_the_logged_in_cli_and_records_every_call(lane):
    llm, vault, tmp = lane
    assert llm.plan(vault)[0][0] == "cli"
    assert llm.complete("secret prompt text", vault).strip() == "reply from the stand-in"
    row = json.loads((tmp / "state/host-calls.jsonl").read_text().splitlines()[0])
    assert row["cli"] == "claude" and row["ok"] is True and row["chars_in"] == len("secret prompt text")
    page = (vault / llm.HOST_LOG_PAGE).read_text(encoding="utf-8")
    assert "| claude |" in page and "订阅额度" in page and "secret prompt text" not in page  # 只记元数据
    assert llm.host_calls_today() == 1


def test_daily_cap_stops_the_borrowing_quietly(lane, monkeypatch):
    llm, vault, _ = lane
    monkeypatch.setenv("KROUTER_HOST_CLI_MAX", "1")
    llm.complete("one", vault)
    with pytest.raises(llm.HostCapReached) as e:  # a NoModel: callers skip the step, as with no model
        llm.complete("two", vault)
    assert isinstance(e.value, llm.NoModel) and "KROUTER_HOST_CLI_MAX" in str(e.value)


def as_step(monkeypatch, name: str) -> None:
    import sys

    monkeypatch.setattr(sys, "argv", [f"/somewhere/{name}.py"])


def test_session_import_leaves_a_share_of_the_day_for_the_nightly_steps(lane, monkeypatch):
    """A busy day of session import does not leave the nightly steps with nothing (30 a day: import stops at 18)."""
    llm, vault, _ = lane
    monkeypatch.setenv("KROUTER_HOST_CLI_MAX", "10")
    assert llm.host_cli_kept() == 4
    as_step(monkeypatch, "import_sessions")
    for i in range(6):
        llm.complete(f"session {i}", vault)
    with pytest.raises(llm.HostCapReached) as e:
        llm.complete("a seventh session", vault)
    assert "session import" in str(e.value) and "KROUTER_HOST_CLI_MAX" in str(e.value)
    assert llm.host_calls_split() == (6, 0)
    for step in ("consolidate_topics", "consolidate_topics", "answer_cards", "reconsolidate"):
        as_step(monkeypatch, step)
        llm.complete("a nightly step", vault)
    with pytest.raises(llm.HostCapReached) as e:  # 整天的次数用完：谁都不再调
        llm.complete("an eleventh call", vault)
    assert "session import" not in str(e.value)
    assert llm.host_calls_today() == 10


def test_what_the_nightly_steps_used_is_no_longer_kept_and_import_gets_the_rest(lane, monkeypatch):
    llm, vault, _ = lane
    monkeypatch.setenv("KROUTER_HOST_CLI_MAX", "10")
    as_step(monkeypatch, "consolidate_topics")
    for i in range(3):
        llm.complete(f"topic {i}", vault)
    as_step(monkeypatch, "import_sessions")
    assert llm.host_cli_room()  # 留 4 次、夜里已用 3 次：还留 1 次，导入能用到第 9 次
    for i in range(6):
        llm.complete(f"session {i}", vault)
    assert not llm.host_cli_room() and llm.host_cli_room("answer_cards")
    assert llm.host_calls_split() == (6, 3)


def test_the_nightly_steps_may_use_more_than_their_share_when_import_left_room(lane, monkeypatch):
    llm, vault, _ = lane
    monkeypatch.setenv("KROUTER_HOST_CLI_MAX", "5")
    as_step(monkeypatch, "consolidate_topics")
    for i in range(5):
        llm.complete(f"topic {i}", vault)
    assert llm.host_calls_split() == (0, 5) and not llm.host_cli_room("import_sessions")


def test_a_cap_too_small_to_split_keeps_nothing_back(lane, monkeypatch):
    llm, vault, _ = lane
    monkeypatch.setenv("KROUTER_HOST_CLI_MAX", "2")
    assert llm.host_cli_kept() == 0
    as_step(monkeypatch, "import_sessions")
    llm.complete("one", vault)
    llm.complete("two", vault)
    assert llm.host_calls_split() == (2, 0)


def test_one_switch_turns_it_off_and_says_what_is_off(lane, monkeypatch):
    llm, vault, _ = lane
    monkeypatch.setenv("KROUTER_HOST_CLI", "0")
    assert llm.plan(vault) == []
    with pytest.raises(llm.NoModel):
        llm.complete("x", vault)
    rep = llm.channel_report(vault)
    assert rep["lane"] == "none" and rep["host_cli"].startswith("off") and "问答卡" in rep["off_without_model"]
    monkeypatch.setenv("KROUTER_LEARN_CLI", str(llm.detect_candidates()[0]))  # 点名的 CLI 也一样关
    assert llm.plan(vault) == []


def test_a_key_the_user_set_still_goes_before_the_borrowed_cli(lane, monkeypatch):
    llm, vault, _ = lane
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    assert [k for k, _ in llm.plan(vault)] == ["api:DEEPSEEK_API_KEY", "cli"]


def test_nightly_report_says_what_is_off_without_a_lane(lane, monkeypatch):
    llm, vault, _ = lane
    import nightly

    monkeypatch.setenv("KROUTER_HOST_CLI", "0")
    text = "\n".join(nightly.channel_lines(vault))
    assert "off" in text and "这些功能没开" in text and "会话提炼" in text
