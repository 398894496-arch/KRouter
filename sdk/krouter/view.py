"""`krouter view`: a read-only web page about the memory, on this machine only.

    krouter view                  # prints http://127.0.0.1:<free port>/ and waits; Ctrl-C stops it
    krouter view --open           # the same, and opens it in the default browser (nothing opens without this flag)
    krouter view --demo           # on a throwaway sample memory instead of yours

What it is: Python's standard library HTTP server and a hand-written page (`view_ui/`), nothing downloaded, nothing
installed. It binds 127.0.0.1 only (there is no option to bind anything else), answers GET and HEAD only (every other
method gets 405: there is no endpoint that writes, so the page cannot change the memory), refuses requests whose Host
header is not the loopback address it listens on (so a web page on another site cannot read it through your browser),
and sends a Content-Security-Policy that allows nothing from outside: no script, font, style or image is ever loaded
from another address, and the page makes no request to any other.

What it shows: the pages (a list that pages through the memory, with search), one page with what replaced it and what it
connects to, the connections around a page and why each exists, the experience cards and how they were used, what the
last nights did, and a box that takes a sentence and shows what `krouter why` says about it.

The recall cache (outside the memory folder, rebuildable) is the only thing it writes: it keeps it current in a
background thread, so a page you edit shows up within about twenty seconds.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import __version__
from .viewdata import MAX_LIST, REFRESH_EVERY, Store
from . import why as whymod

UI = Path(__file__).resolve().parent / "view_ui"
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/app.css": ("app.css", "text/css; charset=utf-8")}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
BIND = "127.0.0.1"  # the only address it ever listens on
MAX_Q = 500


class Handler(BaseHTTPRequestHandler):
    server_version = "krouter-view"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # ---- plumbing ----

    def log_message(self, fmt, *args):  # quiet unless --verbose
        if getattr(self.server, "verbose", False):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _send(self, status: int, body: bytes, ctype: str, head_only: bool = False, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _json(self, status: int, obj, head_only: bool = False) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False, default=list).encode("utf-8"),
                   "application/json; charset=utf-8", head_only)

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        port = self.server.server_address[1]
        return host in (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}")

    # ---- methods: only GET and HEAD read; everything else is refused ----

    def do_GET(self):
        self._serve(False)

    def do_HEAD(self):
        self._serve(True)

    def _refuse(self):
        self.close_connection = True  # an unread request body must not be taken for the next request
        self._send(405, b'{"error": "this page is read only"}', "application/json; charset=utf-8",
                   extra={"Allow": "GET, HEAD", "Connection": "close"})

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _refuse

    # ---- routes ----

    def _serve(self, head_only: bool) -> None:
        if not self._host_ok():
            return self._send(403, b'{"error": "unexpected Host header"}', "application/json; charset=utf-8", head_only)
        url = urlsplit(self.path)
        path = url.path
        q = {k: v[0] for k, v in parse_qs(url.query, keep_blank_values=True, max_num_fields=20).items()}
        if path in STATIC:
            name, ctype = STATIC[path]
            try:
                body = (UI / name).read_bytes()
            except OSError:
                return self._json(500, {"error": "the page files are missing from this install"}, head_only)
            return self._send(200, body, ctype, head_only)
        if path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon", head_only)
        if not path.startswith("/api/"):
            return self._json(404, {"error": "not found"}, head_only)
        try:
            status, obj = self._api(path, q)
        except Exception as exc:  # noqa: BLE001  one request failing must not take the viewer down
            status, obj = 500, {"error": f"{type(exc).__name__}: {exc}"[:300]}
        self._json(status, obj, head_only)

    def _api(self, path: str, q: dict):
        store: Store = self.server.store
        num = lambda k, d: int(q.get(k) or d) if str(q.get(k) or d).lstrip("-").isdigit() else d  # noqa: E731
        text = lambda k: (q.get(k) or "")[:MAX_Q]  # noqa: E731
        if path == "/api/config":
            return 200, {"version": __version__, "lang": store.lang, "vault": "sample memory" if self.server.demo else str(store.vault),
                         "demo": self.server.demo,
                         "read_only": True, "refresh_every": REFRESH_EVERY}
        if path == "/api/stats":
            return 200, store.stats()
        if path == "/api/pages":
            return 200, store.pages(text("q"), text("tier"), text("status"), "recent" if q.get("sort") == "recent" else "path",
                                    num("offset", 0), min(num("limit", 50), MAX_LIST))
        if path == "/api/page":
            page = store.page(text("rel"))
            return (200, page) if page else (404, {"error": "no such page in this memory"})
        if path == "/api/graph":
            g = store.neighbors(text("rel"))
            return (200, g) if g else (404, {"error": "no such page in this memory"})
        if path == "/api/experience":
            return 200, store.experience()
        if path == "/api/recalled":
            return 200, store.recalled()
        if path == "/api/nightly":
            return 200, store.nightly(lang="en" if q.get("lang") == "en" else "")
        if path == "/api/why":
            lang = q.get("lang") if q.get("lang") in ("en", "zh") else None
            e = whymod.explain(store.vault, text("q"), lang, refresh=False, store=store)
            return 200, {"explanation": e, "blocks": whymod.blocks(e), "text": whymod.render(e), "pages": whymod.pages_in(e)}
        return 404, {"error": "not found"}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # a fixed --port can be taken again right after Ctrl-C (the old connections sit in TIME_WAIT); not on Windows,
    # where the same option would let a second program share the port
    allow_reuse_address = sys.platform != "win32"

    def __init__(self, store: Store, port: int = 0, demo: bool = False, verbose: bool = False):
        super().__init__((BIND, port), Handler)
        self.store, self.demo, self.verbose = store, demo, verbose
        self._stop = threading.Event()

    @property
    def url(self) -> str:
        return f"http://{BIND}:{self.server_address[1]}/"

    def keep_fresh(self) -> threading.Thread:
        def loop():
            while not self._stop.wait(REFRESH_EVERY):
                try:
                    self.store.refresh(force=True)
                except Exception:  # noqa: BLE001  a refresh that fails is tried again next round
                    pass

        th = threading.Thread(target=loop, daemon=True)
        th.start()
        return th

    def shutdown(self) -> None:
        self._stop.set()
        super().shutdown()


def run(vault, port: int = 0, open_browser: bool = False, demo: bool = False, verbose: bool = False,
        lang: str = "en") -> int:
    """Serve until Ctrl-C. Prints the address; opens a browser only when `open_browser`."""
    import os
    import shutil
    import tempfile

    tmp = None
    if demo:
        from . import sample

        tmp = Path(tempfile.mkdtemp(prefix="krouter-view-demo-"))
        os.environ.update({"KROUTER_NO_QUERY_LOG": "1", "KROUTER_CACHE_DIR": str(tmp / "cache"),
                           "KROUTER_STATE_DIR": str(tmp / "state")})  # the demo touches nothing of yours
        vault = sample.build(tmp, lang)
    if not vault:
        print("set KROUTER_VAULT to your memory folder (or pass --vault), or run `krouter view --demo`", file=sys.stderr)
        return 2
    vault = Path(vault).expanduser()
    if not vault.is_dir():
        print(f"memory folder not found: {vault}", file=sys.stderr)
        return 1
    store = Store(vault)
    t0 = time.time()
    print(f"indexing {vault} …", file=sys.stderr, flush=True)
    stats = store.refresh(force=True)
    print(f"indexed {stats.get('docs', '?')} pages in {time.time() - t0:.1f}s", file=sys.stderr, flush=True)
    try:
        srv = Server(store, port, demo, verbose)
    except OSError as exc:
        print(f"cannot listen on {BIND}:{port}: {exc}", file=sys.stderr)
        return 1
    srv.keep_fresh()
    print(f"KRouter view: {srv.url}", flush=True)
    print("read only, this machine only; Ctrl-C to stop" + (" (demo memory, deleted on exit)" if demo else ""), flush=True)
    if open_browser:
        webbrowser.open(srv.url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    return 0
