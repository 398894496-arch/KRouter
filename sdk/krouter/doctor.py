"""`krouter doctor`: one verdict on this machine's KRouter — OK, or what is missing and the command that fixes it.

Reads only: the recorded vault, its health page, the apps' settings files, the nightly job's file. Runs one local
lookup to prove the router answers. Calls no model and nothing on the network. Exit 0 when lookup works (notes are
things that are off by choice or need a model), 1 when something is broken.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import ask, router_dir


def _vault(explicit: str | None) -> Path | None:
    raw = explicit or os.environ.get("KROUTER_VAULT") or os.environ.get("OBSIDIAN_VAULT", "")
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


LEGACY = "krouter-obsidian"  # 2.0 以前的目录名：~/.agents/skills/krouter-obsidian，仓库里的 skill/krouter-obsidian


def _legacy_configs() -> list[str]:
    """Settings files that still start KRouter from the pre-2.0 path."""
    home = Path.home()
    if sys.platform == "darwin":
        desktop = home / "Library/Application Support/Claude/claude_desktop_config.json"
    elif os.name == "nt":
        desktop = Path(os.environ.get("APPDATA", "")) / "Claude/claude_desktop_config.json"
    else:
        desktop = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "Claude/claude_desktop_config.json"
    codex = Path(os.environ.get("CODEX_HOME") or home / ".codex")
    files = [home / ".claude.json", codex / "config.toml", codex / "hooks.json", home / ".cursor/mcp.json",
             home / ".cursor/hooks.json", home / ".gemini/settings.json", desktop,
             home / "Library/LaunchAgents/local.dsh-krouter.daily-evolution.plist",
             home / ".config/systemd/user/dsh-krouter-daily.service"]
    out = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if f"skills/{LEGACY}/" in text or f"skills\\{LEGACY}\\" in text or f"skill/{LEGACY}/" in text:
            out.append(str(f).replace(str(home), "~", 1))
    return out


def _nightly_installed() -> bool:
    home = Path.home()
    if (home / "Library/LaunchAgents/local.dsh-krouter.daily-evolution.plist").is_file():
        return True
    if (home / ".config/systemd/user/dsh-krouter-daily.timer").is_file():
        return True
    if os.name == "nt":
        try:
            res = subprocess.run(["schtasks", "/Query", "/TN", "KRouter daily evolution"], capture_output=True, text=True,
                                 timeout=30)
        except (OSError, subprocess.SubprocessError):
            return False
        return res.returncode == 0
    if sys.platform.startswith("linux") and shutil.which("crontab"):  # install.sh 只在 Linux 上用 crontab
        try:  # 能找到却不能执行（沙箱）也当没有
            res = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return False
        return "# dsh-krouter-daily" in (res.stdout or "")
    return False


def _desktop_dir() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library/Application Support/Claude"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", "")) / "Claude"
    return Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "Claude"


def _desktop_note(boot: str) -> tuple[str, str] | None:
    """Claude Desktop is installed but KRouter is in neither its settings file nor its extensions. The usual cause:
    the entry was written while the app was open, and the app wrote its old settings back when it quit."""
    d = _desktop_dir()
    cfg = Path(os.environ.get("KROUTER_CLAUDE_DESKTOP_CONFIG") or d / "claude_desktop_config.json")
    if not d.is_dir() and not cfg.exists():
        return None
    if "krouter" in (_json(cfg).get("mcpServers") or {}):
        return ("ok", f"Claude Desktop: connected through {cfg}")
    for man in (d / "Claude Extensions").glob("*/manifest.json"):
        if _json(man).get("name") == "krouter":
            return ("ok", f"Claude Desktop: connected as an extension ({man.parent})")
    vf = Path(os.environ.get("KROUTER_VAULT_FILE") or Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
              / "krouter" / "vault")
    mcpb = vf.parent / "KRouter.mcpb"
    return ("note", "Claude Desktop: installed, but KRouter is in neither its settings file nor its extensions (an "
                    "entry written while the app is open is lost when it quits). Fix: quit Claude Desktop, then "
                    f"{boot} --connect claude-desktop; or double-click "
                    + (str(mcpb) if mcpb.is_file() else "KRouter.mcpb from the release") + " and press Install")


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
        rows.append(("FAIL", f"memory folder: none recorded. Fix: {boot} (or pass --vault, or set KROUTER_VAULT)"))
    elif not vault.is_dir():
        rows.append(("FAIL", f"memory folder: {vault} does not exist. Fix: {boot} --vault <your folder>"))
    else:
        layout = "English names" if zones.lang(vault) == "en" else "default names"
        rows.append(("ok", f"memory folder: {vault} ({layout})"))
        home = zones.path(vault, "Agent第二大脑.md")
        if not home.is_file():
            rows.append(("FAIL", f"home page missing: {home}. Fix: {boot} --vault \"{vault}\" (adds only missing files)"))
        start = time.time()
        os.environ["KROUTER_NO_QUERY_LOG"] = "1"  # 自检不是真问题：不进夜间学习读的查询日志
        try:
            a = ask("home", vault=vault)
            took = time.time() - start
            if a.page or a.refused:
                rows.append(("ok", f"lookup: answered in {took:.2f} s" + (f" from {a.page}" if a.page else " (said: not in the memory)")))
            else:
                rows.append(("FAIL", "lookup: no receipt came back. Fix: reinstall with " + boot))
        except Exception as exc:  # noqa: BLE001 - 查询失败本身就是要报的结论
            rows.append(("FAIL", f"lookup failed: {exc}. Fix: reinstall with {boot}"))
        table = zones.path(vault, "90 系统文件/canonical_sources.psv")
        rows.append(("ok", f"alias table: {table}") if table.is_file() else
                    ("note", f"alias table: none in the memory folder; the sample one is used. Fix: {boot} --vault \"{vault}\""))
        meta = _frontmatter(zones.path(vault, "90 系统文件/自动化/日更健康.md"))
        key = meta.get("self_evolution_key", "missing")
        if key == "present":  # install.sh 探过：登录了的 CLI 或能用的 key（只装了 CLI、没登录不算）
            rows.append(("ok", "model: connected (distilling and the nightly upkeep can run)"))
        else:
            keys = os.environ.get("KROUTER_KEYS_ENV") or str(Path.home() / ".dsh-krouter-keys.env")
            rows.append(("note", "model: none. Lookup, sources, refusals and the local import work, and a change of "
                                 "mind still wins when the newer page says so (listed first, flagged) or the agent "
                                 "records it with krouter_correct; distilling, the nightly upkeep and settling correction "
                                 "candidates do not run, so a change worded another way can leave the old answer first. "
                                 f"Fix: log in to claude / codex / grok once, or put an API key in {keys}"))
        installed = _nightly_installed()
        lamp = meta.get("lamp", "")
        if installed:
            rows.append(("ok", "nightly job: installed"))
        elif lamp == "running":
            rows.append(("FAIL", "nightly job: the health page says running, but no job is installed. Fix: "
                                 f"{boot} --timer --vault \"{vault}\", or set lamp: unused on the health page"))
        else:
            rows.append(("note", f"nightly job: not installed (off by default). Turn on: {boot} --timer --vault \"{vault}\""))
    desk = _desktop_note(boot)
    if desk:
        rows.append(desk)
    old = _legacy_configs()
    if old:
        link = Path.home() / ".agents/skills" / LEGACY
        works = link.is_symlink() and link.exists()
        rows.append(("note" if works else "FAIL",
                     "old path: " + ", ".join(old) + f": KRouter still starts from ~/.agents/skills/{LEGACY} (renamed to "
                     "~/.agents/skills/krouter in 2.0" + ("; the old path is a link to it, so it works for now" if works
                                                          else ", and nothing is there any more") +
                     f"). Fix: {boot} (registers MCP, hooks and the nightly job at the new path)"))
    apps = _apps()
    rows.append(("ok", "connected: " + ", ".join(apps)) if apps else
                ("note", f"connected: no app found. Fix: {boot} --apps claude,codex,cursor (or the MCP block in the README)"))
    if not shutil.which("rg"):
        rows.append(("note", "ripgrep: not found; literal search uses the built-in fallback (same answers, slower on "
                             "large vaults)"))
    zh = vault is not None and vault.is_dir() and zones.lang(vault) == "zh"  # 中文名字的库：结论用中文说
    width = max(len(s) for s, _ in rows)
    print("krouter doctor")
    for state, text in rows:
        print(f"  {state.ljust(width)}  {to_zh(text) if zh else text}")
    fails = [t for s, t in rows if s == "FAIL"]
    notes = sum(1 for s, _ in rows if s == "note")
    if fails:
        print(f"结论：有问题，{len(fails)} 处（FAIL 那几行写了怎么修）" if zh else
              f"verdict: NOT OK, {len(fails)} problem{'s' if len(fails) > 1 else ''} (the FAIL lines say how to fix each)")
        return 1
    if zh:
        print("结论：OK" + (f"（上面 {notes} 条提示：有意关着的，或者要模型才行的）" if notes else ""))
    else:
        print("verdict: OK" + (f" ({notes} note{'s' if notes > 1 else ''} above: off by choice, or needs a model)" if notes else ""))
    return 0


# 中文名字的库里，每一行按同一个意思换成中文；路径、命令原样保留。新加一行英文，记得在这里加一条
ZH = [
    (r"^python: (.+); KRouter needs 3\.9 or newer$", r"Python：\1；KRouter 需要 3.9 或更新版本"),
    (r"^memory folder: none recorded\. Fix: (.+) \(or pass --vault, or set KROUTER_VAULT\)$",
     r"记忆文件夹：没有记录。修复：\1（或者传 --vault，或者设 KROUTER_VAULT）"),
    (r"^memory folder: (.+) does not exist\. Fix: (.+)$", r"记忆文件夹：\1 不存在。修复：\2"),
    (r"^memory folder: (.+) \(default names\)$", r"记忆文件夹：\1（默认的中文名字）"),
    (r"^memory folder: (.+) \(English names\)$", r"记忆文件夹：\1（英文名字）"),
    (r"^home page missing: (.+)\. Fix: (.+) \(adds only missing files\)$", r"首页不见了：\1。修复：\2（只补缺的文件）"),
    (r"^lookup: answered in ([\d.]+) s from (.+)$", r"查询：\1 秒答出，出处 \2"),
    (r"^lookup: answered in ([\d.]+) s \(said: not in the memory\)$", r"查询：\1 秒答出（答的是：库里没有）"),
    (r"^lookup: no receipt came back\. Fix: reinstall with (.+)$", r"查询：没有拿到回执。修复：用 \1 重装"),
    (r"^lookup failed: (.+)\. Fix: reinstall with (.+)$", r"查询出错：\1。修复：用 \2 重装"),
    (r"^alias table: none in the memory folder; the sample one is used\. Fix: (.+)$",
     r"别名表：库里没有，用的是样例那份。修复：\1"),
    (r"^alias table: (.+)$", r"别名表：\1"),
    (r"^model: connected \(distilling and the nightly upkeep can run\)$", r"模型：已接上（提炼和夜间整理能跑）"),
    (r"^model: none\. .*Fix: log in to claude / codex / grok once, or put an API key in (.+)$",
     r"模型：没有。查询、出处、拒答、本地导入都照常；新页写明改了主意时会排在前面并标出来，agent 用 krouter_correct "
     r"当轮落实纠正也照常；提炼、夜间整理和纠正候选的判定不跑，所以换了别的说法的改主意，旧答案仍可能排第一。"
     r"修复：登录一次 claude / codex / grok，或者把 API key 写进 \1"),
    (r"^nightly job: installed$", r"夜间任务：已装"),
    (r"^nightly job: the health page says running, but no job is installed\. Fix: (.+), or set lamp: unused on the health page$",
     r"夜间任务：健康页说在跑，但本机没装任何任务。修复：\1，或者把健康页的 lamp 改成 unused"),
    (r"^nightly job: not installed \(off by default\)\. Turn on: (.+)$", r"夜间任务：没装（默认不装）。要开：\1"),
    (r"^Claude Desktop: connected through (.+)$", r"Claude Desktop：已通过 \1 接上"),
    (r"^Claude Desktop: connected as an extension \((.+)\)$", r"Claude Desktop：已作为扩展接上（\1）"),
    (r"^Claude Desktop: installed, but KRouter is in neither .*Fix: quit Claude Desktop, then (.+) --connect "
     r"claude-desktop; or double-click (.+) and press Install$",
     r"Claude Desktop：装了，但它的设置文件和扩展里都没有 KRouter（应用开着时写进去的条目，退出时会被它冲掉）。"
     r"修复：退出 Claude Desktop，再运行 \1 --connect claude-desktop；或者双击 \2，点一次安装"),
    (r"^old path: (.+): KRouter still starts from (\S+) \(renamed to ~/\.agents/skills/krouter in 2\.0; the old path "
     r"is a link to it, so it works for now\)\. Fix: (.+) \(registers MCP, hooks and the nightly job at the new path\)$",
     r"旧路径：\1 还在从 \2 启动 KRouter（2.0 改名为 ~/.agents/skills/krouter；旧路径是指向它的链接，暂时还能用）。"
     r"修复：\3（把 MCP、钩子、夜间任务登记到新路径）"),
    (r"^old path: (.+): KRouter still starts from (\S+) \(renamed to ~/\.agents/skills/krouter in 2\.0, and nothing "
     r"is there any more\)\. Fix: (.+) \(registers MCP, hooks and the nightly job at the new path\)$",
     r"旧路径：\1 还在从 \2 启动 KRouter（2.0 改名为 ~/.agents/skills/krouter，旧路径那里已经什么都没有了）。"
     r"修复：\3（把 MCP、钩子、夜间任务登记到新路径）"),
    (r"^connected: no app found\. Fix: (.+) \(or the MCP block in the README\)$",
     r"已接上：没找到任何应用。修复：\1（或者照 README 里的 MCP 配置手动加）"),
    (r"^connected: (.+)$", r"已接上：\1"),
    (r"^ripgrep: not found; literal search uses the built-in fallback \(same answers, slower on large vaults\)$",
     r"ripgrep：没找到；字面搜索用内置的替代（答案一样，大库上慢一些）"),
]


def to_zh(text: str) -> str:
    """One doctor line in Chinese; a line with no rule stays as it is (so nothing is lost)."""
    for pat, rep in ZH:
        out, n = re.subn(pat, rep, text, flags=re.S)
        if n:
            return out
    return text
