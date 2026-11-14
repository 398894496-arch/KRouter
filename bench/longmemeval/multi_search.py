#!/usr/bin/env python3
"""Set 46 (bench/memory_honesty/HELDOUT.md): the reader may search again. Development half only.

    python3 bench/longmemeval/multi_search.py prepare            # pick the questions, write the reader batch folders
    python3 bench/longmemeval/multi_search.py search PID "QUERY" # what a reader runs: up to MAX_EXTRA times per prompt
    python3 bench/longmemeval/multi_search.py collect            # answers -> judge batch folders (set 22's judge prompts)
    python3 bench/longmemeval/multi_search.py score              # the counts against the registered line

The first pages a reader sees are set 22's, exactly: the prompt is `qa.reader_prompt` with the sessions set 22 handed over
(read from set 22's results file), and `prepare` checks every prompt against the prompt set 22's reader was given. After
that the reader may run `search` with its own words: KRouter's own entry point (`route_knowledge.py search`, as set 22 ran
it, on the same question's vault) at up to 8 pages; up to `NEW_PER_SEARCH` sessions the reader has not been shown yet are
printed in the benchmark's history format (no page names); a fourth search for the same prompt is refused. Every search,
refused or not, is written to `searches.jsonl` in the state folder. Prompt ids are opaque; the map stays in the state folder.
State: `~/.local/state/krouter-eval/set46` (`KROUTER_SET46_STATE`). `KROUTER_NO_QUERY_LOG=1` is set for every lookup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import lme  # noqa: E402
import qa  # noqa: E402

STATE = Path(os.environ.get("KROUTER_SET46_STATE") or Path.home() / ".local/state/krouter-eval/set46")
DATA = Path(os.environ.get("KROUTER_LME_DATA") or Path.home() / ".cache/krouter-eval/lme-data/longmemeval_s_cleaned.json")
QUESTIONS = Path.home() / ".local/state/krouter-eval/lme-set22/questions.jsonl"
STORED = Path.home() / ".cache/krouter-eval/set22"
SET22 = REPO / "bench/longmemeval/results/2026-11-13-sonnet-qa.set22.jsonl"
SEED = 20261146
CONTROL = 30
ABS_DEV = 15
MAX_EXTRA = 3
NEW_PER_SEARCH = 3
SEARCH_PAGES = 8
BATCH_PROMPTS = 6
BATCH_CHARS = 400_000
JUDGE_BATCH = 25


def jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in Path(p).read_text(encoding="utf-8").split("\n") if x.strip()] if Path(p).exists() else []


def pid_of(qid: str) -> str:
    return "q" + hashlib.sha1(f"set46:{qid}".encode()).hexdigest()[:10]


def kind_of(row: dict, it: dict) -> str:
    """Set 22's wrong answers: no answer session handed over / some / all."""
    given = set() if row["refused"] else {qa.session_of(p) for p in row["sessions"]}
    need = set(it["answer_session_ids"])
    have = need & given
    return "none" if not have else ("all" if have == need else "some")


def selection() -> dict[str, dict]:
    rows = [json.loads(x) for x in QUESTIONS.read_text(encoding="utf-8").split("\n") if x.strip()]
    split = lme.split_of(rows)
    res = {r["qid"]: r for r in qa.read_jsonl([SET22])}
    data = qa.load_data(DATA)
    dev = sorted(q for q, s in split.items() if s == "dev")
    wrong = [q for q in dev if not qa.correct(str(res[q]["verdict"]))]
    right = [q for q in dev if qa.correct(str(res[q]["verdict"]))]
    rng = random.Random(SEED)  # 抽题顺序是登记的一部分：先对照题，再不可答题
    control = sorted(rng.sample(right, CONTROL))
    abs_all = sorted(q for q, s in split.items() if s == "abs")
    abs_dev = sorted(rng.sample(abs_all, ABS_DEV))
    out = {}
    for group, ids in (("wrong", wrong), ("control", control), ("abs", abs_dev)):
        for q in ids:
            r = res[q]
            out[q] = {"qid": q, "pid": pid_of(q), "group": group, "type": data[q]["question_type"],
                      "kind": kind_of(r, data[q]) if group == "wrong" else "",
                      "set22": "right" if qa.correct(str(r["verdict"])) else "wrong",
                      "sessions": [] if r["refused"] else r["sessions"]}
    return out


def stored_prompts() -> dict[str, str]:
    out = {r["qid"]: r["prompt"] for f in sorted((STORED / "reader_jsonl").glob("*.jsonl")) for r in jl(f)}
    data = qa.load_data(DATA)
    for r in jl(STORED / "reuse_set11_12.jsonl"):
        out.setdefault(("reuse", r["qid"]), [])
        out[("reuse", r["qid"])].append(qa.reader_prompt(data[r["qid"]], [] if r["refused"] else r["sessions"]))
    return out


