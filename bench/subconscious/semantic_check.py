#!/usr/bin/env python3
"""Set 45, third addendum (bench/memory_honesty/HELDOUT.md): can a local embedding model tell a message that mentions a
page from one that should be left alone, where the hook's word matching cannot? A one-off mechanical check on the
development half. Not a product path: nothing here is imported by the engine.

    python3 -m pip install fastembed numpy            # in an environment of its own; not a KRouter dependency
    python3 bench/subconscious/semantic_check.py --model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
        --save bench/subconscious/results/set45/semantic/dev-minilm.json

Pages: every page of the bench vault (vault3 + overlay) outside `90 系统文件/` whose `type` is not a log type, as one text
(title and body). A message is embedded as the hook sees it (`recollect.prose`). The first page by cosine is mapped to the
page in force (`recollect.current`, as the hook does: a replaced page stands for the one that replaced it). It is
brought when its cosine is at least T and leads the best page of another topic by at least D. T and D are chosen on this
half: among the settings with at most 3 of 48 quiet messages loud and at most 1 wrong page, the one with the most recall
cases right (then changed right, then fewer loud, then the higher T). Scored by set 32's `score` and printed by set 45's
`report`. The model runs on this machine; nothing is sent anywhere after the model file is downloaded.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "skill/krouter/scripts"))
sys.path.insert(0, str(HERE))
os.environ["KROUTER_NO_QUERY_LOG"] = "1"

QUIET_MAX, WRONG_MAX = 3, 1
TS = [round(0.20 + 0.01 * i, 2) for i in range(71)]
DS = [0.0, 0.02, 0.05, 0.10]


def auc(pos: list[float], neg: list[float]) -> float:
    """The chance that a mention scores above a quiet message (ties count half)."""
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg)) if pos and neg else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--save", default="")
    ap.add_argument("--model-dir", default="", help="a folder that already holds the model's files (no download)")
    ap.add_argument("--query-prefix", default="")
    ap.add_argument("--page-prefix", default="")
    a = ap.parse_args()

    import numpy as np
    from fastembed import TextEmbedding

    import recollect as R
    import run as set32
    import set45

    rows = set45.case_file("set45dev")
    tmp = Path(tempfile.mkdtemp())
    os.environ.update(KROUTER_CACHE_DIR=str(tmp / "cache"), KROUTER_STATE_DIR=str(tmp / "state"))
    v = set32.make_vault(tmp)
    import recall_index as ri

    ri.recall(v, "warm up the index")
    today = date.today()

    rels, texts = [], []
    for p in sorted(v.rglob("*.md")):
        rel = p.relative_to(v).as_posix()
        if rel.startswith("90 系统文件/"):
            continue
        got = R.page(v, rel)
        if got is None or (got[0].get("type") or "").lower() in R.LOG_TYPES:
            continue
        rels.append(rel)
        texts.append(f"{got[0].get('title') or p.stem}\n{got[1]}".strip())
    cur = {rel: R.current(v, rel, today) for rel in rels}

    t0 = time.perf_counter()
    model = TextEmbedding(a.model, specific_model_path=a.model_dir) if a.model_dir else TextEmbedding(a.model)
    t_load = time.perf_counter() - t0

    def embed(xs: list[str], prefix: str):
        m = np.array(list(model.embed([prefix + x for x in xs])), dtype="float32")
        return m / np.linalg.norm(m, axis=1, keepdims=True)

    t0 = time.perf_counter()
    P = embed(texts, a.page_prefix)
    t_pages = time.perf_counter() - t0

    feats, lat = {}, []
    for r in rows:
        said = R.prose(r["text"])
        if not said:
            feats[r["id"]] = None
            continue
        t0 = time.perf_counter()
        sims = (P @ embed([said], a.query_prefix)[0])
        order = np.argsort(-sims)
        lat.append(time.perf_counter() - t0)
        top = rels[order[0]]
        c = cur[top]
        topic = c[0] if c else top
        s2 = 0.0
        for j in order[1:]:
            cj = cur[rels[j]]
            if (cj[0] if cj else rels[j]) != topic:
                s2 = float(sims[j])
                break
        feats[r["id"]] = {"s1": float(sims[order[0]]), "s2": s2, "top": top, "bring": c[0] if c else "",
                          "older": c[1] if c else ""}

    hook = {r["id"]: R.recollect(v, r["text"], R.DEFAULT_ROUTES) for r in rows}

    def brought(T: float, D: float, with_hook: bool) -> dict[str, list[dict]]:
        out = {}
        for r in rows:
            f = feats[r["id"]]
            hs = list(hook[r["id"]]) if with_hook else []
            if f and f["bring"] and f["s1"] >= T and f["s1"] - f["s2"] >= D and len(hs) < R.PER_PROMPT \
                    and f["bring"] not in [h["real"] for h in hs]:
                hs.append({"real": f["bring"], "route": "semantic"})
            out[r["id"]] = hs
        return out

    def summary(b: dict) -> dict:
        s = set32.score(rows, b)
        tot = lambda k: s.get(f"{k}_zh", 0) + s.get(f"{k}_en", 0)  # noqa: E731
        rec = [r for r in rows if r["kind"] == "recall"]
        unnamed = sum(1 for r in rec if not r["named_mech"] and r["expect"] in [h["real"] for h in b[r["id"]]])
        return {"recall": tot("recall_right"), "unnamed": unnamed, "changed": tot("changed_right"),
                "quiet_loud": tot("quiet_loud"), "wrong": tot("wrong"), "old": tot("old")}

    def choose(with_hook: bool):
        best = None
        for T in TS:
            for D in DS:
                s = summary(brought(T, D, with_hook))
                if s["quiet_loud"] > QUIET_MAX or s["wrong"] > WRONG_MAX:
                    continue
                key = (s["recall"], s["changed"], -s["quiet_loud"], T)
                if best is None or key > best[0]:
                    best = (key, T, D, s)
        return best

    kinds = {r["id"]: r["kind"] for r in rows}
    pos = [feats[i]["s1"] for i in feats if kinds[i] == "recall" and feats[i]]
    neg = [feats[i]["s1"] for i in feats if kinds[i] == "quiet" and feats[i]]
    lex = {}
    for r in rows:
        if r["kind"] in ("recall", "quiet"):
            res = ri.recall(v, R.prose(r["text"]), refresh_first=False, assoc=False, gate=False) or {}
            hits = res.get("hits") or []
            lex[r["id"]] = (hits[0]["score"] if hits else 0.0, res.get("margin") or 0.0)
    lpos = [lex[i] for i in lex if kinds[i] == "recall"]
    lneg = [lex[i] for i in lex if kinds[i] == "quiet"]
    top1 = sum(1 for r in rows if r["kind"] == "recall" and feats[r["id"]] and feats[r["id"]]["bring"] == r["expect"])

    out = {"model": a.model, "pages": len(rels), "dim": int(P.shape[1]),
           "auc": {"semantic first-page cosine": round(auc(pos, neg), 3),
                   "semantic lead over the next topic": round(auc(
                       [feats[i]["s1"] - feats[i]["s2"] for i in feats if kinds[i] == "recall" and feats[i]],
                       [feats[i]["s1"] - feats[i]["s2"] for i in feats if kinds[i] == "quiet" and feats[i]]), 3),
                   "lexical first-page score (gate off)": round(auc([x[0] for x in lpos], [x[0] for x in lneg]), 3),
                   "lexical margin (gate off)": round(auc([x[1] for x in lpos], [x[1] for x in lneg]), 3)},
           "recall cases whose first page by cosine is the expected page, no threshold": f"{top1}/48",
           "hook alone": summary(hook)}
    for label, wh in (("semantic alone", False), ("hook and semantic", True)):
        best = choose(wh)
        if best is None:
            out[label] = "no setting keeps quiet loud and wrong pages within the limits"
            continue
        _k, T, D, s = best
        out[label] = {"T": T, "D": D, **s}
        set45.report(rows, brought(T, D, wh), f"{label} (T={T}, D={D})")
    rnd = np.random.default_rng(1).standard_normal((10000, P.shape[1])).astype("float32")
    q = P[0]
    t0 = time.perf_counter()
    for _ in range(20):
        np.argsort(-(rnd @ q))
    t_dot = (time.perf_counter() - t0) / 20
    out["cost"] = {"model load s": round(t_load, 2), "embed all pages s": round(t_pages, 2),
                   "per page ms": round(1000 * t_pages / len(rels), 1),
                   "per message ms, median (embed and rank)": round(1000 * statistics.median(lat), 1),
                   "ranking 10,000 pages ms": round(1000 * t_dot, 2),
                   "embedding 10,000 pages of this length, estimate s": round(t_pages / len(rels) * 10000)}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if a.save:
        Path(a.save).parent.mkdir(parents=True, exist_ok=True)
        Path(a.save).write_text(json.dumps({"summary": out, "cases": [
            {"id": r["id"], "kind": r["kind"], **({k: (round(x, 4) if isinstance(x, float) else x)
                                                  for k, x in feats[r["id"]].items()} if feats[r["id"]] else {})}
            for r in rows]}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
