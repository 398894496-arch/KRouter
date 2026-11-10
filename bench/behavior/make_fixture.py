#!/usr/bin/env python3
"""A throwaway memory folder for the real-session behaviour sets (30, 31): the English layout the installer makes,
the 30-page engineering vault of the memory-honesty bench (decisions, some replaced), the 14 English experience
cards of the transfer bench, one git commit. Nothing outside DEST is touched.

    python3 bench/behavior/make_fixture.py DEST
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def build(dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    with tempfile.TemporaryDirectory() as home:
        env = {"HOME": home, "PATH": os.environ.get("PATH", ""), "LANG": "en_US.UTF-8", "KROUTER_NO_PROMPT": "1",
               "KROUTER_NO_QUERY_LOG": "1", "XDG_CONFIG_HOME": f"{home}/.config", "KROUTER_STATE_DIR": f"{home}/state"}
        res = subprocess.run([sys.executable, str(ROOT / "scripts/bootstrap.py"), "--minimal", "--no-open", "--no-timer",
                              "--no-import", "--lang", "en", "--vault", str(dest)], env=env, capture_output=True, text=True)
        if res.returncode:
            raise SystemExit(res.stdout[-800:] + res.stderr[-800:])
    shutil.copytree(ROOT / "bench/memory_honesty/vault/Engineering", dest / "Engineering")
    sys.path.insert(0, str(ROOT / "skill/krouter/scripts"))
    import recall_index as ri
    import zones

    cards = zones.path(dest, ri.EXPERIENCE_DIR)
    cards.mkdir(parents=True, exist_ok=True)
    for f in sorted((ROOT / "bench/transfer/cards_en").glob("*.md")):
        shutil.copy2(f, cards / f.name)
    git = ["git", "-C", str(dest), "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid"]
    subprocess.run(["git", "-C", str(dest), "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "fixture"], check=True)
    return dest


if __name__ == "__main__":
    print(build(Path(sys.argv[1])))
