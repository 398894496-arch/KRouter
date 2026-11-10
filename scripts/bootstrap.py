#!/usr/bin/env python3
"""One-step install for anyone: a vault, the router, the daily timer. No terminal knowledge assumed.

Usually started by `bootstrap.sh` (macOS / Linux) or `bootstrap.ps1` (Windows), which find Python and fetch the
latest release; can also be run from a clone. What it does, in order:

1. Pick the language: `--lang zh|en`, else `LC_ALL` / `LC_MESSAGES` / `LANG`, else the system's; and the template.
2. Pick the memory folder: `--vault PATH`, else `KROUTER_VAULT`, else `OBSIDIAN_VAULT` (the older name), else a new folder `Documents/第二大脑` (`Second Brain`).
   A new or empty folder gets the template; in English its folders and files have English names (`zones_en.psv`,
   recorded in the vault's `krouter-zones.psv`). An existing vault keeps every file and its own names; only missing
   skeleton files are added (`--vault` on a vault of your own). Nothing is ever overwritten.
3. Install the router skill and the agent rules, keeping an existing alias table. Re-running it is an upgrade.
4. Check for a model: a logged-in CLI or an API key. If there is none, say in one sentence what to do.
5. Connect the apps it finds (a copy of every settings file it changes is kept as `*.krouter-bak`, and each one is
   listed at the end) and start remembering from now on: turns are recorded as they end, on this machine, redacted,
   no model. Past sessions are not imported by default; the last line says the one command that brings in the last
   7 days. `--all` does that too (the old default); `--no-import` records nothing (lookup only). `--ask` asks about
   importing (and claude-mem's memory), distilling and the nightly job; `--import`, `--import-distill` and `--timer`
   say yes in advance. An upgrade where the host said yes before keeps what is on.
6. Open the new vault in Obsidian when Obsidian is installed and this runs in a terminal (`--open` forces it,
   `--no-open` never); run by an agent, with no terminal, nothing is opened.

`--minimal` installs lookup only: no session import, no nightly job, no Claude Code plugin, no hooks, no Cursor
rules, and only the apps named with `--apps` (none by default). `--dry-run` prints every change and changes nothing.
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
        "plan": "计划", "vault_new": "新建记忆文件夹", "vault_merge": "使用已有的文件夹（只补缺失的骨架文件，不覆盖任何文件）",
        "vault_ours": "已是 KRouter 记忆文件夹（升级）", "added": "补上的文件", "skill": "路由器", "timer": "每日定时任务",
        "model_ok": "模型通道", "model_none": "还没有可用的模型：登录一个 AI 编程工具（Claude Code 运行 `claude`、Codex、grok 等任选其一），"
        "或把 API key 写进 {keys}（一行，如 DEEPSEEK_API_KEY=sk-…）。夜间任务开着的话，之后每晚自动整理，不用再做任何事。\n"
        "没有模型时：查询、带出处的回答、库里没有就直说、本地导入会话、记下纠正候选都照常；改了主意时，新旧两页冲突会把新页排前面并标出来，"
        "你纠正 agent 时它会当轮调 krouter_correct 把旧页标成已取代。不工作的是提炼（每页开头的「定了什么、改了什么」）、夜间整理和纠正候选的判定，"
        "所以换了别的说法、agent 也没当轮落实的改动，旧页仍可能排第一，要等接上模型、提炼过之后才换。",
        "done": "装好了。记忆文件夹在：{vault}\nagent 查询走：{router}",
        "obsidian": "已在 Obsidian 里打开这个记忆文件夹（用任何编辑器打开也一样）。", "obsidian_none": "它就是一个纯 Markdown 文件夹：用任何编辑器打开都行；想用 Obsidian（https://obsidian.md），选「打开本地仓库」→ {vault}",
        "py_old": "需要 Python 3.9 或更新版本，当前是 {v}。",
        "ask": "要开启每晚自动整理吗？开启后每天 09:10：{lane}整理昨天的记录{perm}；并把 {pages} 页规则页和主题页（约 {tokens} token）发给它，预先算好常见问题的答案。之后随时可以用 uninstall.sh 关掉。开启？[y/N] ",
        "lane_cli": "用 {cli} ", "lane_key": "用你的 API key ", "lane_none": "（等你登录一个 AI 编程工具或贴好 key 之后）",
        "perm_grok": "（在内核沙箱里运行：只能读写这个知识库、运行路由器，读不到你账户里的其他文件，包括 key 文件）",
        "perm_claude": "（只允许读写这个知识库、运行路由器，不能执行别的命令，也不能上网抓网页；但没有内核沙箱）",
        "perm_codex": "（在 Codex 沙箱里运行：只能写这个知识库，但读得到你账户里的文件，包括 key 文件）",
        "perm_key": "（直接调用 API，不在本机运行任何 agent）",
        "sub_note": "这会用到你已登录的 {cli} 的订阅额度：每天最多 {n} 次调用，每次记在知识库的「订阅调用记录」页；"
        "KROUTER_HOST_CLI=0 关掉。\n",
        "perm_other": "（不受限制：它以你的身份运行，能读写你账户里的任何文件）",
        "prefer_key": "更稳妥的是用 API key：它直接调用接口，不在本机运行任何 agent（把 key 贴到知识库的「自进化钥匙」页就行）。\n",
        "timer_off": "没有开启每晚自动整理。想开的时候运行：{cmd}",
        "timer_failed": "夜间任务没有装上：这台机器上没有可用的定时器（Linux 要 systemd 用户会话或 crontab）。"
        "没有装任何任务；需要时按 extras/host-daily-evolution/cron.example 手动配置，或在有定时器的机器上重跑 --timer。",
        "timer_skip_noninteractive": "不是在交互终端里运行，所以没有开启每晚自动整理（需要你明确同意）。想开的时候运行：{cmd}",
        "lookup_only": "装的是只查询的版本：不导入会话、不装夜间任务，没有任何内容离开这台机器。\n"
        "想让它开始记住你和 agent 定下的事（会先问你、先说清发出多少字），运行：{cmd}",
        "import_ask": "要把本机已有的 agent 会话导进记忆文件夹吗？找到近 7 天 {agents} 的 {sessions} 个会话、{turns} 轮。"
        "只留你的提问和每轮最后的回答，先脱敏，只写在本机这个记忆文件夹里，不发给任何模型；以后每晚也导入前一天的。导入？[y/N] ",
        "distill_ask": "再让 {lane} 把最近 {n} 个会话「定了什么、改了什么」提炼出来吗？会发出约 {chars} 字（已脱敏），"
        "需要几分钟；以后每晚只提炼前一天的。提炼？[y/N] ",
        "import_none": "本机没找到近 7 天的 Claude Code / Codex 会话，跳过导入。",
        "import_off": "没有导入会话。想导的时候运行：{cmd}",
        "import_done": "导入了 {pages} 页会话摘录（{folder}）{distilled}。",
        "distilled": "，其中 {n} 个会话已提炼出定下来的事",
        "distilling": "正在提炼（每个会话一次模型调用）…",
        "try": "现在就可以问你的 agent，比如：「{q}」——它会先查这个记忆文件夹，答案带出处页；没有的会直说没有。",
        "mcp": "已把 KRouter 注册成 {cli} 的 MCP 工具（krouter_ask）。",
        "mcp_desktop": "已把 KRouter 加进 Claude Desktop 的 MCP 设置（重启 Claude Desktop 后生效）。",
        "mcp_app": "已把 KRouter 加进 {app} 的 MCP 设置（{file}；重启 {app} 后生效）。",
        "mcp_app_skip": "{app} 的设置文件 {file} 不是纯 JSON（可能带注释），没动它；要接上，把 krouter 这一项手动加进 {key}。",
        "cmem_ask": "发现 claude-mem 的记忆库：{sessions} 个会话、{decisions} 条决定和改动（{projects} 个项目）。要导进记忆文件夹吗？"
        "只读它的库、不改 claude-mem，脱敏后写在本机{distill}；以后每晚同步一次。导入？[y/N] ",
        "cmem_distill": "，并让模型把每个项目的决定理一遍：哪些还有效、哪些被后来的取代了（约 {chars} 字）",
        "cmem_done": "从 claude-mem 导入了 {sessions} 个会话、{decisions} 条决定和改动{distilled}。",
        "cmem_distilled": "，{n} 个项目已理出现在有效的决定",
        "plugin_done": "已装上 Claude Code 插件（来自这份校验过的发布包）：会话结束时自动记下，开新会话时带上本项目的决定，你当场纠正的话也会记下。",
        "capture_on": "从现在起它自己记：{how}。只写进本机这个记忆文件夹，先脱敏，不调任何模型。某个会话不想记，在提问里写 #不记；"
        "整个停掉：{revoke}；这次导入的每一页都记在 {ledger}，按里面的 run 编号可以撤回。",
        "capture_how_plugin": "Claude Code 的每个会话结束时记下",
        "capture_how_live": "{apps} 每轮结束时当场记下",
        "hooks_done": "已把 KRouter 的钩子加进 {app}（{file}）：开会话时带上本项目的决定，每轮结束记下这一轮，你当场纠正的话也会记下。",
        "hooks_skip": "{app} 的钩子文件 {file} 不是纯 JSON，没动它，也就没加上 {app} 的钩子。",
        "hooks_codex_shape": "{file} 的写法这个版本的 Codex 读不了：事件名要放在顶层的 \"hooks\" 下面（Codex 文档的写法），"
        "现在 Codex 会整份跳过它，里面原有的钩子也没在跑。KRouter 没动它，也就没加上 Codex 的钩子。",
        "hooks_codex_trust": "Codex 只跑你信任过的钩子：下次打开 Codex 输入 /hooks，把 KRouter 的 4 个钩子标为信任；信任之前 Codex 不跑它们。",
        "hooks_codex_off": "你在 Codex 的 config.toml 里关了钩子（[features] hooks = false），KRouter 的钩子要等你打开才会跑。",
        "capture_how_nightly": "其他 agent 的会话，打开每晚任务后每晚导入前一天的（{ask}）",
        "capture_how_timer": "其他 agent 的会话由每晚任务导入前一天的",
        "plugin_hint": "用 Claude Code 的话，装上插件还能在会话结束时自动记下、开会话时自动带上本项目的决定："
        "/plugin install krouter --marketplace 398894496-arch/KRouter",
        "cli": "命令行（给你和 agent）：{cli} doctor 一条命令给结论（正常，或缺什么、怎么补）；{cli} search \"问题\" 查询；"
        "卸载：sh {uninstall}",
        "minimal": "最小安装：只装查找。没有导入会话、没有夜间任务、没有插件和钩子；只接了你点名的应用：{apps}。",
        "desktop_running": "Claude Desktop 正在运行，所以没有改它的配置文件：它开着的时候把设置留在内存里，退出时整份写回去，"
        "现在写进去的条目一重启就没了。两条路任选：① 退出 Claude Desktop 后运行 {cmd}；② 不用退出，双击这个扩展包，在 Claude Desktop "
        "里点安装（不改配置文件、不用重启）：{mcpb}",
        "desktop_uninstall_running": "Claude Desktop 正在运行，没有改它的配置文件（它退出时会把旧内容写回去）。退出 Claude Desktop 后运行："
        "{cmd}；如果是用扩展包装的，在 Claude Desktop 的「设置 → 扩展」里移除 KRouter。",
        "capture_now": "从现在起它自己记：{how}。只写进本机这个记忆文件夹，先脱敏，不调任何模型。某个会话不想记，在提问里写 #不记；"
        "整个停掉：{revoke}。以前的会话没有导入；要把近 7 天的导进来，一条命令：{cmd}",
        "changed": "改动的文件（每个改之前都在旁边留了一份 *.krouter-bak）：",
        "created": "新建的文件和文件夹：",
        "obsidian_skip": "没有打开任何应用（不是在终端里运行）。它是纯 Markdown 文件夹，用任何编辑器或 Obsidian 打开都行：{vault}",
    },
    "en": {
        "plan": "Plan", "vault_new": "New memory folder", "vault_merge": "Existing folder (adds only missing skeleton files; overwrites nothing)",
        "vault_ours": "Already a KRouter memory folder (upgrade)", "added": "files added", "skill": "Router", "timer": "Daily timer",
        "model_ok": "Model lane", "model_none": "No model yet: log in to one AI coding CLI (`claude`, Codex, grok, …), "
        "or put an API key in {keys} (one line, e.g. DEEPSEEK_API_KEY=sk-…). With the nightly job on, it then runs every night on its own.\n"
        "Without a model: lookup, answers with their source page, \"not in the memory\" instead of a guess, the local "
        "session import and noting correction candidates all work. A change of mind: when an older and a newer page "
        "disagree, the newer one is listed first and flagged, and when you correct your agent it calls krouter_correct "
        "in the same turn, which marks the old page superseded. What does not run: distilling (each page's \"what was "
        "decided, what changed\"), the nightly upkeep, and settling correction candidates, so a change worded another "
        "way that the agent did not record can leave the older page first until a model is connected and the session "
        "is distilled.",
        "done": "Done. Your memory folder: {vault}\nAgents query: {router}",
        "obsidian": "Opened the memory folder in Obsidian (any editor works too).", "obsidian_none": "It is a plain Markdown folder: open it in any editor, or in Obsidian (https://obsidian.md) with “Open folder as vault” → {vault}",
        "py_old": "Python 3.9 or newer is required; this is {v}.",
        "ask": "Turn on the nightly upkeep? Every day at 09:10 it will {lane}distill yesterday{perm}, and send {pages} rule and topic pages (about {tokens} tokens) to it to precompute answers. uninstall.sh turns it off any time. Turn on? [y/N] ",
        "lane_cli": "use {cli} to ", "lane_key": "use your API key to ", "lane_none": "(once you log in to an AI coding CLI or paste a key) ",
        "perm_grok": " (in a kernel sandbox: it can read and write only this vault and run the router; nothing else in your account, keys file included)",
        "perm_claude": " (allowed only to read and write this vault and run the router: no other command, no web fetch; but no kernel sandbox)",
        "perm_codex": " (in Codex's sandbox: it writes only this vault but can read files in your account, keys file included)",
        "perm_key": " (a direct API call; no agent runs on this machine)",
        "sub_note": "This uses the subscription of the {cli} you are logged in to: at most {n} calls a day, each one "
        "recorded on the vault's 订阅调用记录 page; KROUTER_HOST_CLI=0 turns it off.\n",
        "perm_other": " (unconfined: it runs as you and can read and write any file in your account)",
        "prefer_key": "The safer choice is an API key: a direct API call, no agent runs on this machine (paste it on the vault's key page).\n",
        "timer_off": "Nightly upkeep is off. To turn it on later: {cmd}",
        "timer_failed": "The nightly job was NOT installed: this machine has no usable scheduler (on Linux, a systemd user "
        "session or crontab). Nothing was scheduled; set it up by hand from extras/host-daily-evolution/cron.example, or "
        "re-run --timer on a machine that has one.",
        "timer_skip_noninteractive": "Not run from an interactive terminal, so the nightly upkeep was not turned on (it needs your yes). To turn it on: {cmd}",
        "lookup_only": "Installed for lookup only: no session import, no nightly job, nothing leaves this machine.\n"
        "To have it start remembering what you and your agents decide (it asks first and says how much it sends): {cmd}",
        "import_ask": "Import the agent sessions already on this machine? Found {sessions} sessions ({turns} turns) from {agents} "
        "in the last 7 days. Only your questions and each turn's closing answer are kept, redacted, written to this memory folder "
        "on this machine, and sent to no model; each night it imports the previous day too. Import? [y/N] ",
        "distill_ask": "Also have {lane} pull out what was decided and what changed in the latest {n} sessions? It sends about "
        "{chars} characters (redacted) and takes a few minutes; after that only the previous day, each night. Distill? [y/N] ",
        "import_none": "No Claude Code / Codex sessions from the last 7 days on this machine; nothing to import.",
        "import_off": "Sessions were not imported. To import them later: {cmd}",
        "import_done": "Imported {pages} session excerpt pages ({folder}){distilled}.",
        "distilled": "; {n} sessions distilled into what was decided",
        "distilling": "Distilling (one model call per session) …",
        "try": "Ask your agent now, for example: \"{q}\" — it checks this memory folder first and cites the page; what it "
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
        "capture_on": "From now on it keeps up by itself: {how}. Written only to this memory folder on this machine, redacted, no model "
        "called. To keep a session out, put #nocapture in a question; to stop it: {revoke}; every page this import wrote is "
        "listed in {ledger}, and its run number takes it back.",
        "capture_how_plugin": "each Claude Code session when it ends",
        "capture_how_live": "each turn in {apps}, as it ends",
        "hooks_done": "Added KRouter's hooks to {app} ({file}): a session starts with this project's decisions, each turn is recorded as it ends, and a correction you type is noted on the spot.",
        "hooks_skip": "{app}'s hooks file {file} is not plain JSON, so it was left alone and {app} got no KRouter hooks.",
        "hooks_codex_shape": "{file} is not in the shape this Codex reads: event names belong under a top-level \"hooks\" key (as Codex's docs show), "
        "so Codex skips the whole file and the hooks already in it are not running. KRouter left it alone and added no Codex hooks.",
        "hooks_codex_trust": "Codex runs only hooks you have trusted: next time you open Codex, type /hooks and trust KRouter's 4 hooks; until then Codex skips them.",
        "hooks_codex_off": "Hooks are turned off in Codex's config.toml ([features] hooks = false); KRouter's hooks run once you turn them back on.",
        "capture_how_nightly": "other agents' sessions each night once the nightly job is on ({ask})",
        "capture_how_timer": "other agents' sessions each night, by the nightly job",
        "plugin_hint": "On Claude Code, the plugin also records each session when it ends and brings this project's "
        "decisions when one starts: /plugin install krouter --marketplace 398894496-arch/KRouter",
        "cli": "Command line (for you and your agents): {cli} doctor gives one verdict (OK, or what is missing and how to "
        "fix it); {cli} search \"question\" looks up. Uninstall: sh {uninstall}",
        "minimal": "Minimal install: lookup only. No session import, no nightly job, no plugin, no hooks; connected only "
        "the apps you named: {apps}.",
        "desktop_running": "Claude Desktop is running, so its settings file was left alone: while it is open it keeps its "
        "settings in memory and writes the whole file back when it quits, so an entry written now would be gone after a "
        "restart. Either: (1) quit Claude Desktop, then run {cmd}; or (2) without quitting, double-click this extension "
        "and press Install in Claude Desktop (no settings file, no restart): {mcpb}",
        "desktop_uninstall_running": "Claude Desktop is running, so its settings file was left alone (it would write the old "
        "contents back when it quits). Quit Claude Desktop, then run {cmd}; if KRouter was installed as an extension, "
        "remove it in Claude Desktop under Settings → Extensions.",
        "capture_now": "From now on it keeps up by itself: {how}. Written only to this memory folder on this machine, redacted, "
        "no model called. To keep a session out, put #nocapture in a question; to stop it: {revoke}. Past sessions were not "
        "imported; to bring in the last 7 days, one command: {cmd}",
        "changed": "Files changed (a copy of each, taken first, sits next to it as *.krouter-bak):",
        "created": "Files and folders created:",
        "obsidian_skip": "No app was opened (not run from a terminal). It is a plain Markdown folder: open it in any editor, "
        "or in Obsidian: {vault}",
    },
}
KEEP = ("canonical_sources.psv", "canonical_alias_ledger.jsonl")
CHANGED: list[str] = []  # 改过的设置文件（改之前都留了 *.krouter-bak），装完逐条列出
CREATED: list[str] = []  # 新建的文件和文件夹


def backup(cfg: Path) -> None:
    """Before KRouter changes a settings file: keep a copy next to it (`*.krouter-bak`) and list it at the end."""
    if cfg.exists():
        shutil.copy2(cfg, cfg.with_name(cfg.name + ".krouter-bak"))
        if str(cfg) not in CHANGED:
            CHANGED.append(str(cfg))
    elif str(cfg) not in CREATED:
        CREATED.append(str(cfg))


def env_lang() -> str:
    """zh or en from LC_ALL / LC_MESSAGES / LANG / LANGUAGE (first one set, as the C library reads them); `C`,
    `POSIX` and unset say nothing, so the system's language decides."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        val = os.environ.get(var, "").strip().lower()
        if not val or val.split(".")[0] in ("c", "posix"):
            continue
        return "zh" if val.startswith("zh") else "en"
    return ""