def prepare(_a) -> int:
    sel = selection()
    data = qa.load_data(DATA)
    stored = stored_prompts()
    prompts, same = {}, 0
    for q, s in sel.items():
        p = qa.reader_prompt(data[q], s["sessions"])
        prompts[q] = p
        same += p == stored.get(q) or p in stored.get(("reuse", q), [])
    if same != len(sel):
        raise SystemExit(f"only {same} of {len(sel)} prompts equal set 22's")
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "selection.json").write_text(json.dumps(sel, ensure_ascii=False, indent=1), encoding="utf-8")
    order = sorted(sel, key=lambda q: sel[q]["pid"])  # 按不透明 id 排：一批里各组混在一起
    batches, cur, size = [], [], 0
    for q in order:
        n = len(prompts[q])
        if cur and (len(cur) >= BATCH_PROMPTS or size + n > BATCH_CHARS):
            batches.append(cur)
            cur, size = [], 0
        cur.append(q)
        size += n
    if cur:
        batches.append(cur)
    for i, b in enumerate(batches, 1):
        d = STATE / "reader" / f"batch_{i:02d}"
        d.mkdir(parents=True, exist_ok=True)
        (STATE / "answers" / f"batch_{i:02d}").mkdir(parents=True, exist_ok=True)
        idx = []
        for q in b:
            pid = sel[q]["pid"]
            (d / f"prompt_{pid}.txt").write_text(prompts[q], encoding="utf-8")
            idx.append(f"{pid}\tprompt_{pid}.txt\t{len(prompts[q])} chars")
        (d / "INDEX.txt").write_text(f"batch_{i:02d}: {len(b)} prompts, one file each\n" + "\n".join(idx) + "\n",
                                     encoding="utf-8")
    print(json.dumps({"questions": len(sel), "groups": dict(Counter(s["group"] for s in sel.values())),
                      "wrong_kinds": dict(Counter(s["kind"] for s in sel.values() if s["group"] == "wrong")),
                      "identical_to_set22": same, "batches": len(batches),
                      "chars": sum(len(p) for p in prompts.values())}))
    return 0


def search(a) -> int:
    sel = {s["pid"]: s for s in json.loads((STATE / "selection.json").read_text(encoding="utf-8")).values()}
    log = STATE / "searches.jsonl"
    if a.pid not in sel:
        print(f"unknown prompt id {a.pid}")
        return 2
    s = sel[a.pid]
    mine = [r for r in jl(log) if r["pid"] == a.pid and not r.get("refused")]
    rec = {"pid": a.pid, "n": len(mine) + 1, "query": a.query, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if len(mine) >= MAX_EXTRA:
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({**rec, "refused": True}, ensure_ascii=False) + "\n")
        print(f"Search limit reached: {MAX_EXTRA} of {MAX_EXTRA} searches already used for this prompt. No search was run.")
        return 1
    rows = {r["id"]: r for r in (json.loads(x) for x in QUESTIONS.read_text(encoding="utf-8").split("\n") if x.strip())}
    it_row = rows[s["qid"]]
    sys.path.insert(0, str(REPO / "bench/real_questions"))
    import run_real

    os.environ["KROUTER_NO_QUERY_LOG"] = "1"
    cache = STATE / "cache" / s["qid"]
    ans = run_real.route_answers(REPO, [{"id": s["qid"], "q": a.query}], Path(it_row["vault"]), cache, pages=SEARCH_PAGES)[0]
    shown = {qa.session_of(p) for p in s["sessions"]} | {x for r in mine for x in r.get("returned", [])}
    data = qa.load_data(DATA)
    it = data[s["qid"]]
    known = set(it["haystack_session_ids"])
    new = [qa.session_of(p) for p in ans["cited"] if qa.session_of(p) in known and qa.session_of(p) not in shown]
    new = list(dict.fromkeys(new))[:NEW_PER_SEARCH]
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({**rec, "returned": new, "found": len(ans["cited"])}, ensure_ascii=False) + "\n")
    head = f"Search {rec['n']} of {MAX_EXTRA} for this prompt."
    if not new:
        print(head + " Nothing more was found (no history chats you have not already been shown).")
        return 0
    page_of = {qa.session_of(p): p for p in ans["cited"]}
    text = qa.history(it, [page_of[x] for x in new]).replace("### Session ", "### Extra session ")
    print(head + f" {len(new)} more history chat(s), not in your prompt:\n{text}")
    return 0


