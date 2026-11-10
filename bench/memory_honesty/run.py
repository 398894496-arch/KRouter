#!/usr/bin/env python3
"""Memory honesty bench: does an agent memory cite the right page, follow corrections, and refuse what it does not hold?

30 questions on a 30-page vault (`vault/`, plain Markdown):
- 10 `correction`: the vault has an old page and a newer page that replaces it; the answer must cite the new one.
- 10 `current`: one page answers it.
- 10 `refuse`: nothing in the vault answers it, but each borrows words from a page that answers a neighbouring
  question (the *search* API timeout, when the vault has the *payments* API timeout). Citing that page is a wrong
  citation, not a near miss.

A system under test is an adapter: a command that reads one question per line on stdin (JSON `{"id", "q"}`) and
writes one JSON line per question: `{"id", "cited": ["Engineering/…md", …], "refused": bool}` — `cited` in rank order,
vault-relative paths. `--adapter krouter` (default) runs KRouter's recall in-process. Score with `--answers FILE` to
grade another system's output.

Metrics
- wrong-citation rate: of the questions a system answered, how many cited something other than the gold page first
  (every answered `refuse` question counts as wrong).
- refusal rate: of the 10 `refuse` questions, how many it refused.
- correction hit rate: of the 10 `correction` questions, how many cited the new page first, not the replaced one.
- current hit rate: of the 10 `current` questions, how many cited the gold page first.

    python3 bench/memory_honesty/run.py                 # KRouter
    python3 bench/memory_honesty/run.py --adapter bm25  # baseline: plain full-text search, always answers
    python3 bench/memory_honesty/run.py --adapter bm25-floor  # + superseded pages skipped + a floor picked on dev
    python3 bench/memory_honesty/run.py --answers other.jsonl

Held-out set (`heldout.jsonl`, rules in `HELDOUT.md`): 25 questions on the same vault, never used for tuning.
`--set heldout` prints aggregate metrics only; which questions were missed stays hidden unless `--reveal`, and a
reveal followed by a ranking or refusal change burns the set (see `HELDOUT.md`).

    python3 bench/memory_honesty/run.py --set heldout
    python3 bench/memory_honesty/run.py --set heldout --adapter bm25

Third vault, held-out only (`vault3/`, 110 pages: 30 English and 30 Chinese rule pages, their 30 replaced pages,
and 20 daily logs as distractors): `--set heldout3`, 200 questions (60 corrections, 60 current, 80 neighbours, half
Chinese). Nobody tunes on vault3; `bm25-floor` there uses the floor picked on dev3, as a new user's vault would.

Confidence and curves (any set; on held-out sets they are aggregates, so allowed):

    python3 bench/memory_honesty/run.py --set heldout3 --ci                 # 95% bootstrap intervals
    python3 bench/memory_honesty/run.py --set heldout3 --vs bm25-floor      # paired intervals for the differences
    python3 bench/memory_honesty/run.py --set heldout3 --curve --adapter bm25-floor

Second bench, written by the reviewer (`vault2/`, 60 pages, 30 English and 30 Chinese): `--set dev3` (50 questions,
tune on these) and `--set heldout2` (50 questions, never tune on these; stored gzipped so it does not show up in a
grep or a diff; same rules, HELDOUT.md). The BM25 baselines on vault2 split Chinese into character pairs, so a
Chinese question is searched, not refused for having no Latin words.

    python3 bench/memory_honesty/run.py --set dev3
    python3 bench/memory_honesty/run.py --set heldout2 --adapter bm25-floor
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


SETS = {"dev": "questions.jsonl", "dev2": "questions_dev2.jsonl", "heldout": "heldout.jsonl",
        "dev3": "questions_dev3.jsonl", "heldout2": "heldout2.jsonl.gz", "heldout3": "heldout3.jsonl.gz"}
# Sets on the second, bilingual vault (vault2/, 60 pages). Everything else runs on vault/.
VAULT2_SETS = {"dev3", "heldout2"}
# The third vault (vault3/, 110 pages with daily logs) has a held-out set only: nobody tunes on this vault, so it
# measures what a new user's vault gets. Floors and any learned settings come from other vaults.
VAULT3_SETS = {"heldout3"}
CJK_SETS = VAULT2_SETS | VAULT3_SETS
HELDOUT_SETS = {"heldout", "heldout2", "heldout3"}


def vault_of(name: str) -> Path:
    return HERE / ("vault3" if name in VAULT3_SETS else "vault2" if name in VAULT2_SETS else "vault")


def floor_dev_of(name: str) -> str:
    """The dev set a floor is picked on: the one on the same vault; for vault3, which has none, dev3 (vault2)."""
    return "dev3" if name in CJK_SETS else "dev"


def questions(name: str = "dev") -> list[dict]:
    path = HERE / SETS[name]
    if path.suffix == ".gz":  # heldout2 is stored compressed so it does not show up in grep or a diff by accident
        import gzip

        text = gzip.decompress(path.read_bytes()).decode("utf-8")
    else:
        text = path.read_text(encoding="utf-8")
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def aggregate(result: dict) -> dict:
    """The score without per-question detail: what may be looked at on the held-out set."""
    return {k: v for k, v in result.items() if k != "misses"}


def krouter_answers(rows: list[dict], vault_src: Path | None = None) -> list[dict]:
    sys.path.insert(0, str(REPO / "skill/krouter-obsidian/scripts"))
    saved = {k: os.environ.get(k) for k in ("KROUTER_NO_QUERY_LOG", "KROUTER_CACHE_DIR", "KROUTER_MAP")}
    # Windows 上召回缓存的 SQLite 连接在进程里一直开着，临时目录删不掉也不算失败
    with tempfile.TemporaryDirectory(prefix="krouter-bench-", ignore_cleanup_errors=True) as tmp:
        os.environ["KROUTER_NO_QUERY_LOG"] = "1"
        os.environ["KROUTER_CACHE_DIR"] = str(Path(tmp) / "cache")
        os.environ.pop("KROUTER_MAP", None)
        vault = Path(tmp) / "vault"
        shutil.copytree(vault_src or HERE / "vault", vault)
        import recall_index as ri

        out = []
        for it in rows:
            # 和 agent 拿到的一样：联想通路按产品默认（`KROUTER_ASSOC`），冲突兜底按产品默认（`KROUTER_CONFLICT`）
            res = ri.recall(vault, it["q"], limit=3, assoc=ri.associate.enabled())
            refused = res["confidence"] == "none" or not res["hits"]
            out.append({"id": it["id"], "refused": refused, "cited": [] if refused else ri.page_list(res, 3),
                        "score": None if refused else float(res["hits"][0]["score"])})
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    return out


def _cjk_tokens(text: str) -> list[str]:
    """Latin words of 3+ letters, and CJK runs split into overlapping character pairs (a single character alone)."""
    import re

    out = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2]
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        out += [run] if len(run) == 1 else [run[i:i + 2] for i in range(len(run) - 1)]
    return out


def bm25_answers(rows: list[dict], vault_src: Path | None = None, cjk: bool = False) -> list[dict]:
    if cjk:
        return [{"id": qid, "refused": not hits, "cited": [h[0] for h in hits], "score": hits[0][1] if hits else None}
                for qid, hits in bm25_scored(rows, skip_superseded=False, vault_src=vault_src, cjk=True)]
    return _bm25_answers_v1(rows)


def _bm25_answers_v1(rows: list[dict]) -> list[dict]:
    """Baseline: plain full-text search (SQLite FTS5, BM25) over the same pages, always answering with its top hit —
    what a memory that "returns the nearest chunk" does. No refusal, no notion of superseded."""
    import re
    import sqlite3

    con = sqlite3.connect(":memory:")
    con.execute("CREATE VIRTUAL TABLE d USING fts5(rel UNINDEXED, body)")
    for path in sorted((HERE / "vault").rglob("*.md")):
        con.execute("INSERT INTO d VALUES (?, ?)", (path.relative_to(HERE / "vault").as_posix(), path.read_text(encoding="utf-8")))
    out = []
    for it in rows:
        words = [w for w in re.findall(r"[a-z0-9]+", it["q"].lower()) if len(w) > 2]
        hits = con.execute("SELECT rel FROM d WHERE d MATCH ? ORDER BY bm25(d) LIMIT 3",
                           (" OR ".join(f'"{w}"' for w in words),)).fetchall() if words else []
        out.append({"id": it["id"], "refused": not hits, "cited": [h[0] for h in hits]})
    return out


def _bm25_index(skip_superseded: bool, vault_src: Path | None = None, cjk: bool = False):
    import re
    import sqlite3

    root = vault_src or HERE / "vault"
    con = sqlite3.connect(":memory:")
    con.execute("CREATE VIRTUAL TABLE d USING fts5(rel UNINDEXED, body)")
    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        if skip_superseded and re.search(r"(?m)^status:\s*superseded\s*$", text.split("\n---", 1)[0]):
            continue
        con.execute("INSERT INTO d VALUES (?, ?)", (path.relative_to(root).as_posix(), " ".join(_cjk_tokens(text)) if cjk else text))
    return con


def bm25_scored(rows: list[dict], skip_superseded: bool = True, vault_src: Path | None = None,
                cjk: bool = False) -> list[tuple[str, list[tuple[str, float]]]]:
    """[(id, [(page, score)])] — BM25 over the pages, superseded pages left out, score = -bm25 (higher is better)."""
    import re

    con = _bm25_index(skip_superseded, vault_src, cjk)
    out = []
    for it in rows:
        words = _cjk_tokens(it["q"]) if cjk else [w for w in re.findall(r"[a-z0-9]+", it["q"].lower()) if len(w) > 2]
        hits = con.execute("SELECT rel, -bm25(d) FROM d WHERE d MATCH ? ORDER BY bm25(d) LIMIT 3",
                           (" OR ".join(f'"{w}"' for w in words),)).fetchall() if words else []
        out.append((it["id"], [(r, float(sc)) for r, sc in hits]))
    return out


def floor_answers(scored: list[tuple[str, list[tuple[str, float]]]], floor: float) -> list[dict]:
    out = []
    for qid, hits in scored:
        ok = bool(hits) and hits[0][1] >= floor
        out.append({"id": qid, "refused": not ok, "cited": [h[0] for h in hits] if ok else [],
                    "score": hits[0][1] if hits else None})
    return out


def pick_floor(rows: list[dict], scored) -> float:
    """The floor a careful baseline would pick on the dev set: most right answers minus wrong citations; on a tie, the
    lower floor (answer more). Picked on dev only, then applied unchanged to held-out."""
    cands = sorted({0.0} | {h[0][1] for _, h in scored if h})
    best, best_floor = None, 0.0
    for f in cands:
        res = score(rows, floor_answers(scored, f))
        right = int(res["correction_hit"].split("/")[0]) + int(res["current_hit"].split("/")[0])
        util = right - res["wrong_citations"]
        if best is None or util > best:
            best, best_floor = util, f
    return best_floor


def bm25_floor_answers(rows: list[dict], qset: str = "dev") -> list[dict]:
    """Baseline with the two things anyone would add to full-text search: superseded pages left out, and a score floor
    below which it refuses. The floor is picked on the dev set (`pick_floor`) and applied as is to any set."""
    if qset in CJK_SETS:
        dev_name = floor_dev_of(qset)
        dev = questions(dev_name)
        floor = pick_floor(dev, bm25_scored(dev, vault_src=vault_of(dev_name), cjk=True))
        return floor_answers(bm25_scored(rows, vault_src=vault_of(qset), cjk=True), floor)
    dev = questions("dev")
    floor = pick_floor(dev, bm25_scored(dev))
    return floor_answers(bm25_scored(rows), floor)


def score(rows: list[dict], answers: list[dict]) -> dict:
    by_id = {a["id"]: a for a in answers}
    answered = wrong = refused_ok = corr_ok = cur_ok = 0
    detail = []
    for it in rows:
        a = by_id.get(it["id"], {"refused": True, "cited": []})
        top = None if a.get("refused") else (a.get("cited") or [None])[0]
        if top is not None:
            answered += 1
            wrong += top != it["gold"]
        if it["kind"] == "refuse":
            refused_ok += top is None
        elif it["kind"] == "correction":
            corr_ok += top == it["gold"]
        else:
            cur_ok += top == it["gold"]
        ok = top == it["gold"] if it["gold"] else top is None
        detail.append({"id": it["id"], "ok": ok, "top": top})
    n = {k: sum(1 for r in rows if r["kind"] == k) for k in ("refuse", "correction", "current")}
    return {"questions": len(rows), "answered": answered, "wrong_citations": wrong,
            "wrong_citation_rate": round(wrong / answered, 3) if answered else 0.0,
            "refused": f"{refused_ok}/{n['refuse']}", "correction_hit": f"{corr_ok}/{n['correction']}",
            "current_hit": f"{cur_ok}/{n['current']}", "misses": [d for d in detail if not d["ok"]]}


def candidates(adapter: str, rows: list[dict], qset: str) -> list[dict]:
    """Each question's best page and its score, before any refusal threshold: what a coverage curve sweeps.
    krouter: only questions KRouter answers (its own refusals stay refusals). bm25: plain BM25. bm25-floor: BM25 with
    superseded pages left out, i.e. the floor baseline at every possible floor."""
    src, cjk = vault_of(qset), qset in CJK_SETS
    if adapter == "krouter":
        return [a for a in krouter_answers(rows, src) if not a["refused"]]
    if adapter == "bm25" and not cjk:
        return [a for a in _bm25_answers_v1(rows) if not a["refused"]]  # v1 baseline has no scores: one point
    scored = bm25_scored(rows, skip_superseded=adapter == "bm25-floor", vault_src=src, cjk=cjk)
    return [{"id": qid, "refused": False, "cited": [h[0] for h in hits], "score": hits[0][1]} for qid, hits in scored if hits]


def curve(rows: list[dict], cands: list[dict], points: int = 12) -> list[dict]:
    """Coverage curve: for thresholds from strict to loose, how many questions get answered, how many of those cite a
    wrong page, how many answerable ones are right, how many neighbours are refused. Aggregates only."""
    scored = sorted((c for c in cands if c.get("score") is not None), key=lambda c: -c["score"])
    unscored = [c for c in cands if c.get("score") is None]
    if not scored:
        res = score(rows, unscored)
        return [{"threshold": None, **{k: res[k] for k in ("answered", "wrong_citations", "refused")},
                 "right": _right(res)}]
    cuts = sorted({max(1, round(i * len(scored) / points)) for i in range(1, points + 1)})
    out = []
    for n in cuts:
        res = score(rows, scored[:n])
        out.append({"threshold": round(scored[n - 1]["score"], 4), "answered": res["answered"],
                    "wrong_citations": res["wrong_citations"], "wrong_citation_rate": res["wrong_citation_rate"],
                    "right": _right(res), "refused": res["refused"]})
    return out


def _right(res: dict) -> int:
    return int(res["correction_hit"].split("/")[0]) + int(res["current_hit"].split("/")[0])


def bootstrap(rows: list[dict], answers: list[dict], other: list[dict] | None = None, n: int = 2000,
              seed: int = 20261013) -> dict:
    """95% intervals by resampling questions with replacement (same resamples for both systems when `other` is
    given, so the difference is paired). Fixed seed: the same input gives the same interval."""
    import random

    rng = random.Random(seed)
    by_a = {a["id"]: a for a in answers}
    by_b = {a["id"]: a for a in other} if other is not None else None
    stats: dict[str, list[float]] = {}

    def add(key: str, v: float) -> None:
        stats.setdefault(key, []).append(v)

    for _ in range(n):
        sample = [rows[rng.randrange(len(rows))] for _ in rows]
        ids = [f"{i}:{r['id']}" for i, r in enumerate(sample)]  # duplicates stay distinct
        rs = [{**r, "id": k} for r, k in zip(sample, ids)]
        ra = score(rs, [{**by_a.get(r["id"], {"refused": True, "cited": []}), "id": k} for r, k in zip(sample, ids)])
        add("wrong_citation_rate", ra["wrong_citation_rate"])
        add("right", _right(ra))
        add("refused", int(ra["refused"].split("/")[0]))
        if by_b is not None:
            rb = score(rs, [{**by_b.get(r["id"], {"refused": True, "cited": []}), "id": k} for r, k in zip(sample, ids)])
            add("delta_wrong_citation_rate", ra["wrong_citation_rate"] - rb["wrong_citation_rate"])
            add("delta_right", _right(ra) - _right(rb))
            add("delta_refused", int(ra["refused"].split("/")[0]) - int(rb["refused"].split("/")[0]))
    out = {}
    for key, vals in stats.items():
        vals.sort()
        lo, hi = vals[int(0.025 * (n - 1))], vals[int(0.975 * (n - 1))]
        out[key] = [round(lo, 3), round(hi, 3)]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--answers", help="grade this JSONL instead of running KRouter")
    ap.add_argument("--adapter", choices=["krouter", "bm25", "bm25-floor"], default="krouter")
    ap.add_argument("--set", choices=sorted(SETS), default="dev", dest="qset",
                    help="dev: the 30 bench questions (tune on these); heldout: never tune on these (HELDOUT.md)")
    ap.add_argument("--reveal", action="store_true",
                    help="held-out only: also print which questions were missed. Changing ranking or refusal after "
                         "this burns the set; record it in HELDOUT.md")
    ap.add_argument("--ci", action="store_true", help="add 95%% bootstrap intervals (questions resampled)")
    ap.add_argument("--vs", choices=["krouter", "bm25", "bm25-floor"],
                    help="also run this adapter and give paired 95%% intervals for the differences")
    ap.add_argument("--vs-matched", choices=["bm25", "bm25-floor"], dest="vs_matched",
                    help="compare at the same coverage: the other system answers exactly as many questions as this "
                         "one (its top-scored ones), with paired 95%% intervals for the differences")
    ap.add_argument("--curve", action="store_true",
                    help="print the coverage curve (answered vs wrong citations at each threshold) instead")
    args = ap.parse_args()
    rows = questions(args.qset)

    def run(adapter: str) -> list[dict]:
        src, cjk = vault_of(args.qset), args.qset in CJK_SETS
        return {"krouter": lambda r: krouter_answers(r, src),
                "bm25": lambda r: bm25_answers(r, src, cjk),
                "bm25-floor": lambda r: bm25_floor_answers(r, args.qset)}[adapter](rows)

    if args.curve:
        print(json.dumps({"set": args.qset, "adapter": args.adapter,
                          "curve": curve(rows, candidates(args.adapter, rows, args.qset))}, ensure_ascii=False, indent=1))
        return 0
    if args.answers:
        answers = [json.loads(x) for x in Path(args.answers).read_text(encoding="utf-8").splitlines() if x.strip()]
    else:
        answers = run(args.adapter)
    result = score(rows, answers)
    if args.vs_matched:
        n = sum(1 for a in answers if not a.get("refused") and a.get("cited"))
        pool = sorted(candidates(args.vs_matched, rows, args.qset), key=lambda c: -c["score"])[:n]
        matched = pool + [{"id": r["id"], "refused": True, "cited": []} for r in rows
                          if r["id"] not in {c["id"] for c in pool}]
        result["vs_matched"] = {"adapter": args.vs_matched, "answers": n, **aggregate(score(rows, matched)),
                                "ci95": {k: v for k, v in bootstrap(rows, answers, matched).items() if k.startswith("delta")}}
    if args.ci or args.vs:
        other = run(args.vs) if args.vs else None
        result["ci95"] = bootstrap(rows, answers, other)
        if args.vs:
            result["vs"] = {"adapter": args.vs, **aggregate(score(rows, other))}
    if args.qset in HELDOUT_SETS and not args.reveal:
        result = aggregate(result)
    elif args.qset in HELDOUT_SETS:
        print("held-out per-question results revealed: if ranking or refusal changes after this, the set is burned "
              "(bench/memory_honesty/HELDOUT.md)", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