def system_lang() -> str:
    """The language when `--lang` is not given: the terminal's locale first, the system's only when it says nothing
    (an English terminal on a Mac set to Chinese gets English)."""
    lang = env_lang()
    if lang:
        return lang
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


def recorded_vault() -> str:
    """The memory folder an earlier install recorded, when it is still there: a second install (an upgrade) keeps
    using it, whatever language this terminal now says (1.x picked the folder name from the system's language)."""
    from krouter_home import vault_path

    raw = vault_path()
    return raw if raw and Path(raw).expanduser().is_dir() else ""


def default_vault(lang: str) -> Path:
    return Path.home() / "Documents" / ("第二大脑" if lang == "zh" else "Second Brain")


DEFAULT_MARKS = ("Agent第二大脑.md", "90 系统文件", "05 时间日志", "02 经验与方法", "01 项目")
sys.path.insert(0, str(ROOT / "skill/krouter/scripts"))
import zones  # noqa: E402


def layout_for(vault: Path, lang: str) -> Path | None:
    """The names a vault is laid down with: its own `krouter-zones.psv`; else, for an English vault that does not
    already use the default (Chinese) names, `zones_en.psv`; else None (the default names)."""
    own = vault / zones.ZONES_FILE
    if own.is_file():
        return own
    if lang == "en" and not any((vault / m).exists() for m in DEFAULT_MARKS):
        return zones.EN_TABLE
    return None


