#!/usr/bin/env python3
"""Set 40: score the automatic reference-material recognition (kb.py) on the labelled vaults of make.py.

    python3 bench/kb_auto/run.py DIR dev        # thresholds are set on this split only
    python3 bench/kb_auto/run.py DIR heldout    # once, with the code as chosen on dev

Builds each vault's index in a temporary cache (KROUTER_NO_QUERY_LOG=1), asks `kb.classify` about every page, and reports
the share of outside pages recognised and the share of your own pages taken for reference material, by kind.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def main(argv: list[str]) -> int:
    base, split = Path(argv[0]), argv[1]
    labels = [json.loads(x) for x in (base / "labels.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    rows = [r for r in labels if r["split"] == split]
    with tempfile.TemporaryDirectory(prefix="krouter-kbauto-") as tmp:
        os.environ["KROUTER_NO_QUERY_LOG"] = "1"
        os.environ["KROUTER_CACHE_DIR"] = str(Path(tmp) / "cache")
        os.environ["KROUTER_STATE_DIR"] = str(Path(tmp) / "state")
        sys.path.insert(0, str(REPO / "skill/krouter/scripts"))
        import kb
        import recall_index as ri

        verdict = {}
        detail = {}
        for name in sorted({r["vault"] for r in rows}):
            vault = base / name
            con = ri.connect(ri.cache_path(vault))
            try:
                ri.refresh(vault, con)
                rels = [r["rel"] for r in rows if r["vault"] == name]
                got = kb.classify(con, vault, rels)
                info = kb.origin_rows(con, vault, rels)
            finally:
                con.close()
            for rel in rels:
                verdict[(name, rel)] = bool(got.get(rel))
                detail[(name, rel)] = info.get(rel, {})
    ext = [r for r in rows if r["label"] == "ext"]
    own = [r for r in rows if r["label"] == "own"]
    found = sum(verdict[(r["vault"], r["rel"])] for r in ext)
    wrong = [r for r in own if verdict[(r["vault"], r["rel"])]]
    missed = [r for r in ext if not verdict[(r["vault"], r["rel"])]]
    out = {"split": split, "outside_recognised": f"{found}/{len(ext)}", "own_misjudged": f"{len(wrong)}/{len(own)}",
           "missed_by_kind": Counter(r["kind"] for r in missed), "misjudged_by_kind": Counter(r["kind"] for r in wrong),
           "missed": [(r["vault"], r["rel"], detail[(r["vault"], r["rel"])]) for r in missed],
           "misjudged": [(r["vault"], r["rel"], detail[(r["vault"], r["rel"])]) for r in wrong]}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
