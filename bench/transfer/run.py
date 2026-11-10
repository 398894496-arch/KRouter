#!/usr/bin/env python3
"""Set 13 (bench/memory_honesty/HELDOUT.md): does a lesson from one task come back as a suggestion on another task in
the same situation, and stay quiet otherwise?

The vault is the public Chinese template (`template-zh/`) with the 14 hand-written cards of `cards/` in
`02 经验与方法/经验卡/`. Every case is a task description; the suggestion path (`experience.suggest`) runs on it, no
model call. Scored mechanically:

- recalled: a `transfer` case whose expected card is among the suggestions;
- wrong: any suggestion on a case that should get none (`topic-trap`, `word-trap`, `unrelated`), and any other card
  on a transfer case.

    python3 bench/transfer/run.py dev                # the development cases, current threshold
    python3 bench/transfer/run.py dev --sweep        # thresholds tried on development (how the default was picked)
    python3 bench/transfer/run.py heldout            # once, after registration (HELDOUT.md, set 13)
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "skill/krouter-obsidian/scripts"))
import experience  # noqa: E402


def load(split: str) -> list[dict]:
    if split == "dev":
        text = (HERE / "dev.jsonl").read_text(encoding="utf-8")
    else:
        with gzip.open(HERE / "heldout.jsonl.gz", "rt", encoding="utf-8") as fh:
            text = fh.read()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def build_vault(root: Path) -> Path:
    vault = root / "vault"
    shutil.copytree(REPO / "template-zh", vault)
    folder = vault / experience.FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    for card in sorted((HERE / "cards").glob("*.md")):
        shutil.copy(card, folder / card.name)
    return vault


def card_id(rel: str) -> str:
    return Path(rel).name.split("｜", 1)[0]


def score(cases: list[dict], vault: Path, **kw) -> dict:
    cards = experience.load_cards(vault)
    rows, recalled, wrong_cases, wrong_cards = [], 0, 0, 0
    quiet_bad = Counter()
    for c in cases:
        got = [card_id(s["rel"]) for s in experience.suggest(vault, c["query"], cards=cards, **kw)]
        if c["expect"]:
            ok = c["expect"] in got
            recalled += ok
            others = [g for g in got if g != c["expect"]]
        else:
            ok, others = not got, got
            if got:
                quiet_bad[c["kind"]] += 1
        wrong_cards += len(others)
        wrong_cases += bool(others)
        rows.append({"id": c["id"], "kind": c["kind"], "expect": c["expect"], "got": got, "ok": ok})
    transfer = sum(1 for c in cases if c["expect"])
    quiet = len(cases) - transfer
    return {"transfer": transfer, "recalled": recalled, "quiet_cases": quiet,
            "quiet_cases_with_suggestion": sum(quiet_bad.values()), "by_kind": dict(quiet_bad),
            "transfer_wrong_cards": sum(len([g for g in r["got"] if g != r["expect"]]) for r in rows if r["expect"]),
            "cases_with_wrong_suggestion": wrong_cases, "wrong_cards": wrong_cards, "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("split", choices=("dev", "heldout"))
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--rows", action="store_true", help="print every case (development only)")
    args = ap.parse_args()
    if args.split == "heldout" and (args.sweep or args.rows):
        print("held-out is run once at the default threshold, aggregates only", file=sys.stderr)
        return 2
    cases = load(args.split)
    with tempfile.TemporaryDirectory() as tmp:
        vault = build_vault(Path(tmp))
        if args.sweep:
            for words in (1, 2):
                for cover in (0.4, 0.5, 0.6, 0.67, 0.75, 0.99):
                    r = score(cases, vault, min_cover=cover, min_words=words)
                    print(json.dumps({"min_words": words, "min_cover": cover, "recalled": r["recalled"],
                                      "quiet_with_suggestion": r["quiet_cases_with_suggestion"],
                                      "transfer_wrong_cards": r["transfer_wrong_cards"]}))
            return 0
        r = score(cases, vault)
        rows = r.pop("rows")
        print(json.dumps({"split": args.split, "min_cover": experience.MIN_COVER, "min_words": experience.MIN_WORDS,
                          **r}, ensure_ascii=False))
        if args.rows:
            for row in rows:
                print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
