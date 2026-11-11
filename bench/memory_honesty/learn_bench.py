#!/usr/bin/env python3
"""Does KRouter get better with use? The "learns from use" bench.

Each thing is asked twice, a week apart, in different words. Week 1's wordings go through the router as a host's
agent would send them (`route_knowledge.py search`, into a private query log); then the real nightly learner runs
once (`reconsolidate.py`: for each question the router did not answer well, a model picks the page that answers it
from the recall candidates, or none, and the question becomes a recall trigger of that page). Week 2's wordings are
scored before and after that one night, and against BM25 with the two rules, which does not learn.

    python3 bench/memory_honesty/learn_bench.py --pairs human_set/human_pairs.jsonl.gz --cli /opt/homebrew/bin/claude
    python3 bench/memory_honesty/learn_bench.py --from-dev vault1 --cli …   # on the dev questions of vault1 / vault2

Pairs: JSONL (optionally gzipped), one row per wording: {id, intent, week (1 or 2), q, kind, gold}
(`human_set/check_human_set.py` writes them). `--set` names the bench set whose vault and BM25 floor are used
(`heldout3` → vault3, the default; `dev3` → vault2). Everything runs on a copy of the vault with its own state and
cache; the host's query log, learned triggers and caches are never touched. The learner's model call is the only
thing that leaves the machine: week 1's questions the router did not answer well, with up to 4 candidate pages each
(path and first 600 characters, redacted; never secret pages), to `--cli` (or the model lane).
Prints aggregates only.
"""

from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[1] / "skill/krouter/scripts"
spec = importlib.util.spec_from_file_location("mh_bench_learn", HERE / "run.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def load_pairs(path: Path) -> list[dict]:
    data = path.read_bytes()
    text = gzip.decompress(data).decode("utf-8") if path.suffix == ".gz" else data.decode("utf-8")
    return [json.loads(x) for x in text.splitlines() if x.strip()]


DEV_VAULTS = {"vault1": ("dev", "dev2"), "vault2": ("dev3",)}


def dev_pairs(vault: str) -> list[dict]:
    """Pairs from the dev sets on one vault (dev sets: fine to look at): two dev questions with the same gold page are
    one intent asked twice; a neighbour question is asked twice in the same words (learning must not make it answered)."""
    by_gold: dict[str, list[dict]] = defaultdict(list)
    out: list[dict] = []
    for r in [q for s in DEV_VAULTS[vault] for q in bench.questions(s)]:
        if r.get("gold"):
            by_gold[r["gold"]].append(r)
        else:
            for week in (1, 2):
                out.append({"id": f"{r['id']}-{week}", "intent": r["id"], "week": week, "q": r["q"],
                            "kind": "refuse", "gold": None})
    for gold, rs in by_gold.items():
        if len(rs) >= 2:
            for week, r in ((1, rs[0]), (2, rs[1])):
                out.append({"id": f"{r['id']}-{week}", "intent": gold, "week": week, "q": r["q"],
                            "kind": rs[1]["kind"], "gold": gold})
    return out


def env_for(vault: Path, state: Path, cache: Path, cli: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "KROUTER_NO_QUERY_LOG"}  # 第一周的提问要进（私有的）查询日志
    env.update({"OBSIDIAN_VAULT": str(vault), "KROUTER_STATE_DIR": str(state), "KROUTER_CACHE_DIR": str(cache),
                "KROUTER_DENSE": "0", "KROUTER_NOTIFY": "0"})
    if cli:
        env["KROUTER_LEARN_CLI"] = cli
    return env


def right(res: dict) -> int:
    return int(res["correction_hit"].split("/")[0]) + int(res["current_hit"].split("/")[0])


def summary(res: dict) -> dict:
    return {"wrong_citations": res["wrong_citations"], "answered": res["answered"], "refused": res["refused"],
            "right": right(res)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="")
    ap.add_argument("--from-dev", choices=sorted(DEV_VAULTS), default="")
    ap.add_argument("--scripts", default=str(SCRIPTS), help="KRouter scripts to run (e.g. an older checkout)")
    ap.add_argument("--set", default="", help="bench set for the vault and the BM25 floor (heldout3 / dev3)")
    ap.add_argument("--cli", default="", help="the learner's model: a logged-in CLI (default: the model lane)")
    ap.add_argument("--route", default="search")
    ap.add_argument("--show-learned", action="store_true", help="dev sets only: print the learned triggers")
    args = ap.parse_args()
    scripts = Path(args.scripts)
    if args.from_dev:
        pairs, qset = dev_pairs(args.from_dev), args.set or DEV_VAULTS[args.from_dev][0]
    elif args.pairs:
        pairs, qset = load_pairs(Path(args.pairs)), args.set or "heldout3"
    else:
        ap.error("--pairs or --from-dev3")
    w1 = [p for p in pairs if p["week"] == 1]
    w2 = [p for p in pairs if p["week"] == 2]
    src = bench.vault_of(qset)
    tmp = Path(tempfile.mkdtemp(prefix="krouter-learn-"))
    try:
        vault = tmp / "vault"
        shutil.copytree(src, vault)
        env = env_for(vault, tmp / "state", tmp / "cache", args.cli)
        for p in w1:  # 第一周：像宿主的 agent 那样问，进私有的查询日志
            subprocess.run([sys.executable, str(scripts / "route_knowledge.py"), args.route, p["q"]], env=env,
                           capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
        log = tmp / "state" / "queries.jsonl"
        logged = len(log.read_text(encoding="utf-8").splitlines()) if log.is_file() else 0
        night = subprocess.run([sys.executable, str(scripts / "reconsolidate.py"), "--vault", str(vault), "--since", "",
                                "--max", str(len(w1))], env=env, capture_output=True, text=True, timeout=1800,
                               stdin=subprocess.DEVNULL)
        try:
            learned = json.loads(night.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            learned = {"error": (night.stderr or night.stdout)[-300:]}
        if args.show_learned:
            if qset in bench.HELDOUT_SETS or not args.from_dev:
                ap.error("--show-learned is for dev sets only")
            for f in (vault / "90 系统文件").rglob("*自学习*.psv"):
                print(f.read_text(encoding="utf-8"), file=sys.stderr)
        os.environ["KROUTER_DENSE"] = "0"
        before = bench.krouter_answers(w2, src)
        after = bench.krouter_answers(w2, vault)
        floor = bench.bm25_floor_answers(w2, qset)
        report = {
            "set": qset, "intents": len({p["intent"] for p in pairs}), "week1_logged": logged, "night": learned,
            "week2": {"krouter_before": summary(bench.score(w2, before)),
                      "krouter_after_one_night": summary(bench.score(w2, after)),
                      "bm25_two_rules": summary(bench.score(w2, floor))},
            "after_minus_before_ci95": {k: v for k, v in bench.bootstrap(w2, after, before).items()
                                        if k.startswith("delta")},
        }
        print(json.dumps(report, ensure_ascii=False, indent=1))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
