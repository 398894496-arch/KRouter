"""The installer adds KRouter to Claude Desktop's MCP settings and the uninstaller takes only that entry out."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import bootstrap  # noqa: E402

SERVER = ["/usr/bin/python3", "/home/u/.agents/skills/krouter/scripts/mcp_server.py"]


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    path = tmp_path / "Claude" / "claude_desktop_config.json"
    path.parent.mkdir()
    monkeypatch.setenv("KROUTER_CLAUDE_DESKTOP_CONFIG", str(path))
    return path


def test_adds_krouter_and_keeps_the_rest(cfg):
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}), encoding="utf-8")
    assert bootstrap.register_desktop(SERVER, dry=False)
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["mcpServers"]["krouter"] == {"command": SERVER[0], "args": SERVER[1:]}
    assert data["mcpServers"]["other"] == {"command": "x"} and data["theme"] == "dark"
    assert cfg.with_name(cfg.name + ".krouter-bak").exists()
    assert bootstrap.register_desktop(SERVER, dry=False)  # 再跑一次不重复、不出错


def test_new_file_when_the_app_has_none_yet(cfg):
    assert bootstrap.register_desktop(SERVER, dry=False)
    assert json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]["krouter"]["args"] == SERVER[1:]


def test_leaves_someone_elses_entry_and_broken_files_alone(cfg):
    cfg.write_text(json.dumps({"mcpServers": {"krouter": {"command": "node", "args": ["their-server.js"]}}}), encoding="utf-8")
    before = cfg.read_text(encoding="utf-8")
    assert not bootstrap.register_desktop(SERVER, dry=False)
    assert cfg.read_text(encoding="utf-8") == before
    cfg.write_text("{ not json", encoding="utf-8")
    assert not bootstrap.register_desktop(SERVER, dry=False)
    assert cfg.read_text(encoding="utf-8") == "{ not json"


def test_no_app_no_file(tmp_path, monkeypatch):
    monkeypatch.delenv("KROUTER_CLAUDE_DESKTOP_CONFIG", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    assert bootstrap.claude_desktop_config() is None


def test_dry_run_changes_nothing(cfg, capsys):
    assert not bootstrap.register_desktop(SERVER, dry=True)
    assert not cfg.exists() and "Claude Desktop: add mcpServers.krouter" in capsys.readouterr().out


@pytest.mark.skipif(os.name == "nt", reason="uninstall.sh is POSIX")
def test_uninstall_takes_out_only_our_entry(cfg, tmp_path):
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"},
                                              "krouter": {"command": "python3", "args": ["/a/mcp_server.py"]}}}),
                   encoding="utf-8")
    env = {"HOME": str(tmp_path / "home"), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8",
           "KROUTER_CLAUDE_DESKTOP_CONFIG": str(cfg), "KROUTER_SKILL_HOME": str(tmp_path / "home/skill"),
           "KROUTER_VAULT_FILE": str(tmp_path / "vf"),
           "KROUTER_CLAUDE_DESKTOP_RUNNING": "0"}  # 本机开着的 Claude Desktop 不算：这里测的是它关着时
    (tmp_path / "home").mkdir()
    res = subprocess.run(["/bin/sh", str(REPO / "scripts/uninstall.sh")], env=env, capture_output=True, text=True,
                         timeout=120)
    assert res.returncode == 0, res.stderr
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "krouter" not in data["mcpServers"] and data["mcpServers"]["other"] == {"command": "x"}
    assert "removed: MCP server krouter (Claude Desktop)" in res.stdout
