#!/usr/bin/env python3
"""Implementation check on template/: exhaustive map + rewrite invariants.

Not an LLM session. Not the author’s private 25. Not a comparison to cosine.
Mechanical 25/25 is table consistency. Rewrite 25/25 is “code matches protocol.”
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "skill/krouter/scripts"))
sys.path.insert(0, str(ROOT / "scripts"))

from canonical_lookup import load_rows, lookup  # noqa: E402
from verify_canonical_map import verify  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_MAP = HERE / "canonical_sources.psv"
DEFAULT_GOLD = HERE / "gold.jsonl"
DEFAULT_VAULT = ROOT / "template"
TODAY = date(2026, 8, 27)


def load_gold(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def score_rewrite(gold: list[dict], rows, vault: Path) -> list[dict]:
    out = []
    for item in gold:
        para = lookup(item["query"], rows, vault=vault, today=TODAY)
        noun = lookup(item["noun"], rows, vault=vault, today=TODAY)
        noun_path = noun[1].replace("\\", "/") if noun else None
        out.append(
            {
                "id": item["id"],
                "paraphrase_miss": para is None,
                "noun_hit": noun_path == item["gold"],
                "noun_id": noun[0] if noun else None,
                "noun_path": noun_path,
                "gold": item["gold"],
            }
        )
    return out


def run(
    map_path: Path = DEFAULT_MAP,
    gold_path: Path = DEFAULT_GOLD,
    vault: Path = DEFAULT_VAULT,
) -> dict:
    mech = verify(map_path, vault, today=TODAY)
    rows = load_rows(map_path)
    gold = load_gold(gold_path)
    rewrite = score_rewrite(gold, rows, vault)
    n = len(rewrite)
    para_ok = sum(1 for r in rewrite if r["paraphrase_miss"])
    noun_ok = sum(1 for r in rewrite if r["noun_hit"])
    return {
        "mechanical": mech,
        "rewrite": {
            "n": n,
            "paraphrase_miss": para_ok,
            "noun_hit": noun_ok,
            "ok": n == 25 and para_ok == n and noun_ok == n,
            "rows": rewrite,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["mechanical"]["ok"] and result["rewrite"]["ok"] else 1
    mech = result["mechanical"]
    rw = result["rewrite"]
    print(
        f"mechanical {'PASS' if mech['ok'] else 'FAIL'} "
        f"topics={mech['topics']} aliases={mech['aliases']}"
    )
    for line in mech["failures"]:
        print(f"  {line}")
    print(
        f"rewrite {'PASS' if rw['ok'] else 'FAIL'} "
        f"paraphrase_miss={rw['paraphrase_miss']}/{rw['n']} "
        f"noun_hit={rw['noun_hit']}/{rw['n']}"
    )
    for row in rw["rows"]:
        if not row["paraphrase_miss"] or not row["noun_hit"]:
            print(
                f"  {row['id']} para_miss={row['paraphrase_miss']} "
                f"noun={row['noun_id']} {row['noun_path']}"
            )
    return 0 if mech["ok"] and rw["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