def vault_state(vault: Path) -> str:
    if not vault.exists() or (vault.is_dir() and not any(p for p in vault.iterdir() if p.name != ".DS_Store")):
        return "new"
    if (vault / "Agent第二大脑.md").is_file() or (vault / "krouter-zones.psv").is_file() \
            or (vault / "90 系统文件" / "自动化" / "日更健康.md").is_file():
        return "ours"
    return "merge"


def lay_down(template: Path, vault: Path, dry: bool, lang: str = "zh") -> list[str]:
    """Copy template files that are missing in the vault, under the vault's names (`layout_for`). Never overwrites."""
    table = layout_for(vault, lang)
    if table is not None:
        sample = ROOT / "skill/krouter/scripts/canonical_sources.psv"
        return zones.lay_out(template, vault, dry, table, sample if template == ROOT / "template" else None)
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


def skill_home() -> Path:
    return Path(os.environ.get("KROUTER_SKILL_HOME") or Path.home() / ".agents/skills/krouter")


LEGACY_SKILL = ".agents/skills/krouter-obsidian"  # 2.0 以前的安装目录；升级后留成指向新目录的软链


def legacy_skill_home() -> Path | None:
    """The pre-2.0 install directory, when it is still a real directory (not yet upgraded). None with a custom path."""
    if os.environ.get("KROUTER_SKILL_HOME"):
        return None
    old = Path.home() / LEGACY_SKILL
    return old if old.is_dir() and not old.is_symlink() else None


