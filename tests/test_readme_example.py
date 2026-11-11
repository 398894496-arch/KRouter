"""The Claude Desktop + Obsidian example (moved from the READMEs to docs/OVERVIEW*.md) is the receipt the sample vault really gives."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ROUTE = REPO / "skill/krouter/scripts/route_knowledge.py"
CASES = [
    ("docs/OVERVIEW.md", "docs/examples/writer-vault", "Going to open this week's newsletter with a question to the reader."),
    ("docs/OVERVIEW.zh.md", "docs/examples/writer-vault-zh", "这周的周报我想用提问开头。"),
]


@pytest.mark.parametrize("readme,vault,query", CASES)
def test_example_receipt_is_verbatim(readme, vault, query, tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    env.update(KROUTER_NO_QUERY_LOG="1", KROUTER_CACHE_DIR=str(tmp_path / "cache"),
               KROUTER_VAULT=str(REPO / vault), OBSIDIAN_VAULT=str(REPO / vault))
    out = subprocess.run([sys.executable, str(ROUTE), "search", query], capture_output=True, text=True, env=env,
                         check=True).stdout
    real = out[out.index("recall_confidence:"):out.index("open_page:")]
    last = out[out.index("open_page:"):].splitlines()[0]
    text = (REPO / readme).read_text(encoding="utf-8")
    m = re.search(r"```text\n(recall_confidence:.*?open_page:[^\n]*)\n```", text, re.S)
    assert m, "the example block is missing from " + readme
    assert m.group(1) == (real + last).rstrip("\n")
