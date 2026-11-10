"""`krouter doctor`: one verdict on this machine's KRouter — OK, or what is missing and the command that fixes it.

Reads only: the recorded vault, its health page, the apps' settings files, the nightly job's file. Runs one local
lookup to prove the router answers. Calls no model and nothing on the network. Exit 0 when lookup works (notes are
things that are off by choice or need a model), 1 when something is broken.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import ask, router_dir


def _vault(explicit: str | None) -> Path | None:
    raw = explicit or os.environ.get("OBSIDIAN_VAULT", "")
    if not raw:
        vf = Path(os.environ.get("KROUTER_VAULT_FILE") or Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
                  / "krouter" / "vault")
        try:
            raw = vf.read_text(encoding="utf-8").splitlines()[0].strip()
        except (OSError, IndexError):
            raw = ""
    return Path(raw).expanduser() if raw else None


def _frontmatter(page: Path) -> dict:
    try:
        text = page.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    out = {}
    for line in text.split("---", 2)[1].splitlines():
        key, sep, val = line.partition(":")
        if sep:
            out[key.strip()] = val.strip().strip('"')
    return out


def _json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _apps() -> list[str]:
    """Where KRouter is connected: MCP entries the installer writes, and the Claude Code plugin."""
    home = Path.home()
    found = []
    if "krouter" in (_json(home / ".claude.json").get("mcpServers") or {}):
        found.append("Claude Code (MCP)")
    if (_json(home / ".claude/settings.json").get("enabledPlugins") or {}).get("krouter@krouter"):
        found.append("Claude Code plugin")
    codex = Path(os.environ.get("CODEX_HOME") or home / ".codex") / "config.toml"
    try:
        if "[mcp_servers.krouter]" in codex.read_text(encoding="utf-8"):
            found.append("Codex (MCP)")
    except OSError:
        pass
    if sys.platform == "darwin":
        desktop = home / "Library/Application Support/Claude/claude_desktop_config.json"
    elif os.name == "nt":
        desktop = Path(os.environ.get("APPDATA", "")) / "Claude/claude_desktop_config.json"
    else:
        desktop = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "Claude/claude_desktop_config.json"
    for name, path, key in (("Claude Desktop", desktop, "mcpServers"), ("Cursor", home / ".cursor/mcp.json", "mcpServers"),
                            ("Gemini CLI", home / ".gemini/settings.json", "mcpServers")):
        if "krouter" in (_json(path).get(key) or {}):
            found.append(name)
    return found


def _nightly_installed() -> bool:
    home = Path.home()
    if (home / "Library/LaunchAgents/local.dsh-krouter.daily-evolution.plist").is_file():
        return True
    if (home / ".config/systemd/user/dsh-krouter-daily.timer").is_file():
        return True
    if os.name == "nt":
        res = subprocess.run(["schtasks", "/Query", "/TN", "KRouter daily evolution"], capture_output=True, text=True)
        return res.returncode == 0
    if sys.platform.startswith("linux") and shutil.which("crontab"):  # install.sh 只在 Linux 上用 crontab
        res = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        return "# dsh-krouter-daily" in (res.stdout or "")
    return False


def _bootstrap() -> str:
    """The installer to name in a fix: the downloaded release's, else this repository's."""
    for cand in (Path(os.environ.get("KROUTER_HOME") or Path.home() / ".dsh-krouter") / "current/scripts/bootstrap.py",
                 Path(__file__).resolve().parents[2] / "scripts/bootstrap.py"):
        if cand.is_file():
            return f'python3 "{cand}"'
    return "the one-line install in the README"


def run(vault_arg: str | None = None) -> int:
    rows: list[tuple[str, str]] = []  # (ok | note | FAIL, text)
    if sys.version_info < (3, 9):
        rows.append(("FAIL", f"python: {sys.version.split()[0]}; KRouter needs 3.9 or newer"))
    sys.path.insert(0, str(router_dir()))
    import zones

    vault = _vault(vault_arg)
    boot = _bootstrap()
    if vault is None:
        rows.append(("FAIL", f"vault: none recorded. Fix: {boot} (or pass --vault, or set OBSIDIAN_VAULT)"))
    elif not vault.is_dir():
        rows.append(("FAIL", f"vault: {vault} does not exist. Fix: {boot} --vault <your folder>"))
    else:
        layout = "English names" if zones.lang(vault) == "en" else "default names"
        rows.append(("ok", f"vault: {vault} ({layout})"))
        home = zones.path(vault, "Agent第二大脑.md")
        if not home.is_file():
            rows.append(("FAIL", f"home page missing: {home}. Fix: {boot} --vault \"{vault}\" (adds only missing files)"))
        start = time.time()
        os.environ["KROUTER_NO_QUERY_LOG"] = "1"  # 自检不是真问题：不进夜间学习读的查询日志
        try:
            a = ask("home", vault=vault)
            took = time.time() - start
            if a.page or a.refused:
                rows.append(("ok", f"lookup: answered in {took:.2f} s" + (f" from {a.page}" if a.page else " (said: not in the vault)")))
            else:
                rows.append(("FAIL", "lookup: no receipt came back. Fix: reinstall with " + boot))
        except Exception as exc:  # noqa: BLE001 - 查询失败本身就是要报的结论
            rows.append(("FAIL", f"lookup failed: {exc}. Fix: reinstall with {boot}"))
        table = zones.path(vault, "90 系统文件/canonical_sources.psv")
        rows.append(("ok", f"alias table: {table}") if table.is_file() else
                    ("note", f"alias table: none in the vault; the sample one is used. Fix: {boot} --vault \"{vault}\""))
        meta = _frontmatter(zones.path(vault, "90 系统文件/自动化/日更健康.md"))
        key = meta.get("self_evolution_key", "missing")
        if key == "present":  # install.sh 探过：登录了的 CLI 或能用的 key（只装了 CLI、没登录不算）
            rows.append(("ok", "model: connected (distilling and the nightly upkeep can run)"))
        else:
            keys = os.environ.get("KROUTER_KEYS_ENV") or str(Path.home() / ".dsh-krouter-keys.env")
            rows.append(("note", "model: none. Lookup, sources, refusals and the local import work; distilling, the "
                                 "nightly upkeep and settling correction candidates do not, so a changed decision does "
                                 "not replace the old answer on its own. Fix: log in to claude / codex / grok once, or "
                                 f"put an API key in {keys}"))
        installed = _nightly_installed()
        lamp = meta.get("lamp", "")
        if installed:
            rows.append(("ok", "nightly job: installed"))
        elif lamp == "running":
            rows.append(("FAIL", "nightly job: the health page says running, but no job is installed. Fix: "
                                 f"{boot} --timer --vault \"{vault}\", or set lamp: unused on the health page"))
        else:
            rows.append(("note", f"nightly job: not installed (off by default). Turn on: {boot} --timer --vault \"{vault}\""))
    apps = _apps()
    rows.append(("ok", "connected: " + ", ".join(apps)) if apps else
                ("note", f"connected: no app found. Fix: {boot} --apps claude,codex,cursor (or the MCP block in the README)"))
    if not shutil.which("rg"):
        rows.append(("note", "ripgrep: not found; literal search uses the built-in fallback (same answers, slower on "
                             "large vaults)"))
    width = max(len(s) for s, _ in rows)
    print("krouter doctor")
    for state, text in rows:
        print(f"  {state.ljust(width)}  {text}")
    fails = [t for s, t in rows if s == "FAIL"]
    notes = sum(1 for s, _ in rows if s == "note")
    if fails:
        print(f"verdict: NOT OK, {len(fails)} problem{'s' if len(fails) > 1 else ''} (the FAIL lines say how to fix each)")
        return 1
    print("verdict: OK" + (f" ({notes} note{'s' if notes > 1 else ''} above: off by choice, or needs a model)" if notes else ""))
    return 0
