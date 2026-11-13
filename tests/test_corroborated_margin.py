"""Set 45, C1a: page keywords with no model (`page_keys.py`, the index's `kw` table) and the prompt hook's corroborated
margin (`recollect.margin_low`): a full-text top page less than `RECALL_MARGIN` ahead is brought only when the lower margin
is switched on, it is at least that far ahead, and a keyword only that page has is in the message. Off by default, and off
means the old path, untouched."""

from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skill/krouter/scripts"))
import page_keys  # noqa: E402
import recall_index as ri  # noqa: E402
import recollect  # noqa: E402


def _page(v: Path, rel: str, meta: str, body: str) -> None:
    p = v / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{meta}\n---\n\n{body}\n", encoding="utf-8")


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    v = tmp_path / "vault"
    _page(v, "团队手册/灰度发布.md", "title: 灰度发布\nstatus: active\naliases: [canary]",
          "# 灰度发布\n\n先放 **百分之五** 的流量，盯 `error_rate` 半小时再全量。\n\n## 回滚条件\n\n错误率翻倍就回滚。")
    _page(v, "团队手册/发布窗口.md", "title: 发布窗口\nstatus: active", "# 发布窗口\n\n周五下午不发布。回滚条件见值班表。")
    _page(v, "团队手册/旧灰度.md", "title: 旧灰度\nstatus: superseded\nsuperseded_by: \"[[灰度发布]]\"", "以前直接全量。")
    _page(v, "05 时间日志/会话摘录/2026-11-01 灰度.md", "title: 会话 灰度复盘\ntype: session-excerpt", "聊了 FooBarBaz。")
    _page(v, "团队手册/密钥轮换.md", "title: 密钥轮换\nstatus: active\nsecret: true", "# 密钥轮换\n\n九十天一次。")
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("KROUTER_NO_QUERY_LOG", "1")
    monkeypatch.delenv(recollect.MARGIN_LOW_ENV, raising=False)
    monkeypatch.delenv(recollect.KEYWORDS_MIN_ENV, raising=False)
    con = ri.connect(ri.cache_path(v))
    ri.refresh(v, con)
    con.close()
    return v


def _kw(v: Path) -> dict[str, set[tuple[str, str]]]:
    con = sqlite3.connect(ri.cache_path(v))
    out: dict[str, set] = {}
    for term, rel, kind in con.execute("SELECT term, rel, kind FROM kw"):
        out.setdefault(rel, set()).add((term, kind))
    con.close()
    return out


def test_keywords_come_from_names_headings_bold_and_identifiers(vault):
    kw = _kw(vault)
    terms = {t for t, _k in kw["团队手册/灰度发布.md"]}
    assert {"灰度发布", "canary", "回滚条件", "百分之五", "errorrate"} <= terms
    assert ("灰度发布", "title") in kw["团队手册/灰度发布.md"]
    # 被取代的页、日志页、机密页没有关键词
    assert "团队手册/旧灰度.md" not in kw
    assert "05 时间日志/会话摘录/2026-11-01 灰度.md" not in kw
    assert "团队手册/密钥轮换.md" not in kw


def test_keywords_follow_the_page(vault):
    (vault / "团队手册/灰度发布.md").unlink()
    con = ri.connect(ri.cache_path(vault))
    ri.refresh(vault, con)
    con.close()
    assert "团队手册/灰度发布.md" not in _kw(vault)


def test_norm_matches_the_hook():
    for s in ("Error Rate", "灰度 发布！", "error_rate", "的了灰度"):
        assert page_keys.norm(s) == recollect.norm(s)


def test_switch_reads_the_environment(monkeypatch):
    monkeypatch.delenv(recollect.MARGIN_LOW_ENV, raising=False)
    assert recollect.margin_low() is None
    for bad in ("0", "2.5", "3", "0.9", "x"):
        monkeypatch.setenv(recollect.MARGIN_LOW_ENV, bad)
        assert recollect.margin_low() is None
    monkeypatch.setenv(recollect.MARGIN_LOW_ENV, "1.5")
    assert recollect.margin_low() == (1.5, 1)
    monkeypatch.setenv(recollect.KEYWORDS_MIN_ENV, "2")
    assert recollect.margin_low() == (1.5, 2)


