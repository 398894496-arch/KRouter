#!/usr/bin/env python3
"""Mechanical check of a canonical map against a vault.

Every alias must unique-hit its row. Every source file must exist and be in
force. Exhaustive on that map — not a sample, not a claim the ranker is smart.

Any host can run this on their own files. It does not verify the historical
claim that the author’s live map was 26/26 · 156/156.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill/krouter/scripts"))

from canonical_lookup import in_force, live_rows, load_rows, lookup, parse_frontmatter  # noqa: E402


def verify(
    map_path: Path,
    vault: Path,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    rows = load_rows(map_path)
    live = live_rows(rows, vault, today)
    failures: list[str] = []
    alias_count = 0
    seen_id: dict[str, int] = {}

    for case_id, aliases, source, _anchor in rows:
        seen_id[case_id] = seen_id.get(case_id, 0) + 1
        alias_count += len(aliases)
        path = vault / source
        if not path.is_file():
            failures.append(f"{case_id}: missing {source}")
            continue
        live_ok, _, invalid_s = in_force(parse_frontmatter(path), today)
        if not live_ok:
            failures.append(f"{case_id}: not in force {source} invalid_at={invalid_s}")
            continue
        for alias in aliases:
            hit = lookup(alias, rows, vault=vault, today=today)
            if hit is None:
                failures.append(f"{case_id}: alias {alias!r} missed")
                continue
            if hit[0] != case_id:
                failures.append(f"{case_id}: alias {alias!r} hit {hit[0]}")
            if hit[1].replace("\\", "/") != source.replace("\\", "/"):
                failures.append(f"{case_id}: alias {alias!r} source {hit[1]}")

    dup = sorted(cid for cid, n in seen_id.items() if n != 1)
    if dup:
        failures.append(f"duplicate ids: {dup}")
    if len(live) != len(rows):
        failures.append(f"live_rows {len(live)} != map rows {len(rows)}")

    return {
        "ok": not failures,
        "topics": len(rows),
        "aliases": alias_count,
        "live": len(live),
        "failures": failures,
        "map": str(map_path),
        "vault": str(vault),
        "today": today.isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--map",
        type=Path,
        default=ROOT / "tests/fixtures/clone_25/canonical_sources.psv",
    )
    parser.add_argument(
        "--vault",
        type=Path,
        default=ROOT / "template",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = verify(args.map, args.vault)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if result["ok"] else "FAIL"
        print(
            f"{status} topics={result['topics']}/{result['topics']} "
            f"aliases={result['aliases']}/{result['aliases']} "
            f"live={result['live']} failures={len(result['failures'])}"
        )
        for line in result["failures"]:
            print(f"  {line}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
