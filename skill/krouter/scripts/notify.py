#!/usr/bin/env python3
"""A desktop notification when the nightly work did not happen — for hosts who never open a terminal.

macOS: `osascript`. Linux: `notify-send` when present. Windows: a PowerShell balloon tip (the text travels in an
environment variable, so the ASCII-only script never has to carry Chinese). Never raises; `KROUTER_NOTIFY=0`
turns it off (tests do). At most one notification per kind per day, so a broken setup reminds once a night
instead of nagging.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from datetime import date
from pathlib import Path

TITLE = "第二大脑 / Second Brain"
PS = (
    "Add-Type -AssemblyName System.Windows.Forms; $n = New-Object System.Windows.Forms.NotifyIcon; "
    "$n.Icon = [System.Drawing.SystemIcons]::Information; $n.BalloonTipTitle = $env:KROUTER_NOTE_TITLE; "
    "$n.BalloonTipText = $env:KROUTER_NOTE_TEXT; $n.Visible = $true; $n.ShowBalloonTip(10000); Start-Sleep 11; $n.Dispose()"
)


def _once_today(kind: str) -> bool:
    state = Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local/state/krouter") / f"notified-{kind}"
    today = date.today().isoformat()
    try:
        if state.is_file() and state.read_text(encoding="utf-8").strip() == today:
            return False
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(today, encoding="utf-8")
    except OSError:
        pass
    return True


def send(text: str, kind: str = "general") -> bool:
    if os.environ.get("KROUTER_NOTIFY", "1") == "0" or not _once_today(kind):
        return False
    try:
        system = platform.system()
        if system == "Darwin":
            esc = text.replace("\\", "\\\\").replace('"', '\\"')
            return subprocess.run(["osascript", "-e", f'display notification "{esc}" with title "{TITLE}"'],
                                  capture_output=True, timeout=10).returncode == 0
        if os.name == "nt":
            env = {**os.environ, "KROUTER_NOTE_TITLE": TITLE, "KROUTER_NOTE_TEXT": text}
            subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", PS], env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        if shutil.which("notify-send"):
            return subprocess.run(["notify-send", TITLE, text], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
    return False


NIGHTLY = {
    "skipped": "今晚的夜间整理没做：没有可用的模型。登录一个 AI 编程工具（如 Claude Code），或把 API key 贴到知识库的「自进化钥匙」页。"
               " / Nightly upkeep skipped: no model. Log in to an AI coding CLI or paste an API key on the key page.",
    "failed": "今晚的夜间整理出错了，原因在知识库「90 系统文件/自动化/夜间维护」。 / Nightly upkeep failed; see 夜间维护 in the vault.",
}
PENDING_KEY = ("你贴的 key 认不出是哪家服务，还没生效：打开 ~/.dsh-krouter-keys.env，把 KROUTER_PENDING_KEY_1 改成对应的名字"
               "（如 DEEPSEEK_API_KEY），或在知识库的「自进化钥匙」页按 DEEPSEEK_API_KEY=… 的格式重贴。"
               " / A pasted key's provider is unknown, so it is not used yet: rename KROUTER_PENDING_KEY_1 in ~/.dsh-krouter-keys.env.")
NO_WRITER = ("昨天没有封账：没有可用的模型。登录一个 AI 编程工具（如 Claude Code），或把 API key 贴到知识库的「自进化钥匙」页。"
             " / Yesterday was not sealed: no model. Log in to an AI coding CLI or paste an API key on the key page.")
