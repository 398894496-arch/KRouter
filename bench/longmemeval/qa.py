#!/usr/bin/env python3
"""Set 11 (HELDOUT.md): LongMemEval answer accuracy, scored the way other memory projects report it.

Set 7 counts whether KRouter cites an answer session. This script turns those citations into the benchmark's own
question-answering evaluation: a reader model answers each question from the cited sessions with the benchmark's
reader template, and a judge model grades each answer with the benchmark's per-type judge prompts. The templates are
copied verbatim from LongMemEval (Wu et al., ICLR 2025; MIT): `src/generation/run_generation.py` (the step-by-step
reader, `nl` history format) and `src/evaluation/evaluate_qa.py` (`get_anscheck_prompt`).

The reader and the judge are whatever model you run the prompts through; this script only writes the prompts and
scores the replies. Each prompt file is JSONL `{qid, prompt}`; the replies you write back are JSONL
`{qid, response}` (reader) and `{qid, verdict}` (judge, the raw reply text).

    python3 bench/longmemeval/qa.py prepare --outputs outputs.krouter.jsonl --data longmemeval_s_cleaned.json --out qa/reader
    (run every qa/reader/batch_*.jsonl through the reader; write qa/answers/batch_*.jsonl)
    python3 bench/longmemeval/qa.py judge-prepare --answers qa/answers --data longmemeval_s_cleaned.json --out qa/judge
    (run every qa/judge/batch_*.jsonl through the judge; write qa/verdicts/batch_*.jsonl)
    python3 bench/longmemeval/qa.py score --verdicts qa/verdicts --data longmemeval_s_cleaned.json
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

READER = ("I will give you several history chats between you and a user. Please answer the question based on the "
          "relevant chat history. Answer the question step by step: first extract all the relevant information, and "
          "then reason over the information to get the answer.\n\n\nHistory Chats:\n\n{}\n\nCurrent Date: {}\n"
          "Question: {}\nAnswer (step by step):")
NO_HISTORY = "(no chat history was retrieved)"

_BASE = ("I will give you a question, a correct answer, and a response from a model. Please answer yes if the response "
         "contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or "
         "contains all the intermediate steps to get the correct answer, you should also answer yes. If the response "
         "only contains a subset of the information required by the answer, answer no. ")
_TAIL = "\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only."
JUDGE = {
    "single-session-user": _BASE + _TAIL,
    "single-session-assistant": _BASE + _TAIL,
    "multi-session": _BASE + _TAIL,
    "temporal-reasoning": _BASE + "In addition, do not penalize off-by-one errors for the number of days. If the "
                          "question asks for the number of days/weeks/months, etc., and the model makes off-by-one "
                          "errors (e.g., predicting 19 days when the answer is 18), the model's response is still "
                          "correct. " + _TAIL,
    "knowledge-update": ("I will give you a question, a correct answer, and a response from a model. Please answer yes "
                         "if the response contains the correct answer. Otherwise, answer no. If the response contains "
                         "some previous information along with an updated answer, the response should be considered as "
                         "correct as long as the updated answer is the required answer." + _TAIL),
    "single-session-preference": ("I will give you a question, a rubric for desired personalized response, and a "
                                  "response from a model. Please answer yes if the response satisfies the desired "
                                  "response. Otherwise, answer no. The model does not need to reflect all the points "
                                  "in the rubric. The response is correct as long as it recalls and utilizes the "
                                  "user's personal information correctly.\n\nQuestion: {}\n\nRubric: {}\n\nModel "
                                  "Response: {}\n\nIs the model response correct? Answer yes or no only."),
}
ABSTENTION = ("I will give you an unanswerable question, an explanation, and a response from a model. Please answer yes "
              "if the model correctly identifies the question as unanswerable. The model could say that the information "
              "is incomplete, or some other information is given but the asked information is not.\n\nQuestion: {}\n\n"
              "Explanation: {}\n\nModel Response: {}\n\nDoes the model correctly identify the question as unanswerable? "
              "Answer yes or no only.")


def load_data(path: Path) -> dict:
    return {it["question_id"]: it for it in json.loads(path.read_text(encoding="utf-8"))}


def read_jsonl(paths) -> list[dict]:
    out = []
    for p in paths:
        out += [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]
    return out


def session_of(page: str) -> str:
    """`05 时间日志/会话摘录/2023-05-22 answer_40a90d51.md` → `answer_40a90d51` (the page name is date + session id)."""
    return Path(page).stem.split(" ", 1)[-1]


def history(it: dict, cited: list[str]) -> str:
    """The cited sessions in the benchmark's `nl` history format, sorted by date as the original sorts them."""
    by_id = {sid: (it["haystack_dates"][i], it["haystack_sessions"][i]) for i, sid in enumerate(it["haystack_session_ids"])}
    chunks = sorted((by_id[s] for s in dict.fromkeys(session_of(p) for p in cited) if s in by_id), key=lambda x: x[0])
    out = ""
    for i, (date, turns) in enumerate(chunks):
        sess = "".join("\n\n{}: {}".format(t["role"], t["content"].strip()) for t in turns)
        out += "\n### Session {}:\nSession Date: {}\nSession Content:\n{}\n".format(i + 1, date, sess)
    return out or NO_HISTORY


