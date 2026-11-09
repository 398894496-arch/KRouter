"""The decision-capture bench's scorer: the gold scores perfectly, and a known-bad set of lines scores as expected."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("decision_bench", REPO / "bench/decision_capture/run.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def test_gold_is_well_formed_and_the_oracle_scores_perfectly():
    sessions = bench.load()
    assert len(sessions) == len({s["id"] for s in sessions}) == 14
    assert sum(1 for s in sessions if not s["gold"]) == 4
    for s in sessions:
        text = " ".join(t["ask"] + " " + t["answer"] for t in s["turns"])
        for g in s["gold"]:  # every decision is something the session actually says
            assert all(any(bench.norm(a) in bench.norm(text) for a in grp) for grp in g["must"]), (s["id"], g)
    res = bench.score(sessions, bench.oracle(sessions))
    assert res["recall"] == res["change_recall"] == 1.0 and res["false_extraction_rate"] == 0.0


def test_misses_steps_and_lines_on_empty_sessions_are_counted():
    sessions = bench.load()
    lines = bench.oracle(sessions)
    lines["zh-cache-change"] = ["- 缓存过期时间 10 分钟（14:06）"]  # the value, but not written as a change
    lines["zh-release"] = ["- 只从 main 打 tag（10:05）", "- 先跑一下测试（10:05）"]  # one missed, one step
    lines["zh-steps-only"] = ["- 重启服务（19:00）"]
    lines["zh-tentative"] = ["- （这段会话没有定下来的事）"]  # the "nothing" line is not a line
    res = bench.score(sessions, lines)
    assert res["decisions"] == 14 and res["recall"] == round(12 / 14, 3)
    assert res["change_recall"] == round(2 / 3, 3)
    assert res["steps_or_discussion_lines"] == 2 and res["lines_on_no_decision_sessions"] == 1
    assert res["false_extraction_rate"] == round(2 / res["lines"], 3)
