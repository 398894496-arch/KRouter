"""#103: the plugin's hooks and the router find a Python that really runs. On Windows `python3` is often the Microsoft
Store app-execution alias, which exits 9009 and prints nothing; Claude Code runs hooks there through Git Bash, so the
`sh` launcher has to skip it. Here a stand-in alias (a `python3` under a `WindowsApps` folder that exits without a
word) and a stand-in `uname` that says MINGW play Windows on any machine; on the Windows CI runner the same tests run
in Git Bash itself."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_session_hook import _ctx, _hook, _setup

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter/scripts"
HOOKS = json.loads((REPO / "hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]


def _sh() -> str:
    """POSIX sh, or on Windows Git Bash's (System32's bash.exe is WSL, not what Claude Code runs)."""
    if os.name != "nt":
        return shutil.which("sh") or "/bin/sh"
    for p in (Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git/bin/bash.exe",
              Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git/usr/bin/sh.exe"):
        if p.is_file():
            return str(p)
    pytest.skip("no Git Bash on this Windows machine")


def _script(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8", newline="\n")
    path.chmod(0o755)


def _windows_like(tmp: Path, with_real_python: bool = True) -> str:
    """A PATH whose `python3` is the silent alias, with `python` the real interpreter behind it."""
    fake = tmp / "fakebin"
    _script(fake / "uname", 'echo "MINGW64_NT-10.0-26300"')
    _script(tmp / "Microsoft/WindowsApps/python3", "exit 49")  # 9009 % 256: no output at all, like the alias
    if with_real_python:
        _script(tmp / "realpy/python", f'exec "{Path(sys.executable).as_posix()}" "$@"')
    dirs = [fake, tmp / "Microsoft/WindowsApps"] + ([tmp / "realpy"] if with_real_python else [])
    return os.pathsep.join([str(d) for d in dirs] + [os.environ.get("PATH", "")])


def _run_command(command: str, env: dict, payload: dict) -> subprocess.CompletedProcess:
    """The hook command line, the way Claude Code runs it: through a shell, with CLAUDE_PLUGIN_ROOT set."""
    return subprocess.run([_sh(), "-c", command], input=json.dumps(payload), env={**env, "CLAUDE_PLUGIN_ROOT": REPO.as_posix()},
                          capture_output=True, text=True, timeout=60)


def test_every_plugin_hook_runs_through_the_sh_launcher():
    for event, groups in HOOKS.items():
        cmd = groups[0]["hooks"][0]["command"]
        assert cmd.startswith('sh "${CLAUDE_PLUGIN_ROOT}/skill/krouter/scripts/session_hook" '), event
        assert "python3" not in cmd


def test_the_start_hook_as_written_gives_what_the_script_gives(tmp_path):
    s = _setup(tmp_path)
    direct = _ctx(_hook(s["env"], "start", {"cwd": str(s["shop"])}))
    res = _run_command(HOOKS["SessionStart"][0]["hooks"][0]["command"], s["env"], {"cwd": str(s["shop"])})
    assert res.returncode == 0, res.stderr
    assert _ctx(res) == direct and "改成 CI 发布" in direct


def test_the_store_alias_is_skipped_and_the_real_python_runs(tmp_path):
    s = _setup(tmp_path)
    env = {**s["env"], "PATH": _windows_like(tmp_path)}
    res = _run_command(HOOKS["SessionStart"][0]["hooks"][0]["command"], env, {"cwd": str(s["shop"])})
    assert res.returncode == 0, res.stderr
    assert "改成 CI 发布" in _ctx(res)  # 走到了真 Python：记过的决定照样带进来


@pytest.mark.skipif(os.name == "nt", reason="a Windows runner keeps py.exe in C:\\Windows, out of a test's reach")
def test_no_python_that_runs_is_said_out_loud(tmp_path):
    fake = tmp_path / "only"
    _script(fake / "uname", 'echo "MINGW64_NT-10.0-26300"')
    _script(tmp_path / "Microsoft/WindowsApps/python3", "exit 49")
    _script(tmp_path / "Microsoft/WindowsApps/python", "exit 49")
    dirname = shutil.which("dirname")
    assert dirname
    (fake / "dirname").symlink_to(dirname)
    env = {"PATH": os.pathsep.join([str(fake), str(tmp_path / "Microsoft/WindowsApps")]), "HOME": str(tmp_path)}
    res = subprocess.run([_sh(), str(SCRIPTS / "session_hook"), "start"], input="{}", env=env,
                         capture_output=True, text=True, timeout=30)
    assert res.returncode == 127 and res.returncode != 2  # 2 would block the prompt; anything else only reports
    assert "no working Python 3" in res.stderr and "Microsoft Store" in res.stderr


def test_macos_and_linux_use_python3_with_no_check_first(tmp_path):
    """No extra process on every message where python3 is real: the launcher only checks what looks like the alias."""
    if os.name == "nt":
        pytest.skip("POSIX path")
    marker = tmp_path / "ran"
    _script(tmp_path / "bin/python3", f'echo "$@" >> "{marker}"; exec "{sys.executable}" "$@"')
    env = {"PATH": os.pathsep.join([str(tmp_path / "bin"), os.environ.get("PATH", "")]), "HOME": str(tmp_path)}
    res = subprocess.run([_sh(), str(SCRIPTS / "session_hook"), "start"], input="not json", env=env,
                         capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    assert marker.read_text(encoding="utf-8").splitlines() == [f"{SCRIPTS / 'session_hook.py'} start"]  # 一次，没有 -c 试跑


def test_the_router_skips_the_store_alias_too(tmp_path):
    s = _setup(tmp_path)
    env = {**s["env"], "PATH": _windows_like(tmp_path)}
    res = subprocess.run([_sh(), (SCRIPTS / "route_knowledge.sh").as_posix(), "search", "发版"], env=env,
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip()  # 有回执：走到了 route_knowledge.py，或者纯 shell 那条路


def test_the_lookup_command_handed_to_the_agent_uses_forward_slashes(tmp_path):
    sys.path.insert(0, str(SCRIPTS))
    import compile_subconscious as cs

    src = Path(cs.__file__).read_text(encoding="utf-8")
    assert 'with_name("route_knowledge.sh").as_posix()' in src  # Git Bash 里 C:\… 的反斜杠不当路径分隔
