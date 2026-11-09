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


def test_page_and_how_come_from_recall_and_a_replaced_page_is_never_the_answer(capsys):
    from krouter import demo

    assert demo.run("en") == 0
    out = capsys.readouterr().out
    assert "from: 02 经验与方法/Release day, changed.md" in out
    assert "replaced, shown but not the answer: 02 经验与方法/Release day.md" in out
    assert out.count("recall: none") == 1 and "Deleted the demo memory" in out
    assert demo.run("zh") == 0 and "出处：02 经验与方法/发版日（改）.md" in capsys.readouterr().out


def test_answer_fields_on_a_recall_hit(tmp_path, monkeypatch):
    from krouter import demo

    monkeypatch.setenv("KROUTER_NO_QUERY_LOG", "1")
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    vault = demo.build(tmp_path, "en")
    a = krouter.ask("when do we ship releases", vault=vault)
    assert a.page == "02 经验与方法/Release day, changed.md" and "Tuesday" in a.how and not a.refused
    assert [h["status"] for h in a.hits][:2] == ["active", "superseded"]
    b = krouter.ask("what is our on-call rotation", vault=vault)
    assert b.refused and b.page == "" and b.how == "" and b.hits == []
