"""bench/longmemeval/qa.py: the benchmark's prompts, its history format and its yes/no parse."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lme_qa", ROOT / "bench" / "longmemeval" / "qa.py")
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)

ITEM = {
    "question_id": "q1", "question_type": "temporal-reasoning", "question": "When?", "answer": "Monday",
    "question_date": "2023/05/30 (Tue) 10:00",
    "haystack_session_ids": ["s_late", "s_early"],
    "haystack_dates": ["2023/05/20 (Sat) 09:00", "2023/05/10 (Wed) 09:00"],
    "haystack_sessions": [[{"role": "user", "content": "late"}], [{"role": "user", "content": " early "}]],
}


def test_history_is_the_cited_sessions_sorted_by_date_in_the_nl_format():
    h = qa.history(ITEM, ["05 时间日志/会话摘录/2023-05-20 s_late.md", "x/2023-05-10 s_early.md", "x/2023-05-10 s_early.md"])
    assert h.index("early") < h.index("late")
    assert "### Session 1:\nSession Date: 2023/05/10 (Wed) 09:00\nSession Content:\n\n\nuser: early\n" in h
    assert qa.history(ITEM, []) == qa.NO_HISTORY


def test_judge_prompts_follow_the_type_and_abstention():
    assert "off-by-one" in qa.judge_prompt(ITEM, "Monday")
    abs_item = dict(ITEM, question_id="q1_abs", question_type="multi-session")
    assert qa.judge_prompt(abs_item, "no idea").startswith("I will give you an unanswerable question")


def test_the_original_parse_and_missing_verdicts_count_as_wrong(tmp_path, capsys):
    assert qa.correct("Yes.") and qa.correct(" yes") and not qa.correct("No")
    data = tmp_path / "d.json"
    data.write_text(json.dumps([ITEM, dict(ITEM, question_id="q2")]), encoding="utf-8")
    (tmp_path / "v").mkdir()
    (tmp_path / "v" / "a.jsonl").write_text(json.dumps({"qid": "q1", "verdict": "yes"}) + "\n", encoding="utf-8")
    qa.score(type("A", (), {"data": str(data), "verdicts": str(tmp_path / "v"), "seed": 1})())
    out = json.loads(capsys.readouterr().out)
    assert out["accuracy"]["all"]["right"] == 1 and out["accuracy"]["all"]["of"] == 2
