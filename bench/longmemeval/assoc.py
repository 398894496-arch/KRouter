#!/usr/bin/env python3
"""Set 18 (HELDOUT.md): does the associative path bring every answer session, in the same number of pages?

Offline, no model: for each answerable LongMemEval question and k = 3, 5, 8, whether the k pages a system returns
include every session the benchmark labels as holding the answer. Systems, each giving exactly k pages, no refusal:

- `bm25`: FTS5 BM25 over character pairs and words, superseded pages skipped (`bench/memory_honesty/run.py`);
- `krouter`: in-process `recall(..., gate=False)` with the associative path off;
- `krouter+assoc`: the same direct hits, the associative pages filling the k slots as `recall_index.page_list` does.

    python3 bench/longmemeval/assoc.py --half dev                  # tune on this
    python3 bench/longmemeval/assoc.py --half heldout              # once, for the configuration chosen on dev
    python3 bench/longmemeval/assoc.py --half dev --why            # per-question detail (dev only)

`--locomo` runs the same count on LoCoMo (set 10's vaults, `bench/locomo/locomo.py convert` first; categories 1-4
with evidence labels, a session counts as an answer session when the authors cite a turn in it). Nothing is tuned on
it; it is a second outside check, all questions, no halves.

The halves are set 14's (`lme.split_of`, seed 20261110). Questions come from `lme.py convert` (state in
`~/.local/state/krouter-eval/lme/`, `KROUTER_LME_STATE` to move it). The recall cache goes to a temporary directory.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import random
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import lme  # noqa: E402

KS = (3, 5, 8)
SYSTEMS = ("bm25", "krouter", "krouter+assoc")
SEED = 20261110
_BM25: dict = {}
RESAMPLES = 10_000


def locomo_rows() -> list[dict]:
    """LoCoMo questions in this script's shape: categories 1-4 with evidence, sessions as `answer_sessions`."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("locomo_bench", REPO / "bench/locomo/locomo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = []
    for it in mod.load_questions():
        if it["abs"] or not it["evidence_sessions"]:
            continue
        pages = {rel: {"sid": str(n)} for rel, n in it["pages"].items()}
        out.append({"id": it["id"], "q": it["q"], "type": f"category-{it['category']}", "vault": it["vault"],
                    "pages": pages, "answer_sessions": [str(n) for n in it["evidence_sessions"]]})
    return out


def bm25_pages(bench, vault: Path, q: str, n: int) -> list[str]:
    key = str(vault)
    if key not in _BM25:
        _BM25.clear()
        _BM25[key] = bench._bm25_index(True, vault, True)
    con = _BM25[key]
    words = bench._cjk_tokens(q)
    if not words:
        return []
    rows = con.execute("SELECT rel FROM d WHERE d MATCH ? ORDER BY bm25(d) LIMIT ?",
                       (" OR ".join(f'"{w}"' for w in words), n)).fetchall()
    return [r[0] for r in rows]


def krouter_pages(ri, vault: Path, q: str, k: int, assoc: bool) -> tuple[list[str], list[dict]]:
    res = ri.recall(vault, q, limit=k, gate=False, assoc=assoc)
    return ri.page_list(res, k), res.get("assoc", [])


def full(it: dict, pages: list[str]) -> bool:
    got = {it["pages"].get(rel, {}).get("sid") for rel in pages}
    return bool(it["answer_sessions"]) and set(it["answer_sessions"]) <= got


