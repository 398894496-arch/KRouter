"""The receipt's first line says one of three things (set 38): `memory: direct` (an alias lock or `high`), `memory:
related` (only related pages, with how to use them), `memory: none`. Strict mode hands `related` over as `none`, the
pages named on one line. Ranking, pages and confidence are untouched; strict mode is off unless switched on."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(REPO / "bench/refusal"))
import recall_index as ri  # noqa: E402
import synthetic  # noqa: E402

RELATED_Q = "值班的加班费怎么算？"     # 记忆里只有「值班交接」：相关，不是答案
NONE_Q = "咖啡机怎么除垢？"
LOCK_ALIAS = "发版流程"


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("KROUTER_NO_QUERY_LOG", "1")
    monkeypatch.delenv("KROUTER_STRICT", raising=False)
    monkeypatch.delenv("KROUTER_MAP", raising=False)
    v = tmp_path / "v"
    synthetic.lay_out(v)
    table = v / "90 系统文件/canonical_sources.psv"
    table.parent.mkdir(parents=True)
    table.write_text(f"# id|aliases|source|anchor\nRELEASE|{LOCK_ALIAS}|02 经验与方法/发版流程.md|先跑全量测试\n", encoding="utf-8")
    return v


def _receipt(v: Path, q: str, **env) -> str:
    e = {k: val for k, val in os.environ.items() if not k.endswith("_API_KEY")}
    e.update(KROUTER_VAULT=str(v), OBSIDIAN_VAULT=str(v), **env)
    out = subprocess.run([sys.executable, str(SCRIPTS / "route_knowledge.py"), "search", q], env=e, capture_output=True,
                         text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_three_states(vault):
    locked = _receipt(vault, LOCK_ALIAS).splitlines()[0]
    assert locked.startswith("memory: direct") and "注明出处" in locked
    related = _receipt(vault, RELATED_Q)
    first = related.splitlines()[0]
    assert first.startswith("memory: related") and ri.RELATED_USE["zh"] in first
    assert "recall:\n- 02 经验与方法/值班交接.md" in related  # 照常列出相关页
    none = _receipt(vault, NONE_Q).splitlines()[0]
    assert none.startswith("memory: none") and "严格模式" not in none


def test_state_is_a_fixed_function_of_confidence():
    assert ri.answer_state({"hits": [{}], "confidence": "high"}) == "direct"
    assert ri.answer_state({"hits": [{}], "confidence": "medium"}) == "related"
    assert ri.answer_state({"hits": [{}], "confidence": "low"}) == "related"
    assert ri.answer_state({"hits": [], "confidence": "none"}) == "none"
    assert ri.answer_state(None, locked=True) == "direct"


def test_the_pages_after_the_first_line_are_the_same_as_before(vault):
    """The state line is added before the receipt; the recall block is what `print_recall` printed before set 38."""
    import contextlib
    import io

    import route_knowledge as rk

    res = ri.recall(vault, RELATED_Q)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rk.print_recall(res, vault, 1, RELATED_Q)
    text = _receipt(vault, RELATED_Q)
    assert buf.getvalue() in text


def test_strict_mode_folds_related_into_none(vault):
    text = _receipt(vault, RELATED_Q, KROUTER_STRICT="1")
    lines = text.splitlines()
    assert lines[0].startswith("memory: none") and "严格模式" in lines[0]
    assert "recall: none" in text and "\nrecall:\n" not in text
    assert any(ln.startswith("related_pages: 02 经验与方法/值班交接.md") for ln in lines)
    assert _receipt(vault, LOCK_ALIAS, KROUTER_STRICT="1").startswith("memory: direct")  # 锁命中照答


def test_strict_switch_file_and_env_priority(vault, monkeypatch):
    assert ri.strict_on(vault) is False  # 默认关
    (vault / ri.SETTINGS_FILE).write_text("# settings\nstrict|on\n", encoding="utf-8")
    assert ri.strict_on(vault) is True
    assert _receipt(vault, RELATED_Q).startswith("memory: none")
    monkeypatch.setenv("KROUTER_STRICT", "0")  # 环境变量优先
    assert ri.strict_on(vault) is False
    assert _receipt(vault, RELATED_Q, KROUTER_STRICT="0").startswith("memory: related")


def test_strict_mode_keeps_the_prompt_hook_to_direct_pages(vault, monkeypatch):
    import recollect

    res = {"hits": [{"rel": "02 经验与方法/值班交接.md", "tier": "rule"}], "confidence": "medium", "margin": 9.9,
           "query_tokens": ["值班"]}
    assert recollect._recall_hits(vault, res, date.today(), set())
    monkeypatch.setenv("KROUTER_STRICT", "1")
    assert recollect._recall_hits(vault, res, date.today(), set()) == []


def test_sdk_reads_the_state(vault):
    sys.path.insert(0, str(REPO / "sdk"))
    import krouter

    for q, want in ((LOCK_ALIAS, "direct"), (RELATED_Q, "related"), (NONE_Q, "none")):
        text = _receipt(vault, q)
        assert krouter.Answer(text, krouter._parse(text)).state == want, q
