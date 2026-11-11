#!/usr/bin/env python3
"""Claude Desktop extension entry point: start KRouter's MCP server (stdio) on the memory folder the user picked.

An empty choice, or the placeholder left unexpanded when nothing was picked, means "the folder the KRouter install
recorded" (`~/.config/krouter/vault`), which `mcp_server.py` falls back to on its own.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main(argv: list[str]) -> int:
    args = list(argv)
    if "--vault" in args:
        i = args.index("--vault")
        value = args[i + 1] if i + 1 < len(args) else ""
        if not value.strip() or value.strip().startswith("${"):
            del args[i:i + 2]
    import mcp_server

    return mcp_server.main(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
