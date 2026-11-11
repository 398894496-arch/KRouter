#!/usr/bin/env python3
"""Copy the current-status block into every entry file an agent may read on its own.

An agent that lands on PROTOCOL.md or VERIFY.md alone should still get the latest numbers and their limits, not an
older story. The block's source is `docs/STATUS.md` (English) and `docs/STATUS.zh.md` (Chinese); each entry file holds
a copy between the markers, right under its title. Edit the source, then run this; `tests/test_docs_status.py` fails
when a copy drifts.

    python3 scripts/sync_status.py [--check]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START, END = "<!-- krouter-status:start (source: docs/STATUS{lang}.md; run scripts/sync_status.py) -->", "<!-- krouter-status:end -->"
TARGETS = {"": ["PROTOCOL.md", "SECURITY.md", "docs/VERIFY.md", "docs/ARCHITECTURE.md", "docs/BENCHMARK.md",
                "docs/DETAILS.md", "docs/FOR-AGENTS.md"],
           ".zh": ["docs/DETAILS.zh.md"]}
BLOCK = re.compile(r"<!-- krouter-status:start[^>]*-->.*?<!-- krouter-status:end -->\n*", re.S)


def block(lang: str) -> str:
    body = (ROOT / f"docs/STATUS{lang}.md").read_text(encoding="utf-8").strip()
    return f"{START.format(lang=lang)}\n{body}\n{END}\n\n"


def synced(text: str, blk: str) -> str:
    text = BLOCK.sub("", text, count=1)
    head, sep, rest = text.partition("\n")  # 标题行之后
    return f"{head}\n\n{blk}{rest.lstrip(chr(10))}" if sep else f"{head}\n\n{blk}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="only report files whose copy differs")
    args = ap.parse_args()
    stale = []
    for lang, files in TARGETS.items():
        blk = block(lang)
        for rel in files:
            path = ROOT / rel
            text = path.read_text(encoding="utf-8")
            new = synced(text, blk)
            if new != text:
                stale.append(rel)
                if not args.check:
                    path.write_text(new, encoding="utf-8")
    print(("stale: " if args.check else "updated: ") + (", ".join(stale) or "none"))
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
