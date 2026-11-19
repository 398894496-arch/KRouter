#!/usr/bin/env python3
"""Set 50 (bench/memory_honesty/HELDOUT.md): replies that carry nothing to look up, through the per-message hook.

    python3 bench/subconscious/thin.py VAULT [--scripts DIR] [--heldout] [--show]

Calls `recollect.recollect()` on each line of `short_replies.txt` (`--heldout`: `short_replies_heldout.txt`) exactly as `session_hook.py prompt` does, on VAULT as
it is (its recall index must exist; nothing is rebuilt, nothing is logged, no model is called). Prints how many lines
brought a page and by which route; `--show` also prints the lines and the pages (leave it off on a vault that is not
yours to show).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("vault", type=Path)
    ap.add_argument("--scripts", type=Path, default=HERE.parents[1] / "skill/krouter/scripts")
    ap.add_argument("--heldout", action="store_true")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    os.environ["KROUTER_NO_QUERY_LOG"] = "1"
    sys.path.insert(0, str(args.scripts))
    import recollect

    lines = [x.strip() for x in (HERE / ("short_replies_heldout.txt" if args.heldout else "short_replies.txt")).read_text(encoding="utf-8").splitlines()
             if x.strip() and not x.startswith("#")]
    routes: Counter = Counter()
    loud = 0
    for line in lines:
        hits = recollect.recollect(args.vault, line, recollect.DEFAULT_ROUTES)
        loud += bool(hits)
        for h in hits:
            routes[h["route"]] += 1
            if args.show:
                print(f"  {line!r} -> {h['rel']} ({h['route']}: {h['word']})")
    print(f"replies: {len(lines)}  brought a page: {loud}  pages by route: {dict(routes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
