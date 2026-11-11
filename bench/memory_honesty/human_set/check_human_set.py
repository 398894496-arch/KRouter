#!/usr/bin/env python3
"""Check a person-written question set for vault3 and pack it (README.md in this folder says how to write one).

Checks format and facts only, the same soundness rules as set 3: each answerable question's `evidence` sentence is on
its answer page, the page is live, a `correction` page has a replaced `(old)` / `（旧）` page next to it, each neighbour
question's `absent` term is in both wordings and on no page of vault3 (logs included, English plurals counted), and no
question repeats one from another set. Never runs KRouter or any other system and prints no answers.

    python3 bench/memory_honesty/human_set/check_human_set.py my_questions.csv [--out human_pairs.jsonl.gz]

Output rows, one per wording: {id, intent, week, q, kind, gold, lang}; `kind` uses the bench's names
(`correction`, `current`, `refuse`), `gold` is null for neighbours.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
VAULT3 = BENCH / "vault3"
spec = importlib.util.spec_from_file_location("mh_bench_human", BENCH / "run.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

KINDS = {"correction": "correction", "改过": "correction", "current": "current", "现行": "current",
         "neighbour": "refuse", "neighbor": "refuse", "库里没有": "refuse"}
WANT = {"correction": 15, "current": 15, "refuse": 20}
LOGS = ("Daily log/", "工作日志/")


def has(term: str, text: str) -> bool:
    if re.search(r"[一-鿿]", term):
        return term in text
    return re.search(r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?:s|es)?(?![a-z0-9])", text.lower()) is not None


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def old_page(rel: str) -> str:
    p = Path(rel)
    for name in (f"{p.stem}（旧）.md", f"{p.stem} (old).md"):
        cand = (p.parent / name).as_posix()
        if (VAULT3 / cand).is_file():
            return cand
    return ""


def check(rows: list[dict], pages: dict[str, str], known: set[str]) -> list[str]:
    problems: list[str] = []
    seen_q: set[str] = set()
    counts: Counter = Counter()
    for i, r in enumerate(rows, 2):  # 第 1 行是表头
        where = f"line {i} ({r.get('intent') or '?'})"
        kind = KINDS.get((r.get("kind") or "").strip().lower(), KINDS.get((r.get("kind") or "").strip()))
        if not kind:
            problems.append(f"{where}: kind must be correction / current / neighbour")
            continue
        counts[kind] += 1
        w1, w2 = squash(r.get("week1", "")), squash(r.get("week2", ""))
        if not w1 or not w2:
            problems.append(f"{where}: both week1 and week2 are needed")
        if w1 and w1 == w2:
            problems.append(f"{where}: week1 and week2 are the same sentence")
        for q in (w1, w2):
            if q in seen_q:
                problems.append(f"{where}: a wording repeats another row")
            if q in known:
                problems.append(f"{where}: a wording repeats a question from another set")
            seen_q.add(q)
        page = (r.get("page") or "").strip()
        if kind == "refuse":
            absent = (r.get("absent") or "").strip()
            if page:
                problems.append(f"{where}: a neighbour question has no answer page")
            if not absent:
                problems.append(f"{where}: neighbour needs the `absent` term")
            elif not (has(absent, w1) and has(absent, w2)):
                problems.append(f"{where}: the `absent` term must be in both wordings")
            elif any(has(absent, text) for text in pages.values()):
                problems.append(f"{where}: the `absent` term is on a vault3 page, so the vault may answer it")
            continue
        if page not in pages:
            problems.append(f"{where}: no page {page!r} in vault3")
            continue
        if page.startswith(LOGS):
            problems.append(f"{where}: a daily log cannot be the answer page")
        if "status: superseded" in pages[page]:
            problems.append(f"{where}: the answer page is a replaced page; use the new one")
        if squash(r.get("evidence", "")) not in squash(pages[page]):
            problems.append(f"{where}: the evidence sentence is not on the answer page (copy it exactly)")
        if kind == "correction":
            old = old_page(page)
            if not old or "status: superseded" not in pages.get(old, ""):
                problems.append(f"{where}: a correction needs a replaced (old) / （旧） page next to its answer page")
    for kind, n in WANT.items():
        if counts[kind] != n:
            problems.append(f"expected {n} {kind} rows, found {counts[kind]}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", default=str(HERE / "human_pairs.jsonl.gz"))
    args = ap.parse_args()
    with open(args.csv, encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if not (r.get("intent") or "").startswith("EXAMPLE")]
    pages = {p.relative_to(VAULT3).as_posix(): p.read_text(encoding="utf-8") for p in VAULT3.rglob("*.md")}
    known = {squash(q["q"]) for name in bench.SETS for q in bench.questions(name)}
    problems = check(rows, pages, known)
    if problems:
        print("\n".join(problems))
        print(f"{len(problems)} problem(s); nothing written")
        return 1
    out = []
    for r in rows:
        kind = KINDS.get(r["kind"].strip().lower(), KINDS.get(r["kind"].strip()))
        gold = None if kind == "refuse" else r["page"].strip()
        for week in ("week1", "week2"):
            q = squash(r[week])
            out.append({"id": f"P-{r['intent'].strip()}-{week[-1]}", "intent": r["intent"].strip(), "week": int(week[-1]),
                        "q": q, "kind": kind, "gold": gold, "lang": "zh" if re.search(r"[一-鿿]", q) else "en"})
    Path(args.out).write_bytes(gzip.compress(("\n".join(json.dumps(o, ensure_ascii=False) for o in out) + "\n")
                                             .encode("utf-8"), mtime=0))
    print(json.dumps({"ok": True, "intents": len(rows), "questions": len(out), "out": args.out,
                      "lang": dict(Counter(o["lang"] for o in out))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
