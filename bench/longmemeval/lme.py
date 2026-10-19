#!/usr/bin/env python3
"""Set 7 (HELDOUT.md): KRouter and a BM25 floor on LongMemEval, scored from the benchmark authors' own labels.

LongMemEval (Wu et al., ICLR 2025) gives each of its 500 questions a haystack of about 50 dated chat sessions and
labels which sessions hold the answer. Each question becomes its own small vault, one Markdown page per session, and
each system answers with up to three cited pages or a refusal. Scoring needs no model:

- evidence cited (answerable questions): a cited page is an answer session;
- knowledge update: the cited pages include the latest-dated answer session; "stale only" = an earlier one, not it;
- abstention (`_abs` questions): refused; against it, refusals on the answerable questions.

The dataset is not in this repository and this script downloads nothing; pass the file you fetched:

    python3 bench/longmemeval/lme.py convert --data longmemeval_s_cleaned.json
    python3 bench/longmemeval/lme.py run --system krouter
    python3 bench/longmemeval/lme.py run --system bm25-floor
    python3 bench/longmemeval/lme.py score

State (vaults, outputs, report) lives in `~/.local/state/krouter-eval/lme/` (`KROUTER_LME_STATE` to move it).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STATE = Path(os.environ.get("KROUTER_LME_STATE") or Path.home() / ".local/state/krouter-eval/lme")
SESSIONS = "05 时间日志/会话摘录"  # KRouter 自己导入会话时放的位置
SEED = 20261018
RESAMPLES = 10_000


def day_of(raw: str) -> str:
    """LongMemEval dates look like `2023/05/20 (Sat) 02:21`."""
    m = re.match(r"(\d{4})/(\d{2})/(\d{2})", raw or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def page_name(day: str, sid: str) -> str:
    return f"{day} {re.sub(r'[^A-Za-z0-9_-]', '_', sid)}.md"


def convert(data: Path) -> None:
    items = json.loads(data.read_text(encoding="utf-8"))
    vaults = STATE / "vaults"
    if vaults.exists():
        shutil.rmtree(vaults)
    meta = []
    for it in items:
        qid = it["question_id"]
        root = vaults / re.sub(r"[^A-Za-z0-9_-]", "_", qid) / SESSIONS
        root.mkdir(parents=True)
        pages = {}
        for sid, raw_day, turns in zip(it["haystack_session_ids"], it["haystack_dates"], it["haystack_sessions"],
                                       strict=True):
            day = day_of(raw_day)
            name = page_name(day, sid)
            body = [f"---\ntitle: Session {day}\ndate: {day}\nsource: longmemeval\n---\n", f"# Session {day}\n"]
            for t in turns:
                body.append(f"**{t.get('role', '?')}:** {t.get('content', '').strip()}\n")
            (root / name).write_text("\n".join(body), encoding="utf-8")
            pages[f"{SESSIONS}/{name}"] = {"sid": sid, "day": day}
        answer = set(it.get("answer_session_ids") or [])
        meta.append({"id": qid, "q": it["question"], "type": it["question_type"], "abs": qid.endswith("_abs"),
                     "date": day_of(it.get("question_date", "")), "answer_sessions": sorted(answer),
                     "vault": str(root.parents[1]), "pages": pages})
    (STATE / "questions.jsonl").write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in meta),
                                           encoding="utf-8")
    print(json.dumps({"questions": len(meta), "abs": sum(m["abs"] for m in meta),
                      "knowledge_update": sum(m["type"] == "knowledge-update" for m in meta)}))


def load_questions() -> list[dict]:
    return [json.loads(x) for x in (STATE / "questions.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]


def bench_module():
    sys.path.insert(0, str(REPO / "bench/real_questions"))
    import run_real

    return run_real, run_real.bench_from(REPO)


def run(system: str, limit: int, repo: Path) -> None:
    rows = load_questions()[: limit or None]
    run_real, bench = bench_module()
    out = []
    if system == "krouter":
        cache = STATE / "cache"
        for it in rows:
            ans = run_real.route_answers(repo, [{"id": it["id"], "q": it["q"]}], Path(it["vault"]), cache / it["id"])[0]
            out.append({"id": it["id"], "cited": ans["cited"], "refused": ans["refused"], "repo": str(repo)})
            shutil.rmtree(cache / it["id"], ignore_errors=True)
    else:
        dev = bench.questions("dev3")
        floor = bench.pick_floor(dev, bench.bm25_scored(dev, skip_superseded=True, vault_src=bench.vault_of("dev3"),
                                                        cjk=True))
        for it in rows:
            scored = bench.bm25_scored([{"id": it["id"], "q": it["q"]}], skip_superseded=True,
                                       vault_src=Path(it["vault"]), cjk=True)
            ans = bench.floor_answers(scored, floor)[0]
            out.append({"id": it["id"], "cited": ans["cited"][:3], "refused": ans["refused"]})
    path = STATE / f"outputs.{system}.jsonl"
    path.write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in out), encoding="utf-8")
    print(json.dumps({"system": system, "questions": len(out), "refused": sum(o["refused"] for o in out)}))


def judge(it: dict, ans: dict) -> dict:
    """Per-question outcomes from the labels alone."""
    cited = [it["pages"].get(rel, {}).get("sid") for rel in ans["cited"]]
    answer = set(it["answer_sessions"])
    days = {v["sid"]: v["day"] for v in it["pages"].values()}
    latest = max(answer, key=lambda s: (days.get(s, ""), s)) if answer else None
    hit = bool(answer & set(cited))
    return {"answerable": not it["abs"], "ku": it["type"] == "knowledge-update" and not it["abs"],
            "refused": ans["refused"], "evidence": hit, "latest": latest in cited,
            "stale_only": hit and latest not in cited}


METRICS = {
    "evidence_cited": ("answerable", "evidence"),
    "refused_answerable": ("answerable", "refused"),
    "ku_latest_cited": ("ku", "latest"),
    "ku_stale_only": ("ku", "stale_only"),
    "abs_refused": ("abs", "refused"),
}


def rate(outcomes: list[dict], subset: str, field: str) -> tuple[int, int]:
    pool = [o for o in outcomes if (not o["answerable"] if subset == "abs" else o[subset])]
    return sum(o[field] for o in pool), len(pool)


def score() -> None:
    qs = {q["id"]: q for q in load_questions()}
    systems = {}
    for path in sorted(STATE.glob("outputs.*.jsonl")):
        name = path.name.split(".", 1)[1].rsplit(".", 1)[0]
        ans = {a["id"]: a for a in map(json.loads, path.read_text(encoding="utf-8").splitlines())}
        systems[name] = {qid: judge(qs[qid], a) for qid, a in ans.items() if qid in qs}
    report = {"questions": len(qs), "systems": {}}
    for name, res in systems.items():
        outs = list(res.values())
        report["systems"][name] = {m: "{}/{}".format(*rate(outs, *spec)) for m, spec in METRICS.items()}
    if {"krouter", "bm25-floor"} <= systems.keys():
        common = sorted(systems["krouter"].keys() & systems["bm25-floor"].keys())
        rng = random.Random(SEED)
        diffs = {}
        for m, (subset, field) in METRICS.items():
            ids = [i for i in common if (not systems["krouter"][i]["answerable"] if subset == "abs"
                                         else systems["krouter"][i][subset])]
            if not ids:
                continue
            d = [int(systems["krouter"][i][field]) - int(systems["bm25-floor"][i][field]) for i in ids]
            boots = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(RESAMPLES))
            diffs[m] = {"krouter_minus_bm25": round(sum(d) / len(d), 4),
                        "ci95": [round(boots[int(0.025 * RESAMPLES)], 4), round(boots[int(0.975 * RESAMPLES)], 4)],
                        "n": len(ids)}
        report["paired"] = diffs
    report["scored_at"] = datetime.now().isoformat(timespec="seconds")
    (STATE / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert")
    c.add_argument("--data", required=True)
    r = sub.add_parser("run")
    r.add_argument("--system", choices=["krouter", "bm25-floor"], required=True)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--repo", default=str(REPO), help="the KRouter checkout to run (e.g. a worktree at the release tag)")
    sub.add_parser("score")
    args = ap.parse_args()
    os.environ["KROUTER_NO_QUERY_LOG"] = "1"
    STATE.mkdir(parents=True, exist_ok=True)
    if args.cmd == "convert":
        convert(Path(args.data))
    elif args.cmd == "run":
        run(args.system, args.limit, Path(args.repo))
    else:
        score()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
