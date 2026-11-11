"""The commands the install prints at the end run as printed (issue #74).

On Windows the install used to print `set "PYTHONPATH=…" && python -m krouter.cli doctor`: `&&` is not a statement
separator in PowerShell 5.1, `set` does not set an environment variable in PowerShell 7 (so the module could not be
imported), and `… search "question"` was rejected by the Python command line, which has no `search` (it is `ask`).

What these tests can show on any machine: the printed Windows line has no `&&` and no `set`, it is `python "<launcher>"`
followed by arguments, the launcher exists and runs, and the arguments printed for `doctor` and `ask` are accepted by the
command line's own argument parser. What they cannot show: that the line runs in a real PowerShell 5.1, PowerShell 7 or
cmd. That waits for CI's Windows machine after this is pushed.
"""

from __future__ import annotations

import importlib.util
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "sdk"))


def _bootstrap():
    spec = importlib.util.spec_from_file_location("bootstrap_under_test", REPO / "scripts/bootstrap.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _printed(mod, lang: str, windows: bool, monkeypatch) -> str:
    monkeypatch.setattr(mod, "WINDOWS", windows)
    monkeypatch.setattr(mod.shutil, "which", lambda name, *a, **k: None)  # `krouter` is not on PATH
    return mod.cli_line(mod.MSG[lang])


def _commands(line: str, prefix: str) -> list[str]:
    """The command lines in the printed text: each starts with the prefix the install printed."""
    out = []
    for m in re.finditer(re.escape(prefix) + r"(?: doctor| ask \"[^\"]*\")", line):
        out.append(m.group(0))
    return out


@pytest.mark.parametrize("lang", ["en", "zh"])
def test_windows_line_has_no_and_and_no_set(lang, monkeypatch):
    mod = _bootstrap()
    line = _printed(mod, lang, True, monkeypatch)
    cli = mod.cli_path()  # WINDOWS is still patched
    assert "&&" not in cli and "&&" not in line
    assert not cli.startswith("set ")
    assert cli.startswith('python "') and cli.endswith('krouter_run.py"')
    assert "krouter.cli" not in line  # no module call that needs PYTHONPATH


@pytest.mark.parametrize("lang", ["en", "zh"])
@pytest.mark.parametrize("windows", [True, False])
def test_printed_doctor_and_ask_are_accepted_by_the_argument_parser(lang, windows, monkeypatch):
    from krouter.cli import build_parser

    mod = _bootstrap()
    line = _printed(mod, lang, windows, monkeypatch)
    monkeypatch.setattr(mod, "WINDOWS", windows)
    prefix = mod.cli_path()
    cmds = _commands(line, prefix)
    assert [c.split(prefix)[1].split()[0] for c in cmds] == ["doctor", "ask"], line
    for c in cmds:
        rest = c.split(prefix, 1)[1]
        args = shlex.split(rest)  # the words the shell hands the program after its name
        ns = build_parser().parse_args(args)  # raises SystemExit on an invalid choice, the old `search`
        assert ns.cmd in ("doctor", "ask")
    assert "search" not in line


def test_the_old_search_is_rejected_by_the_parser():
    from krouter.cli import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(["search", "x"])


def test_launcher_runs_without_pythonpath():
    env = {k: v for k, v in __import__("os").environ.items() if k != "PYTHONPATH"}
    res = subprocess.run([sys.executable, str(REPO / "scripts/krouter_run.py"), "--version"], capture_output=True, text=True,
                         env=env, timeout=60, cwd="/")
    assert res.returncode == 0 and res.stdout.startswith("krouter "), res.stdout + res.stderr
    bad = subprocess.run([sys.executable, str(REPO / "scripts/krouter_run.py"), "search", "x"], capture_output=True, text=True,
                         env=env, timeout=60, cwd="/")
    assert bad.returncode != 0 and "invalid choice" in bad.stderr


def test_posix_line_unchanged_in_shape(monkeypatch):
    mod = _bootstrap()
    line = _printed(mod, "en", False, monkeypatch)
    assert "scripts/krouter doctor" in line.replace("\\", "/") and "&&" not in line
