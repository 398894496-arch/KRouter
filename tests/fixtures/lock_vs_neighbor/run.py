#!/usr/bin/env python3
"""Reproduce the lock-vs-neighbor experiment.

Naive retrievers see every markdown file, including expired pages.
Ablations get the same metadata the lock has: `invalid_at` (`*_live`) and the
live alias table with nouns prepended (`tfidf_map`).

Scoring is exact path match. Citing a neighbor is a failure. A miss is success
when gold is null. Rewrite hits (CJK / paraphrase aliases) are tagged in gold.
Not LongMemEval. Claim B is lexical TF-IDF. Claim C is frozen multilingual MiniLM
on the same gold file (replay dense_vectors.json; no extra pip in pytest).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "skill/krouter/scripts"))

from canonical_lookup import in_force, live_rows, load_rows, lookup, parse_frontmatter  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_VAULT = HERE / "vault"
DEFAULT_MAP = HERE / "canonical_sources.psv"
DEFAULT_GOLD = HERE / "gold.jsonl"
DEFAULT_DENSE = HERE / "dense_vectors.json"
DEFAULT_DENSE_MID = HERE / "dense_m3_vectors.json"
DENSE_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DENSE_SEQ = 256
DENSE_MID_MODEL = "BAAI/bge-m3"
DENSE_MID_SEQ = 512
TODAY = date(2026, 8, 27)
MISS = None
TOKEN = re.compile(r"[a-z0-9\u4e00-\u9fff]+", re.I)
THRESHOLDS = (0.0, 0.05, 0.08, 0.10, 0.15, 0.19, 0.20, 0.23, 0.25, 0.30)
STOP = frozenset(
    "a an the is in of to for and or on at by from with what how why when where "
    "this that these those it its be are was were been being not no do does did".split()
)


def rel(path: Path, vault: Path) -> str:
    return path.relative_to(vault).as_posix()


def md_files(vault: Path) -> list[Path]:
    return sorted(
        p
        for p in vault.rglob("*.md")
        if p.is_file() and ".obsidian" not in p.parts
    )


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def tokens(text: str) -> list[str]:
    return [m.group(0).lower() for m in TOKEN.finditer(text)]


def char_ngrams(text: str, n: int = 3) -> list[str]:
    compact = re.sub(r"\s+", " ", text.lower())
    if len(compact) < n:
        return [compact] if compact else []
    return [compact[i : i + n] for i in range(len(compact) - n + 1)]


def features(text: str, mode: str = "word_char") -> Counter[str]:
    bag: Counter[str] = Counter()
    toks = tokens(text)
    if mode == "word_stopped":
        toks = [t for t in toks if t not in STOP]
    bag.update(f"w:{t}" for t in toks)
    if mode == "word_char":
        bag.update(f"c:{g}" for g in char_ngrams(text, 3))
    return bag


def feat_fn(mode: str):
    return lambda text: features(text, mode)


def dense_fingerprint(gold, files, live_files, named_map, vault: Path) -> str:
    h = hashlib.sha256()
    for item in gold:
        h.update(item["id"].encode())
        h.update(b"\0")
        h.update(item["query"].encode())
        h.update(b"\n")
    for path in files:
        h.update(rel(path, vault).encode())
        h.update(b"\0")
        h.update(read(path).encode())
        h.update(b"\n")
    for path in live_files:
        h.update(b"live:")
        h.update(rel(path, vault).encode())
        h.update(b"\n")
    for name, text in named_map:
        h.update(b"map:")
        h.update(name.encode())
        h.update(b"\0")
        h.update(text.encode())
        h.update(b"\n")
    return h.hexdigest()


def load_dense(
    path: Path,
    gold,
    files,
    live_files,
    named_map,
    vault: Path,
    expected_model: str,
) -> dict:
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} missing. Run python3 tests/fixtures/lock_vs_neighbor/encode_dense.py"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = dense_fingerprint(gold, files, live_files, named_map, vault)
    if payload.get("fingerprint") != expected:
        raise RuntimeError(
            f"{path} is stale (fingerprint mismatch). Re-run encode_dense.py"
        )
    if payload.get("model") != expected_model:
        raise RuntimeError(
            f"{path} model {payload.get('model')!r} != {expected_model!r}"
        )
    missing_q = [item["id"] for item in gold if item["id"] not in payload.get("queries", {})]
    if missing_q:
        raise RuntimeError(f"{path} missing query vectors: {missing_q}")
    return payload


def dense_dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def dense_predict(
    query_id: str,
    query_vecs: dict[str, list[float]],
    doc_vecs: dict[str, list[float]],
    min_score: float = 0.0,
) -> str | None:
    qv = query_vecs[query_id]
    ranked = sorted(
        ((dense_dot(qv, dv), name) for name, dv in doc_vecs.items()),
        key=lambda item: (-item[0], item[1]),
    )
    if not ranked or ranked[0][0] < min_score:
        return MISS
    return ranked[0][1]


def dense_top(
    query_id: str,
    query_vecs: dict[str, list[float]],
    doc_vecs: dict[str, list[float]],
) -> tuple[float, str | None]:
    qv = query_vecs[query_id]
    ranked = sorted(
        ((dense_dot(qv, dv), name) for name, dv in doc_vecs.items()),
        key=lambda item: (-item[0], item[1]),
    )
    if not ranked:
        return 0.0, MISS
    return ranked[0][0], ranked[0][1]


def load_gold(path: Path) -> list[dict]:
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            rows.append(json.loads(raw))
    return rows


def krouter_predict(query: str, rows, vault: Path) -> str | None:
    hit = lookup(query, rows, vault=vault, today=TODAY)
    if hit is None:
        return MISS
    return hit[1].replace("\\", "/")


def lexical_predict(query: str, files: list[Path], vault: Path) -> str | None:
    qtok = tokens(query)
    if not qtok:
        return MISS
    scored: list[tuple[int, str]] = []
    for path in files:
        text = read(path).lower()
        score = sum(text.count(tok) for tok in qtok)
        if score:
            scored.append((score, rel(path, vault)))
    if not scored:
        return MISS
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][1]


def live_md_files(vault: Path, today: date) -> list[Path]:
    """Drop pages whose frontmatter is expired or not yet valid. Unmapped pages stay."""
    kept: list[Path] = []
    for path in md_files(vault):
        live, _, _ = in_force(parse_frontmatter(path), today)
        if live:
            kept.append(path)
    return kept


def map_texts(vault: Path, rows, today: date) -> list[tuple[str, str]]:
    """Live alias rows only. Aliases are prepended so cosine sees the same nouns."""
    out: list[tuple[str, str]] = []
    for _case_id, aliases, source, _anchor in live_rows(rows, vault, today):
        text = " ".join(aliases) + "\n" + read(vault / source)
        out.append((source.replace("\\", "/"), text))
    return out


def build_tfidf(files: list[Path], vault: Path, feat=None):
    feat = feat or features
    return build_tfidf_texts([(rel(p, vault), read(p)) for p in files], feat=feat)


def build_tfidf_texts(named: list[tuple[str, str]], feat=None):
    feat = feat or features
    docs = [(name, feat(text)) for name, text in named]
    df: Counter[str] = Counter()
    for _, bag in docs:
        df.update(bag.keys())
    n = max(len(docs), 1)
    idf = {term: math.log((1 + n) / (1 + count)) + 1.0 for term, count in df.items()}

    def vec(bag: Counter[str]) -> dict[str, float]:
        return {term: (1 + math.log(count)) * idf.get(term, 0.0) for term, count in bag.items()}

    doc_vecs = [(name, vec(bag)) for name, bag in docs]
    return doc_vecs, vec


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    keys = set(a) & set(b)
    num = sum(a[k] * b[k] for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return num / (na * nb)


def tfidf_predict(query: str, doc_vecs, vec, min_score: float = 0.0, feat=None) -> str | None:
    feat = feat or features
    qv = vec(feat(query))
    ranked = sorted(
        ((cosine(qv, dv), name) for name, dv in doc_vecs),
        key=lambda item: (-item[0], item[1]),
    )
    if not ranked or ranked[0][0] < min_score:
        return MISS
    if ranked[0][0] <= 0:
        return MISS
    return ranked[0][1]


def tfidf_top(query: str, doc_vecs, vec, feat=None) -> tuple[float, str | None]:
    feat = feat or features
    qv = vec(feat(query))
    ranked = sorted(
        ((cosine(qv, dv), name) for name, dv in doc_vecs),
        key=lambda item: (-item[0], item[1]),
    )
    if not ranked:
        return 0.0, MISS
    return ranked[0][0], ranked[0][1]


def tfidf_ranks(query: str, doc_vecs, vec, feat=None) -> list[str]:
    feat = feat or features
    qv = vec(feat(query))
    ranked = sorted(
        ((cosine(qv, dv), name) for name, dv in doc_vecs),
        key=lambda item: (-item[0], item[1]),
    )
    return [name for score, name in ranked if score > 0]


def lexical_ranks(query: str, files: list[Path], vault: Path) -> list[str]:
    qtok = tokens(query)
    scored: list[tuple[int, str]] = []
    for path in files:
        text = read(path).lower()
        score = sum(text.count(tok) for tok in qtok) if qtok else 0
        if score:
            scored.append((score, rel(path, vault)))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [name for _, name in scored]


def rrf(rank_lists: list[list[str]], k: int = 60) -> str | None:
    scores: dict[str, float] = defaultdict(float)
    for ranks in rank_lists:
        for i, name in enumerate(ranks):
            scores[name] += 1.0 / (k + i + 1)
    if not scores:
        return MISS
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0][0]


def score_one(pred: str | None, item: dict) -> dict:
    gold = item.get("gold")
    old = item.get("old")
    trap = item.get("trap")
    exact = pred == gold
    false_neighbor = pred is not None and pred != gold
    old_page = bool(old) and pred == old
    trapped = bool(trap) and pred == trap
    return {
        "id": item["id"],
        "slice": item["slice"],
        "query": item["query"],
        "gold": gold,
        "pred": pred,
        "exact": exact,
        "false_neighbor": false_neighbor,
        "old_page": old_page,
        "trapped": trapped,
        "miss": pred is None,
    }


def summarize(rows: list[dict]) -> dict:
    def rate(pred, subset=None):
        use = [r for r in rows if subset is None or r["slice"] == subset]
        if not use:
            return None
        return round(sum(1 for r in use if pred(r)) / len(use), 4)

    slices = {}
    for name in ("hit", "supersede", "neighbor", "negative"):
        part = [r for r in rows if r["slice"] == name]
        if not part:
            continue
        slices[name] = {
            "n": len(part),
            "exact": rate(lambda r: r["exact"], name),
            "false_neighbor": rate(lambda r: r["false_neighbor"], name),
            "old_page": rate(lambda r: r["old_page"], name),
            "trapped": rate(lambda r: r["trapped"], name),
            "miss": rate(lambda r: r["miss"], name),
        }
    return {
        "n": len(rows),
        "exact": rate(lambda r: r["exact"]),
        "false_neighbor": rate(lambda r: r["false_neighbor"]),
        "old_page": rate(lambda r: r["old_page"]),
        "miss": rate(lambda r: r["miss"]),
        "slices": slices,
        "rows": rows,
    }


def sweep_floors(gold: list[dict], doc_vecs, vec, feat=None) -> list[dict]:
    feat = feat or features
    curve = []
    for floor in THRESHOLDS:
        scored = [
            score_one(
                tfidf_predict(item["query"], doc_vecs, vec, min_score=floor, feat=feat),
                item,
            )
            for item in gold
        ]
        block = summarize(scored)
        block.pop("rows")
        hit = block["slices"]["hit"]["exact"]
        neg_miss = block["slices"]["negative"]["miss"]
        curve.append(
            {
                "min_score": floor,
                "hit_exact": hit,
                "negative_miss": neg_miss,
                "false_neighbor": block["false_neighbor"],
                "exact": block["exact"],
                "matches_lock": hit == 1.0
                and neg_miss == 1.0
                and block["false_neighbor"] == 0,
            }
        )
    return curve


def any_floor_matches(gold: list[dict], doc_vecs, vec, feat=None) -> bool:
    return any(point["matches_lock"] for point in sweep_floors(gold, doc_vecs, vec, feat))


DENSE_THRESHOLDS = (
    0.0, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80
)


def sweep_dense_floors(gold: list[dict], query_vecs, doc_vecs) -> list[dict]:
    curve = []
    for floor in DENSE_THRESHOLDS:
        scored = [
            score_one(dense_predict(item["id"], query_vecs, doc_vecs, min_score=floor), item)
            for item in gold
        ]
        block = summarize(scored)
        block.pop("rows")
        hit = block["slices"]["hit"]["exact"]
        neg_miss = block["slices"]["negative"]["miss"]
        leftover = [r["id"] for r in scored if r["false_neighbor"]]
        missed_hits = [r["id"] for r in scored if r["slice"] == "hit" and not r["exact"]]
        curve.append(
            {
                "min_score": floor,
                "hit_exact": hit,
                "negative_miss": neg_miss,
                "false_neighbor": block["false_neighbor"],
                "exact": block["exact"],
                "leftover_false_neighbor": leftover,
                "missed_hits": missed_hits,
                "matches_lock": hit == 1.0
                and neg_miss == 1.0
                and block["false_neighbor"] == 0,
            }
        )
    return curve


def dense_hinge_report(gold: list[dict], query_vecs, doc_vecs) -> dict:
    rewrite = [item for item in gold if item.get("kind") == "rewrite"]
    negatives = [item for item in gold if item["slice"] == "negative"]
    scored_rewrite = []
    for item in rewrite:
        score, pred = dense_top(item["id"], query_vecs, doc_vecs)
        scored_rewrite.append(
            {
                "id": item["id"],
                "query": item["query"],
                "gold": item["gold"],
                "score": round(score, 4),
                "pred": pred,
            }
        )
    scored_neg = []
    for item in negatives:
        score, pred = dense_top(item["id"], query_vecs, doc_vecs)
        scored_neg.append(
            {
                "id": item["id"],
                "query": item["query"],
                "score": round(score, 4),
                "pred": pred,
            }
        )
    max_neg = max((row["score"] for row in scored_neg), default=0.0)
    inverted = [row for row in scored_rewrite if row["score"] < max_neg]
    drop_rewrite_still = []
    for item in rewrite:
        rest = [g for g in gold if g["id"] != item["id"]]
        curve = sweep_dense_floors(rest, query_vecs, doc_vecs)
        drop_rewrite_still.append(
            {
                "dropped": item["id"],
                "still_no_threshold": not any(point["matches_lock"] for point in curve),
            }
        )
    drop_neg_still = []
    for item in negatives:
        rest = [g for g in gold if g["id"] != item["id"]]
        curve = sweep_dense_floors(rest, query_vecs, doc_vecs)
        drop_neg_still.append(
            {
                "dropped": item["id"],
                "still_no_threshold": not any(point["matches_lock"] for point in curve),
            }
        )
    return {
        "n_rewrite": len(rewrite),
        "n_negative": len(negatives),
        "max_negative": max_neg,
        "min_rewrite": min((row["score"] for row in scored_rewrite), default=None),
        "inverted_rewrite": inverted,
        "n_inverted_rewrite": len(inverted),
        "rewrite_scores": scored_rewrite,
        "negative_scores": scored_neg,
        "drop_any_one_rewrite_still_no_threshold": all(
            row["still_no_threshold"] for row in drop_rewrite_still
        ),
        "drop_any_one_negative_still_no_threshold": all(
            row["still_no_threshold"] for row in drop_neg_still
        ),
        "drop_rewrite": drop_rewrite_still,
        "drop_negative": drop_neg_still,
    }


def hinge_report(gold: list[dict], doc_vecs, vec, feat=None) -> dict:
    """Is 'no floor' one inverted pair, or still true after dropping any one item?"""
    feat = feat or features
    rewrite = [item for item in gold if item.get("kind") == "rewrite"]
    negatives = [item for item in gold if item["slice"] == "negative"]
    scored_rewrite = []
    for item in rewrite:
        score, pred = tfidf_top(item["query"], doc_vecs, vec, feat=feat)
        scored_rewrite.append(
            {"id": item["id"], "query": item["query"], "gold": item["gold"], "score": round(score, 4), "pred": pred}
        )
    scored_neg = []
    for item in negatives:
        score, pred = tfidf_top(item["query"], doc_vecs, vec, feat=feat)
        scored_neg.append(
            {"id": item["id"], "query": item["query"], "score": round(score, 4), "pred": pred}
        )
    max_neg = max((row["score"] for row in scored_neg), default=0.0)
    inverted = [row for row in scored_rewrite if row["score"] < max_neg]
    drop_rewrite_still = []
    for item in rewrite:
        rest = [g for g in gold if g["id"] != item["id"]]
        drop_rewrite_still.append(
            {
                "dropped": item["id"],
                "still_no_threshold": not any_floor_matches(rest, doc_vecs, vec, feat),
            }
        )
    drop_neg_still = []
    for item in negatives:
        rest = [g for g in gold if g["id"] != item["id"]]
        drop_neg_still.append(
            {
                "dropped": item["id"],
                "still_no_threshold": not any_floor_matches(rest, doc_vecs, vec, feat),
            }
        )
    return {
        "n_rewrite": len(rewrite),
        "n_negative": len(negatives),
        "max_negative": max_neg,
        "min_rewrite": min((row["score"] for row in scored_rewrite), default=None),
        "inverted_rewrite": inverted,
        "n_inverted_rewrite": len(inverted),
        "rewrite_scores": scored_rewrite,
        "negative_scores": scored_neg,
        "drop_any_one_rewrite_still_no_threshold": all(
            row["still_no_threshold"] for row in drop_rewrite_still
        ),
        "drop_any_one_negative_still_no_threshold": all(
            row["still_no_threshold"] for row in drop_neg_still
        ),
        "drop_rewrite": drop_rewrite_still,
        "drop_negative": drop_neg_still,
    }


def timed(bucket: list[float], fn):
    t0 = time.perf_counter()
    value = fn()
    bucket.append((time.perf_counter() - t0) * 1000)
    return value


def run(
    vault: Path = DEFAULT_VAULT,
    map_path: Path = DEFAULT_MAP,
    gold_path: Path = DEFAULT_GOLD,
) -> dict:
    gold = load_gold(gold_path)
    files = md_files(vault)
    live_files = live_md_files(vault, TODAY)
    rows = load_rows(map_path)
    doc_vecs, vec = build_tfidf(files, vault)
    live_vecs, live_vec = build_tfidf(live_files, vault)
    named_map = map_texts(vault, rows, TODAY)
    map_vecs, map_vec = build_tfidf_texts(named_map)
    word_vecs, word_vec = build_tfidf_texts(named_map, feat=feat_fn("word"))
    stopped_vecs, stopped_vec = build_tfidf_texts(named_map, feat=feat_fn("word_stopped"))
    dense = load_dense(
        DEFAULT_DENSE, gold, files, live_files, named_map, vault, DENSE_MODEL
    )
    q_dense = dense["queries"]
    dense_all = dense["docs_all"]
    dense_live = dense["docs_live"]
    dense_map = dense["docs_map"]
    dense_mid = load_dense(
        DEFAULT_DENSE_MID, gold, files, live_files, named_map, vault, DENSE_MID_MODEL
    )
    q_mid = dense_mid["queries"]
    mid_all = dense_mid["docs_all"]
    mid_live = dense_mid["docs_live"]
    mid_map = dense_mid["docs_map"]

    systems = {
        "krouter": [],
        "lexical": [],
        "tfidf": [],
        "hybrid": [],
        "lexical_live": [],
        "tfidf_live": [],
        "tfidf_map": [],
        "hybrid_live": [],
        "dense": [],
        "dense_live": [],
        "dense_map": [],
        "dense_m3": [],
        "dense_m3_live": [],
        "dense_m3_map": [],
    }
    latencies_ms: dict[str, list[float]] = {name: [] for name in systems}

    for item in gold:
        q = item["query"]
        systems["krouter"].append(
            score_one(timed(latencies_ms["krouter"], lambda: krouter_predict(q, rows, vault)), item)
        )
        systems["lexical"].append(
            score_one(timed(latencies_ms["lexical"], lambda: lexical_predict(q, files, vault)), item)
        )
        systems["tfidf"].append(
            score_one(timed(latencies_ms["tfidf"], lambda: tfidf_predict(q, doc_vecs, vec)), item)
        )
        systems["hybrid"].append(
            score_one(
                timed(
                    latencies_ms["hybrid"],
                    lambda: rrf([lexical_ranks(q, files, vault), tfidf_ranks(q, doc_vecs, vec)]),
                ),
                item,
            )
        )
        systems["lexical_live"].append(
            score_one(
                timed(latencies_ms["lexical_live"], lambda: lexical_predict(q, live_files, vault)),
                item,
            )
        )
        systems["tfidf_live"].append(
            score_one(
                timed(latencies_ms["tfidf_live"], lambda: tfidf_predict(q, live_vecs, live_vec)),
                item,
            )
        )
        systems["tfidf_map"].append(
            score_one(
                timed(latencies_ms["tfidf_map"], lambda: tfidf_predict(q, map_vecs, map_vec)),
                item,
            )
        )
        systems["hybrid_live"].append(
            score_one(
                timed(
                    latencies_ms["hybrid_live"],
                    lambda: rrf(
                        [
                            lexical_ranks(q, live_files, vault),
                            tfidf_ranks(q, live_vecs, live_vec),
                        ]
                    ),
                ),
                item,
            )
        )
        qid = item["id"]
        systems["dense"].append(
            score_one(
                timed(latencies_ms["dense"], lambda: dense_predict(qid, q_dense, dense_all)),
                item,
            )
        )
        systems["dense_live"].append(
            score_one(
                timed(
                    latencies_ms["dense_live"],
                    lambda: dense_predict(qid, q_dense, dense_live),
                ),
                item,
            )
        )
        systems["dense_map"].append(
            score_one(
                timed(
                    latencies_ms["dense_map"],
                    lambda: dense_predict(qid, q_dense, dense_map),
                ),
                item,
            )
        )
        systems["dense_m3"].append(
            score_one(
                timed(latencies_ms["dense_m3"], lambda: dense_predict(qid, q_mid, mid_all)),
                item,
            )
        )
        systems["dense_m3_live"].append(
            score_one(
                timed(
                    latencies_ms["dense_m3_live"],
                    lambda: dense_predict(qid, q_mid, mid_live),
                ),
                item,
            )
        )
        systems["dense_m3_map"].append(
            score_one(
                timed(
                    latencies_ms["dense_m3_map"],
                    lambda: dense_predict(qid, q_mid, mid_map),
                ),
                item,
            )
        )

    out = {
        "today": TODAY.isoformat(),
        "vault": str(vault),
        "map": str(map_path),
        "gold": str(gold_path),
        "systems": {},
    }
    for name, scored in systems.items():
        summary = summarize(scored)
        times = sorted(latencies_ms[name])
        summary["latency_p50_ms"] = round(times[len(times) // 2], 3)
        summary.pop("rows")
        summary["cases"] = scored
        out["systems"][name] = summary
    curve = sweep_floors(gold, map_vecs, map_vec)
    out["threshold_curve"] = curve
    out["threshold_any_matches_lock"] = any(point["matches_lock"] for point in curve)
    out["hinge"] = hinge_report(gold, map_vecs, map_vec)
    word_curve = sweep_floors(gold, word_vecs, word_vec, feat=feat_fn("word"))
    stopped_curve = sweep_floors(gold, stopped_vecs, stopped_vec, feat=feat_fn("word_stopped"))
    out["word_only"] = {
        "threshold_any_matches_lock": any(point["matches_lock"] for point in word_curve),
        "hinge": hinge_report(gold, word_vecs, word_vec, feat=feat_fn("word")),
    }
    out["word_stopped"] = {
        "threshold_any_matches_lock": any(point["matches_lock"] for point in stopped_curve),
        "hinge": hinge_report(gold, stopped_vecs, stopped_vec, feat=feat_fn("word_stopped")),
    }
    dense_curve = sweep_dense_floors(gold, q_dense, dense_map)
    out["dense_model"] = dense["model"]
    out["dense_threshold_curve"] = dense_curve
    out["dense_threshold_any_matches_lock"] = any(point["matches_lock"] for point in dense_curve)
    out["dense_hinge"] = dense_hinge_report(gold, q_dense, dense_map)
    mid_curve = sweep_dense_floors(gold, q_mid, mid_map)
    out["dense_m3_model"] = dense_mid["model"]
    out["dense_m3_threshold_curve"] = mid_curve
    out["dense_m3_threshold_any_matches_lock"] = any(
        point["matches_lock"] for point in mid_curve
    )
    out["dense_m3_hinge"] = dense_hinge_report(gold, q_mid, mid_map)
    return out


def print_table(result: dict) -> None:
    n = result["systems"]["krouter"]["n"]
    slices = result["systems"]["krouter"]["slices"]
    counts = " ".join(f"{name}={block['n']}" for name, block in slices.items())
    print(f"today={result['today']}  N={n} ({counts})")
    print(
        f"{'system':<16} {'exact':>8} {'falseN':>8} {'oldPg':>8} {'miss':>8} {'p50ms':>8}"
    )
    for name, block in result["systems"].items():
        print(
            f"{name:<16} {block['exact']:>8.2%} {block['false_neighbor']:>8.2%} "
            f"{block['old_page']:>8.2%} {block['miss']:>8.2%} {block['latency_p50_ms']:>8.3f}"
        )
    print()
    print("by slice (exact / false_neighbor / old_page)")
    for slice_name in ("hit", "supersede", "neighbor", "negative"):
        parts = []
        for name, block in result["systems"].items():
            sl = block["slices"][slice_name]
            parts.append(
                f"{name} {sl['exact']:.0%}/{sl['false_neighbor']:.0%}/{sl['old_page']:.0%}"
            )
        print(f"  {slice_name:<10} " + "  ".join(parts))
    print()
    print("tfidf_map cosine threshold sweep (same live map; miss if top-1 < min_score)")
    print(f"{'min_score':>9} {'hit':>8} {'negMiss':>8} {'falseN':>8} {'matches_lock':>14}")
    for point in result["threshold_curve"]:
        print(
            f"{point['min_score']:>9.2f} {point['hit_exact']:>8.0%} "
            f"{point['negative_miss']:>8.0%} {point['false_neighbor']:>8.0%} "
            f"{str(point['matches_lock']):>14}"
        )
    print(
        "any lexical TF-IDF threshold matches lock (all hits exact, all negatives miss, false_neighbor 0):",
        result["threshold_any_matches_lock"],
    )
    hinge = result["hinge"]
    print()
    print(
        f"hinge rewrite={hinge['n_rewrite']} negatives={hinge['n_negative']} "
        f"inverted={hinge['n_inverted_rewrite']} "
        f"min_rewrite={hinge['min_rewrite']} max_neg={hinge['max_negative']}"
    )
    for row in hinge["inverted_rewrite"]:
        print(f"  inverted {row['id']} {row['query']!r} {row['score']} -> {row['pred']}")
    print(
        "drop any one rewrite still no threshold:",
        hinge["drop_any_one_rewrite_still_no_threshold"],
    )
    print(
        "drop any one negative still no threshold:",
        hinge["drop_any_one_negative_still_no_threshold"],
    )
    print(
        "word-only matches lock:",
        result["word_only"]["threshold_any_matches_lock"],
        "inverted",
        result["word_only"]["hinge"]["n_inverted_rewrite"],
    )
    print(
        "word-stopped matches lock:",
        result["word_stopped"]["threshold_any_matches_lock"],
        "inverted",
        result["word_stopped"]["hinge"]["n_inverted_rewrite"],
    )
    print()
    print(f"dense_map MiniLM threshold sweep ({result['dense_model']}; miss if top-1 < min_score)")
    print(f"{'min_score':>9} {'hit':>8} {'negMiss':>8} {'falseN':>8} {'matches_lock':>14}")
    for point in result["dense_threshold_curve"]:
        print(
            f"{point['min_score']:>9.2f} {point['hit_exact']:>8.0%} "
            f"{point['negative_miss']:>8.0%} {point['false_neighbor']:>8.0%} "
            f"{str(point['matches_lock']):>14}"
        )
    print(
        "any dense MiniLM threshold matches lock (all hits exact, all negatives miss, false_neighbor 0):",
        result["dense_threshold_any_matches_lock"],
    )
    h15 = next(c for c in result["systems"]["dense_map"]["cases"] if c["id"] == "H15")
    print(
        f"MiniLM precision (before any floor): H15 {h15['query']!r} "
        f"pred={h15['pred']} gold={h15['gold']}"
    )
    dh = result["dense_hinge"]
    print()
    print(
        f"dense hinge rewrite={dh['n_rewrite']} negatives={dh['n_negative']} "
        f"inverted={dh['n_inverted_rewrite']} "
        f"min_rewrite={dh['min_rewrite']} max_neg={dh['max_negative']}"
    )
    for row in dh["inverted_rewrite"]:
        print(f"  inverted {row['id']} {row['query']!r} {row['score']} -> {row['pred']}")
    print(
        "dense drop any one rewrite still no threshold:",
        dh["drop_any_one_rewrite_still_no_threshold"],
    )
    print(
        "dense drop any one negative still no threshold:",
        dh["drop_any_one_negative_still_no_threshold"],
    )
    print()
    print(
        f"dense_m3_map BGE-M3 threshold sweep ({result['dense_m3_model']}; miss if top-1 < min_score)"
    )
    print(f"{'min_score':>9} {'hit':>8} {'negMiss':>8} {'falseN':>8} {'matches_lock':>14}")
    for point in result["dense_m3_threshold_curve"]:
        print(
            f"{point['min_score']:>9.2f} {point['hit_exact']:>8.0%} "
            f"{point['negative_miss']:>8.0%} {point['false_neighbor']:>8.0%} "
            f"{str(point['matches_lock']):>14}"
        )
    print(
        "any dense BGE-M3 threshold matches lock (all hits exact, all negatives miss, false_neighbor 0):",
        result["dense_m3_threshold_any_matches_lock"],
    )
    for want in (0.40, 0.45):
        point = next(p for p in result["dense_m3_threshold_curve"] if p["min_score"] == want)
        print(
            f"BGE-M3 at {want:.2f}: leftover_false_neighbor={point['leftover_false_neighbor']} "
            f"missed_hits={point['missed_hits']}"
        )
    print("B03 is neighbor slice (gold null), not one of the 12 OOD negatives")
    mh = result["dense_m3_hinge"]
    print()
    print(
        f"dense_m3 hinge rewrite={mh['n_rewrite']} negatives={mh['n_negative']} "
        f"inverted={mh['n_inverted_rewrite']} "
        f"min_rewrite={mh['min_rewrite']} max_neg={mh['max_negative']}"
    )
    for row in mh["inverted_rewrite"]:
        print(f"  inverted {row['id']} {row['query']!r} {row['score']} -> {row['pred']}")
    print(
        "dense_m3 drop any one rewrite still no threshold:",
        mh["drop_any_one_rewrite_still_no_threshold"],
    )
    print(
        "dense_m3 drop any one negative still no threshold:",
        mh["drop_any_one_negative_still_no_threshold"],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_table(result)
        first = run()
        second = run()
        same = first["systems"]["krouter"]["cases"] == second["systems"]["krouter"]["cases"]
        print()
        print("krouter determinism (two runs, same preds):", same)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
