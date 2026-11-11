"""2.0 renamed the router folder (skill/krouter-obsidian → skill/krouter, ~/.agents/skills/krouter-obsidian →
~/.agents/skills/krouter). An install made before that upgrades in place: the code moves, the alias table comes with
it, the old path is left as a link to the new folder, the old Cursor rule goes; uninstall clears both; doctor says when
a settings file still starts KRouter from the old path."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "skill/krouter/scripts/canonical_sources.psv"
MY_ROW = "Q99|my noun|02 经验与方法/经验与方法.md|Methods\n"

pytestmark = pytest.mark.skipif(os.name == "nt", reason="install.sh is POSIX")


def _env(home: Path) -> dict:
    # 不设 KROUTER_SKILL_HOME / KROUTER_CURSOR_RULE：要测的正是默认路径下的新旧两处
    home.mkdir(parents=True, exist_ok=True)
    return {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8",
            "KROUTER_KEYS_ENV": str(home / "keys.env"), "KROUTER_NO_TIMER": "1", "KROUTER_SKIP_LAUNCHD": "1",
            "KROUTER_SKIP_TIMER": "1", "KROUTER_WRITER": "/nonexistent/grok", "KROUTER_NO_MCP": "1",
            "KROUTER_NO_HOOKS": "1", "KROUTER_NO_QUERY_LOG": "1", "KROUTER_VAULT_FILE": str(home / "no-vault-file")}


def _sh(script: str, env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/bin/sh", str(REPO / "scripts" / script), *args], env=env, capture_output=True, text=True,
                          timeout=300)


def _old_install(home: Path) -> Path:
    """The layout 1.x left: the skill under krouter-obsidian (its table edited by the host) and its Cursor rule."""
    old = home / ".agents/skills/krouter-obsidian"
    shutil.copytree(REPO / "skill/krouter", old)
    (old / "scripts/canonical_sources.psv").write_text(SAMPLE.read_text(encoding="utf-8") + MY_ROW, encoding="utf-8")
    rule = home / ".cursor/rules/krouter-obsidian.mdc"
    rule.parent.mkdir(parents=True)
    rule.write_text("Run `~/.agents/skills/krouter-obsidian/scripts/route_knowledge.sh status` first.\n", encoding="utf-8")
    return old


def test_upgrade_from_the_old_folder_moves_it_and_leaves_a_link(tmp_path):
    home = tmp_path / "home"
    env = _env(home)
    old = _old_install(home)
    new = home / ".agents/skills/krouter"
    refused = _sh("install.sh", env)
    assert refused.returncode == 1 and "--upgrade" in refused.stdout  # an old install counts as an install
    up = _sh("install.sh", env, "--upgrade")
    assert up.returncode == 0, up.stdout + up.stderr
    assert (new / "scripts/route_knowledge.py").is_file() and not new.is_symlink()
    assert old.is_symlink() and old.resolve() == new.resolve(), up.stdout
    assert MY_ROW in (new / "scripts/canonical_sources.psv").read_text(encoding="utf-8")  # the host's table came along
    assert (old / "scripts/route_knowledge.sh").is_file()  # a path the host pasted somewhere still works
    assert (home / ".cursor/rules/krouter.mdc").is_file()
    assert not (home / ".cursor/rules/krouter-obsidian.mdc").exists()
    again = _sh("install.sh", env, "--upgrade")  # a second upgrade keeps the link as it is
    assert again.returncode == 0 and old.is_symlink() and old.resolve() == new.resolve()

    gone = _sh("uninstall.sh", env)
    assert gone.returncode == 0, gone.stdout + gone.stderr
    assert not new.exists() and not old.exists() and not old.is_symlink()
    assert not (home / ".cursor/rules/krouter.mdc").exists()


def test_uninstall_clears_an_old_install_that_was_never_upgraded(tmp_path):
    home = tmp_path / "home"
    env = _env(home)
    old = _old_install(home)
    gone = _sh("uninstall.sh", env)
    assert gone.returncode == 0, gone.stdout + gone.stderr
    assert not old.exists() and not (home / ".cursor/rules/krouter-obsidian.mdc").exists()
    saved = list(home.glob("dsh-krouter-canonical_sources.*.psv"))  # the edited table is saved, never lost
    assert saved and MY_ROW in saved[0].read_text(encoding="utf-8")


def test_a_fresh_install_makes_no_old_path(tmp_path):
    home = tmp_path / "home"
    env = _env(home)
    res = _sh("install.sh", env)
    assert res.returncode == 0, res.stdout + res.stderr
    assert (home / ".agents/skills/krouter/scripts/route_knowledge.py").is_file()
    assert not (home / ".agents/skills/krouter-obsidian").exists()


def test_doctor_names_a_settings_file_that_still_uses_the_old_path(tmp_path):
    home = tmp_path / "home"
    env = _env(home)
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template", vault)
    old_cmd = str(home / ".agents/skills/krouter-obsidian/scripts/mcp_server.py")
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {"krouter": {"command": "python3", "args": [old_cmd]}}}),
                                       encoding="utf-8")
    doctor = [sys.executable, "-m", "krouter.cli", "--vault", str(vault), "doctor"]
    run_env = {**env, "PYTHONPATH": str(REPO / "sdk"), "KROUTER_STATE_DIR": str(tmp_path / "state"),
               "KROUTER_CACHE_DIR": str(tmp_path / "cache")}
    broken = subprocess.run(doctor, env=run_env, capture_output=True, text=True, timeout=120)
    line = next(ln for ln in broken.stdout.splitlines() if "旧路径：" in ln)  # the template's default names: Chinese
    assert "FAIL" in line and "~/.claude.json" in line and "已经什么都没有了" in line, broken.stdout
    assert broken.returncode == 1
    new = home / ".agents/skills/krouter"
    shutil.copytree(REPO / "skill/krouter", new)
    (home / ".agents/skills/krouter-obsidian").symlink_to(new)  # what an upgrade leaves
    linked = subprocess.run(doctor, env=run_env, capture_output=True, text=True, timeout=120)
    line = next(ln for ln in linked.stdout.splitlines() if "旧路径：" in ln)
    assert line.lstrip().startswith("note") and "暂时还能用" in line, linked.stdout
