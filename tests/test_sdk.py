"""`import krouter`: ask, status and note from Python, the same receipts as the router."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "sdk"))
import krouter  # noqa: E402


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    v = tmp_path / "vault"
    shutil.copytree(REPO / "template", v)
    monkeypatch.setenv("KROUTER_NO_QUERY_LOG", "1")
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("OBSIDIAN_VAULT", raising=False)
    return v


def test_router_found_in_the_repository():
    assert (krouter.router_dir() / "route_knowledge.py").exists()


def test_ask_parses_the_receipt_and_says_when_the_memory_does_not_know(vault):
    a = krouter.ask("量子火锅的配方是什么", vault=vault)
    assert a.refused and "receipt_version:" in a.text and a.fields["requested_route"] == "search"
    with pytest.raises(ValueError):
        krouter.ask("x", route="rm -rf", vault=vault)


def test_status_and_note(vault, monkeypatch):
    assert "receipt_version:" in krouter.status(vault=vault).text
    msg = krouter.note("发版只从 main 打 tag", kind="decision", vault=vault)
    assert msg.startswith("noted: 05 时间日志/会话摘录/")
    with pytest.raises(ValueError):
        krouter.note("", vault=vault)
    assert "OBSIDIAN_VAULT" not in os.environ  # note() 不留下环境变量


def test_cli(vault, capsys):
    from krouter import cli

    assert cli.main(["--vault", str(vault), "ask", "量子火锅的配方是什么"]) == 0
    assert "recall: none" in capsys.readouterr().out
