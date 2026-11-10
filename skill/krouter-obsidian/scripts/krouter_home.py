"""Where the memory folder is, for a caller that was not told: `KROUTER_VAULT`, else `OBSIDIAN_VAULT` (the older name,
still read), else the path the installer recorded. When both are set, `KROUTER_VAULT` wins.

Importing this module (`zones.py` does) carries `KROUTER_VAULT` over to `OBSIDIAN_VAULT`, the name every script and
child process reads, and drops it, so a parent that hands a child another folder in `OBSIDIAN_VAULT` is not overridden.

The one-line install writes the vault path to `~/.config/krouter/vault` (one line; `KROUTER_VAULT_FILE` points
elsewhere), so an agent, the MCP server or a plugin can route without anyone exporting a variable first.
"""

from __future__ import annotations

import os
from pathlib import Path


def adopt_env() -> None:
    """`KROUTER_VAULT` → `OBSIDIAN_VAULT` in this process (and so in its children)."""
    raw = os.environ.pop("KROUTER_VAULT", "").strip()
    if raw:
        os.environ["OBSIDIAN_VAULT"] = raw


adopt_env()


def vault_file() -> Path:
    raw = os.environ.get("KROUTER_VAULT_FILE", "")
    if raw:
        return Path(raw).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "krouter" / "vault"


def vault_path() -> str:
    adopt_env()
    raw = os.environ.get("OBSIDIAN_VAULT", "")
    if raw:
        return raw
    try:
        line = vault_file().read_text(encoding="utf-8").strip().splitlines()[0].strip()
    except (OSError, IndexError):
        return ""
    return str(Path(line).expanduser()) if line else ""


def remember(vault: Path) -> Path:
    path = vault_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(vault) + "\n", encoding="utf-8")
    return path


_ROOTS: dict[str, str] = {}


def project_root(cwd: str) -> str:
    """Which project a working directory belongs to: its git top level when it is in a repo, else the directory
    itself, as an absolute path. A folder name alone (`api`, `web`, `app`) is shared by unrelated repos and customers,
    so it never identifies a project. Empty when there is no cwd."""
    if not cwd:
        return ""
    if cwd in _ROOTS:
        return _ROOTS[cwd]
    import subprocess

    path = Path(cwd).expanduser()
    try:
        path = path.resolve()
    except OSError:
        pass
    root = str(path)
    if path.is_dir():
        try:
            out = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"], capture_output=True,
                                 text=True, timeout=5)
            if out.returncode == 0 and out.stdout.strip():
                root = str(Path(out.stdout.strip()).resolve())
        except (OSError, subprocess.TimeoutExpired):
            pass
    root = root.replace("\\", "/").rstrip("/") or "/"
    if os.name == "nt":
        root = root.lower()  # Windows 路径不区分大小写
    _ROOTS[cwd] = root
    return root
