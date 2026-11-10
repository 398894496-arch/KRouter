"""Framework adapters are opt-in: the core package needs nothing installed, and importing KRouter never imports a
framework. Runs whether or not the frameworks are installed."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_the_core_package_has_no_required_dependencies():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    project = text.split("[project]", 1)[1].split("\n[", 1)[0]
    assert not re.search(r"^dependencies\s*=", project, re.M)
    extras = text.split("[project.optional-dependencies]", 1)[1].split("\n[", 1)[0]
    assert re.search(r'^langgraph = \["langgraph>=1\.0,<2"\]', extras, re.M)
    assert re.search(r"^llamaindex = ", extras, re.M)


def test_importing_krouter_imports_no_framework():
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import krouter, krouter.integrations; "
            "print(sorted(m for m in sys.modules if m.split('.')[0] in ('langgraph', 'langchain_core', 'llama_index')))")
    out = subprocess.run([sys.executable, "-c", code, str(REPO / "sdk")], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"


def test_the_adapters_ship_in_the_package():
    for name in ("llamaindex.py", "langgraph.py", "langgraph_demo.py"):
        assert (REPO / "sdk" / "krouter" / "integrations" / name).is_file()
