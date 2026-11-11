"""Paragraph-level evidence (evidence.py, set 39): cutting pages into paragraphs, speakers, answer types, time cues,
and what recall does with them."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skill/krouter/scripts"))

import evidence as ev  # noqa: E402
import recall_index as ri  # noqa: E402


def test_blocks_follow_turns_and_paragraphs():
    body = ("**user:** I lead a team of 4 engineers.\n\n**assistant:** That is a good size.\n1. **Tip**: keep it\n\n"
            "**user:** thanks\n- **问**（10:02）：怎么发版\n  **答**：先跑测试")
    got = ev.blocks(body)
    assert [b[3] for b in got] == ["user", "assistant", "user", "问", "答"]
    assert got[0][0] == 0 and got[1][0] == 2  # 行号相对正文，从 0 起
    assert "**Tip**" in got[1][2]  # 列表里的加粗不是说话人


def test_answer_types_and_their_text():
    assert ev.answer_type("How many fish are in my tank?") == "count"
    assert ev.answer_type("How long was I in Japan?") == "duration"
    assert ev.answer_type("How often do I see Dr. Smith?") == "freq"
    assert ev.answer_type("What is the total cost of the headphones?") == "money"
    assert ev.answer_type("When did I book the hotel?") == "date"
    assert ev.answer_type("上次发版是什么时候") == "date"
    assert ev.answer_type("服务器多少钱一个月") == "money"
    assert ev.answer_type("我一周去几次健身房？") == "count"
    assert ev.answer_type("What is the name of my hamster?") is None  # 拿不准的类型不检查
    assert ev.has_type("I stayed for two weeks", "duration") and not ev.has_type("I loved it", "duration")
    assert ev.has_type("花了 300 元", "money") and ev.tags_have(ev.type_tags("every Sunday"), "freq")


def test_time_window():
    now = dt.date(2023, 5, 30)
    assert ev.time_window("What did I bake in the past two weeks?", now) == (dt.date(2023, 5, 16), now)
    assert ev.time_window("museums I visited in December", now) == (dt.date(2022, 12, 1), dt.date(2022, 12, 31))
    assert ev.time_window("from July to October", dt.date(2023, 11, 1)) == (dt.date(2023, 7, 1), dt.date(2023, 10, 31))
    assert ev.time_window("上周六去哪了", now) == (dt.date(2023, 5, 26), dt.date(2023, 5, 28))
    assert ev.time_window("What may happen next?", now) is None
    assert ev.time_window("How do I deploy?", now) is None


def test_aggregate_questions():
    assert ev.aggregate("How many times did I bake this month?")
    assert ev.aggregate("这个项目一共用了哪些服务？")
    assert not ev.aggregate("What is my cat's name?")


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture()
def chat(tmp_path, monkeypatch):
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("KROUTER_NO_QUERY_LOG", "1")
    monkeypatch.delenv("KROUTER_MAP", raising=False)
    v = tmp_path / "v"
    _write(v, "krouter-zones.psv", "@lang|en\n")
    turns = []
    for i in range(12):
        turns.append(f"**Caroline:** I went hiking with my sister on day {i}, the trail was steep.")
        turns.append(f"**Melanie:** I painted a sunset over the lake on day {i}, it took all afternoon.")
    _write(v, "05 时间日志/会话摘录/2023-05-08 session_1.md",
           "---\ndate: 2023-05-08\n---\n\n# Session 1\n\n" + "\n\n".join(turns) + "\n")
    for i in range(30):
        _write(v, f"Notes/other {i}.md", f"# Other {i}\n\nGroceries, laundry and the weekly plan number {i}.\n")
    return v


def test_paragraph_index_and_evidence(chat):
    res = ri.recall(chat, "What sunset over the lake was painted by Melanie?")
    assert res["confidence"] != "none"
    top = res["hits"][0]
    assert top["rel"].endswith("session_1.md")
    e = top["ev"]
    assert e["pc"] > 0.5 and e["l0"] >= 7 and e["bind"] >= e["bind_other"]


def test_question_about_the_other_speaker_is_refused(chat):
    """LoCoMo's adversarial questions: the thing was said by the other person. Caroline never painted."""
    res = ri.recall(chat, "What sunset over the lake was painted by Caroline?")
    assert res["confidence"] == "none" and res.get("evidence_none") == "other-speaker"
    ok = ri.recall(chat, "What did Caroline say about hiking with her sister on the trail?")
    assert ok["confidence"] != "none"


def test_receipt_names_the_passage(chat):
    import io
    from contextlib import redirect_stdout

    import route_knowledge

    res = ri.recall(chat, "What sunset over the lake was painted by Melanie?")
    buf = io.StringIO()
    with redirect_stdout(buf):
        route_knowledge.print_recall(res, chat, 1, "What sunset over the lake was painted by Melanie?")
    assert "(passage L" in buf.getvalue()
