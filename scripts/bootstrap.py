#!/usr/bin/env python3
"""One-step install for anyone: a vault, the router, the daily timer. No terminal knowledge assumed.

Usually started by `bootstrap.sh` (macOS / Linux) or `bootstrap.ps1` (Windows), which find Python and fetch the
latest release; can also be run from a clone. What it does, in order:

1. Pick the language (`--lang zh|en`, default: the system's) and the matching template.
2. Pick the vault: `--vault PATH`, else `OBSIDIAN_VAULT`, else a new folder `Documents/第二大脑` (`Second Brain`).
   A new or empty folder gets the template. An existing vault keeps every file; only missing skeleton files are
   added (`--vault` on a vault of your own). Nothing is ever overwritten.
3. Install the router skill and the agent rules, keeping an existing alias table. Re-running it is an upgrade.
4. Check for a model: a logged-in CLI or an API key. If there is none, say in one sentence what to do.
5. By default that is all: lookup only, no questions, nothing leaves the machine; the last lines say how to turn on
   remembering. `--ask` asks whether to import recent agent sessions (and claude-mem's memory) and whether to install
   the nightly job (launchd / systemd / cron / Windows task); `--import`, `--import-distill` and `--timer` say yes in
   advance. An upgrade where the host said yes before keeps what is on.
6. Open the new vault in Obsidian when Obsidian is installed.

`--dry-run` prints the plan and changes nothing.
"""

from __future__ import annotations