def write_batches(rows: list[dict], out: Path, max_items: int, max_chars: int) -> int:
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("batch_*.jsonl"):
        old.unlink()
    batches, cur, size = [], [], 0
    for r in rows:
        n = len(r["prompt"])
        if cur and (len(cur) >= max_items or size + n > max_chars):
            batches.append(cur)
            cur, size = [], 0
        cur.append(r)
        size += n
    if cur:
        batches.append(cur)
    for i, b in enumerate(batches, 1):
        (out / f"batch_{i:03d}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in b),
                                                  encoding="utf-8")
    return len(batches)


def prepare(args) -> None:
    data = load_data(Path(args.data))
    outputs = {o["id"]: o for o in read_jsonl([args.outputs])}
    rows = [{"qid": qid, "prompt": READER.format(history(it, [] if outputs[qid]["refused"] else outputs[qid]["cited"]),
                                                  it["question_date"], it["question"])}
            for qid, it in data.items() if qid in outputs]
    n = write_batches(rows, Path(args.out), args.batch, args.max_chars)
    print(json.dumps({"prompts": len(rows), "batches": n, "missing": sorted(set(data) - set(outputs))[:5],
                      "refused": sum(1 for o in outputs.values() if o["refused"])}))


def judge_prompt(it: dict, response: str) -> str:
    if "_abs" in it["question_id"]:
        return ABSTENTION.format(it["question"], it["answer"], response)
    return JUDGE[it["question_type"]].format(it["question"], it["answer"], response)


def judge_prepare(args) -> None:
    data = load_data(Path(args.data))
    answers = {a["qid"]: a["response"] for a in read_jsonl(sorted(Path(args.answers).glob("*.jsonl")))}
    rows = [{"qid": qid, "prompt": judge_prompt(data[qid], resp)} for qid, resp in answers.items() if qid in data]
    n = write_batches(rows, Path(args.out), args.batch, args.max_chars)
    print(json.dumps({"prompts": len(rows), "batches": n, "unanswered": len(set(data) - set(answers))}))


def correct(verdict: str) -> bool:
    return "yes" in verdict.strip().lower()  # 原版的判法：回复里有 yes 就算对


def interval(flags: list[bool], seed: int, n: int = 10000) -> list[float]:
    if not flags:
        return [0.0, 0.0]
    rng = random.Random(seed)
    k = len(flags)
    means = sorted(sum(flags[rng.randrange(k)] for _ in range(k)) / k for _ in range(n))
    return [round(means[int(0.025 * n)] * 100, 1), round(means[int(0.975 * n) - 1] * 100, 1)]


def score(args) -> None:
    data = load_data(Path(args.data))
    verdicts = {v["qid"]: correct(str(v["verdict"])) for v in read_jsonl(sorted(Path(args.verdicts).glob("*.jsonl")))}
    groups: dict[str, list[bool]] = {"all": [], "answerable": [], "abstention": []}
    for qid, it in data.items():
        ok = verdicts.get(qid, False)  # 没判到的算错，不丢题
        groups["all"].append(ok)
        groups["abstention" if "_abs" in qid else "answerable"].append(ok)
        if "_abs" not in qid:
            groups.setdefault(it["question_type"], []).append(ok)
    report = {"questions": len(data), "judged": len(verdicts), "seed": args.seed,
              "accuracy": {g: {"right": sum(f), "of": len(f), "pct": round(100 * sum(f) / len(f), 1) if f else 0.0,
                               "ci95": interval(f, args.seed)} for g, f in groups.items()}}
    print(json.dumps(report, ensure_ascii=False, indent=1))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--outputs", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--batch", type=int, default=12)
    p.add_argument("--max-chars", type=int, default=240_000)
    j = sub.add_parser("judge-prepare")
    j.add_argument("--answers", required=True)
    j.add_argument("--data", required=True)
    j.add_argument("--out", required=True)
    j.add_argument("--batch", type=int, default=60)
    j.add_argument("--max-chars", type=int, default=200_000)
    s = sub.add_parser("score")
    s.add_argument("--verdicts", required=True)
    s.add_argument("--data", required=True)
    s.add_argument("--seed", type=int, default=20261109)
    args = ap.parse_args()
    {"prepare": prepare, "judge-prepare": judge_prepare, "score": score}[args.cmd](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
