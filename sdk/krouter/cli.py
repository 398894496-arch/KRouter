"""`krouter ask|why|view|status|doctor|note|kb|demo|mcp`: the same lookups from a terminal, an explanation of one, a read-only page about the memory, a one-verdict check, the knowledge base, and the MCP server."""

from __future__ import annotations

import argparse
import os
import sys

from . import ROUTES, __version__, ask, note, router_dir, status


def env_lang() -> str:
    """en or zh from LC_ALL / LC_MESSAGES / LANG (the first one set; C and POSIX say nothing); en when none does."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var, "").strip().lower()
        if val and val.split(".")[0] not in ("c", "posix"):
            return "zh" if val.startswith("zh") else "en"
    return "en"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="krouter", description="Ask your KRouter memory from a terminal.")
    ap.add_argument("--version", action="version", version=f"krouter {__version__}")
    ap.add_argument("--vault", default=None, help="the memory folder (default: the installed one)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask", help="look a question up")
    a.add_argument("question")
    a.add_argument("--route", default="search", choices=ROUTES)
    w = sub.add_parser("why", help="explain how a lookup came out: the alias or words that matched, why each page sits where it does, "
                                   "why the confidence is that, what came along a connection, what replaced what (read only)")
    w.add_argument("question")
    w.add_argument("--lang", choices=("en", "zh"), default=None, help="language of the explanation (default: the memory's)")
    w.add_argument("--json", action="store_true", help="the structured explanation instead of text")
    v = sub.add_parser("view", help="a read-only page about the memory on this machine: pages, connections, experience cards, "
                                    "what last night did, and a box that runs `why` (prints the address; add --open to open it)")
    v.add_argument("--port", type=int, default=0, help="port on 127.0.0.1 (default: a free one)")
    v.add_argument("--open", action="store_true", help="also open the address in the default browser (nothing opens without this)")
    v.add_argument("--demo", action="store_true", help="show a throwaway sample memory instead of yours")
    v.add_argument("--lang", choices=("en", "zh"), default=None, help="language of the --demo memory")
    v.add_argument("--verbose", action="store_true", help="log each request to stderr")
    sub.add_parser("status", help="health of the memory and the nightly job (the raw receipt)")
    sub.add_parser("doctor", help="one verdict: OK, or what is missing and the command that fixes it")
    n = sub.add_parser("note", help="write one line into the memory")
    n.add_argument("text")
    n.add_argument("--kind", default="note", choices=("decision", "correction", "note"))
    d = sub.add_parser("demo", help="decide, change your mind, ask: on a throwaway memory, no install, no key")
    d.add_argument("--lang", choices=("en", "zh"), default=env_lang())
    d.add_argument("--keep", action="store_true", help="keep the demo memory to look at")
    k = sub.add_parser("kb", help="the knowledge base: declare reference folders (add / remove / list), see folders that "
                                  "look like reference material (suggest), import a PDF, Word or HTML file (import)")
    k.add_argument("rest", nargs=argparse.REMAINDER)
    m = sub.add_parser("mcp", help="run the MCP server (stdio; --http for a team server)")
    m.add_argument("rest", nargs=argparse.REMAINDER)
    args = ap.parse_args(argv)
    if args.cmd == "ask":
        print(ask(args.question, args.route, args.vault))
    elif args.cmd == "status":
        print(status(args.vault))
    elif args.cmd in ("why", "view"):
        sys.path.insert(0, str(router_dir()))
        from krouter_home import vault_path

        vault = args.vault or vault_path()
        if args.cmd == "why":
            if not vault:
                print("set KROUTER_VAULT to your memory folder, or pass --vault", file=sys.stderr)
                return 2
            from .why import run as why_run

            return why_run(vault, args.question, args.lang, args.json)
        from .view import run as view_run

        return view_run(vault, args.port, args.open, args.demo, args.verbose, args.lang or env_lang())
    elif args.cmd == "doctor":
        from .doctor import run as doctor

        return doctor(args.vault)
    elif args.cmd == "demo":
        from .demo import run

        return run(args.lang, args.keep)
    elif args.cmd == "note":
        print(note(args.text, args.kind, args.vault))
    elif args.cmd == "kb":
        sys.path.insert(0, str(router_dir()))
        import kb

        return kb.main((["--vault", args.vault] if args.vault else []) + args.rest)
    else:
        sys.path.insert(0, str(router_dir()))
        import mcp_server

        return mcp_server.main((["--vault", args.vault] if args.vault else []) + args.rest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
