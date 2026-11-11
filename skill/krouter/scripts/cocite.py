#!/usr/bin/env python3
"""Nightly step: pages a confident lookup returned together get a stronger co-citation edge.

Reads the router's query log (`queries.jsonl` in the state directory, the same log trigger learning reads) from where
the last run stopped. Each logged lookup that recall answered with `high` or `medium` confidence and that lists two
or more direct hits (`pages`) adds one to the co-citation weight of every pair among them, through
`associate.reinforce`; the recall cache reads the weights on its next refresh, and the associative path follows the
edge (saturating at `associate.COCITE_SAT`). Only direct hits are logged, never associated pages, so the path cannot
strengthen itself. Pages no longer in the vault are skipped. No model, nothing in the vault is written.

    python3 cocite.py --vault <vault>            # what the nightly job runs
    python3 cocite.py --vault <vault> --dry-run  # counts only, writes nothing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import associate  # noqa: E402

CONFIDENT = {"high", "medium"}
MAX_PAGES = 3


def state_dir() -> Path:
    return Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local/state/krouter")


def cursor_file(vault: Path) -> Path:
    return state_dir() / f"cocite-cursor-{hashlib.sha1(str(vault.resolve()).encode('utf-8')).hexdigest()[:12]}.json"


def groups_since(vault: Path, log: Path, offset: int) -> tuple[list[list[str]], int, int]:
    """(page groups, lookups read, new offset). A log shorter than the offset was rotated: read it from the start."""
    if not log.is_file():
        return [], 0, 0
    data = log.read_bytes()
    if offset > len(data):
        offset = 0
    chunk = data[offset:]
    end = chunk.rfind(b"\n") + 1  # 最后一行可能还没写完：留到下次
    groups, read = [], 0
    for line in chunk[:end].decode("utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        read += 1
        if not str(row.get("status", "")).startswith("ranked-recall-complete") or row.get("confidence") not in CONFIDENT:
            continue
        pages = [p for p in dict.fromkeys(row.get("pages") or []) if isinstance(p, str) and (vault / p).is_file()]
        if len(pages) >= 2:
            groups.append(pages[:MAX_PAGES])
    return groups, read, offset + end


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--vault", default=os.environ.get("KROUTER_VAULT") or os.environ.get("OBSIDIAN_VAULT", ""))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.vault:
        print("set KROUTER_VAULT (or the older name OBSIDIAN_VAULT)", file=sys.stderr)
        return 2
    vault = Path(args.vault)
    cur = cursor_file(vault)
    try:
        offset = int(json.loads(cur.read_text(encoding="utf-8")).get("offset", 0))
    except (OSError, ValueError):
        offset = 0
    groups, read, new_offset = groups_since(vault, state_dir() / "queries.jsonl", offset)
    pairs = sum(len(g) * (len(g) - 1) // 2 for g in groups)
    if args.dry_run:
        print(json.dumps({"cocite": "dry-run", "lookups": read, "groups": len(groups), "pairs": pairs,
                          "writes": [str(associate.cocite_file(vault))] if groups else []}, ensure_ascii=False))
        return 0
    written = sum(associate.reinforce(vault, g, 1.0) for g in groups)
    cur.parent.mkdir(parents=True, exist_ok=True)
    cur.write_text(json.dumps({"offset": new_offset}), encoding="utf-8")
    print(json.dumps({"cocite": "done", "lookups": read, "groups": len(groups), "pairs": written}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