def collect(_a) -> int:
    sel = json.loads((STATE / "selection.json").read_text(encoding="utf-8"))
    by_pid = {s["pid"]: q for q, s in sel.items()}
    data = qa.load_data(DATA)
    answers = {}
    for f in (STATE / "answers").glob("batch_*/*.txt"):
        if f.stem in by_pid:
            answers[by_pid[f.stem]] = f.read_text(encoding="utf-8", errors="replace").strip()
    missing = sorted(sel[q]["pid"] for q in sel if q not in answers)
    (STATE / "answers.jsonl").write_text("".join(json.dumps({"qid": q, "response": answers[q]}, ensure_ascii=False) + "\n"
                                                 for q in sorted(answers)), encoding="utf-8")
    order = sorted(answers, key=lambda q: sel[q]["pid"])
    for i in range(0, len(order), JUDGE_BATCH):
        d = STATE / "judge" / f"batch_{i // JUDGE_BATCH + 1:02d}"
        d.mkdir(parents=True, exist_ok=True)
        idx = []
        for q in order[i:i + JUDGE_BATCH]:
            pid = sel[q]["pid"]
            p = qa.judge_prompt(data[q], answers[q])
            (d / f"prompt_{pid}.txt").write_text(p, encoding="utf-8")
            idx.append(f"{pid}\tprompt_{pid}.txt\t{len(p)} chars")
        (d / "INDEX.txt").write_text(f"{d.name}: {len(idx)} prompts, one file each\n" + "\n".join(idx) + "\n", encoding="utf-8")
    print(json.dumps({"answers": len(answers), "missing": missing, "judge_batches": -(-len(order) // JUDGE_BATCH)}))
    return 0


def score(_a) -> int:
    sel = json.loads((STATE / "selection.json").read_text(encoding="utf-8"))
    by_pid = {s["pid"]: q for q, s in sel.items()}
    verdicts = {}
    for f in (STATE / "verdicts").glob("*.jsonl"):
        for r in jl(f):
            verdicts[by_pid.get(r["qid"], r["qid"])] = str(r["verdict"])
    searches = defaultdict(list)
    for r in jl(STATE / "searches.jsonl"):
        searches[by_pid[r["pid"]]].append(r)
    out: dict = {"judged": len(verdicts), "of": len(sel)}
    rows = []
    for q, s in sel.items():
        now = "right" if qa.correct(verdicts.get(q, "")) else ("unjudged" if q not in verdicts else "wrong")
        used = [r for r in searches[q] if not r.get("refused")]
        rows.append({"qid": q, "pid": s["pid"], "group": s["group"], "kind": s["kind"], "type": s["type"],
                     "set22": s["set22"], "now": now, "searches": len(used),
                     "refused_searches": sum(1 for r in searches[q] if r.get("refused")),
                     "sessions_returned": sum(len(r.get("returned", [])) for r in used)})
    for g in ("wrong", "control", "abs"):
        sel_g = [r for r in rows if r["group"] == g]
        out[g] = {"n": len(sel_g), "now_right": sum(r["now"] == "right" for r in sel_g),
                  "unjudged": sum(r["now"] == "unjudged" for r in sel_g),
                  "mean_searches": round(sum(r["searches"] for r in sel_g) / max(1, len(sel_g)), 2),
                  "searched_at_all": sum(r["searches"] > 0 for r in sel_g)}
    out["wrong_by_kind"] = {k: {"n": sum(1 for r in rows if r["group"] == "wrong" and r["kind"] == k),
                                "recovered": sum(1 for r in rows if r["group"] == "wrong" and r["kind"] == k and r["now"] == "right")}
                            for k in ("none", "some", "all")}
    rec = out["wrong"]["now_right"]
    lost_c = out["control"]["n"] - out["control"]["now_right"]
    lost_a = out["abs"]["n"] - out["abs"]["now_right"]
    out["net"] = rec - lost_c - lost_a
    out["mean_searches_all"] = round(sum(r["searches"] for r in rows) / len(rows), 2)
    out["max_searches"] = max(r["searches"] for r in rows)
    out["line"] = {"recovered>=5": rec >= 5, "net>=4": out["net"] >= 4, "control_lost<=1": lost_c <= 1,
                   "abs_lost<=1": lost_a <= 1, "max_searches<=3": out["max_searches"] <= MAX_EXTRA}
    out["passed"] = all(out["line"].values())
    res_dir = REPO / "bench/longmemeval/results/set46"
    res_dir.mkdir(parents=True, exist_ok=True)
    (res_dir / "dev-rows.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    (res_dir / "dev-score.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("prepare", "search", "collect", "score"))
    ap.add_argument("pid", nargs="?")
    ap.add_argument("query", nargs="?")
    a = ap.parse_args()
    if a.cmd == "search" and not (a.pid and a.query):
        ap.error("search needs PID and QUERY")
    return {"prepare": prepare, "search": search, "collect": collect, "score": score}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
