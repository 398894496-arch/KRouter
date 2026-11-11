#!/usr/bin/env python3
"""Deny Clippings mutation and Obsidian restart. Vault root from OBSIDIAN_VAULT."""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = (os.environ.get("KROUTER_VAULT") or os.environ.get("OBSIDIAN_VAULT", "")).rstrip("/")
INBOX = f"{ROOT}/Clippings" if ROOT else ""

DENY = {
    "permission": "deny",
    "user_message": "Execution gate: do not move, edit, or delete Clippings originals; do not quit or reload Obsidian.",
    "agent_message": "Vault execution gate denied this action.",
}
ALLOW = {"permission": "allow"}


def load() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def tool_name(payload: dict) -> str:
    return str(payload.get("tool_name") or payload.get("tool") or "")


def command_text(payload: dict) -> str:
    return str(payload.get("command") or payload.get("command_line") or "")


def path_text(payload: dict) -> str:
    parts = []
    for key in ("path", "file_path", "target_file"):
        for src in (payload, payload.get("tool_input") or {}, payload.get("input") or {}):
            if isinstance(src, dict) and isinstance(src.get(key), str):
                parts.append(src[key])
    return " ".join(parts)


def hits_inbox(text: str) -> bool:
    if not INBOX:
        return False
    return INBOX in text.replace("\\", "/")


def hits_app_restart(text: str) -> bool:
    t = text.lower()
    app = "obsid" + "ian"
    if re.search(r"\b(killall|pkill)\b", t) and app in t:
        return True
    if ("quit app" in t) and (app in t):
        return True
    if (app + " --reload") in t:
        return True
    return False


def should_deny(payload: dict) -> bool:
    command = command_text(payload)
    path = path_text(payload)
    tool = tool_name(payload)
    if hits_app_restart(command):
        return True
    mutating = any(name in tool for name in ("Delete", "Write", "StrReplace", "EditNotebook"))
    destructive = bool(re.search(r"\b(mv|rm|rmdir|unlink|rename|trash)\b", command))
    if (mutating or destructive) and (hits_inbox(command) or hits_inbox(path)):
        return True
    return False


def main() -> None:
    payload = load()
    sys.stdout.write(json.dumps(DENY if should_deny(payload) else ALLOW, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
