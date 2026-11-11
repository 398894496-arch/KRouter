#!/usr/bin/env python3
"""KRouter's MCP tools from a shell, for a host that cannot be given an MCP server (a Claude Code subagent here):

    kr_cli.py TOOL '{"json": "arguments"}'      # TOOL is krouter_ask, krouter_note, krouter_status, krouter_correct, krouter_learn
    kr_cli.py --context                         # server instructions + tool descriptions + the SessionStart digest

It calls the same functions the MCP server answers with (`mcp_server.call`), on the memory folder in KROUTER_VAULT, and
appends every call to $KR_CALL_LOG. The host sees the same words an MCP host would show it, but it reaches the tools
through Bash: an approximation of a Claude Code session with the MCP server, not that session.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skill/krouter/scripts"))


def context() -> str:
    import mcp_server as m

    parts = ["## KRouter (MCP server instructions)\n" + m.INSTRUCTIONS + m.CORRECT_INSTRUCTION + m.LEARN_INSTRUCTION,
             "## KRouter tools (call one with: $KR <tool> '<json arguments>')"]
    for t in m.tools():
        parts.append(f"- {t['name']}: {t['description']}\n  arguments (JSON schema): {json.dumps(t['inputSchema'])}")
    hook = subprocess.run([sys.executable, str(ROOT / "skill/krouter/scripts/session_hook.py"), "start"], input="{}",
                          capture_output=True, text=True, env=os.environ)
    try:
        extra = json.loads(hook.stdout)["hookSpecificOutput"]["additionalContext"]
    except (ValueError, KeyError):
        extra = ""
    parts.append("## SessionStart hook output (added to the session's context)\n" + extra)
    return "\n\n".join(parts)


def main() -> int:
    if sys.argv[1:2] == ["--context"]:
        print(context())
        return 0
    import mcp_server as m

    name = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    res = m.call(name, args)
    text = res["content"][0]["text"]
    log = os.environ.get("KR_CALL_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "tool": name, "arguments": args, "error": bool(res.get("isError")),
                                "result": text[:600]}, ensure_ascii=False) + "\n")
    print(text)
    return 1 if res.get("isError") else 0


if __name__ == "__main__":
    raise SystemExit(main())
