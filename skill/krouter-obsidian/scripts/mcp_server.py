#!/usr/bin/env python3
"""KRouter as an MCP server (standard library only): any MCP client can ask the vault, over stdio or HTTP.

Tools
- `krouter_ask(query, route="search")`: the router's receipt for one question — the page, its `how` line, the
  matching lines, or `recall: none` when the vault does not know. Routes: search (whole vault), preference,
  correction, memory, project, suggest.
- `krouter_status()`: whether the vault and the nightly job are healthy, and what the host must do if not.

The vault is `--vault`, else `OBSIDIAN_VAULT`, else the path the one-line install recorded (`~/.config/krouter/vault`).
Register it, e.g. for Claude Code: `claude mcp add krouter -- python3 ~/.agents/skills/krouter-obsidian/scripts/mcp_server.py`.

Over HTTP (a team server, or an app that only takes a remote MCP server), Streamable HTTP with JSON responses:

    python3 mcp_server.py --http 127.0.0.1:8787 --vault ~/team-vault --label team --token-file ~/.krouter-token

`POST /mcp` takes JSON-RPC; `GET /healthz` says whether the vault is there. It binds to 127.0.0.1 unless told
otherwise, and refuses to listen on any other address without `--token-file` (clients send
`Authorization: Bearer <token>`). The access log (stderr, one JSON line a request) holds a hash of each question,
never the question; questions are not written to the query log either, unless `--log-queries`. `--label` puts
`vault_label: <label>` at the top of every receipt, so an answer says which vault it came from.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from krouter_home import vault_path  # noqa: E402

VERSION = "1.3.0"
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


LABEL = ""                 # --label: which vault this server answers from, stamped on every receipt
MAX_BODY = 1_000_000       # bytes; a JSON-RPC call is a few hundred
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def labelled(text: str) -> str:
    return f"vault_label: {LABEL}\n{text}" if LABEL else text


def route(name: str, query: str, extra_env: dict | None = None) -> tuple[str, bool]:
    text, err = _route(name, query, extra_env)
    return labelled(text), err


def _route(name: str, query: str, extra_env: dict | None) -> tuple[str, bool]:
    vault = vault_path()
    if not vault:
        return ("No vault configured: run the KRouter one-line install, or set OBSIDIAN_VAULT for this server.", True)
    env = {**os.environ, "OBSIDIAN_VAULT": vault, **(extra_env or {})}
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
                  "serverInfo": {"name": "krouter", "title": f"KRouter ({LABEL})" if LABEL else "KRouter",
                                 "version": VERSION},
                  "instructions": INSTRUCTIONS + (f" This server answers from the '{LABEL}' vault "
                                                  "(`vault_label:` in each receipt); say which vault an answer "
                                                  "came from." if LABEL else "")}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        result = call(str(params.get("name") or ""), params.get("arguments") or {})
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve_stdio() -> int:
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


def _rpc_summary(msg) -> dict:
    """What the access log keeps of a JSON-RPC message: method, tool, and a hash of the question, never its text."""
    if not isinstance(msg, dict):
        return {}
    out = {"rpc": msg.get("method")}
    params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
    if msg.get("method") == "tools/call":
        out["tool"] = params.get("name")
        q = str((params.get("arguments") or {}).get("query") or "")
        if q:
            out["q_sha256"] = hashlib.sha256(q.encode("utf-8")).hexdigest()[:16]
    return out


def _origin_ok(origin: str, allowed: list[str]) -> bool:
    """No Origin (a CLI or server client), a loopback origin, or one named with --allow-origin (DNS rebinding guard)."""
    if not origin:
        return True
    if origin in allowed:
        return True
    return (urlsplit(origin).hostname or "") in LOOPBACK


def make_handler(token: str, allowed_origins: list[str], started: float):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = f"krouter/{VERSION}"

        def log_message(self, *_):  # 访问日志由 _log 写，一请求一行 JSON，不含问题原文
            pass

        def _log(self, code: int, t0: float, extra: dict | None = None) -> None:
            row = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "remote": self.client_address[0],
                   "method": self.command, "path": self.path, "status": code,
                   "ms": round((time.perf_counter() - t0) * 1000, 1), **(extra or {})}
            sys.stderr.write(json.dumps(row, ensure_ascii=False) + "\n")
            sys.stderr.flush()

        def _send(self, code: int, body: bytes = b"", ctype: str = "application/json", headers: dict | None = None):
            self.send_response(code)
            if body:
                self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _json(self, code: int, obj, headers: dict | None = None) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), headers=headers)

        def _reject(self, code: int, obj=None, headers: dict | None = None) -> None:
            """Refuse a POST before reading it: drain a body of sane size (so the client is not cut off mid-send),
            then answer and close, so leftover bytes never read as the next request."""
            try:
                left = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                left = 0
            if 0 < left <= 8 * MAX_BODY:
                while left > 0:
                    chunk = self.rfile.read(min(65536, left))
                    if not chunk:
                        break
                    left -= len(chunk)
            self.close_connection = True
            hdrs = {"Connection": "close", **(headers or {})}
            if obj is None:
                self._send(code, headers=hdrs)
            else:
                self._json(code, obj, headers=hdrs)

        def _authorized(self) -> bool:
            if not token:
                return True
            got = self.headers.get("Authorization", "")
            return got.startswith("Bearer ") and hmac.compare_digest(got[7:].strip().encode(), token.encode())

        def do_GET(self):  # noqa: N802
            t0 = time.perf_counter()
            path = urlsplit(self.path).path
            if path == "/healthz":
                vault = vault_path()
                ok = bool(vault) and Path(vault).expanduser().is_dir()
                self._json(200 if ok else 503, {"ok": ok, "version": VERSION, "label": LABEL or None,
                                                "uptime_s": round(time.time() - started)})
                return self._log(200 if ok else 503, t0)
            if path == "/mcp":  # no server-to-client stream: every reply comes back on its POST
                self._send(405, headers={"Allow": "POST"})
                return self._log(405, t0)
            self._send(404)
            self._log(404, t0)

        def do_DELETE(self):  # noqa: N802  stateless: there is no session to end
            t0 = time.perf_counter()
            self._send(405, headers={"Allow": "POST"})
            self._log(405, t0)

        def do_POST(self):  # noqa: N802
            t0 = time.perf_counter()
            if urlsplit(self.path).path != "/mcp":
                self._reject(404)
                return self._log(404, t0)
            if not _origin_ok(self.headers.get("Origin", ""), allowed_origins):
                self._reject(403, {"error": "origin not allowed"})
                return self._log(403, t0)
            if not self._authorized():
                self._reject(401, {"error": "missing or wrong bearer token"}, headers={"WWW-Authenticate": "Bearer"})
                return self._log(401, t0)
            proto = self.headers.get("MCP-Protocol-Version", "")
            if proto and proto not in PROTOCOLS:
                self._reject(400, {"error": f"unsupported MCP-Protocol-Version {proto}"})
                return self._log(400, t0)
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY:
                self._reject(413, {"error": f"body must be at most {MAX_BODY} bytes"})
                return self._log(413, t0)
            ctype = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if ctype != "application/json":
                self._reject(415, {"error": "Content-Type must be application/json"})
                return self._log(415, t0)
            raw = self.rfile.read(length)
            try:
                msg = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
                return self._log(400, t0)
            batch = isinstance(msg, list)
            replies = [r for r in (handle(m) if isinstance(m, dict) else
                                   {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
                                   for m in (msg if batch else [msg])) if r is not None]
            summary = _rpc_summary(msg[0] if batch and msg else msg)
            if not replies:  # only notifications or responses: accepted, nothing to say
                self._send(202)
                return self._log(202, t0, summary)
            self._json(200, replies if batch else replies[0])
            self._log(200, t0, summary)

    return Handler


def serve_http(addr: str, token_file: str, allowed_origins: list[str], log_queries: bool) -> int:
    host, sep, port = addr.rpartition(":")
    if not sep:
        host, port = "127.0.0.1", addr
    host = host.strip("[]") or "127.0.0.1"
    try:
        port_n = int(port)
    except ValueError:
        print(f"--http takes HOST:PORT, got {addr!r}", file=sys.stderr)
        return 2
    token = ""
    if token_file:
        try:
            token = Path(token_file).expanduser().read_text(encoding="utf-8").strip()
        except OSError as exc:
            print(f"cannot read --token-file: {exc}", file=sys.stderr)
            return 2
        if len(token) < 16:
            print("the token in --token-file must be at least 16 characters", file=sys.stderr)
            return 2
        if os.name != "nt" and Path(token_file).expanduser().stat().st_mode & 0o077:
            print(f"warning: {token_file} is readable by other users (chmod 600 it)", file=sys.stderr)
    if host not in LOOPBACK and not token:
        print(f"refusing to listen on {host}: anyone who can reach it could read the vault. "
              "Pass --token-file, or bind to 127.0.0.1.", file=sys.stderr)
        return 2
    if not log_queries:  # 团队服务器默认不把同事的问题原文写进查询日志
        os.environ["KROUTER_NO_QUERY_LOG"] = "1"
    started = time.time()
    if vault_path():  # 先建好索引，第一位提问的人不用等
        t0 = time.perf_counter()
        _route("search", "krouter index warm-up", {"KROUTER_NO_QUERY_LOG": "1"})
        print(f"index ready in {time.perf_counter() - t0:.1f} s", file=sys.stderr)
    server = ThreadingHTTPServer((host, port_n), make_handler(token, allowed_origins, started))
    server.daemon_threads = True
    print(json.dumps({"listening": f"http://{host}:{server.server_address[1]}/mcp", "label": LABEL or None,
                      "auth": "bearer" if token else "none (loopback only)"}), file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    global LABEL
    ap = argparse.ArgumentParser(description="KRouter MCP server: stdio by default, HTTP with --http.")
    ap.add_argument("--http", metavar="HOST:PORT", help="serve Streamable HTTP on this address instead of stdio")
    ap.add_argument("--token-file", default="", help="file holding the bearer token clients must send")
    ap.add_argument("--allow-origin", action="append", default=[], help="a browser Origin allowed to call (repeat)")
    ap.add_argument("--label", default=os.environ.get("KROUTER_LABEL", ""),
                    help="name of this vault, stamped on every receipt (e.g. team)")
    ap.add_argument("--vault", default="", help="the vault to serve (default: OBSIDIAN_VAULT, else the installed one)")
    ap.add_argument("--log-queries", action="store_true", help="HTTP: also write question text to the query log")
    args = ap.parse_args(argv)
    LABEL = args.label.strip()
    if args.vault:
        os.environ["OBSIDIAN_VAULT"] = str(Path(args.vault).expanduser().resolve())
    if args.http:
        return serve_http(args.http, args.token_file, args.allow_origin, args.log_queries)
    return serve_stdio()


if __name__ == "__main__":
    raise SystemExit(main())
