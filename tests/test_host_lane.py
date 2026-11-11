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