import argparse
import json
import locale
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = os.name == "nt"
MSG = {
    "zh": {
        "plan": "计划", "vault_new": "新建知识库", "vault_merge": "使用已有知识库（只补缺失的骨架文件，不覆盖任何文件）",
        "vault_ours": "已是第二大脑知识库（升级）", "added": "补上的文件", "skill": "路由器", "timer": "每日定时任务",
        "model_ok": "模型通道", "model_none": "还没有可用的模型：登录一个 AI 编程工具（Claude Code 运行 `claude`、Codex、grok 等任选其一），"
        "或把 API key 写进 {keys}（一行，如 DEEPSEEK_API_KEY=sk-…）。夜间任务开着的话，之后每晚自动整理，不用再做任何事。",
        "done": "装好了。知识库在：{vault}\nagent 查询走：{router}",
        "obsidian": "已在 Obsidian 里打开这个知识库。", "obsidian_none": "装上 Obsidian（https://obsidian.md）后，选「打开本地仓库」→ {vault}",
        "py_old": "需要 Python 3.9 或更新版本，当前是 {v}。",
        "ask": "要开启每晚自动整理吗？开启后每天 09:10：{lane}整理昨天的记录{perm}；并把 {pages} 页规则页和主题页（约 {tokens} token）发给它，预先算好常见问题的答案。之后随时可以用 uninstall.sh 关掉。开启？[y/N] ",
        "lane_cli": "用 {cli} ", "lane_key": "用你的 API key ", "lane_none": "（等你登录一个 AI 编程工具或贴好 key 之后）",
        "perm_grok": "（在内核沙箱里运行：只能读写这个知识库、运行路由器，读不到你账户里的其他文件，包括 key 文件）",
        "perm_claude": "（只允许读写这个知识库、运行路由器，不能执行别的命令，也不能上网抓网页；但没有内核沙箱）",
        "perm_codex": "（在 Codex 沙箱里运行：只能写这个知识库，但读得到你账户里的文件，包括 key 文件）",
        "perm_key": "（直接调用 API，不在本机运行任何 agent）",
        "perm_other": "（不受限制：它以你的身份运行，能读写你账户里的任何文件）",
        "prefer_key": "更稳妥的是用 API key：它直接调用接口，不在本机运行任何 agent（把 key 贴到知识库的「自进化钥匙」页就行）。\n",
        "timer_off": "没有开启每晚自动整理。想开的时候运行：{cmd}",
        "timer_skip_noninteractive": "不是在交互终端里运行，所以没有开启每晚自动整理（需要你明确同意）。想开的时候运行：{cmd}",
        "lookup_only": "装的是只查询的版本：不导入会话、不装夜间任务，没有任何内容离开这台机器。\n"
        "想让它开始记住你和 agent 定下的事（会先问你、先说清发出多少字），运行：{cmd}",
        "import_ask": "要把本机已有的 agent 会话导进知识库吗？找到近 7 天 {agents} 的 {sessions} 个会话、{turns} 轮。"
        "只留你的提问和每轮最后的回答，先脱敏，只写在本机这个库里，不发给任何模型；以后每晚也导入前一天的。导入？[y/N] ",
        "distill_ask": "再让 {lane} 把最近 {n} 个会话「定了什么、改了什么」提炼出来吗？会发出约 {chars} 字（已脱敏），"
        "需要几分钟；以后每晚只提炼前一天的。提炼？[y/N] ",
        "import_none": "本机没找到近 7 天的 Claude Code / Codex 会话，跳过导入。",
        "import_off": "没有导入会话。想导的时候运行：{cmd}",
        "import_done": "导入了 {pages} 页会话摘录（{folder}）{distilled}。",
        "distilled": "，其中 {n} 个会话已提炼出定下来的事",
        "distilling": "正在提炼（每个会话一次模型调用）…",
        "try": "现在就可以问你的 agent，比如：「{q}」——它会先查这个库，答案带出处页；库里没有的会直说没有。",
        "mcp": "已把 KRouter 注册成 {cli} 的 MCP 工具（krouter_ask）。",
        "mcp_desktop": "已把 KRouter 加进 Claude Desktop 的 MCP 设置（重启 Claude Desktop 后生效）。",
        "mcp_app": "已把 KRouter 加进 {app} 的 MCP 设置（{file}；重启 {app} 后生效）。",
        "mcp_app_skip": "{app} 的设置文件 {file} 不是纯 JSON（可能带注释），没动它；要接上，把 krouter 这一项手动加进 {key}。",
        "cmem_ask": "发现 claude-mem 的记忆库：{sessions} 个会话、{decisions} 条决定和改动（{projects} 个项目）。要导进知识库吗？"
        "只读它的库、不改 claude-mem，脱敏后写在本机{distill}；以后每晚同步一次。导入？[y/N] ",
        "cmem_distill": "，并让模型把每个项目的决定理一遍：哪些还有效、哪些被后来的取代了（约 {chars} 字）",
        "cmem_done": "从 claude-mem 导入了 {sessions} 个会话、{decisions} 条决定和改动{distilled}。",
        "cmem_distilled": "，{n} 个项目已理出现在有效的决定",
        "plugin_done": "已装上 Claude Code 插件（来自这份校验过的发布包）：会话结束时自动记下，开新会话时带上本项目的决定，你当场纠正的话也会记下。",
        "capture_on": "从现在起它自己记：{how}。只写进本机这个库，先脱敏，不调任何模型。某个会话不想记，在提问里写 #不记；"
        "整个停掉：{revoke}；这次导入的每一页都记在 90 系统文件/自动化/记忆变更记录.md，按里面的 run 编号可以撤回。",
        "capture_how_plugin": "Claude Code 的每个会话结束时记下",
        "capture_how_live": "{apps} 每轮结束时当场记下",
        "hooks_done": "已把 KRouter 的钩子加进 {app}（{file}）：开会话时带上本项目的决定，每轮结束记下这一轮，你当场纠正的话也会记下。",
        "hooks_skip": "{app} 的钩子文件 {file} 不是纯 JSON，没动它，也就没加上 {app} 的钩子。",
        "hooks_codex_shape": "{file} 的写法这个版本的 Codex 读不了：事件名要放在顶层的 \"hooks\" 下面（Codex 文档的写法），"
        "现在 Codex 会整份跳过它，里面原有的钩子也没在跑。KRouter 没动它，也就没加上 Codex 的钩子。",
        "hooks_codex_trust": "Codex 只跑你信任过的钩子：下次打开 Codex 输入 /hooks，把 KRouter 的 4 个钩子标为信任；信任之前 Codex 不跑它们。",
        "hooks_codex_off": "你在 Codex 的 config.toml 里关了钩子（[features] hooks = false），KRouter 的钩子要等你打开才会跑。",
        "capture_how_nightly": "其他 agent 的会话，打开每晚任务后每晚导入前一天的（{ask}）",
        "plugin_hint": "用 Claude Code 的话，装上插件还能在会话结束时自动记下、开会话时自动带上本项目的决定："
        "/plugin install krouter --marketplace 398894496-arch/KRouter",
    },
    "en": {
        "plan": "Plan", "vault_new": "New vault", "vault_merge": "Existing vault (adds only missing skeleton files; overwrites nothing)",
        "vault_ours": "Already a Second Brain vault (upgrade)", "added": "files added", "skill": "Router", "timer": "Daily timer",
        "model_ok": "Model lane", "model_none": "No model yet: log in to one AI coding CLI (`claude`, Codex, grok, …), "
        "or put an API key in {keys} (one line, e.g. DEEPSEEK_API_KEY=sk-…). With the nightly job on, it then runs every night on its own.",
        "done": "Done. Your vault: {vault}\nAgents query: {router}",
        "obsidian": "Opened the vault in Obsidian.", "obsidian_none": "Install Obsidian (https://obsidian.md), then “Open folder as vault” → {vault}",
        "py_old": "Python 3.9 or newer is required; this is {v}.",
        "ask": "Turn on the nightly upkeep? Every day at 09:10 it will {lane}distill yesterday{perm}, and send {pages} rule and topic pages (about {tokens} tokens) to it to precompute answers. uninstall.sh turns it off any time. Turn on? [y/N] ",
        "lane_cli": "use {cli} to ", "lane_key": "use your API key to ", "lane_none": "(once you log in to an AI coding CLI or paste a key) ",
        "perm_grok": " (in a kernel sandbox: it can read and write only this vault and run the router; nothing else in your account, keys file included)",
        "perm_claude": " (allowed only to read and write this vault and run the router: no other command, no web fetch; but no kernel sandbox)",
        "perm_codex": " (in Codex's sandbox: it writes only this vault but can read files in your account, keys file included)",
        "perm_key": " (a direct API call; no agent runs on this machine)",
        "perm_other": " (unconfined: it runs as you and can read and write any file in your account)",
        "prefer_key": "The safer choice is an API key: a direct API call, no agent runs on this machine (paste it on the vault's key page).\n",
        "timer_off": "Nightly upkeep is off. To turn it on later: {cmd}",
        "timer_skip_noninteractive": "Not run from an interactive terminal, so the nightly upkeep was not turned on (it needs your yes). To turn it on: {cmd}",
        "lookup_only": "Installed for lookup only: no session import, no nightly job, nothing leaves this machine.\n"
        "To have it start remembering what you and your agents decide (it asks first and says how much it sends): {cmd}",
        "import_ask": "Import the agent sessions already on this machine? Found {sessions} sessions ({turns} turns) from {agents} "
        "in the last 7 days. Only your questions and each turn's closing answer are kept, redacted, written to this vault "
        "on this machine, and sent to no model; each night it imports the previous day too. Import? [y/N] ",
        "distill_ask": "Also have {lane} pull out what was decided and what changed in the latest {n} sessions? It sends about "
        "{chars} characters (redacted) and takes a few minutes; after that only the previous day, each night. Distill? [y/N] ",
        "import_none": "No Claude Code / Codex sessions from the last 7 days on this machine; nothing to import.",
        "import_off": "Sessions were not imported. To import them later: {cmd}",
        "import_done": "Imported {pages} session excerpt pages ({folder}){distilled}.",
        "distilled": "; {n} sessions distilled into what was decided",
        "distilling": "Distilling (one model call per session) …",
        "try": "Ask your agent now, for example: \"{q}\" — it checks this vault first and cites the page; what the vault "
        "does not hold, it says so.",
        "mcp": "Registered KRouter as an MCP tool for {cli} (krouter_ask).",
        "mcp_desktop": "Added KRouter to Claude Desktop's MCP settings (restart Claude Desktop to load it).",
        "mcp_app": "Added KRouter to {app}'s MCP settings ({file}; restart {app} to load it).",
        "mcp_app_skip": "{app}'s settings file {file} is not plain JSON (comments?), so it was left alone; to connect it, add the krouter entry under {key} by hand.",
        "cmem_ask": "Found a claude-mem memory: {sessions} sessions, {decisions} decisions and changes ({projects} projects). Import it? "
        "It is read only (claude-mem is not changed), redacted, written on this machine{distill}, then synced nightly. "
        "Import? [y/N] ",
        "cmem_distill": ", and the model sorts each project's decisions into still in force and replaced (about {chars} characters)",
        "cmem_done": "Imported {sessions} sessions and {decisions} decisions and changes from claude-mem{distilled}.",
        "cmem_distilled": "; {n} projects sorted into the decisions in force",
        "plugin_done": "Installed the Claude Code plugin (from this checksummed release): each session is recorded when it ends, a new one starts with this project's decisions, and a correction you type is noted on the spot.",
        "capture_on": "From now on it keeps up by itself: {how}. Written only to this vault on this machine, redacted, no model "
        "called. To keep a session out, put #nocapture in a question; to stop it: {revoke}; every page this import wrote is "
        "listed in 90 系统文件/自动化/记忆变更记录.md, and its run number takes it back.",
        "capture_how_plugin": "each Claude Code session when it ends",
        "capture_how_live": "each turn in {apps}, as it ends",
        "hooks_done": "Added KRouter's hooks to {app} ({file}): a session starts with this project's decisions, each turn is recorded as it ends, and a correction you type is noted on the spot.",
        "hooks_skip": "{app}'s hooks file {file} is not plain JSON, so it was left alone and {app} got no KRouter hooks.",
        "hooks_codex_shape": "{file} is not in the shape this Codex reads: event names belong under a top-level \"hooks\" key (as Codex's docs show), "
        "so Codex skips the whole file and the hooks already in it are not running. KRouter left it alone and added no Codex hooks.",
        "hooks_codex_trust": "Codex runs only hooks you have trusted: next time you open Codex, type /hooks and trust KRouter's 4 hooks; until then Codex skips them.",
        "hooks_codex_off": "Hooks are turned off in Codex's config.toml ([features] hooks = false); KRouter's hooks run once you turn them back on.",
        "capture_how_nightly": "other agents' sessions each night once the nightly job is on ({ask})",
        "plugin_hint": "On Claude Code, the plugin also records each session when it ends and brings this project's "
        "decisions when one starts: /plugin install krouter --marketplace 398894496-arch/KRouter",
    },
}
KEEP = ("canonical_sources.psv", "canonical_alias_ledger.jsonl")


