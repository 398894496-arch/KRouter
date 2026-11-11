"""The receipt names question words the top page never uses, when the confidence is not `high`.

A hint only: ranking, confidence and refusal are the lookup's own, unchanged. Not measured against any benchmark; its
effect on a reader's refusals is untested (docs/NUMBERS.md)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter/scripts"
ROUTE = SCRIPTS / "route_knowledge.py"

sys.path.insert(0, str(SCRIPTS))
import recall_index as r  # noqa: E402


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("KROUTER_NO_QUERY_LOG", "1")
    monkeypatch.delenv("KROUTER_ZONES", raising=False)
    return tmp_path


def _en_vault(tmp: Path) -> Path:
    v = tmp / "en"
    (v).mkdir()
    _write(v, "krouter-zones.psv", "@lang|en\n")
    _write(v, "Releases.md", "---\ntitle: Releases\nstatus: active\n---\n\nWe ship releases every other Thursday, "
                              "after the staging deploy has been green for a day.\n")
    _write(v, "Billing.md", "---\ntitle: Billing\nstatus: active\n---\n\nInvoices go out on the first of the month "
                            "from the billing database.\n")
    _write(v, "Hiring.md", "---\ntitle: Hiring\nstatus: active\n---\n\nInterviews are three rounds; the panel "
                            "decides within two days.\n")
    return v


def _zh_vault(tmp: Path) -> Path:
    v = tmp / "zh"
    v.mkdir()
    _write(v, "发版规则.md", "---\ntitle: 发版规则\nstatus: active\n---\n\n每两周的周四发版，预发环境连续绿灯一天之后才发。\n")
    _write(v, "账单.md", "---\ntitle: 账单\nstatus: active\n---\n\n每月一号从账单数据库出发票。\n")
    _write(v, "招聘.md", "---\ntitle: 招聘\nstatus: active\n---\n\n面试一共三轮，评审组两天内给结论。\n")
    return v


def _receipt(vault: Path, query: str) -> str:
    env = {**os.environ, "KROUTER_VAULT": str(vault), "OBSIDIAN_VAULT": str(vault)}
    out = subprocess.run([sys.executable, str(SCRIPTS / "recall_index.py"), "--vault", str(vault), "--query", query],
                         capture_output=True, text=True, env=env, check=True)
    return out.stdout


def test_english_names_the_missing_words(env):
    v = _en_vault(env)
    q = "ship releases staging billing"
    res = r.recall(v, q)
    assert res["confidence"] not in ("none", "high"), res["confidence"]
    assert res["hits"][0]["rel"] == "Releases.md"
    assert r.unseen_words(v, res, q) == ["billing"]
    note = r.unseen_note(v, res, q)
    assert note.startswith("recall_note: the top page does not mention `billing`")
    assert "treat the question as not covered" in note
    out = _receipt(v, q)
    assert note in out and out.index(note) < out.index("recall:\n")


def test_chinese_follows_the_vault_language(env):
    v = _zh_vault(env)
    q = "面试之后多久发版"
    res = r.recall(v, q)
    assert res["confidence"] not in ("none", "high"), res["confidence"]
    words = r.unseen_words(v, res, q)
    assert res["hits"][0]["rel"] == "发版规则.md" and words == ["面试"]
    note = r.unseen_note(v, res, q)
    assert note == "recall_note: 排在第一的这一页没有提到「面试」。除非页面明确写了答案，否则按库里没有处理。"


def test_nothing_added_when_confidence_is_high_or_all_words_are_on_the_page(env):
    v = _en_vault(env)
    fake = {"confidence": "high", "hits": [{"rel": "Releases.md"}], "query_tokens": []}
    assert r.unseen_words(v, fake, "releases billing") == []
    q = "when do we ship releases"
    res = r.recall(v, q)
    assert r.unseen_note(v, res, q) == ""
    assert "does not mention" not in _receipt(v, q)


def test_it_changes_no_ranking_or_confidence(env):
    v = _en_vault(env)
    q = "ship releases staging billing"
    res = r.recall(v, q)
    assert "unseen" not in " ".join(res) and res["hits"][0]["rel"] == "Releases.md"
