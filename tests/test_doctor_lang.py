"""`krouter doctor` speaks the memory folder's language: every line in Chinese for a vault with the default (Chinese)
names, English for an English one; the checks and their ok / note / FAIL marks are the same."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CJK = re.compile(r"[一-鿿]")


def _doctor(tmp: Path, vault: Path) -> subprocess.CompletedProcess:
    env = {"HOME": str(tmp / "home"), "PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO / "sdk"),
           "KROUTER_NO_QUERY_LOG": "1", "KROUTER_STATE_DIR": str(tmp / "state"), "KROUTER_CACHE_DIR": str(tmp / "cache"),
           "KROUTER_VAULT_FILE": str(tmp / "none"), "KROUTER_KEYS_ENV": str(tmp / "keys.env")}
    (tmp / "home").mkdir(exist_ok=True)
    return subprocess.run([sys.executable, "-m", "krouter.cli", "--vault", str(vault), "doctor"], env=env,
                          capture_output=True, text=True, timeout=120)


def test_every_line_is_chinese_in_a_chinese_vault(tmp_path):
    vault = tmp_path / "v"
    shutil.copytree(REPO / "template-zh", vault)
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {"krouter": {"command": "python3", "args": [
        str(home / ".agents/skills/krouter-obsidian/scripts/mcp_server.py")]}}}), encoding="utf-8")
    out = _doctor(tmp_path, vault).stdout
    rows = [ln for ln in out.splitlines()[1:] if ln.strip()]
    assert rows and all(CJK.search(ln) for ln in rows), [ln for ln in rows if not CJK.search(ln)]
    assert rows[-1].startswith("结论：")


def test_an_english_vault_stays_english(tmp_path):
    sys.path.insert(0, str(REPO / "skill/krouter/scripts"))
    import zones

    vault = tmp_path / "en"
    zones.lay_out(REPO / "template", vault, alias_sample=REPO / "skill/krouter/scripts/canonical_sources.psv")
    out = _doctor(tmp_path, vault).stdout
    assert "verdict:" in out and not CJK.search(out.replace(str(tmp_path), ""))