def paired_ci(a: list[int], b: list[int], seed: int = SEED) -> list[float]:
    d = [x - y for x, y in zip(a, b)]
    if not d:
        return [0.0, 0.0]
    rng = random.Random(seed)
    boots = sorted(sum(rng.choice(d) for _ in d) for _ in range(RESAMPLES))
    return [boots[int(0.025 * RESAMPLES)], boots[int(0.975 * RESAMPLES)]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--half", choices=["dev", "heldout"])
    ap.add_argument("--locomo", action="store_true", help="LoCoMo instead of LongMemEval (all questions)")
    ap.add_argument("--repo", default=str(REPO))
    ap.add_argument("--why", action="store_true", help="dev only: per-question detail")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="", help="write per-question results (JSONL) here")
    args = ap.parse_args()
    if args.why and args.half != "dev":
        ap.error("--why is for the dev half only")
    if not args.half and not args.locomo:
        ap.error("--half or --locomo")
    os.environ["KROUTER_NO_QUERY_LOG"] = "1"
    os.environ.pop("KROUTER_MAP", None)
    repo = Path(args.repo)
    sys.path.insert(0, str(repo / "skill/krouter-obsidian/scripts"))
    if args.locomo:
        rows = locomo_rows()[: args.limit or None]
        args.half = "locomo"
    else:
        rows = lme.load_questions()
        split = lme.split_of(rows)
        rows = [r for r in rows if split[r["id"]] == args.half][: args.limit or None]
    _, bench = lme.bench_module()
    result: dict[str, dict[int, list[int]]] = {s: {k: [] for k in KS} for s in SYSTEMS}
    per = []
    with tempfile.TemporaryDirectory(prefix="krouter-assoc-", ignore_cleanup_errors=True) as tmp:
        os.environ["KROUTER_CACHE_DIR"] = tmp
        import recall_index as ri

        for it in rows:
            vault = Path(it["vault"])
            b = bm25_pages(bench, vault, it["q"], max(KS))
            row = {"id": it["id"], "type": it["type"]}
            for k in KS:
                kr, _ = krouter_pages(ri, vault, it["q"], k, False)
                ka, extra = krouter_pages(ri, vault, it["q"], k, True)
                for name, pages in (("bm25", b[:k]), ("krouter", kr), ("krouter+assoc", ka)):
                    result[name][k].append(int(full(it, pages)))
                    row[f"{name}@{k}"] = int(full(it, pages))
                if args.why and k == 3:
                    sid = {rel: m["sid"] for rel, m in it["pages"].items()}
                    row["answer"] = it["answer_sessions"]
                    row["kr3"] = [sid.get(p) for p in kr]
                    row["ka3"] = [sid.get(p) for p in ka]
                    row["via"] = [(sid.get(a["rel"]), [v["kind"] for v in a["via"]]) for a in extra]
            per.append(row)
            if not args.locomo:  # LoCoMo: many questions share one vault, keep its cache
                for f in Path(tmp).glob("recall-*"):
                    f.unlink(missing_ok=True)
    types = sorted({r["type"] for r in rows})
    report = {"half": args.half, "questions": len(rows), "by_type": {t: sum(r["type"] == t for r in rows) for t in types}}
    for name in SYSTEMS:
        report[name] = {}
        for k in KS:
            cell = {"all": sum(result[name][k])}
            for t in types:
                cell[t] = sum(v for v, r in zip(result[name][k], rows) if r["type"] == t)
            report[name][k] = cell
    report["assoc_minus_bm25_ci95"] = {}
    for k in KS:
        focus = "category-1" if args.locomo else "multi-session"
        ms = [i for i, r in enumerate(rows) if r["type"] == focus]
        report["assoc_minus_bm25_ci95"][k] = {
            focus: paired_ci([result["krouter+assoc"][k][i] for i in ms], [result["bm25"][k][i] for i in ms]),
            "all": paired_ci(result["krouter+assoc"][k], result["bm25"][k])}
    if args.out:
        Path(args.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in per), encoding="utf-8")
    if args.why:
        for r in per:
            if r["krouter+assoc@3"] != r["krouter@3"]:
                print(json.dumps(r, ensure_ascii=False))
    if args.out:
        Path(args.out).with_suffix(".report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                                             encoding="utf-8")
    short = {"multi-session": "multi", "temporal-reasoning": "temporal", "knowledge-update": "ku",
             "single-session-user": "ss-user", "single-session-assistant": "ss-asst", "single-session-preference": "ss-pref"}
    print(f"{args.half}: {len(rows)} questions " + " ".join(f"{short.get(t, t)}={n}" for t, n in report["by_type"].items()))
    for name in SYSTEMS:
        print(f"{name:14s} " + " | ".join(f"k={k} all {report[name][k]['all']:3d} " + " ".join(
            f"{short.get(t, t)} {report[name][k][t]}" for t in types) for k in KS))
    ci = report["assoc_minus_bm25_ci95"]
    print(("assoc-bm25 95% CI category-1: " if args.locomo else "assoc-bm25 95% CI multi: ") + ", ".join(f"k={k} {ci[k][focus]}" for k in KS)
          + "; all: " + ", ".join(f"k={k} {ci[k]['all']}" for k in KS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
