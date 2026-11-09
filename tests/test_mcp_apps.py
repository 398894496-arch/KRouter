"""The installer wires every app it finds (official config formats), and the uninstaller takes only our entry out."""

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

SERVER = ["/usr/bin/python3", "/home/u/.agents/skills/krouter-obsidian/scripts/mcp_server.py"]
APPS = {a["id"]: a for a in bootstrap.MCP_APPS}
# 各家官方文档里的写法（2026-11-09 核对）
EXPECT = {
    "claude-desktop": ("mcpServers", {"command": SERVER[0], "args": SERVER[1:]}),
    "cursor": ("mcpServers", {"command": SERVER[0], "args": SERVER[1:]}),
    "vscode": ("servers", {"type": "stdio", "command": SERVER[0], "args": SERVER[1:]}),
    "copilot-cli": ("mcpServers", {"type": "local", "command": SERVER[0], "args": SERVER[1:], "tools": ["*"]}),
    "gemini-cli": ("mcpServers", {"command": SERVER[0], "args": SERVER[1:]}),
    "kiro": ("mcpServers", {"command": SERVER[0], "args": SERVER[1:]}),
    "zed": ("context_servers", {"command": SERVER[0], "args": SERVER[1:], "env": {}}),
    "cline": ("mcpServers", {"command": SERVER[0], "args": SERVER[1:], "disabled": False}),
}


def env_name(app_id: str) -> str:
    return "KROUTER_MCP_CONFIG_" + app_id.upper().replace("-", "_")


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """A home with no app installed, and every override cleared."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    monkeypatch.delenv("COPILOT_HOME", raising=False)
    monkeypatch.delenv("CLINE_MCP_SETTINGS_PATH", raising=False)
    monkeypatch.delenv("KROUTER_CLAUDE_DESKTOP_CONFIG", raising=False)
    for a in APPS:
        monkeypatch.delenv(env_name(a), raising=False)
    return tmp_path


def test_every_app_in_the_table_is_checked():
    assert set(APPS) == set(EXPECT)


def test_an_app_that_is_not_installed_is_left_alone(home):
    for app in bootstrap.MCP_APPS:
        assert bootstrap.app_config(app) is None
        assert not bootstrap.register_app(app, SERVER, dry=False)
    assert not any(home.rglob("*.json"))


@pytest.mark.parametrize("app_id", sorted(EXPECT))
def test_installed_app_gets_its_own_format_and_keeps_the_rest(home, app_id):
    app = APPS[app_id]
    app["dir"]().mkdir(parents=True)  # 应用装了：它的文件夹在
    cfg = bootstrap.app_config(app)
    key, entry = EXPECT[app_id]
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({key: {"other": {"command": "x"}}, "theme": "dark"}), encoding="utf-8")
    assert bootstrap.register_app(app, SERVER, dry=False)
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data[key]["krouter"] == entry
    assert data[key]["other"] == {"command": "x"} and data["theme"] == "dark"
    assert cfg.with_name(cfg.name + ".krouter-bak").exists()
    assert bootstrap.register_app(app, SERVER, dry=False)  # 再跑一次不重复
    assert bootstrap.unregister_apps(dry=False) == [app_id]
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "krouter" not in data[key] and data[key]["other"] == {"command": "x"}


def test_a_file_with_comments_or_someone_elses_krouter_is_not_touched(home, capsys):
    app = APPS["zed"]
    app["dir"]().mkdir(parents=True)
    cfg = bootstrap.app_config(app)
    jsonc = '// Zed settings\n{ "theme": "One Dark", }\n'
    cfg.write_text(jsonc, encoding="utf-8")
    assert not bootstrap.register_app(app, SERVER, dry=False, t=bootstrap.MSG["en"])
    assert cfg.read_text(encoding="utf-8") == jsonc
    assert "by hand" in capsys.readouterr().out
    cur = APPS["cursor"]
    cur["dir"]().mkdir(parents=True)
    path = bootstrap.app_config(cur)
    path.parent.mkdir(parents=True, exist_ok=True)
    foreign = {"mcpServers": {"krouter": {"command": "some-other-krouter"}}}
    path.write_text(json.dumps(foreign), encoding="utf-8")
    assert not bootstrap.register_app(cur, SERVER, dry=False)
    assert bootstrap.unregister_apps(dry=False) == []
    assert json.loads(path.read_text(encoding="utf-8")) == foreign


@pytest.mark.skipif(os.name == "nt", reason="uninstall.sh is POSIX")
def test_uninstall_sh_takes_our_entries_out_of_every_app(home):
    wired = []
    for app_id in ("cursor", "vscode", "gemini-cli"):
        app = APPS[app_id]
        app["dir"]().mkdir(parents=True)
        assert bootstrap.register_app(app, SERVER, dry=False)
        wired.append(bootstrap.app_config(app))
    env = {"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
           "LANG": "en_US.UTF-8", "KROUTER_SKILL_HOME": str(home / "skill"), "KROUTER_VAULT_FILE": str(home / "vf")}
    res = subprocess.run(["/bin/sh", str(REPO / "scripts/uninstall.sh")], env=env, capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    for name in ("Cursor", "VS Code", "Gemini CLI"):
        assert f"removed: MCP server krouter ({name})" in res.stdout
    for cfg in wired:
        assert "krouter" not in cfg.read_text(encoding="utf-8")


@pytest.mark.skipif(os.name == "nt", reason="the stub is a shell script")
def test_plugin_comes_from_this_release_not_from_main(tmp_path, monkeypatch):
    """No krouter marketplace yet → add this release's folder as one, then install from it; already there → install."""
    log = tmp_path / "calls"
    stub = tmp_path / "claude"
    stub.write_text('#!/bin/sh\necho "$@" >> "%s"\n'
                    'if [ "$2" = install ] && ! grep -q "marketplace add" "%s"; then exit 1; fi\nexit 0\n' % (log, log),
                    encoding="utf-8")
    stub.chmod(0o755)
    monkeypatch.delenv("KROUTER_NO_PLUGIN", raising=False)
    assert bootstrap.install_plugin(str(stub))
    calls = log.read_text(encoding="utf-8").splitlines()
    assert calls == ["plugin install krouter@krouter", f"plugin marketplace add {bootstrap.ROOT}",
                     "plugin install krouter@krouter"]
    assert bootstrap.install_plugin(str(stub)) and log.read_text(encoding="utf-8").splitlines()[-1] == "plugin install krouter@krouter"
    monkeypatch.setenv("KROUTER_NO_PLUGIN", "1")
    assert not bootstrap.install_plugin(str(stub))
