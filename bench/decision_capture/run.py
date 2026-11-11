#!/usr/bin/env python3
"""Decision capture: of the decisions made in a session, how many does the distill step write down, and how much of
what it writes is not a decision? A small fixed set, scored by rule, so a change to the distill can be checked in a
minute without a judge model.

`sessions.jsonl` holds 14 short sessions (10 Chinese, 4 English) written for this bench, not taken from anyone's
history: 14 decisions in 10 of them, 3 of them changes of mind ("A → B"), and 4 sessions in which nothing was
decided (discussion, a one-off, steps only, "I'll think about it"). Each decision lists the words a line must hold to
count (`must`: every group needs one of its alternatives; a change also lists its end state, `final`, so a line
that writes only the new value is neither a capture of the change nor a false line); `forbid` lists things that are not decisions (steps,
discussion) so a line that writes one down is reported as such.

    run.py --cli /opt/homebrew/bin/claude     # the shipped distill on the model lane named here
    run.py --replay lines.jsonl               # score lines saved by an earlier run (--save) or by another system
    run.py --oracle                           # the gold itself: checks the scorer (recall 1, false 0)

Reported: recall (decisions matched by some line), change recall (changes matched by a line with "→"), false
extraction rate (lines that match no decision of their session, out of all lines), steps-or-discussion lines (the
part of those that hit `forbid`), and lines written for the sessions where nothing was decided. Matching is lexical,
so a correct line worded with none of the listed alternatives counts as a miss and a false line: read `--show`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[1] / "skill/krouter/scripts"
sys.path.insert(0, str(SCRIPTS))
DAY = date(2026, 10, 1)
NONE_LINES = ("没有定下来的事", "没有改主意的事", "nothing was decided", "no decisions")


def load(path: Path = HERE / "sessions.jsonl") -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def norm(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).lower())


def matches(line: str, must: list[list[str]]) -> bool:
    n = norm(line)
    return all(any(norm(alt) in n for alt in group) for group in must)


def entry(s: dict) -> dict:
    turns = []
    for t in s["turns"]:
        hh, mm = map(int, t["at"].split(":"))
        ts = datetime(DAY.year, DAY.month, DAY.day, hh, mm).astimezone().isoformat()
        turns.append({"ts": ts, "ask": t["ask"], "answer": t["answer"]})
    return {"agent": "claude-code", "id": f"bench-{s['id']}", "day": DAY, "project": "bench", "root": "",
            "title": s["turns"][0]["ask"][:40], "turns": turns}


def distill_all(sessions: list[dict], vault: Path) -> dict[str, list[str]]:
    import import_sessions as imp

    out = {}
    for s in sessions:
        e = entry(s)
        digest, _ = imp.distill(e, imp.render(e), vault, dry=False)
        out[s["id"]] = [ln for ln in digest.splitlines() if ln.strip()]
        print(f"distilled {s['id']}: {len(out[s['id']])} lines", file=sys.stderr)
    return out


def oracle(sessions: list[dict]) -> dict[str, list[str]]:
    def line(g: dict) -> str:
        words = [grp[0] for grp in g["must"]]
        return "- " + (" → ".join(words) if g["kind"] == "change" else " ".join(words))

    return {s["id"]: [line(g) for g in s["gold"]] for s in sessions}


def score(sessions: list[dict], lines: dict[str, list[str]]) -> dict:
    gold = found = changes = changes_found = total = false = forbidden = empty_lines = 0
    per = []
    for s in sessions:
        got = [ln for ln in lines.get(s["id"], []) if not any(n in ln for n in NONE_LINES)]
        hit = [any(matches(ln, g["must"]) and (g["kind"] != "change" or "→" in ln) for ln in got) for g in s["gold"]]
        # 改主意只写了新值（「缓存 10 分钟」）：不算这条改动被记下，也不算错行
        wrong = [ln for ln in got if not any(matches(ln, g["must"]) or (g.get("final") and matches(ln, g["final"]))
                                             for g in s["gold"])]
        steps = [ln for ln in wrong if any(matches(ln, f["must"]) for f in s.get("forbid", []))]
        gold += len(s["gold"])
        found += sum(hit)
        changes += sum(g["kind"] == "change" for g in s["gold"])
        changes_found += sum(h for h, g in zip(hit, s["gold"]) if g["kind"] == "change")
        total += len(got)
        false += len(wrong)
        forbidden += len(steps)
        empty_lines += len(got) if not s["gold"] else 0
        per.append({"id": s["id"], "gold": len(s["gold"]), "found": sum(hit), "lines": len(got), "false": len(wrong),
                    "steps": len(steps), "missed": [g["must"] for g, h in zip(s["gold"], hit) if not h],
                    "false_lines": wrong})
    rate = lambda a, b: round(a / b, 3) if b else None  # noqa: E731
    return {"sessions": len(sessions), "decisions": gold, "recall": rate(found, gold),
            "changes": changes, "change_recall": rate(changes_found, changes), "lines": total,
            "false_extraction_rate": rate(false, total), "steps_or_discussion_lines": forbidden,
            "lines_on_no_decision_sessions": empty_lines, "per_session": per}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--cli", help="model lane: a CLI path (as the nightly job's --cli)")
    src.add_argument("--replay", help="JSONL of {id, lines} to score")
    src.add_argument("--oracle", action="store_true")
    ap.add_argument("--save", help="write the distilled lines here (JSONL), for --replay later")
    ap.add_argument("--show", action="store_true", help="print each session's misses and false lines")
    args = ap.parse_args()
    sessions = load()
    if args.oracle:
        lines = oracle(sessions)
    elif args.replay:
        lines = {r["id"]: r["lines"] for r in map(json.loads, Path(args.replay).read_text(encoding="utf-8").splitlines())}
    else:
        os.environ["KROUTER_LEARN_CLI"] = args.cli
        os.environ.setdefault("KROUTER_NO_QUERY_LOG", "1")
        import tempfile

        lines = distill_all(sessions, Path(tempfile.mkdtemp(prefix="krouter-decision-bench-")))
    if args.save:
        Path(args.save).write_text("".join(json.dumps({"id": k, "lines": v}, ensure_ascii=False) + "\n"
                                           for k, v in lines.items()), encoding="utf-8")
    res = score(sessions, lines)
    if not args.show:
        res["per_session"] = [{k: v for k, v in p.items() if k not in ("missed", "false_lines")} for p in res["per_session"]]
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
