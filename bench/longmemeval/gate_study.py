#!/usr/bin/env python3
"""Set 13 (HELDOUT.md): can KRouter's refusal gate refuse more unanswerable questions without losing answerable ones?

No model is called. For every LongMemEval S question it records what the shipped gate decided and a handful of
candidate signals (top score, gap to the second page, strong-match count, how much of the question's idf mass the
best page covers, question words that no page contains, ...), then searches one- and two-signal rules ("also refuse
when ...") on the DEVELOPMENT part only:

- the 30 real `_abs` questions (a development set since set 7's amendment);
- a seed-drawn half of the 470 answerable questions (`lme.split_of`), for the cost: answers that were right and
  would be refused;
- the same half with its answer sessions removed (`lme.make_ablated`), unanswerable by construction.

The other half (`heldout`) is not opened by this script: it is only written to the feature file so a rule chosen
here can be checked once, afterwards.

    python3 bench/longmemeval/lme.py convert --data longmemeval_s_cleaned.json
    python3 bench/longmemeval/gate_study.py            # ~5 minutes, writes STATE/gate_study.json
"""

from __future__ import annotations

import itertools
import json
import math
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lme  # noqa: E402

SCRIPTS = lme.REPO / "skill/krouter-obsidian/scripts"
FEATURES = ("top", "margin", "strong", "cov1", "nterms", "nabsent", "miss_mass", "gap_rel")
HIGH_IS_ABSENT = {"nabsent", "miss_mass"}  # for these a rule fires when the value is >=; for the rest when <=
BUDGETS = (0, 2, 5)  # answerable-dev answers lost (235 of them: 2 is 0.85 points)


def features(ri, vault: Path, question: str, cache: Path) -> dict:
    """What the gate decided and the signals around it. Uses recall's own helpers, changes nothing in it."""
    os.environ["KROUTER_CACHE_DIR"] = str(cache)
    gated = ri.recall(vault, question, limit=3)
    free = ri.recall(vault, question, limit=5, gate=False, refresh_first=False)
    con = ri.connect(ri.cache_path(vault))
    try:
        n_docs = con.execute("SELECT count(*) FROM files").fetchone()[0] or 1
        raw: list[str] = []
        for t in ri.tokens(question):
            if (len(t) == 1 and ri.CJK_RE.fullmatch(t)) or t in ri.QUERY_STOP or t in raw:
                continue
            raw.append(t)
        raw = [t for t in raw if t not in ri.EN_FUNCTION] or raw

        def forms(t):
            return [t] + ([] if ri.is_cjk_bigram(t) else ri.latin_forms(t))

        df = ri.term_df(con, [f for t in raw for f in forms(t)] + [c for t in raw if ri.is_cjk_bigram(t) for c in t])
    finally:
        con.close()

    def dfx(t):
        return max(df.get(f, 0) for f in forms(t))

    idf = {t: math.log((n_docs - dfx(t) + 0.5) / (dfx(t) + 0.5) + 1) for t in raw}
    hits = free["hits"]
    page = set(ri.tokens((vault / hits[0]["rel"]).read_text(encoding="utf-8", errors="ignore"))) if hits else set()
    seen = {t for t in raw if any(f in page for f in forms(t))}
    total = sum(idf.values()) or 1.0
    top = hits[0]["score"] if hits else 0.0
    second = hits[1]["score"] if len(hits) > 1 else 0.0
    return {"refused": gated["confidence"] == "none" or not gated["hits"],
            "cited": [h["rel"] for h in gated["hits"]] if gated["confidence"] != "none" else [],
            "top": top, "margin": min(free.get("margin") or 0, 5), "strong": free.get("strong") or 0,
            "cov1": sum(idf[t] for t in seen) / total, "nterms": len(raw),
            "nabsent": sum(dfx(t) == 0 for t in raw), "miss_mass": sum(idf[t] for t in raw if t not in seen),
            "gap_rel": (top - second) / max(top, 1e-9)}


