#!/usr/bin/env python3
"""KRouter as an MCP server (stdio, standard library only): any MCP client can ask the vault.

Tools
- `krouter_ask(query, route="search")`: the router's receipt for one question — the page, its `how` line, the
  matching lines, or `recall: none` when the vault does not know. Routes: search (whole vault), preference,
  correction, memory, project, suggest.
- `krouter_status()`: whether the vault and the nightly job are healthy, and what the host must do if not.

The vault is `OBSIDIAN_VAULT`, else the path the one-line install recorded (`~/.config/krouter/vault`).
Register it, e.g. for Claude Code: `claude mcp add krouter -- python3 ~/.agents/skills/krouter-obsidian/scripts/mcp_server.py`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from krouter_home import vault_path  # noqa: E402

VERSION = "1.1.1"
PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
ROUTES = ("search", "preference", "correction", "memory", "project", "suggest")
INSTRUCTIONS = (
    "KRouter answers from the user's own Obsidian vault: decisions, rules, corrections and past sessions. "
    "Call krouter_ask before answering a question about how this user does things, what was decided before, or what "
    "was corrected. Answer from the `how` line and cite the page path; open the page only when `how` does not close "
    "the question. A page marked superseded is out of force. `recall: none` means the vault does not know: say so "
    "instead of guessing; `recall_note:` means only part of the question matched: say that too. If a receipt has `host_action:`, tell the user that line."
)
TOOLS = [
    {
        "name": "krouter_ask",
        "description": "Look up the user's vault for one question. Returns the best page with a one-line answer "
                       "(`how`), the matching lines and a receipt, or `recall: none` when the vault has nothing on it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The question or a short noun, in the user's words."},
                "route": {"type": "string", "enum": list(ROUTES), "default": "search",
                          "description": "search = whole vault; correction = what was corrected; preference = "
                                         "how the user wants things done; memory, project; suggest = alias hints."},
            },
            "required": ["query"],
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "krouter_status",
        "description": "Health of the vault and the nightly job; says what the user must do when something is off.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
]


def route(name: str, query: str) -> tuple[str, bool]:
    vault = vault_path()
    if not vault:
        return ("No vault configured: run the KRouter one-line install, or set OBSIDIAN_VAULT for this server.", True)
    env = {**os.environ, "OBSIDIAN_VAULT": vault}
    try:
        proc = subprocess.run([sys.executable, str(HERE / "route_knowledge.py"), name, query], env=env,
                              capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return ("KRouter timed out after 120 s.", True)
    text = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return ((text + "\n" + (proc.stderr or "")).strip()[-2000:] or f"KRouter exited {proc.returncode}", True)
    return (text, False)


def call(name: str, args: dict) -> dict:
    if name == "krouter_ask":
        query = str(args.get("query") or "").strip()
        rname = str(args.get("route") or "search")
        if not query:
            text, err = "query is required", True
        elif rname not in ROUTES:
            text, err = f"route must be one of {', '.join(ROUTES)}", True
        else:
            text, err = route(rname, query)
    elif name == "krouter_status":
        text, err = route("status", "")
    else:
        return {"content": [{"type": "text", "text": f"unknown tool {name}"}], "isError": True}
    return {"content": [{"type": "text", "text": text}], "isError": err}


def handle(msg: dict) -> dict | None:
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:  # notification
        return None
    params = msg.get("params") or {}
    if method == "initialize":
        asked = params.get("protocolVersion")
        result = {"protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
                  "capabilities": {"tools": {"listChanged": False}},
                  "serverInfo": {"name": "krouter", "title": "KRouter", "version": VERSION},
                  "instructions": INSTRUCTIONS}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        result = call(str(params.get("name") or ""), params.get("arguments") or {})
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            reply = handle(msg) if isinstance(msg, dict) else None
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