def legacy_timer() -> bool:
    """A nightly job installed before 2.0 still runs the router from the old `skill/krouter-obsidian` folder."""
    home = Path.home()
    texts = []
    for f in (home / "Library/LaunchAgents/local.dsh-krouter.daily-evolution.plist",
              home / ".config/systemd/user/dsh-krouter-daily.service"):
        try:
            texts.append(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    if WINDOWS:
        res = subprocess.run(["schtasks", "/Query", "/TN", "KRouter daily evolution", "/XML"], capture_output=True, text=True)
        texts.append(res.stdout or "")
    return any("krouter-obsidian" in t for t in texts)


def install_posix(vault: Path, dry: bool) -> int:
    skill = skill_home()
    upgrade = skill.exists() or legacy_skill_home() is not None
    argv = ["/bin/sh", str(ROOT / "scripts/install.sh")] + (["--upgrade"] if upgrade else [])
    if dry:
        home = Path.home()
        print("  " + " ".join(argv))
        print(f"    {'replace' if skill.exists() else 'create'}: {skill}/ (the router; your alias table is kept)")
        if legacy_skill_home() is not None:
            print(f"    move: {legacy_skill_home()}/ → {skill}/, the old path left as a link to it")
        if os.environ.get("KROUTER_NO_CURSOR_RULES") != "1":
            for f in (os.environ.get("KROUTER_CURSOR_RULE") or home / ".cursor/rules/krouter.mdc",
                      os.environ.get("KROUTER_ASK_RULE") or home / ".cursor/rules/ask-product.mdc"):
                print(f"    write: {f}")
        vf = os.environ.get("KROUTER_VAULT_FILE") or Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "krouter/vault"
        print(f"    write: {vf} (where the vault is, for hooks and the MCP server)")
        print(f"    set: lamp, self_evolution_key, krouter_writer on {zones.path(vault, '90 系统文件/自动化/日更健康.md')}")
        return 0
    return subprocess.run(argv, env={**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_BOOTSTRAP": "1"}).returncode


def install_windows(vault: Path, dry: bool, timer: bool) -> int:
    """install.sh, for Windows: skill (keeping the alias table), agent rules, alias table into the vault, timer."""
    home = Path.home()
    skill = Path(os.environ.get("KROUTER_SKILL_HOME") or home / ".agents/skills/krouter")
    rules = Path(os.environ.get("KROUTER_CURSOR_RULE") or home / ".cursor/rules/krouter.mdc")
    ask = Path(os.environ.get("KROUTER_ASK_RULE") or home / ".cursor/rules/ask-product.mdc")
    if dry:
        print(f"  copy skill → {skill}\n  rules → {rules.parent}\n  timer: {'scheduled task' if timer else 'skipped'}")
        return 0
    kept = {}
    legacy = legacy_skill_home()
    keep_from = skill if (skill / "scripts").is_dir() or legacy is None else legacy
    for name in KEEP:
        p = keep_from / "scripts" / name
        if p.is_file():
            kept[name] = p.read_bytes()
    if skill.exists():
        shutil.rmtree(skill)
    shutil.copytree(ROOT / "skill/krouter", skill)
    for name, data in kept.items():
        (skill / "scripts" / name).write_bytes(data)
    if legacy is not None:  # 2.0 以前的目录：删掉，原处留一个链接（Windows 建链接要权限，不行就用目录联接）
        shutil.rmtree(legacy)
        try:
            os.symlink(skill, legacy, target_is_directory=True)
        except OSError:
            subprocess.run(["cmd", "/c", "mklink", "/J", str(legacy), str(skill)], capture_output=True)
        print(f"moved: {legacy} → {skill}")
    old_rule = None if os.environ.get("KROUTER_CURSOR_RULE") else home / ".cursor/rules/krouter-obsidian.mdc"
    if os.environ.get("KROUTER_NO_CURSOR_RULES") != "1":
        rules.parent.mkdir(parents=True, exist_ok=True)
        ask.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "extras/cursor/krouter.mdc", rules)
        shutil.copy2(ROOT / "extras/cursor/ask-product.mdc", ask)
        if old_rule is not None and old_rule.is_file() and "route_knowledge" in old_rule.read_text(encoding="utf-8", errors="replace"):
            old_rule.unlink()
    table = zones.path(vault, "90 系统文件/canonical_sources.psv")
    if not table.exists() and table.parent.is_dir():
        old = kept.get("canonical_sources.psv")
        sample = (ROOT / "skill/krouter/scripts/canonical_sources.psv").read_bytes()
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
    dry = subprocess.run([sys.executable, str(ROOT / "skill/krouter/scripts/nightly.py"), "--vault", str(vault),
                          "--dry-run"], env=env, capture_output=True, text=True, timeout=600)
    try:
        tokens = int(json.loads(dry.stdout).get("est_tokens_total") or 0)
    except ValueError:
        pass
    cards = subprocess.run([sys.executable, str(ROOT / "skill/krouter/scripts/answer_cards.py"), "--vault", str(vault),
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
    sub = ""
    if kind not in ("", "key"):
        sys.path.insert(0, str(ROOT / "skill/krouter/scripts"))
        import llm

        sub = t["sub_note"].format(cli=cli, n=llm.host_cli_max())  # 借订阅：先说清额度、上限、怎么关
    prompt = (t["prefer_key"] if kind not in ("", "key") else "") + sub + t["ask"].format(lane=lane, perm=perm, pages=pages, tokens=tokens)
    answer = ask_tty(prompt)
    if answer is None:
        return False, False
    return answer.strip().lower() in {"y", "yes", "是", "好", "开"}, True


IMPORT = ROOT / "skill/krouter/scripts/import_sessions.py"


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
    return remembering_timer()


DISTILL_AT_INSTALL = 8  # 安装时只提炼最近几个会话，免得一装就等十几分钟


def run_import(vault: Path, *extra: str) -> dict:
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_NO_QUERY_LOG": "1"}
    res = subprocess.run([sys.executable, str(IMPORT), "--vault", str(vault), *extra], env=env, capture_output=True,
                         text=True, timeout=3600)
    try:
        return json.loads(res.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {}


def consent_from_now() -> None:
    """Remember from now on without importing anything from before: record the same yes `import_sessions.py --consent`
    records (the hooks only work after it), with nothing imported."""
    from datetime import datetime, timezone

    sys.path.insert(0, str(IMPORT.parent))
    import import_sessions

    st = import_sessions.load_state()
    if not st.get("consent"):
        import_sessions.save_state({**st, "consent": True, "distill": False, "overlap": st.get("overlap") or "link",
                                    "cli": "", "exclude_roots": st.get("exclude_roots") or [], "past_imported": False,
                                    "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})


def decide_import(args: argparse.Namespace, vault: Path, t: dict, lane_kind: str) -> tuple[bool, bool, bool]:
    """(import, distill, worth saying how to do it later). Copying chat text into the vault, and sending it to a
    model, each need a yes: a flag, or `y` at the prompt. No terminal to ask on: nothing is imported."""
    if args.no_import or os.environ.get("KROUTER_NO_IMPORT") == "1":
        return False, False, False
    if not (args.ask or args.import_sessions or args.import_distill):
        return False, False, False  # 默认：不导入以前的会话，只从现在起记（main 里记下同意、接上钩子）
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


CLAUDE_MEM = ROOT / "skill/krouter/scripts/import_claude_mem.py"


def run_claude_mem(vault: Path, *extra: str) -> dict:
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_NO_QUERY_LOG": "1"}
    res = subprocess.run([sys.executable, str(CLAUDE_MEM), "--vault", str(vault), *extra], env=env,
                         capture_output=True, text=True, timeout=3600)
    try:
        return json.loads(res.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {}


def offer_claude_mem(args: argparse.Namespace, vault: Path, t: dict, distill: bool) -> dict:
    """claude-mem users already have a memory: offer to bring it in. Same rule as the sessions — a yes or a flag
    (`--import`, `--all`, or `y` with `--ask`); the default install imports nothing from the past."""
    if args.no_import or os.environ.get("KROUTER_NO_IMPORT") == "1":
        return {}
    if not (args.ask or args.import_sessions or args.import_distill):
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
    folder = zones.path(vault, "05 时间日志/会话摘录")
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


def claude_desktop_running() -> bool:
    """Claude Desktop is open right now. macOS: a process whose executable is `…/Claude.app/Contents/MacOS/Claude`
    (case-sensitive, so Claude Code's own `claude` binaries do not count). Windows: a `Claude` process whose path is
    under `AnthropicClaude` or the Store's `WindowsApps` (the desktop app, not the `claude.exe` CLI). Elsewhere there is
    no desktop app. `KROUTER_CLAUDE_DESKTOP_RUNNING=1|0` overrides (tests)."""
    forced = os.environ.get("KROUTER_CLAUDE_DESKTOP_RUNNING", "")
    if forced in ("0", "1"):
        return forced == "1"
    try:
        if platform.system() == "Darwin":
            out = subprocess.run(["ps", "-axo", "comm="], capture_output=True, text=True, timeout=10).stdout
            return any(ln.strip().endswith("/Claude.app/Contents/MacOS/Claude") for ln in out.splitlines())
        if WINDOWS:
            out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                  "Get-Process -Name Claude -ErrorAction SilentlyContinue | ForEach-Object { $_.Path }"],
                                 capture_output=True, text=True, timeout=20).stdout
            return any(("\\AnthropicClaude\\" in ln or "\\WindowsApps\\" in ln) for ln in out.splitlines())
    except (OSError, subprocess.TimeoutExpired):
        return False
    return False


def desktop_extension(py: str) -> Path | None:
    """A Claude Desktop extension for this machine: the memory folder the install recorded as its default, the
    interpreter found here. Built next to the recorded-folder file; None when it cannot be built."""
    builder = ROOT / "scripts" / "build_mcpb.py"
    if not builder.is_file():
        return None
    sys.path.insert(0, str(builder.parent))
    try:
        import build_mcpb
        from krouter_home import vault_file, vault_path

        return build_mcpb.build(vault_file().parent / "KRouter.mcpb", vault_path(), py)
    except Exception:  # noqa: BLE001 - 做不出扩展包就只给"退出后重跑"那条路
        return None


DESKTOP_DEFERRED: dict = {}  # Claude Desktop 开着、没写配置时：给用户的扩展包路径


def claude_desktop_config() -> Path | None:
    """Claude Desktop's MCP settings file, when the app is installed (its settings folder exists); else None."""
    return app_config(MCP_APPS[0])


def register_app(app: dict, server: list[str], dry: bool, t: dict | None = None) -> bool:
    """Add KRouter to one app's MCP settings, keeping everything else in the file. Never touches a file it cannot
    parse, or a `krouter` entry that is not KRouter's mcp_server.py; keeps a copy of the file it changes."""
    cfg = app_config(app)
    if cfg is None:
        return False
    running = app["id"] == "claude-desktop" and claude_desktop_running()
    if dry:
        print(f"  {app['name']}: " + ("running now, so its settings file would be left alone and an extension "
                                     "(KRouter.mcpb) built instead" if running else f"add {app['key']}.krouter to {cfg}"))
        return False
    if running:
        mcpb = desktop_extension(server[0])
        DESKTOP_DEFERRED["mcpb"] = str(mcpb) if mcpb else ""
        if t:
            cmd = f'{"python" if WINDOWS else "python3"} "{ROOT / "scripts" / "bootstrap.py"}" --connect claude-desktop'
            print(t["desktop_running"].format(cmd=cmd, mcpb=mcpb or "-"))
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
    backup(cfg)
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
        if app["id"] == "claude-desktop" and claude_desktop_running():
            cmd = f'{"python" if WINDOWS else "python3"} "{ROOT / "scripts" / "bootstrap.py"}" --unregister-mcp'
            print("HOST ACTION: " + MSG["en"]["desktop_uninstall_running"].format(cmd=cmd))
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


def codex_used() -> Path:
    """~/.codex when Codex has really been used here. A folder holding only `tmp/` is what probing the Codex app's
    login leaves behind (it happens on a machine that has never run Codex); that is not a Codex install."""
    home = codex_home()
    try:
        names = {p.name for p in home.iterdir()} - {".DS_Store"} if home.is_dir() else None
        if names is not None and names != {"tmp"}:
            return home
    except OSError:
        pass
    return home / ".not-used"


# 每轮记下来的钩子：Codex 和 Cursor 各自的事件名 → session_hook.py 的动作。格式照各家官方文档，2026-11-09 核对；
# Codex 那份用 codex-cli 0.155 实测过（事件必须放在顶层 "hooks" 下面，否则整份被跳过）。Claude Code 的在插件里。
HOOK_APPS = (
    {"id": "codex", "name": "Codex", "dir": lambda: codex_used(), "file": lambda: codex_home() / "hooks.json",
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


def register_hooks(t: dict, dry: bool, apps: set[str] | None = None) -> list[str]:
    """Add the turn-by-turn hooks to Codex and Cursor when they are installed, keeping every hook already there.
    Never touches a file it cannot parse; keeps a copy of a file it changes; re-running replaces only its own entries."""
    if os.environ.get("KROUTER_NO_HOOKS") == "1":
        return []
    skill = Path(os.environ.get("KROUTER_SKILL_HOME") or Path.home() / ".agents/skills/krouter")
    py = sys.executable if WINDOWS else (shutil.which("python3") or sys.executable)
    script = str(skill / "scripts" / "session_hook.py")
    done = []
    for app in HOOK_APPS:
        cfg = hooks_config(app)
        if cfg is None or not wanted(app["id"], apps):
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
            backup(cfg)
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
    backup(Path.home() / ".claude/settings.json")  # 插件和它的市场记在这里

    def run(*a: str) -> bool:
        return subprocess.run([exe, "plugin", *a], capture_output=True, text=True, timeout=180).returncode == 0

    try:
        if run("install", "krouter@krouter"):  # 已经加过 krouter 市场（GitHub 或本地）就直接装
            return True
        return run("marketplace", "add", str(ROOT)) and run("install", "krouter@krouter")
    except (OSError, subprocess.TimeoutExpired):
        return False


def wanted(app_id: str, apps: set[str] | None) -> bool:
    """`--apps` names the apps to connect; None (no `--apps`, not `--minimal`) means every installed one."""
    return apps is None or app_id in apps


def uninstall_plugin(dry: bool) -> list[str]:
    """Disable and remove the Claude Code plugin, and the `krouter` marketplace when it points at a folder on this
    machine (the one the installer added: a clone or ~/.dsh-krouter/<tag>). A GitHub marketplace you added is kept."""
    exe = shutil.which("claude")
    if not exe or os.environ.get("KROUTER_NO_PLUGIN") == "1":
        return []
    gone = []

    def run(*a: str) -> subprocess.CompletedProcess:
        return subprocess.run([exe, "plugin", *a], capture_output=True, text=True, timeout=120)

    try:
        listed = run("list", "--json")
        if listed.returncode == 0 and "krouter@krouter" in listed.stdout:
            if dry:
                print("would: claude plugin uninstall krouter@krouter")
            elif run("uninstall", "krouter@krouter").returncode == 0:
                print("removed: Claude Code plugin krouter@krouter")
                gone.append("plugin")
        try:
            rows = json.loads(run("marketplace", "list", "--json").stdout or "[]")
        except ValueError:
            rows = []
        for m in rows if isinstance(rows, list) else []:
            if isinstance(m, dict) and m.get("name") == "krouter" and m.get("source") == "directory":
                if dry:
                    print(f"would: claude plugin marketplace remove krouter ({m.get('path')})")
                elif run("marketplace", "remove", "krouter").returncode == 0:
                    print(f"removed: Claude Code marketplace krouter ({m.get('path')})")
                    gone.append("marketplace")
    except (OSError, subprocess.TimeoutExpired):
        pass
    return gone


def register_mcp(t: dict, dry: bool, apps: set[str] | None = None, plugin: bool = True) -> list[str]:
    """Register the MCP server with the agent CLIs that are installed (user scope). Re-running is harmless."""
    if os.environ.get("KROUTER_NO_MCP") == "1":
        return []
    skill = Path(os.environ.get("KROUTER_SKILL_HOME") or Path.home() / ".agents/skills/krouter")
    # python3 on PATH outlives a versioned interpreter path (a Homebrew upgrade moves python@3.x)
    py = sys.executable if WINDOWS else (shutil.which("python3") or sys.executable)
    server = [py, str(skill / "scripts" / "mcp_server.py")]
    done = []
    for cli, argv in (("claude", ["mcp", "add", "--scope", "user", "krouter", "--"]),
                      ("codex", ["mcp", "add", "krouter", "--"])):
        exe = shutil.which(cli)
        if not exe or not wanted(cli, apps):
            continue
        if dry:
            print("  " + " ".join([cli, *argv, *server]))
            if cli == "claude" and plugin and os.environ.get("KROUTER_NO_PLUGIN") != "1" \
                    and (ROOT / ".claude-plugin" / "marketplace.json").is_file():
                print(f"  claude plugin marketplace add {ROOT}   (writes extraKnownMarketplaces in ~/.claude/settings.json)")
                print("  claude plugin install krouter@krouter   (enables its session hooks: SessionStart, "
                      "UserPromptSubmit, Stop, SessionEnd)")
            continue
        if cli == "claude":
            backup(Path.home() / ".claude.json")  # claude mcp add --scope user 写这里
            subprocess.run([exe, "mcp", "remove", "--scope", "user", "krouter"], capture_output=True, timeout=60)
        else:
            backup(codex_home() / "config.toml")  # codex mcp add 写这里
            subprocess.run([exe, "mcp", "remove", "krouter"], capture_output=True, timeout=60)
        try:
            ok = subprocess.run([exe, *argv, *server], capture_output=True, text=True, timeout=60).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        if ok:
            done.append(cli)
            print(t["mcp"].format(cli=cli))
            if cli == "claude" and plugin and install_plugin(exe):
                done.append("claude-plugin")
                print(t["plugin_done"])
    for app in MCP_APPS:  # 本机装了哪个就接哪个，和 claude / codex 一样不问
        if wanted(app["id"], apps) and register_app(app, server, dry, t):
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


def interactive() -> bool:
    """Run by a person at a terminal (the one-line install's output goes to it), not by an agent capturing output."""
    if os.environ.get("KROUTER_NO_PROMPT") == "1":
        return False
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def should_open(args: argparse.Namespace) -> bool:
    """Open a new vault in Obsidian: `--open`, or a person at a terminal; never `--no-open`, never for an agent."""
    return not args.no_open and (args.open or interactive())


def stable_root() -> Path:
    """This copy of KRouter, by the path that survives upgrades: ~/.dsh-krouter/current when it points here."""
    current = ROOT.parent / "current"
    try:
        if current.is_symlink() and current.resolve() == ROOT:
            return current
    except OSError:
        pass
    return ROOT


def cli_path() -> str:
    """How to call `krouter` right now: on PATH when pipx / uvx put it there, else this copy's own launcher."""
    if shutil.which("krouter"):
        return "krouter"
    if WINDOWS:
        return f'set "PYTHONPATH={stable_root() / "sdk"}" && python -m krouter.cli'
    return str(stable_root() / "scripts" / "krouter")


def remembering_timer() -> bool:
    """A nightly job installed on this machine (launchd / systemd / crontab / Windows task)."""
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


def timer_took(t: dict) -> bool:
    """After `--timer` asked the installer for a nightly job: is one really there? A machine with no scheduler (a
    container, a minimal server) gets no job, and the summary, the health page and `doctor` must not say it did.
    KROUTER_SKIP_TIMER=1 is the tests' and CI's explicit "do not load it": trusted as before."""
    if os.environ.get("KROUTER_SKIP_TIMER") == "1" or remembering_timer():
        return True
    print(t["timer_failed"])
    return False


def set_lamp(vault: Path, on: bool) -> None:
    """The health page says `lamp: running` only when a nightly job is installed; else `unused`, so `status`
    never shows a job running that is not there."""
    health = zones.path(vault, "90 系统文件/自动化/日更健康.md")
    if health.is_file():
        subprocess.run([sys.executable, str(ROOT / "extras/host-daily-evolution/patch_health.py"), str(health), "lamp",
                        "running" if on else "unused"], capture_output=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="One-step install: vault + router + daily timer")
    ap.add_argument("--vault", default="")
    ap.add_argument("--lang", choices=["zh", "en", "auto"], default="auto")
    ap.add_argument("--timer", action="store_true", help="install the nightly job without asking (you have read what it does)")
    ap.add_argument("--no-timer", action="store_true", help="do not install the nightly job, and do not ask")
    ap.add_argument("--no-open", action="store_true", help="do not open the vault in Obsidian")
    ap.add_argument("--open", action="store_true",
                    help="open a new vault in Obsidian even with no terminal (default: only when run from a terminal)")
    ap.add_argument("--minimal", action="store_true",
                    help="lookup only: no session import, nightly job, plugin, hooks or Cursor rules; connects only --apps")
    ap.add_argument("--apps", default=None,
                    help="comma-separated apps to connect (claude, codex, cursor, claude-desktop, vscode, copilot-cli, "
                         "gemini-cli, kiro, zed, cline); default: every one installed, none with --minimal")
    ap.add_argument("--import", dest="import_sessions", action="store_true",
                    help="import the last 7 days of agent sessions, and claude-mem's memory if present, without asking (local only)")
    ap.add_argument("--import-distill", action="store_true", help="import, and have the model lane distill the latest sessions")
    ap.add_argument("--no-import", action="store_true", help="do not record sessions at all (lookup only), and do not ask")
    ap.add_argument("--all", action="store_true",
                    help="everything the install can do without a model: also import the last 7 days of sessions and "
                         "claude-mem's memory (the old default)")
    ap.add_argument("--ask", action="store_true",
                    help="ask before importing sessions, and about distilling and the nightly job (default: import locally without asking, no model, no nightly job)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--unregister-mcp", action="store_true", help=argparse.SUPPRESS)  # uninstall.sh 用
    ap.add_argument("--connect", default="", metavar="APP",
                    help="only connect this app's MCP settings (e.g. claude-desktop, after quitting it), then stop")
    args = ap.parse_args()
    if args.unregister_mcp:
        uninstall_plugin(args.dry_run)
        unregister_apps(args.dry_run)
        unregister_hooks(args.dry_run)
        return 0
    lang = system_lang() if args.lang == "auto" else args.lang
    t = MSG[lang]
    if args.connect:
        app = next((a for a in MCP_APPS if a["id"] == args.connect), None)
        if app is None:
            print(f"unknown app {args.connect!r}: " + ", ".join(a["id"] for a in MCP_APPS))
            return 2
        py = sys.executable if WINDOWS else (shutil.which("python3") or sys.executable)
        ok = register_app(app, [py, str(skill_home() / "scripts" / "mcp_server.py")], args.dry_run, t)
        if ok:
            print((t["mcp_desktop"] if app["id"] == "claude-desktop" else t["mcp_app"].format(app=app["name"], file=app_config(app)))
                  + "".join(f"\n  {p}" for p in CHANGED))
        elif app_config(app) is None:
            print(f"{app['name']} is not installed here (no {app['dir']()}).")
        return 0 if ok or args.dry_run else 1
    apps = {a.strip() for a in args.apps.split(",") if a.strip()} if args.apps is not None else (set() if args.minimal else None)
    if args.all:
        args.import_sessions = True
    if args.minimal:
        args.no_import, args.no_timer, args.ask = True, True, False
        if apps is not None and "cursor" not in apps:
            os.environ["KROUTER_NO_CURSOR_RULES"] = "1"
        os.environ["KROUTER_NO_PLUGIN"] = "1"
    if sys.version_info < (3, 9):
        print(t["py_old"].format(v=platform.python_version()))
        return 1
    vault = Path(args.vault or os.environ.get("OBSIDIAN_VAULT") or recorded_vault() or default_vault(lang)).expanduser().resolve()
    state = vault_state(vault)
    template = template_for(lang)
    print(f"{t['plan']}: {t['vault_' + state]} → {vault}")
    added = lay_down(template, vault, args.dry_run, lang)
    if added and (state != "new" or args.dry_run):
        shown = added if args.dry_run else added[:12]  # 预演把每个文件都列出来
        print(f"  {t['added']}: {len(added)}" + "".join(f"\n    {a}" for a in shown) + ("\n    …" if len(added) > len(shown) else ""))
    had_skill = skill_home().exists()
    rule_files = [Path(os.environ.get("KROUTER_CURSOR_RULE") or Path.home() / ".cursor/rules/krouter.mdc"),
                  Path(os.environ.get("KROUTER_ASK_RULE") or Path.home() / ".cursor/rules/ask-product.mdc")]
    had_rules = [f.exists() for f in rule_files]
    os.environ["KROUTER_NO_TIMER"] = "1"  # 先只装只读部分：库、路由、规则；夜间任务等宿主点头再装
    rc = install_windows(vault, args.dry_run, False) if WINDOWS else install_posix(vault, args.dry_run)
    if rc != 0:
        return rc
    if args.dry_run:
        register_mcp(t, True, apps, not args.minimal)
        if not args.no_import:
            register_hooks(t, True, apps)
        print("  nightly job: " + ("yes (--timer)" if args.timer else "no (--no-timer)" if args.no_timer
                                   else "asks first (--ask)" if args.ask else "no (--ask to be asked)"))
        print("  session import: " + ("no (--no-import)" if args.no_import else "last 7 days (--import / --all)" if args.import_sessions
                                      else "asks first (--ask)" if args.ask else "none from the past; turns recorded from now on, "
                                      "local only, no model (--all also imports the last 7 days)"))
        print("  open in Obsidian: " + ("no (--no-open)" if args.no_open else "yes (--open)" if args.open and state == "new"
                                        else "only if run from a terminal and Obsidian is installed" if state == "new"
                                        else "no (existing vault)"))
        return 0
    sys.path.insert(0, str(ROOT / "skill/krouter/scripts"))
    from krouter_home import remember

    vf = remember(vault)  # agent、MCP、插件不用先 export 变量也找得到这个记忆文件夹
    if state == "new":
        CREATED.append(f"{vault}{os.sep} ({len(added)} files)")
    CREATED.append(f"{skill_home()}{os.sep}" + (" (replaced: upgrade)" if had_skill else ""))
    if os.environ.get("KROUTER_NO_CURSOR_RULES") != "1":
        CREATED.extend(f"{f}" + (" (replaced)" if had else "") for f, had in zip(rule_files, had_rules))
    CREATED.append(str(vf))
    mcp = register_mcp(t, False, apps, not args.minimal)
    os.environ.pop("KROUTER_NO_TIMER", None)
    timer, asked = decide_timer(args, vault, t)
    if not timer and not args.no_timer and legacy_timer():
        timer = True  # 2.0 以前装过的夜间任务：宿主当时同意过，只把它重新登记到新路径
        print("nightly job: installed before 2.0 at the old router path; registered again at the new one")
    if timer:
        rc = install_windows(vault, False, True) if WINDOWS else install_posix(vault, False)
        if rc != 0:
            return rc
        timer = timer_took(t)
    elif args.ask:
        cmd = f"{'python' if WINDOWS else 'python3'} \"{ROOT / 'scripts' / 'bootstrap.py'}\" --timer --vault \"{vault}\""
        print((t["timer_off"] if asked else t["timer_skip_noninteractive"]).format(cmd=cmd))
    lane = model_lane(vault)
    keys = os.environ.get("KROUTER_KEYS_ENV") or str(Path.home() / ".dsh-krouter-keys.env")
    print(f"{t['model_ok']}: {lane}" if lane else t["model_none"].format(keys=keys))
    lane_kind = "" if not lane else ("key" if lane == "API key" else lane.split(" ")[0])
    capture_only = not (args.no_import or os.environ.get("KROUTER_NO_IMPORT") == "1" or args.ask or args.import_sessions
                        or args.import_distill)
    do_import, do_distill, tell_later = decide_import(args, vault, t, lane_kind)
    imported = {}
    hooked: list[str] = []
    if do_import:
        extra = ["--consent"] + (["--distill", "--distill-max", str(DISTILL_AT_INSTALL)] if do_distill else [])
        if do_distill:
            print(t["distilling"])
        imported = run_import(vault, *extra)
        hooked = register_hooks(t, False, apps) if capture_consented() else []
        n = imported.get("distilled") or 0
        if imported.get("pages"):
            print(t["import_done"].format(pages=imported.get("pages", 0), folder=zones.real(vault, "05 时间日志/会话摘录"),
                                          distilled=t["distilled"].format(n=n) if n else ""))
        py = "python" if WINDOWS else "python3"
        live = (["Claude Code"] if "claude-plugin" in mcp else []) + [a["name"] for a in HOOK_APPS if a["id"] in hooked]
        how = ([t["capture_how_live"].format(apps=(" / " if lang == "en" else "、").join(live))] if live else []) + (
            [t["capture_how_timer"]] if timer else [t["capture_how_nightly"].format(ask=f'{py} "{ROOT / "scripts" / "bootstrap.py"}" --ask')])
        print(t["capture_on"].format(how="；".join(how) if lang == "zh" else "; ".join(how),
                                     revoke=f'{py} "{IMPORT}" --revoke',
                                     ledger=zones.real(vault, "90 系统文件/自动化/记忆变更记录.md")))
    elif capture_only:
        consent_from_now()
        hooked = register_hooks(t, False, apps)
        py = "python" if WINDOWS else "python3"
        live = (["Claude Code"] if "claude-plugin" in mcp else []) + [a["name"] for a in HOOK_APPS if a["id"] in hooked]
        how = ([t["capture_how_live"].format(apps=(" / " if lang == "en" else "、").join(live))] if live else []) + (
            [t["capture_how_timer"]] if timer else [t["capture_how_nightly"].format(ask=f'{py} "{ROOT / "scripts" / "bootstrap.py"}" --ask')])
        print(t["capture_now"].format(how="；".join(how) if lang == "zh" else "; ".join(how),
                                      revoke=f'{py} "{IMPORT}" --revoke',
                                      cmd=f'{py} "{IMPORT}" --consent --vault "{vault}"'))
    elif tell_later:
        cmd = f"{'python' if WINDOWS else 'python3'} \"{IMPORT}\" --consent --vault \"{vault}\""
        print(t["import_off"].format(cmd=cmd))
    if not do_import and not capture_only and capture_consented():
        hooked = register_hooks(t, False, apps)  # 升级：以前同意过导入，钩子照样接上（换成这一版的路径）
    cmem = offer_claude_mem(args, vault, t, do_distill)
    set_lamp(vault, timer or remembering_timer())
    if args.minimal:
        print(t["minimal"].format(apps=", ".join(mcp) or "-"))
    elif not (timer or do_import or args.ask or remembering_already()):
        cmd = f"{'python' if WINDOWS else 'python3'} \"{ROOT / 'scripts' / 'bootstrap.py'}\" --ask --vault \"{vault}\""
        print(t["lookup_only"].format(cmd=cmd))
    if "claude" in mcp and "claude-plugin" not in mcp and not args.minimal:
        print(t["plugin_hint"])
    skill = Path(os.environ.get("KROUTER_SKILL_HOME") or Path.home() / ".agents/skills/krouter")
    router = skill / "scripts" / ("route_knowledge.py" if WINDOWS else "route_knowledge.sh")
    if CREATED:
        print(t["created"] + "".join(f"\n  {p}" for p in CREATED))
    if CHANGED:
        print(t["changed"] + "".join(f"\n  {p}" for p in CHANGED))
    print(t["done"].format(vault=vault, router=router))
    print(t["try"].format(q=try_question(vault, lang)))
    print(t["cli"].format(cli=cli_path(), uninstall=stable_root() / "scripts" / "uninstall.sh"))
    if state == "new" and not args.no_open:
        if should_open(args):
            print(t["obsidian"] if open_in_obsidian(vault) else t["obsidian_none"].format(vault=vault))
        else:
            print(t["obsidian_skip"].format(vault=vault))
    print(json.dumps({"vault": str(vault), "lang": lang, "state": state, "added": len(added), "model": lane or None,
                      "timer": timer, "imported": imported.get("pages", 0), "distilled": imported.get("distilled", 0),
                      "claude_mem": cmem.get("sessions", 0),
                      "mcp": mcp, "hooks": hooked, "claude_desktop_extension": DESKTOP_DEFERRED.get("mcpb")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
