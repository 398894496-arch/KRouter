"""`krouter ask|status|note|mcp`: the same lookups from a terminal, and the MCP server."""

from __future__ import annotations

import argparse
import sys

from . import ROUTES, __version__, ask, note, router_dir, status


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="krouter", description="Ask your KRouter memory from a terminal.")
    ap.add_argument("--version", action="version", version=f"krouter {__version__}")
    ap.add_argument("--vault", default=None, help="the memory folder (default: the installed one)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask", help="look a question up")
    a.add_argument("question")
    a.add_argument("--route", default="search", choices=ROUTES)
    sub.add_parser("status", help="health of the memory and the nightly job")
    n = sub.add_parser("note", help="write one line into the memory")
    n.add_argument("text")
    n.add_argument("--kind", default="note", choices=("decision", "correction", "note"))
    m = sub.add_parser("mcp", help="run the MCP server (stdio; --http for a team server)")
    m.add_argument("rest", nargs=argparse.REMAINDER)
    args = ap.parse_args(argv)
    if args.cmd == "ask":
        print(ask(args.question, args.route, args.vault))
    elif args.cmd == "status":
        print(status(args.vault))
    elif args.cmd == "note":
        print(note(args.text, args.kind, args.vault))
    else:
        sys.path.insert(0, str(router_dir()))
        import mcp_server

        return mcp_server.main((["--vault", args.vault] if args.vault else []) + args.rest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
