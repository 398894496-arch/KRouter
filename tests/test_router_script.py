"""Router shell entry on a copied template vault, with and without ripgrep."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ROUTER = REPO / "skill/krouter/scripts/route_knowledge.sh"
BARE_PATH = "/usr/bin:/bin"


def _route(vault: Path, path_env: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/sh", str(ROUTER), *args],
        env={
            "HOME": str(vault.parent),
            "PATH": path_env,
            "LANG": "en_US.UTF-8",
            "OBSIDIAN_VAULT": str(vault),
        },
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    dest = tmp_path / "MySecondBrain"
    shutil.copytree(REPO / "template", dest)
    return dest


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell entry")
def test_search_without_ripgrep_still_matches(vault: Path):
    proc = _route(vault, BARE_PATH, "search", "home")
    assert proc.returncode == 0, proc.stderr
    assert "canonical_match: true" in proc.stdout
    assert "not found" not in proc.stderr, f"noisy stderr: {proc.stderr}"
    assert proc.stderr.strip() == ""


@pytest.mark.skipif(not shutil.which("rg"), reason="ripgrep not installed")
def test_search_with_ripgrep_matches_the_same_source(vault: Path):
    bare = _route(vault, BARE_PATH, "search", "home")
    with_rg = _route(vault, BARE_PATH + ":" + str(Path(shutil.which("rg")).parent), "search", "home")
    assert with_rg.returncode == 0, with_rg.stderr

    def canonical(out: str) -> str:
        for line in out.splitlines():
            if line.startswith("canonical_source:"):
                return line
        return ""

    assert canonical(with_rg.stdout)
    assert canonical(with_rg.stdout) == canonical(bare.stdout)


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell entry")
def test_status_route_returns_source_fields(vault: Path):
    proc = _route(vault, BARE_PATH, "status")
    assert proc.returncode == 0, proc.stderr
    assert "source_status: active" in proc.stdout
    assert "source_sha256:" in proc.stdout
