"""Hot and cold (hot.py): experience cards and trigger phrases unused for hot_days days sort after the others."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

import experience
import hot
import recollect

TODAY = dt.date(2026, 11, 12)


def _card(v: Path, cid: str, day: str, when: str, lesson: str) -> None:
    p = v / experience.FOLDER / f"经验｜{cid}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\ntype: {experience.TYPE}\ncard_id: {cid}\ndate: {day}\nstatus: active\nwhen: {when}\n---\n\n"
                 f"- 通用说法：{lesson}\n", encoding="utf-8")


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("KROUTER_TODAY", TODAY.isoformat())
    monkeypatch.delenv("KROUTER_HOT_DAYS", raising=False)
    v = tmp_path / "v"
    v.mkdir()
    return v


def test_window_edges():
    assert not hot.cold("", (TODAY - dt.timedelta(days=59)).isoformat(), 60, TODAY)
    assert hot.cold("", (TODAY - dt.timedelta(days=60)).isoformat(), 60, TODAY)
    assert not hot.cold((TODAY - dt.timedelta(days=1)).isoformat(), "2020-01-01", 60, TODAY)  # 最近用过
    assert not hot.cold("", "", 60, TODAY)  # 日期不知道：不降
    assert not hot.cold("", "2020-01-01", None, TODAY)  # 关掉


def test_settings_and_env(vault, monkeypatch):
    assert hot.days(vault) == 60
    (vault / "krouter-settings.psv").write_text("hot_days|30\n", encoding="utf-8")
    assert hot.days(vault) == 30
    (vault / "krouter-settings.psv").write_text("hot_days|off\n", encoding="utf-8")
    assert hot.days(vault) is None
    monkeypatch.setenv("KROUTER_HOT_DAYS", "45")
    assert hot.days(vault) == 45


def test_cold_card_sorts_after_and_comes_back_when_adopted(vault):
    old = (TODAY - dt.timedelta(days=60)).isoformat()
    _card(vault, "C01", old, "部署失败", "部署失败时先看日志")
    _card(vault, "C02", (TODAY - dt.timedelta(days=59)).isoformat(), "部署失败", "部署失败时先回滚")
    order = [c["id"] for c in experience.ranked(experience.load_cards(vault), experience.usage(vault), vault)]
    assert order == ["C02", "C01"]
    got = experience.suggest(vault, "部署失败了怎么办")
    assert [c["id"] for c in got][-1] == "C01" and got[-1]["cold"]
    # 被采用一次：当场恢复，而且排到最前（采用过的在前）
    uses = vault / experience.USES
    uses.parent.mkdir(parents=True, exist_ok=True)
    uses.write_text(json.dumps({"at": TODAY.isoformat() + "T09:00:00", "card": "C01", "kind": "adopted"}) + "\n",
                    encoding="utf-8")
    order = [c["id"] for c in experience.ranked(experience.load_cards(vault), experience.usage(vault), vault)]
    assert order == ["C01", "C02"]
    # 只被递出去不算激活
    uses.write_text(json.dumps({"at": TODAY.isoformat() + "T09:00:00", "card": "C01", "kind": "offered"}) + "\n",
                    encoding="utf-8")
    assert experience.ranked(experience.load_cards(vault), experience.usage(vault), vault)[0]["id"] == "C02"


def test_off_means_no_demotion(vault):
    (vault / "krouter-settings.psv").write_text("hot_days|off\n", encoding="utf-8")
    _card(vault, "C01", "2020-01-01", "部署失败", "部署失败时先看日志")
    _card(vault, "C02", "2026-11-01", "部署失败", "部署失败时先回滚")
    assert not any(c["cold"] for c in experience.suggest(vault, "部署失败了怎么办"))


def _trigger_vault(v: Path) -> None:
    for name in ("发版流程", "回滚流程", "值班交接"):
        p = v / "02 经验与方法" / f"{name}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"---\nstatus: active\nhow: {name}的做法\n---\n# {name}\n\n{name}的做法。\n", encoding="utf-8")
    t = v / "90 系统文件/自动化/下意识触发词.psv"
    t.parent.mkdir(parents=True, exist_ok=True)
    t.write_text("02 经验与方法/发版流程.md|周五上线计划\n02 经验与方法/回滚流程.md|线上出事倒回去\n", encoding="utf-8")


def test_cold_trigger_gives_up_its_place_and_is_restored_when_brought(vault, monkeypatch):
    _trigger_vault(vault)
    monkeypatch.setattr(recollect, "GATE", False)
    rep = hot.nightly(vault)  # 第一晚：记下 first_seen，都不冷
    assert rep["triggers_total"] == 2 and rep["triggers_cold"] == []
    monkeypatch.setenv("KROUTER_TODAY", (TODAY + dt.timedelta(days=60)).isoformat())
    rep = hot.nightly(vault)
    assert len(rep["triggers_cold"]) == 2 and len(rep["triggers_new_cold"]) == 2
    assert "冷热" in "".join(hot.report_lines(rep))
    hits = recollect.recollect(vault, "周五上线计划和线上出事倒回去都要看一下", use=("trigger",))
    assert hits  # 冷的照样能递：只是排在后面
    left = hot.cold_triggers(vault)
    assert len(left) == 2 - len(hits)  # 递出去的当场恢复
    # 一条冷一条热：热的排前
    d = hot.load(vault)
    d["cold"] = [hot.key(recollect.norm("周五上线计划"), "02 经验与方法/发版流程.md")]
    hot._write(vault, d)
    hits = recollect.recollect(vault, "周五上线计划和线上出事倒回去都要看一下", use=("trigger",))
    assert hits[0]["rel"].endswith("回滚流程.md")


def test_rule_pages_and_recall_are_not_touched(vault):
    import recall_index as ri

    _trigger_vault(vault)
    before = [h["rel"] for h in ri.recall(vault, "发版流程的做法", gate=False)["hits"]]
    hot.nightly(vault)
    d = hot.load(vault)
    d["cold"] = [f"x|{rel}" for rel in before]
    hot._write(vault, d)
    assert [h["rel"] for h in ri.recall(vault, "发版流程的做法", gate=False)["hits"]] == before