def collect(rows: list[dict], label: str) -> list[dict]:
    sys.path.insert(0, str(SCRIPTS))
    os.environ["KROUTER_NO_QUERY_LOG"] = "1"
    import recall_index as ri

    out = []
    with tempfile.TemporaryDirectory(prefix="krouter-gate-") as tmp:
        for i, it in enumerate(rows):
            out.append({"id": it["id"], "split": it["split"], **features(ri, Path(it["vault"]), it["q"], Path(tmp))})
            for f in Path(tmp).glob("recall-*"):
                f.unlink(missing_ok=True)
            if i % 100 == 99:
                print(f"{label}: {i + 1}/{len(rows)}", file=sys.stderr)
    return out


def fires(rule: tuple, f: dict) -> bool:
    return all((f[name] >= t) if name in HIGH_IS_ABSENT else (f[name] <= t) for name, t in rule)


def search(unrefused_abs: list[dict], answered_right: list[dict]) -> list[tuple]:
    """Every one- and two-signal rule over a coarse threshold grid: (rule, abs newly refused, answers lost)."""
    grid = {n: sorted({round(x[n], 2) for x in unrefused_abs + answered_right}) for n in FEATURES}
    rules = [((n, t),) for n in FEATURES for t in grid[n]]
    for a, b in itertools.combinations(FEATURES, 2):
        rules += [((a, ta), (b, tb)) for ta in grid[a][::2] for tb in grid[b][::2]]
    return [(r, sum(fires(r, x) for x in unrefused_abs), sum(fires(r, x) for x in answered_right)) for r in rules]


def auc(pos: list[dict], neg: list[dict], name: str) -> float:
    """P(a still-answered real `_abs` question scores more 'unanswerable' than a right answer) on one signal, 0.5 = chance."""
    sign = 1 if name in HIGH_IS_ABSENT else -1
    wins = sum((sign * a[name] > sign * b[name]) + 0.5 * (sign * a[name] == sign * b[name]) for a in pos for b in neg)
    return wins / (len(pos) * len(neg))


def main() -> int:
    rows = lme.load_questions()
    split = lme.split_of(rows)
    meta = {r["id"]: r for r in rows}
    full = [{"id": r["id"], "q": r["q"], "split": split[r["id"]], "vault": r["vault"]} for r in rows]
    full = [it for it in full if it["split"] != "heldout"]  # the heldout half is not opened here
    feats = collect(full, "full vaults")
    ablated = [it for it in lme.make_ablated(rows) if it["split"] == "dev"]
    abl = collect(ablated, "answer sessions removed")

    def right(f):  # the shipped gate cited an answer session
        answer = set(meta[f["id"]]["answer_sessions"])
        return any(meta[f["id"]]["pages"][p]["sid"] in answer for p in f["cited"])

    abs_f = [f for f in feats if f["split"] == "abs"]
    dev_f = [f for f in feats if f["split"] == "dev"]
    unrefused = [f for f in abs_f if not f["refused"]]
    kept_right = [f for f in dev_f if right(f)]
    res = search(unrefused, kept_right)
    report = {"abs_refused_now": f"{sum(f['refused'] for f in abs_f)}/{len(abs_f)}",
              "dev_answerable_right_now": f"{len(kept_right)}/{len(dev_f)}",
              "ablated_dev_refused_now": f"{sum(f['refused'] for f in abl)}/{len(abl)}",
              "rules_searched": len(res), "best_by_budget": {},
              "auc_per_signal": {n: round(auc(unrefused, kept_right, n), 3) for n in FEATURES}}
    for budget in BUDGETS:
        ok = [r for r in res if r[2] <= budget]
        best = max(r[1] for r in ok)
        report["best_by_budget"][f"lost<={budget}"] = {
            "newly_refused_of_%d_unrefused_abs" % len(unrefused): best,
            "example": [list(map(list, r[0])) for r in ok if r[1] == best][:2]}
    # a single-signal curve for the signal that looks most natural: how much of the question the best page covers
    report["cov1_curve"] = [{"refuse_if_cov1_below": c,
                             "abs_refused": sum(f["refused"] or f["cov1"] < c for f in abs_f),
                             "answers_lost": sum((not f["refused"]) and f["cov1"] < c for f in kept_right),
                             "ablated_refused": sum(f["refused"] or f["cov1"] < c for f in abl)}
                            for c in (0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6)]
    (lme.STATE / "gate_study.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