def _res(rel: str, margin: float) -> dict:
    return {"hits": [{"rel": rel, "tier": "rule"}], "confidence": "medium", "margin": margin, "query_tokens": ["灰度"]}


def test_corroborated_margin(vault, monkeypatch):
    rel = "团队手册/灰度发布.md"
    said = "上次说的灰度发布要先放多少流量来着"
    today = date(2026, 11, 14)
    # 关着：领先 1.8 不递（原规则）
    assert recollect._recall_hits(vault, _res(rel, 1.8), today, set(), said) == []
    monkeypatch.setenv(recollect.MARGIN_LOW_ENV, "1.5")
    got = recollect._recall_hits(vault, _res(rel, 1.8), today, set(), said)
    assert [h["real"] for h in got] == [rel] and got[0]["word"] == "灰度发布"
    # 领先低于较低倍数：不递
    assert recollect._recall_hits(vault, _res(rel, 1.4), today, set(), said) == []
    # 消息里没有这页特有的关键词：不递
    assert recollect._recall_hits(vault, _res(rel, 1.8), today, set(), "流量要先放多少") == []
    # 要两个关键词时，一个不够
    monkeypatch.setenv(recollect.KEYWORDS_MIN_ENV, "2")
    assert recollect._recall_hits(vault, _res(rel, 1.8), today, set(), said) == []
    assert recollect._recall_hits(vault, _res(rel, 1.8), today, set(), said + "，回滚条件呢") != []


def test_a_keyword_two_pages_have_does_not_corroborate(vault, monkeypatch):
    _page(vault, "团队手册/灰度发布手册.md", "title: 灰度发布\nstatus: active", "另一页也叫灰度发布。")
    con = ri.connect(ri.cache_path(vault))
    ri.refresh(vault, con)
    con.close()
    monkeypatch.setenv(recollect.MARGIN_LOW_ENV, "1.5")
    assert recollect.corroborating(vault, "团队手册/灰度发布.md", "灰度发布怎么放量") == []


def test_full_margin_and_the_old_rules_are_unchanged(vault, monkeypatch):
    rel = "团队手册/灰度发布.md"
    today = date(2026, 11, 14)
    monkeypatch.setenv(recollect.MARGIN_LOW_ENV, "1.5")
    # 领先够 2.5：照旧递，不看关键词，word 照旧是查询词
    got = recollect._recall_hits(vault, _res(rel, 3.0), today, set(), "随便")
    assert [h["real"] for h in got] == [rel] and got[0]["word"] == "灰度"
    # 被取代的页、日志页照旧不递
    old = {"hits": [{"rel": "团队手册/旧灰度.md", "tier": "dead"}], "confidence": "medium", "margin": 1.8}
    assert recollect._recall_hits(vault, old, today, set(), "旧灰度 灰度发布") == []


def test_off_never_reads_the_keywords(vault, monkeypatch):
    monkeypatch.delenv(recollect.MARGIN_LOW_ENV, raising=False)

    def boom(*_a, **_k):
        raise AssertionError("keywords read while the switch is off")

    monkeypatch.setattr(recollect, "corroborating", boom)
    for m in (1.0, 1.6, 2.4, 3.0):
        recollect._recall_hits(vault, _res("团队手册/灰度发布.md", m), date(2026, 11, 14), set(), "灰度发布")
    recollect.recollect(vault, "灰度发布要先放多少流量", use=("alias", "trigger", "recall"))


def test_missing_table_is_no_corroboration(tmp_path, monkeypatch):
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "nocache"))
    assert recollect.corroborating(tmp_path / "v", "a.md", "灰度发布") == []
