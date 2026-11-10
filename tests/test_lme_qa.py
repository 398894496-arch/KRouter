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


HAY = dict(ITEM, question="Which espresso grinder did I buy?", answer_session_ids=["s_grinder"],
           haystack_session_ids=["s_tea", "s_grinder", "s_bike", "s_none"],
           haystack_dates=["2023/05/01 (Mon) 09:00", "2023/05/02 (Tue) 09:00", "2023/05/03 (Wed) 09:00",
                           "2023/05/04 (Thu) 09:00"],
           haystack_sessions=[[{"role": "user", "content": "I buy green tea every week."}],
                              [{"role": "user", "content": "I bought the Niche espresso grinder."},
                               {"role": "assistant", "content": "A good grinder for espresso."}],
                              [{"role": "user", "content": "My bike needs a new chain."}],
                              [{"role": "user", "content": "zzz"}]])


def test_bm25_ranks_the_session_that_shares_the_question_s_words_and_drops_those_that_share_none():
    top = qa.bm25_top(HAY)
    assert top[0] == "s_grinder" and "s_none" not in top and "s_bike" not in top and len(top) <= 3


def test_baselines_give_nothing_bm25_or_the_labelled_sessions(tmp_path, capsys):
    data = tmp_path / "d.json"
    data.write_text(json.dumps([HAY]), encoding="utf-8")
    got = {}
    for kind in ("none", "bm25", "oracle"):
        out = tmp_path / f"{kind}.jsonl"
        qa.baseline(type("A", (), {"data": str(data), "kind": kind, "out": str(out)})())
        got[kind] = json.loads(out.read_text(encoding="utf-8"))
    assert got["none"]["cited"] == [] and got["none"]["refused"]
    assert got["oracle"]["cited"] == ["s_grinder"] and not got["oracle"]["refused"]
    assert got["bm25"]["cited"][0] == "s_grinder"


def test_a_prompt_set_11_already_ran_is_copied_and_only_the_rest_are_written(tmp_path, capsys):
    other = dict(HAY, question_id="q2")
    data = tmp_path / "d.json"
    data.write_text(json.dumps([HAY, other]), encoding="utf-8")
    outputs = tmp_path / "o.jsonl"
    outputs.write_text("".join(json.dumps({"id": q, "cited": ["s_grinder"], "refused": False}) + "\n" for q in ("q1", "q2")),
                       encoding="utf-8")
    before = tmp_path / "set11.jsonl"  # 第 11 组：q1 给的是同一段会话，q2 给的是另一段
    before.write_text(json.dumps({"qid": "q1", "refused": False, "sessions": ["s_grinder"], "response": "Niche", "verdict": "yes"}) + "\n"
                      + json.dumps({"qid": "q2", "refused": False, "sessions": ["s_tea"], "response": "tea", "verdict": "no"}) + "\n",
                      encoding="utf-8")
    qa.prepare(type("A", (), {"data": str(data), "outputs": str(outputs), "out": str(tmp_path / "r" / "reader"),
                              "batch": 12, "max_chars": 10_000, "reuse": str(before)})())
    reused = [json.loads(x) for x in (tmp_path / "r" / "reused.jsonl").read_text(encoding="utf-8").splitlines()]
    assert reused == [{"qid": "q1", "response": "Niche", "verdict": "yes"}]
    written = [json.loads(x)["qid"] for f in (tmp_path / "r" / "reader").glob("batch_*.jsonl")
               for x in f.read_text(encoding="utf-8").splitlines()]
    assert written == ["q2"]


def test_paired_difference_counts_the_questions_only_one_row_got_right():
    d = qa.paired([True, True, False, False], [True, False, False, False], seed=1, n=200)
    assert d["diff"] == 25.0 and d["only_first_right"] == 1 and d["only_second_right"] == 0
