"""The templates a new memory starts from name no one's machine: no app bundle path, no home folder, no Homebrew
prefix (a sample page with one came up as a hit for unrelated questions)."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MACHINE = re.compile(r"/Applications/|/Users/[A-Za-z]|/home/[a-z]|/opt/homebrew|C:\\\\Users\\\\")


def test_no_machine_paths_in_the_templates():
    hits = [f"{p.relative_to(REPO)}: {m.group(0)}" for t in ("template", "template-zh") for p in (REPO / t).rglob("*.md")
            for m in [MACHINE.search(p.read_text(encoding="utf-8"))] if m]
    assert not hits, hits
