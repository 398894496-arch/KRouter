"""Set 50: a reply with nothing in it ("多久", "right", "装吧") must not bring a page by the full-text route just because
one page happens to hold its one word; a message that is only a name the vault has a page for still brings that page."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter/scripts"
sys.path.insert(0, str(SCRIPTS))


def _page(v: Path, rel: str, title: str, body: str) -> None:
    p = v / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\ntitle: {title}\nstatus: active\n---\n\n# {title}\n\n{body}\n", encoding="utf-8")


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    import recollect

    v = tmp_path / "vault"
    _page(v, "团队手册/客户投诉.md", "客户投诉", "客户投诉要在多久内回复：四小时内先回一句，两个工作日内给结论。")
    _page(v, "团队手册/发布流程.md", "发布流程", "发布只从 main 打 tag，发布前跑完整测试；周五不发。")
    _page(v, "团队手册/测试环境.md", "测试环境", "测试环境每天凌晨 3 点自动重置数据。")
    _page(v, "团队手册/值班.md", "值班", "值班表每月最后一个周五排好，换班要提前两天说。")
    _page(v, "团队手册/报销.md", "报销", "打车费当月报，超过三百要附说明。")
    _page(v, "Handbook/Customer data deletion.md", "Customer data deletion",
          "A deletion request is confirmed within 3 days; only the account owner has the right to ask for it.")
    _page(v, "Handbook/Model deployment.md", "Model deployment", "We ship a model only after the offline eval and a canary.")
    _page(v, "Handbook/Zentrix gateway.md", "Zentrix gateway", "All outbound calls go through the gateway; keys rotate every 90 days.")
    (v / "90 系统文件").mkdir(parents=True, exist_ok=True)
    (v / "90 系统文件/canonical_sources.psv").write_text("Z01|报销|团队手册/报销.md|打车费当月报\n", encoding="utf-8")
    for k in list(os.environ):
        if k.endswith("_API_KEY") or k in ("KROUTER_IN_DISTILL", "KROUTER_MAP", "OBSIDIAN_VAULT", "KROUTER_RECALL_GATE"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("KROUTER_VAULT", str(v))
    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("KROUTER_NO_QUERY_LOG", "1")
    subprocess.run([sys.executable, str(SCRIPTS / "recall_index.py"), "--vault", str(v), "--stats"], env=dict(os.environ),
                   capture_output=True, check=True, timeout=120)
    recollect._PAGES.clear()
    return v


def brought(v: Path, text: str) -> list[str]:
    import recollect

    return [h["rel"] for h in recollect.recollect(v, text, recollect.DEFAULT_ROUTES)]


@pytest.mark.parametrize("reply", ["多久", "要多久", "right", "is that right?", "ship it"])
def test_a_reply_whose_one_word_is_only_in_a_pages_body_brings_nothing(vault, reply):
    import recollect

    res = recollect._ranked(vault, recollect.prose(reply))
    # 前提：全文召回自己是有把握的（一页有这个词、别的页没有），所以以前会递
    assert res and res["hits"] and res["confidence"] in recollect.RECALL_CONF and res["margin"] >= recollect.RECALL_MARGIN
    assert brought(vault, reply) == []


def test_a_message_that_is_only_a_name_in_a_pages_title_still_brings_it(vault):
    assert brought(vault, "Zentrix") == ["Handbook/Zentrix gateway.md"]
    assert brought(vault, "zentrix?") == ["Handbook/Zentrix gateway.md"]


def test_a_message_with_two_words_of_the_page_is_not_touched(vault):
    assert brought(vault, "客户投诉要在多久内回复") == ["团队手册/客户投诉.md"]


def test_no_recall_index_means_the_thin_rule_says_no_and_does_not_raise(vault, tmp_path, monkeypatch):
    import recollect

    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "nowhere"))
    assert recollect._titled(vault, "Handbook/Zentrix gateway.md", ["zentrix"]) is False
