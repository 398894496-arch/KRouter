"""Python router twin runs without POSIX shell."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROUTER = REPO / "skill/krouter/scripts/route_knowledge.py"


def _route(vault: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROUTER), *args],
        env={
            **os.environ,
            "OBSIDIAN_VAULT": str(vault),
            "PYTHONPATH": str(ROUTER.parent),
        },
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROUTER.parent),
    )


def test_python_router_status_and_home_search(tmp_path):
    import shutil

    vault = tmp_path / "MySecondBrain"
    shutil.copytree(REPO / "template", vault)
    status = _route(vault, "status")
    assert status.returncode == 0, status.stderr
    assert "source_sha256:" in status.stdout
    search = _route(vault, "search", "home")
    assert search.returncode == 0, search.stderr
    assert "canonical_match: true" in search.stdout