def system_lang() -> str:
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        if os.environ.get(var, "").lower().startswith("zh"):
            return "zh"
    if platform.system() == "Darwin":
        try:
            out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True, text=True, timeout=5).stdout
            first = next((ln.strip(' ",()') for ln in out.splitlines() if ln.strip(' ",()')), "")
            return "zh" if first.lower().startswith("zh") else "en"
        except (OSError, subprocess.TimeoutExpired):
            pass
    if WINDOWS:
        try:
            import ctypes

            return "zh" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x04 else "en"
        except (AttributeError, OSError):
            pass
    loc = (locale.getlocale()[0] or "").lower()
    return "zh" if loc.startswith(("zh", "chinese")) else "en"


def template_for(lang: str) -> Path:
    zh = ROOT / "template-zh"
    return zh if lang == "zh" and zh.is_dir() else ROOT / "template"


def default_vault(lang: str) -> Path:
    return Path.home() / "Documents" / ("第二大脑" if lang == "zh" else "Second Brain")


def vault_state(vault: Path) -> str:
    if not vault.exists() or (vault.is_dir() and not any(p for p in vault.iterdir() if p.name != ".DS_Store")):
        return "new"
    if (vault / "Agent第二大脑.md").is_file() or (vault / "krouter-zones.psv").is_file() \
            or (vault / "90 系统文件" / "自动化" / "日更健康.md").is_file():
        return "ours"
    return "merge"


def lay_down(template: Path, vault: Path, dry: bool) -> list[str]:
    """Copy template files that are missing in the vault. Never overwrites."""
    added = []
    for src in sorted(template.rglob("*")):
        if not src.is_file() or src.name == ".DS_Store":
            continue
        rel = src.relative_to(template)
        dst = vault / rel
        if dst.exists():
            continue
        added.append(rel.as_posix())
        if not dry:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    return added


def install_posix(vault: Path, dry: bool) -> int:
    skill = Path(os.environ.get("KROUTER_SKILL_HOME") or Path.home() / ".agents/skills/krouter-obsidian")
    argv = ["/bin/sh", str(ROOT / "scripts/install.sh")] + (["--upgrade"] if skill.exists() else [])
    if dry:
        print("  " + " ".join(argv))
        return 0
    return subprocess.run(argv, env={**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_BOOTSTRAP": "1"}).returncode


def install_windows(vault: Path, dry: bool, timer: bool) -> int:
    """install.sh, for Windows: skill (keeping the alias table), agent rules, alias table into the vault, timer."""
    home = Path.home()
    skill = Path(os.environ.get("KROUTER_SKILL_HOME") or home / ".agents/skills/krouter-obsidian")
    rules = Path(os.environ.get("KROUTER_CURSOR_RULE") or home / ".cursor/rules/krouter-obsidian.mdc")
    ask = Path(os.environ.get("KROUTER_ASK_RULE") or home / ".cursor/rules/ask-product.mdc")
    if dry:
        print(f"  copy skill → {skill}\n  rules → {rules.parent}\n  timer: {'scheduled task' if timer else 'skipped'}")
        return 0
    kept = {}
    for name in KEEP:
        p = skill / "scripts" / name
        if p.is_file():
            kept[name] = p.read_bytes()
    if skill.exists():
        shutil.rmtree(skill)
    shutil.copytree(ROOT / "skill/krouter-obsidian", skill)
    for name, data in kept.items():
        (skill / "scripts" / name).write_bytes(data)
    rules.parent.mkdir(parents=True, exist_ok=True)
    ask.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "extras/cursor/krouter-obsidian.mdc", rules)
    shutil.copy2(ROOT / "extras/cursor/ask-product.mdc", ask)
    table = vault / "90 系统文件" / "canonical_sources.psv"
    if not table.exists() and (vault / "90 系统文件").is_dir():
        old = kept.get("canonical_sources.psv")
        sample = (ROOT / "skill/krouter-obsidian/scripts/canonical_sources.psv").read_bytes()
        table.write_bytes(old if old and old != sample else sample)
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault)}
    subprocess.run([sys.executable, str(ROOT / "extras/host-daily-evolution/resolve.py"), "--sync-health", "--offline"],
                   env=env, capture_output=True)
    if timer:
        ps = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts/install_windows_task.ps1"),
              "-Vault", str(vault), "-Python", sys.executable]
        res = subprocess.run(ps, env=env, capture_output=True, text=True)
        print((res.stdout or res.stderr).strip())
        return res.returncode
    return 0


def model_lane(vault: Path) -> str:
    """The lane the writer would really use: keys are probed, CLIs must be logged in (resolve.py --status)."""
    res = subprocess.run([sys.executable, str(ROOT / "extras/host-daily-evolution/resolve.py"), "--status"],
                         env={**os.environ, "OBSIDIAN_VAULT": str(vault)}, capture_output=True, text=True, timeout=180)
    try:
        st = json.loads(res.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return ""
    if st.get("lane") == "cli-login":
        return f"{Path(st.get('writer_path') or '').name or st.get('kind')} (CLI)"
    if st.get("lane") == "api-key":
        return "API key"
    return ""


def ask_tty(prompt: str) -> str | None:
    """Ask on the terminal even when stdin is the piped install script (`curl … | sh`). None: no terminal."""
    if os.environ.get("KROUTER_NO_PROMPT") == "1":
        return None
    if WINDOWS:
        if not sys.stdin or not sys.stdin.isatty():
            return None
        try:
            return input(prompt)
        except EOFError:
            return None
    try:
        with open("/dev/tty", "r+", encoding="utf-8") as tty:
            tty.write(prompt)
            tty.flush()
            return tty.readline()
    except OSError:
        return None


def nightly_preview(vault: Path) -> tuple[str, str, int, int]:
    """(lane kind, CLI name, pages that would be sent, est tokens) — from resolve --status and nightly --dry-run."""
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_NO_QUERY_LOG": "1"}
    kind, cli = "", ""
    res = subprocess.run([sys.executable, str(ROOT / "extras/host-daily-evolution/resolve.py"), "--status"], env=env,
                         capture_output=True, text=True, timeout=180)
    try:
        st = json.loads(res.stdout.strip().splitlines()[-1])
        if st.get("lane") == "cli-login":
            kind, cli = st.get("kind") or "other", Path(st.get("writer_path") or "").name
        elif st.get("lane") == "api-key":
            kind = "key"
    except (ValueError, IndexError):
        pass
    pages = tokens = 0
    dry = subprocess.run([sys.executable, str(ROOT / "skill/krouter-obsidian/scripts/nightly.py"), "--vault", str(vault),
                          "--dry-run"], env=env, capture_output=True, text=True, timeout=600)
    try:
        tokens = int(json.loads(dry.stdout).get("est_tokens_total") or 0)
    except ValueError:
        pass
    cards = subprocess.run([sys.executable, str(ROOT / "skill/krouter-obsidian/scripts/answer_cards.py"), "--vault", str(vault),
                            "--dry-run"], env=env, capture_output=True, text=True, timeout=600)
    try:
        pages = len(json.loads(cards.stdout.strip().splitlines()[-1]).get("would_send_pages") or [])
    except (ValueError, IndexError):
        pass
    return kind, cli, pages, tokens


def decide_timer(args: argparse.Namespace, vault: Path, t: dict) -> tuple[bool, bool]:
    """(install it, the host was asked). The nightly job runs a model with wide permissions and sends vault text:
    it is installed only on an explicit yes — `--timer`, or `y` at the prompt. No terminal to ask on: not installed."""
    if args.timer:
        return True, True
    if args.no_timer or not args.ask:
        return False, True
    kind, cli, pages, tokens = nightly_preview(vault)
    lane = t["lane_cli"].format(cli=cli) if kind not in ("", "key") else (t["lane_key"] if kind == "key" else t["lane_none"])
    perm = t.get(f"perm_{kind}", t["perm_other"]) if kind else ""
    prompt = (t["prefer_key"] if kind not in ("", "key") else "") + t["ask"].format(lane=lane, perm=perm, pages=pages, tokens=tokens)
    answer = ask_tty(prompt)
    if answer is None:
        return False, False
    return answer.strip().lower() in {"y", "yes", "是", "好", "开"}, True


IMPORT = ROOT / "skill/krouter-obsidian/scripts/import_sessions.py"


def capture_consented() -> bool:
    """The host said yes to importing sessions (the hooks do nothing before that, so they are only wired after it:
    no "trust these hooks" prompt in Codex for hooks that would not run)."""
    try:
        sys.path.insert(0, str(IMPORT.parent))
        import import_sessions

        return bool(import_sessions.load_state().get("consent"))
    except Exception:  # noqa: BLE001
        return False


def remembering_already() -> bool:
    """An upgrade where the host said yes before (session import consent, or a nightly job on disk)."""
    try:
        sys.path.insert(0, str(IMPORT.parent))
        import import_sessions

        if import_sessions.load_state().get("consent"):
            return True
    except Exception:  # noqa: BLE001 - 读不到旧状态就当没开过，只影响要不要多打印一行提示
        pass
    if WINDOWS:
        res = subprocess.run(["schtasks", "/Query", "/TN", "KRouter daily evolution"], capture_output=True, text=True)
        return res.returncode == 0
    home = Path.home()
    if (home / "Library/LaunchAgents/local.dsh-krouter.daily-evolution.plist").is_file():
        return True
    if (home / ".config/systemd/user/dsh-krouter-daily.timer").is_file():
        return True
    res = subprocess.run(["crontab", "-l"], capture_output=True, text=True) if shutil.which("crontab") else None
    return bool(res and "# dsh-krouter-daily" in res.stdout)
DISTILL_AT_INSTALL = 8  # 安装时只提炼最近几个会话，免得一装就等十几分钟


def run_import(vault: Path, *extra: str) -> dict:
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_NO_QUERY_LOG": "1"}
    res = subprocess.run([sys.executable, str(IMPORT), "--vault", str(vault), *extra], env=env, capture_output=True,
                         text=True, timeout=3600)
    try:
        return json.loads(res.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {}


def decide_import(args: argparse.Namespace, vault: Path, t: dict, lane_kind: str) -> tuple[bool, bool, bool]:
    """(import, distill, worth saying how to do it later). Copying chat text into the vault, and sending it to a
    model, each need a yes: a flag, or `y` at the prompt. No terminal to ask on: nothing is imported."""
    if args.no_import or os.environ.get("KROUTER_NO_IMPORT") == "1":
        return False, False, False
    if not (args.ask or args.import_sessions or args.import_distill):
        # 默认就记（像 claude-mem 一样装完就开始）：只在本机导入、脱敏、不调模型；记下同意，之后的会话钩子才会工作
        return True, False, False
    preview = run_import(vault, "--dry-run")
    if not preview.get("pages"):
        print(t["import_none"])
        return False, False, False
    if args.import_sessions or args.import_distill:
        return True, bool(args.import_distill and lane_kind), False
    answer = ask_tty(t["import_ask"].format(sessions=preview["sessions"], turns=preview["turns"],
                                            agents=" / ".join(preview.get("agents") or [])))
    if answer is None or answer.strip().lower() not in {"y", "yes", "是", "好", "导"}:
        return False, False, True
    if not lane_kind:
        return True, False, False
    est = run_import(vault, "--dry-run", "--distill", "--distill-max", str(DISTILL_AT_INSTALL))
    lane = "your API key" if lane_kind == "key" else lane_kind
    answer = ask_tty(t["distill_ask"].format(lane=lane, n=est.get("distilled") or DISTILL_AT_INSTALL,
                                             chars=est.get("chars") or 0))
    return True, bool(answer and answer.strip().lower() in {"y", "yes", "是", "好"}), False


CLAUDE_MEM = ROOT / "skill/krouter-obsidian/scripts/import_claude_mem.py"


def run_claude_mem(vault: Path, *extra: str) -> dict:
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_NO_QUERY_LOG": "1"}
    res = subprocess.run([sys.executable, str(CLAUDE_MEM), "--vault", str(vault), *extra], env=env,
                         capture_output=True, text=True, timeout=3600)
    try:
        return json.loads(res.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {}


def offer_claude_mem(args: argparse.Namespace, vault: Path, t: dict, distill: bool) -> dict:
    """claude-mem users already have a memory: offer to bring it in. Same rule as the sessions — a yes or a flag."""
    if args.no_import or os.environ.get("KROUTER_NO_IMPORT") == "1":
        return {}
    preview = run_claude_mem(vault, "--dry-run", *(["--distill"] if distill else []))
    if preview.get("claude_mem") != "dry-run" or not preview.get("sessions"):
        return {}
    if args.ask and not (args.import_sessions or args.import_distill):
        note = t["cmem_distill"].format(chars=preview.get("chars") or 0) if distill else ""
        answer = ask_tty(t["cmem_ask"].format(sessions=preview["sessions"], decisions=preview.get("decisions", 0),
                                              projects=preview.get("projects", 0), distill=note))
        if not answer or answer.strip().lower() not in {"y", "yes", "是", "好", "导"}:
            return {}
    out = run_claude_mem(vault, "--consent", *(["--distill"] if distill else []))
    n = out.get("distilled") or 0
    print(t["cmem_done"].format(sessions=out.get("sessions", 0), decisions=out.get("decisions", 0),
                                distilled=t["cmem_distilled"].format(n=n) if n else ""))
    return out


def try_question(vault: Path, lang: str) -> str:
    """A question this vault can answer now: the latest distilled session's first decision, else its title."""
    folder = vault / "05 时间日志" / "会话摘录"
    pages = sorted(folder.glob("*.md")) if folder.is_dir() else []  # 文件名以日期开头：最后一个是最近的会话
    for page in reversed(pages):
        head = page.read_text(encoding="utf-8")[:1500]
        title = next((ln[7:].strip() for ln in head.splitlines() if ln.startswith("title: ")), "")
        if "digest_turns:" in head and title:
            return f"{title}那次最后定了什么？" if lang == "zh" else f"What did we decide in {title}?"
    if pages:
        title = next((ln[7:].strip() for ln in pages[-1].read_text(encoding="utf-8")[:1500].splitlines()
                      if ln.startswith("title: ")), "")
        if title:
            return f"{title}那次我们聊到哪了？" if lang == "zh" else f"Where did we leave {title}?"
    return "我们之前定过什么规矩？" if lang == "zh" else "What rules have we set before?"


def app_settings(*parts: str) -> Path:
    """Where desktop apps keep their settings: Application Support on macOS, %APPDATA% on Windows, ~/.config elsewhere."""
    if platform.system() == "Darwin":
        base = Path.home() / "Library/Application Support"
    elif WINDOWS:
        base = Path(os.environ.get("APPDATA", ""))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base.joinpath(*parts)


def _zed_dir() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Zed" if WINDOWS else Path(
        os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "zed"


def _plain(cmd: str, args: list[str]) -> dict:
    return {"command": cmd, "args": args}


# 安装脚本自动接上的应用：名字、应用装了才会有的文件夹、MCP 设置文件、放服务器的键、条目写法。
# 格式照各家官方文档（2026-11-09 核对）；文档对不上或版本间格式不同的（opencode、Windsurf）不自动写。
MCP_APPS = (
    {"id": "claude-desktop", "name": "Claude Desktop", "dir": lambda: app_settings("Claude"),
     "file": lambda: app_settings("Claude", "claude_desktop_config.json"), "key": "mcpServers", "entry": _plain},
    # Cursor：看应用自己的设置目录；~/.cursor 不算数（install.sh 放规则时自己会建它）
    {"id": "cursor", "name": "Cursor", "dir": lambda: app_settings("Cursor"),
     "file": lambda: Path.home() / ".cursor" / "mcp.json", "key": "mcpServers", "entry": _plain},
    {"id": "vscode", "name": "VS Code", "dir": lambda: app_settings("Code", "User"),
     "file": lambda: app_settings("Code", "User", "mcp.json"), "key": "servers",
     "entry": lambda c, a: {"type": "stdio", "command": c, "args": a}},
    {"id": "copilot-cli", "name": "GitHub Copilot CLI", "dir": lambda: Path(os.environ.get("COPILOT_HOME") or Path.home() / ".copilot"),
     "file": lambda: Path(os.environ.get("COPILOT_HOME") or Path.home() / ".copilot") / "mcp-config.json", "key": "mcpServers",
     "entry": lambda c, a: {"type": "local", "command": c, "args": a, "tools": ["*"]}},
    {"id": "gemini-cli", "name": "Gemini CLI", "dir": lambda: Path.home() / ".gemini",
     "file": lambda: Path.home() / ".gemini" / "settings.json", "key": "mcpServers", "entry": _plain},
    {"id": "kiro", "name": "Kiro", "dir": lambda: Path.home() / ".kiro",
     "file": lambda: Path.home() / ".kiro" / "settings" / "mcp.json", "key": "mcpServers", "entry": _plain},
    {"id": "zed", "name": "Zed", "dir": _zed_dir, "file": lambda: _zed_dir() / "settings.json", "key": "context_servers",
     "entry": lambda c, a: {"command": c, "args": a, "env": {}}},
    # Cline CLI：~/.cline/data/settings/cline_mcp_settings.json（CLINE_MCP_SETTINGS_PATH 可改），文档 2026-11-09 核对；
    # Cline 的 VS Code 扩展文档没写文件位置，不自动写
    {"id": "cline", "name": "Cline CLI", "dir": lambda: Path.home() / ".cline",
     "file": lambda: Path(os.environ.get("CLINE_MCP_SETTINGS_PATH") or Path.home() / ".cline/data/settings/cline_mcp_settings.json"),
     "key": "mcpServers", "entry": lambda c, a: {"command": c, "args": a, "disabled": False}},
)


def app_config(app: dict) -> Path | None:
    """The app's MCP settings file when the app is installed (its folder exists); else None.
    `KROUTER_MCP_CONFIG_<ID>` points it elsewhere (tests; an unusual install)."""
    env = "KROUTER_MCP_CONFIG_" + app["id"].upper().replace("-", "_")
    raw = os.environ.get(env, "") or (os.environ.get("KROUTER_CLAUDE_DESKTOP_CONFIG", "") if app["id"] == "claude-desktop" else "")
    if raw:
        return Path(raw).expanduser()
    return app["file"]() if app["dir"]().is_dir() else None


def claude_desktop_config() -> Path | None:
    """Claude Desktop's MCP settings file, when the app is installed (its settings folder exists); else None."""
    return app_config(MCP_APPS[0])


def register_app(app: dict, server: list[str], dry: bool, t: dict | None = None) -> bool:
    """Add KRouter to one app's MCP settings, keeping everything else in the file. Never touches a file it cannot
    parse, or a `krouter` entry that is not KRouter's mcp_server.py; keeps a copy of the file it changes."""
    cfg = app_config(app)
    if cfg is None:
        return False
    if dry:
        print(f"  {app['name']}: add {app['key']}.krouter to {cfg}")
        return False
    try:
        text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
        data = json.loads(text) if text.strip() else {}
    except (OSError, ValueError):
        if t:
            print(t["mcp_app_skip"].format(app=app["name"], file=cfg, key=app["key"]))
        return False
    if not isinstance(data, dict) or not isinstance(data.get(app["key"], {}), dict):
        return False
    servers = data.setdefault(app["key"], {})
    entry = app["entry"](server[0], server[1:])
    old = servers.get("krouter")
    if old == entry:
        return True
    if old is not None and "mcp_server.py" not in json.dumps(old):
        return False  # 别人的 krouter 条目，不动
    if cfg.exists():
        shutil.copy2(cfg, cfg.with_name(cfg.name + ".krouter-bak"))
    servers["krouter"] = entry
    cfg.parent.mkdir(parents=True, exist_ok=True)
    tmp = cfg.with_name(cfg.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, cfg)
    return True


def unregister_apps(dry: bool) -> list[str]:
    """Take our krouter entry (the one pointing at mcp_server.py) out of every app's MCP settings; keep the rest."""
    gone = []
    for app in MCP_APPS:
        cfg = app_config(app)
        if cfg is None or not cfg.is_file():
            continue
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        servers = data.get(app["key"]) if isinstance(data, dict) else None
        if not isinstance(servers, dict) or "mcp_server.py" not in json.dumps(servers.get("krouter", "")):
            continue
        if dry:
            print(f"would: remove {app['key']}.krouter from {cfg}")
            continue
        servers.pop("krouter")
        tmp = cfg.with_name(cfg.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, cfg)
        print(f"removed: MCP server krouter ({app['name']})")
        gone.append(app["id"])
    return gone


def register_desktop(server: list[str], dry: bool) -> bool:
    return register_app(MCP_APPS[0], server, dry)


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


# 每轮记下来的钩子：Codex 和 Cursor 各自的事件名 → session_hook.py 的动作。格式照各家官方文档，2026-11-09 核对；
# Codex 那份用 codex-cli 0.155 实测过（事件必须放在顶层 "hooks" 下面，否则整份被跳过）。Claude Code 的在插件里。
HOOK_APPS = (
    {"id": "codex", "name": "Codex", "dir": codex_home, "file": lambda: codex_home() / "hooks.json",
     "events": (("SessionStart", "start", 10), ("UserPromptSubmit", "prompt", 10), ("Stop", "turn", 10),
                ("SessionEnd", "end", 3))},  # Codex 的 SessionEnd 最多等 3 秒；导入本身在后台跑
    {"id": "cursor", "name": "Cursor", "dir": lambda: app_settings("Cursor"), "file": lambda: Path.home() / ".cursor" / "hooks.json",
     "events": (("sessionStart", "start", 10), ("beforeSubmitPrompt", "prompt", 10), ("stop", "turn", 10),
                ("sessionEnd", "end", 10))},
)


def hooks_config(app: dict) -> Path | None:
    """The app's hooks file when the app is installed (its folder exists); `KROUTER_HOOKS_CONFIG_<ID>` points it elsewhere."""
    raw = os.environ.get("KROUTER_HOOKS_CONFIG_" + app["id"].upper(), "")
    if raw:
        return Path(raw).expanduser()
    return app["file"]() if app["dir"]().is_dir() else None


def _arg(x: str) -> str:
    if WINDOWS:
        return f'"{x}"' if " " in x else x
    import shlex

    return shlex.quote(x)


def _ours(entry, agent: str) -> bool:
    text = json.dumps(entry, ensure_ascii=False)
    return "session_hook.py" in text and f"--agent {agent}" in text


def _write_json(cfg: Path, data: dict) -> None:
    cfg.parent.mkdir(parents=True, exist_ok=True)
    tmp = cfg.with_name(cfg.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, cfg)


def _drop_ours(hooks: dict, app: dict) -> bool:
    """Take KRouter's entries out of `hooks` (Codex: inside each matcher group); True when something was removed."""
    gone = False
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        keep = []
        for g in groups:
            if app["id"] == "codex" and isinstance(g, dict) and isinstance(g.get("hooks"), list):
                inner = [h for h in g["hooks"] if not _ours(h, "codex")]
                gone |= len(inner) != len(g["hooks"])
                if inner:
                    keep.append({**g, "hooks": inner})
            elif _ours(g, app["id"]):
                gone = True
            else:
                keep.append(g)
        if keep:
            hooks[event] = keep
        else:
            hooks.pop(event)
    return gone


def codex_hooks_off() -> bool:
    try:
        text = (codex_home() / "config.toml").read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        import tomllib  # Python 3.11+

        feats = tomllib.loads(text).get("features") or {}
        return feats.get("hooks", feats.get("codex_hooks", True)) is False
    except ImportError:
        block = re.split(r"(?m)^\s*\[features\]\s*$", text, maxsplit=1)
        return len(block) == 2 and bool(re.search(r"(?m)^\s*(codex_)?hooks\s*=\s*false\b", re.split(r"(?m)^\s*\[", block[1])[0]))
    except ValueError:
        return False


def register_hooks(t: dict, dry: bool) -> list[str]:
    """Add the turn-by-turn hooks to Codex and Cursor when they are installed, keeping every hook already there.
    Never touches a file it cannot parse; keeps a copy of a file it changes; re-running replaces only its own entries."""
    if os.environ.get("KROUTER_NO_HOOKS") == "1":
        return []
    skill = Path(os.environ.get("KROUTER_SKILL_HOME") or Path.home() / ".agents/skills/krouter-obsidian")
    py = sys.executable if WINDOWS else (shutil.which("python3") or sys.executable)
    script = str(skill / "scripts" / "session_hook.py")
    done = []
    for app in HOOK_APPS:
        cfg = hooks_config(app)
        if cfg is None:
            continue
        if dry:
            print(f"  {app['name']}: add KRouter's hooks ({', '.join(e for e, _, _ in app['events'])}) to {cfg}")
            continue
        try:
            text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
            data = json.loads(text) if text.strip() else {}
        except (OSError, ValueError):
            print(t["hooks_skip"].format(app=app["name"], file=cfg))
            continue
        if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
            print(t["hooks_skip"].format(app=app["name"], file=cfg))
            continue
        if app["id"] == "codex" and set(data) - {"hooks", "description"}:
            print(t["hooks_codex_shape"].format(file=cfg))  # 不包 "hooks" 的旧写法：Codex 整份跳过，别替人改
            continue
        before = json.dumps(data, sort_keys=True)
        if app["id"] == "cursor":
            data.setdefault("version", 1)
        hooks = data.setdefault("hooks", {})
        _drop_ours(hooks, app)
        for event, which, timeout in app["events"]:
            cmd = " ".join(_arg(x) for x in (py, script, which, "--agent", app["id"]))
            if app["id"] == "codex":
                entry = {"hooks": [{"type": "command", "command": cmd, "timeout": timeout}]}
            else:
                entry = {"command": cmd, "timeout": timeout}
            hooks.setdefault(event, []).append(entry)
        if json.dumps(data, sort_keys=True) != before:
            if cfg.exists():
                shutil.copy2(cfg, cfg.with_name(cfg.name + ".krouter-bak"))
            _write_json(cfg, data)
        done.append(app["id"])
        print(t["hooks_done"].format(app=app["name"], file=cfg))
        if app["id"] == "codex":
            print(t["hooks_codex_off"] if codex_hooks_off() else t["hooks_codex_trust"])
    return done


def unregister_hooks(dry: bool) -> list[str]:
    """Take KRouter's entries out of Codex's and Cursor's hooks files; keep everything else."""
    gone = []
    for app in HOOK_APPS:
        cfg = hooks_config(app)
        if cfg is None or not cfg.is_file():
            continue
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        hooks = data.get("hooks") if isinstance(data, dict) else None
        if not isinstance(hooks, dict) or not _drop_ours(json.loads(json.dumps(hooks)), app):
            continue
        if dry:
            print(f"would: remove KRouter's hooks from {cfg}")
            continue
        _drop_ours(hooks, app)
        _write_json(cfg, data)
        print(f"removed: KRouter hooks ({app['name']})")
        gone.append(app["id"])
    return gone


def install_plugin(exe: str) -> bool:
    """The Claude Code plugin (session hooks) from this very release, added as a local marketplace, so what installs is
    the checksummed package, not GitHub's `main`. An older Claude Code without `claude plugin` just gets the hint."""
    if os.environ.get("KROUTER_NO_PLUGIN") == "1" or not (ROOT / ".claude-plugin" / "marketplace.json").is_file():
        return False

    def run(*a: str) -> bool:
        return subprocess.run([exe, "plugin", *a], capture_output=True, text=True, timeout=180).returncode == 0

    try:
        if run("install", "krouter@krouter"):  # 已经加过 krouter 市场（GitHub 或本地）就直接装
            return True
        return run("marketplace", "add", str(ROOT)) and run("install", "krouter@krouter")
    except (OSError, subprocess.TimeoutExpired):
        return False


def register_mcp(t: dict, dry: bool) -> list[str]:
    """Register the MCP server with the agent CLIs that are installed (user scope). Re-running is harmless."""
    if os.environ.get("KROUTER_NO_MCP") == "1":
        return []
    skill = Path(os.environ.get("KROUTER_SKILL_HOME") or Path.home() / ".agents/skills/krouter-obsidian")
    # python3 on PATH outlives a versioned interpreter path (a Homebrew upgrade moves python@3.x)
    py = sys.executable if WINDOWS else (shutil.which("python3") or sys.executable)
    server = [py, str(skill / "scripts" / "mcp_server.py")]
    done = []
    for cli, argv in (("claude", ["mcp", "add", "--scope", "user", "krouter", "--"]),
                      ("codex", ["mcp", "add", "krouter", "--"])):
        exe = shutil.which(cli)
        if not exe:
            continue
        if dry:
            print("  " + " ".join([cli, *argv, *server]))
            continue
        if cli == "claude":
            subprocess.run([exe, "mcp", "remove", "--scope", "user", "krouter"], capture_output=True, timeout=60)
        else:
            subprocess.run([exe, "mcp", "remove", "krouter"], capture_output=True, timeout=60)
        try:
            ok = subprocess.run([exe, *argv, *server], capture_output=True, text=True, timeout=60).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        if ok:
            done.append(cli)
            print(t["mcp"].format(cli=cli))
            if cli == "claude" and install_plugin(exe):
                done.append("claude-plugin")
                print(t["plugin_done"])
    for app in MCP_APPS:  # 本机装了哪个就接哪个，和 claude / codex 一样不问
        if register_app(app, server, dry, t):
            done.append(app["id"])
            print(t["mcp_desktop"] if app["id"] == "claude-desktop" else t["mcp_app"].format(app=app["name"], file=app_config(app)))
    return done


def open_in_obsidian(vault: Path) -> bool:
    url = "obsidian://open?path=" + urllib.parse.quote(str(vault))
    try:
        if platform.system() == "Darwin":
            if not (Path("/Applications/Obsidian.app").exists() or (Path.home() / "Applications/Obsidian.app").exists()):
                return False
            return subprocess.run(["open", url], capture_output=True).returncode == 0
        if WINDOWS:
            if not (Path(os.environ.get("APPDATA", "")) / "obsidian").exists():
                return False
            os.startfile(url)  # type: ignore[attr-defined]
            return True
        if shutil.which("xdg-open") and (Path.home() / ".config/obsidian").exists():
            return subprocess.run(["xdg-open", url], capture_output=True).returncode == 0
    except OSError:
        return False
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="One-step install: vault + router + daily timer")
    ap.add_argument("--vault", default="")
    ap.add_argument("--lang", choices=["zh", "en", "auto"], default="auto")
    ap.add_argument("--timer", action="store_true", help="install the nightly job without asking (you have read what it does)")
    ap.add_argument("--no-timer", action="store_true", help="do not install the nightly job, and do not ask")
    ap.add_argument("--no-open", action="store_true", help="do not open the vault in Obsidian")
    ap.add_argument("--import", dest="import_sessions", action="store_true",
                    help="import the last 7 days of agent sessions, and claude-mem's memory if present, without asking (local only)")
    ap.add_argument("--import-distill", action="store_true", help="import, and have the model lane distill the latest sessions")
    ap.add_argument("--no-import", action="store_true", help="do not import agent sessions, and do not ask")
    ap.add_argument("--ask", action="store_true",
                    help="ask before importing sessions, and about distilling and the nightly job (default: import locally without asking, no model, no nightly job)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--unregister-mcp", action="store_true", help=argparse.SUPPRESS)  # uninstall.sh 用
    args = ap.parse_args()
    if args.unregister_mcp:
        unregister_apps(args.dry_run)
        unregister_hooks(args.dry_run)
        return 0
    lang = system_lang() if args.lang == "auto" else args.lang
    t = MSG[lang]
    if sys.version_info < (3, 9):
        print(t["py_old"].format(v=platform.python_version()))
        return 1
    vault = Path(args.vault or os.environ.get("OBSIDIAN_VAULT") or default_vault(lang)).expanduser().resolve()
    state = vault_state(vault)
    template = template_for(lang)
    print(f"{t['plan']}: {t['vault_' + state]} → {vault}")
    added = lay_down(template, vault, args.dry_run)
    if added and state != "new":
        print(f"  {t['added']}: {len(added)}" + "".join(f"\n    {a}" for a in added[:12]) + ("\n    …" if len(added) > 12 else ""))
    os.environ["KROUTER_NO_TIMER"] = "1"  # 先只装只读部分：库、路由、规则；夜间任务等宿主点头再装
    rc = install_windows(vault, args.dry_run, False) if WINDOWS else install_posix(vault, args.dry_run)
    if rc != 0:
        return rc
    if args.dry_run:
        register_mcp(t, True)
        if not args.no_import:
            register_hooks(t, True)
        print("  nightly job: " + ("yes (--timer)" if args.timer else "no (--no-timer)" if args.no_timer
                                   else "asks first (--ask)" if args.ask else "no (--ask to be asked)"))
        print("  session import: " + ("no (--no-import)" if args.no_import else "yes (--import)" if args.import_sessions
                                      else "asks first (--ask)" if args.ask else "yes, local only, no model (--no-import to skip)"))
        return 0
    sys.path.insert(0, str(ROOT / "skill/krouter-obsidian/scripts"))
    from krouter_home import remember

    remember(vault)  # agent、MCP、插件不用先 export OBSIDIAN_VAULT 也找得到这个库
    mcp = register_mcp(t, False)
    os.environ.pop("KROUTER_NO_TIMER", None)
    timer, asked = decide_timer(args, vault, t)
    if timer:
        rc = install_windows(vault, False, True) if WINDOWS else install_posix(vault, False)
        if rc != 0:
            return rc
    elif args.ask:
        cmd = f"{'python' if WINDOWS else 'python3'} \"{ROOT / 'scripts' / 'bootstrap.py'}\" --timer --vault \"{vault}\""
        print((t["timer_off"] if asked else t["timer_skip_noninteractive"]).format(cmd=cmd))
    lane = model_lane(vault)
    keys = os.environ.get("KROUTER_KEYS_ENV") or str(Path.home() / ".dsh-krouter-keys.env")
    print(f"{t['model_ok']}: {lane}" if lane else t["model_none"].format(keys=keys))
    lane_kind = "" if not lane else ("key" if lane == "API key" else lane.split(" ")[0])
    do_import, do_distill, tell_later = decide_import(args, vault, t, lane_kind)
    imported = {}
    hooked: list[str] = []
    if do_import:
        extra = ["--consent"] + (["--distill", "--distill-max", str(DISTILL_AT_INSTALL)] if do_distill else [])
        if do_distill:
            print(t["distilling"])
        imported = run_import(vault, *extra)
        hooked = register_hooks(t, False) if capture_consented() else []
        n = imported.get("distilled") or 0
        if imported.get("pages"):
            print(t["import_done"].format(pages=imported.get("pages", 0), folder="05 时间日志/会话摘录",
                                          distilled=t["distilled"].format(n=n) if n else ""))
        py = "python" if WINDOWS else "python3"
        live = (["Claude Code"] if "claude-plugin" in mcp else []) + [a["name"] for a in HOOK_APPS if a["id"] in hooked]
        how = ([t["capture_how_live"].format(apps=(" / " if lang == "en" else "、").join(live))] if live else []) + (
            [] if timer else [t["capture_how_nightly"].format(ask=f'{py} "{ROOT / "scripts" / "bootstrap.py"}" --ask')])
        print(t["capture_on"].format(how="；".join(how) if lang == "zh" else "; ".join(how),
                                     revoke=f'{py} "{IMPORT}" --revoke'))
    elif tell_later:
        cmd = f"{'python' if WINDOWS else 'python3'} \"{IMPORT}\" --consent --vault \"{vault}\""
        print(t["import_off"].format(cmd=cmd))
    if not do_import and capture_consented():
        hooked = register_hooks(t, False)  # 升级：以前同意过导入，钩子照样接上（换成这一版的路径）
    cmem = offer_claude_mem(args, vault, t, do_distill)
    if not (timer or do_import or args.ask or remembering_already()):
        cmd = f"{'python' if WINDOWS else 'python3'} \"{ROOT / 'scripts' / 'bootstrap.py'}\" --ask --vault \"{vault}\""
        print(t["lookup_only"].format(cmd=cmd))
    if "claude" in mcp and "claude-plugin" not in mcp:
        print(t["plugin_hint"])
    skill = Path(os.environ.get("KROUTER_SKILL_HOME") or Path.home() / ".agents/skills/krouter-obsidian")
    router = skill / "scripts" / ("route_knowledge.py" if WINDOWS else "route_knowledge.sh")
    print(t["done"].format(vault=vault, router=router))
    print(t["try"].format(q=try_question(vault, lang)))
    if state == "new" and not args.no_open:
        print(t["obsidian"] if open_in_obsidian(vault) else t["obsidian_none"].format(vault=vault))
    print(json.dumps({"vault": str(vault), "lang": lang, "state": state, "added": len(added), "model": lane or None,
                      "timer": timer, "imported": imported.get("pages", 0), "distilled": imported.get("distilled", 0),
                      "claude_mem": cmem.get("sessions", 0),
                      "mcp": mcp, "hooks": hooked},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
