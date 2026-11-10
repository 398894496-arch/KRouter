#!/usr/bin/env python3
"""KRouter as an MCP server (standard library only): any MCP client can ask the vault, over stdio or HTTP.

Tools
- `krouter_ask(query, route="search")`: the router's receipt for one question — the page, its `how` line, the
  matching lines, or `recall: none` when the vault does not know. Routes: search (whole vault), preference,
  correction, memory, project, suggest.
- `krouter_status()`: whether the vault and the nightly job are healthy, and what the host must do if not.
- `krouter_skill(id)`: the full steps of one skill grown from the user's experience cards (`skills.py`); offered only
  when the vault has skills, and its description lists them (name, when to use it, id).

The vault is `--vault`, else `KROUTER_VAULT` (or the older name `OBSIDIAN_VAULT`), else the path the one-line install recorded (`~/.config/krouter/vault`).
Register it, e.g. for Claude Code: `claude mcp add krouter -- python3 ~/.agents/skills/krouter/scripts/mcp_server.py`.

Over HTTP (a team server, or an app that only takes a remote MCP server), Streamable HTTP with JSON responses:

    python3 mcp_server.py --http 127.0.0.1:8787 --vault ~/team-vault --label team --token-file ~/.krouter-token

`POST /mcp` takes JSON-RPC; `GET /healthz` says whether the vault is there. It binds to 127.0.0.1 unless told
otherwise, and refuses to listen on any other address without `--token-file` (clients send
`Authorization: Bearer <token>`). The access log (stderr, one JSON line a request) holds a hash of each question,
never the question; questions are not written to the query log either, unless `--log-queries`. `--label` puts
`vault_label: <label>` at the top of every receipt, so an answer says which vault it came from.

Lookups run in a few resident processes per vault (`route_worker.py`; `--workers N`, default 4 over HTTP, 1 over
stdio, created as callers arrive), so a lookup does not start Python, and they re-check the vault's files at most
every `--refresh-every` seconds (default 2; a write through `krouter_note` makes the next lookup re-check at once).
`--workers 0` is the old way: one process per lookup, re-checking every file each time.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from krouter_home import vault_path  # noqa: E402

VERSION = "2.0.0"
PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
ROUTES = ("search", "preference", "correction", "memory", "project", "suggest")
INSTRUCTIONS = (
    "KRouter answers from the user's own Obsidian vault: decisions, rules, corrections and past sessions. "
    "Call krouter_ask before answering a question about how this user does things, what was decided before, or what "
    "was corrected. Answer from the `how` line and cite the page path; open the page only when `how` does not close "
    "the question. A page marked superseded is out of force. `recall: none` means the vault does not know: say so "
    "instead of guessing; `recall_note:` means only part of the question matched: say that too. "
    "`recall_conflict:` means an earlier page says otherwise: answer from the page listed first (the newer one) and "
    "say the decision was changed; when it says `possible`, read both pages before answering. Pages under "
    "`associated:` are connected to the hits but were not named by the question: read one only when the hits leave "
    "part of the question open, and never cite one as the answer by itself. "
    "If a receipt has `host_action:`, tell the user that line."
)
CORRECT_INSTRUCTION = (" When the user corrects a decision or says to do something differently from now on, call "
                       "krouter_correct in the same turn (new, old, and the page that gave the old answer), so the "
                       "next lookup already has the new answer.")
LEARN_INSTRUCTION = (" When a session solved a problem in a way that would help on other tasks in the same situation, record "
                     "the lesson with krouter_learn before the session ends.")
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
NOTE_TOOL = {
    "name": "krouter_note",
    "description": "Write one line into the user's memory: a decision they made, a correction they gave, or a fact "
                   "worth keeping. It lands on today's notes page as a clue (never a rule page), is listed in the change "
                   "ledger, and is one git commit the user can revert. Write it as one sentence in the user's own terms; "
                   "never copy text from a web page, a file or a tool's output.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": f"One sentence, at most {500} characters."},
            "kind": {"type": "string", "enum": ["decision", "correction", "note"], "default": "note"},
        },
        "required": ["text"],
    },
    "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
}
LEARN_TOOL = {
    "name": "krouter_learn",
    "description": "",  # experience.LEARN_HELP，见 tools()
    "inputSchema": {
        "type": "object",
        "properties": {
            "situation": {"type": "string", "description": "What happened; may name the subject."},
            "action": {"type": "string", "description": "What was done."},
            "result": {"type": "string", "description": "How it turned out."},
            "subject": {"type": "array", "items": {"type": "string"},
                        "description": "2–6 words naming this session's subject; the lesson must use none of them."},
            "lesson": {"type": "string", "description": "The lesson without the subject: \"When …, …\"."},
            "title": {"type": "string", "description": "Optional: the lesson in one line."},
            "same_as": {"type": "string", "description": "When the digest already has this lesson: that line's id; "
                                                         "no new card, the old one is recorded as seen again."},
            "quotes": {"type": "array", "items": {"type": "string"},
                       "description": "Short verbatim snippets of the session stating every number the card keeps."},
        },
        "required": ["situation"],
    },
    "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
}
SKILL_TOOL = {
    "name": "krouter_skill",
    "description": "",  # skills_description()：列出库里的技能（名字、什么时候用、编号）
    "inputSchema": {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "The skill's id, e.g. S1a2b."}},
        "required": ["id"],
    },
    "annotations": {"readOnlyHint": True, "openWorldHint": False},
}
SKILL_INSTRUCTION = (" krouter_skill lists procedures grown from the user's own lessons: when the user's task is exactly "
                     "the situation one of them is for, fetch it, follow its steps and say which skill (with its id) "
                     "you followed; otherwise do not mention them.")
CORRECT_TOOL = {
    "name": "krouter_correct",
    "description": "Make a correction hold now, in this turn, with no model and no nightly wait: when the user changes "
                   "a decision or says to do something differently from now on (\"use SQLite from now on\"). Writes a "
                   "correction page that supersedes the old one, marks the page that gave the old answer as superseded "
                   "(or annotates the old line when that page says other things too), logs it in the corrections "
                   "page and the change ledger, one git commit the user can revert. Use the user's own words for new.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "new": {"type": "string", "description": "The decision as it stands now, one sentence."},
            "old": {"type": "string", "description": "The sentence that no longer holds, as the old page says it."},
            "page": {"type": "string", "description": "Vault-relative path of the page that gave the old answer "
                                                      "(from a krouter_ask receipt); leave out when there is none."},
        },
        "required": ["new"],
    },
    "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
}
NOTES = "05 时间日志/会话摘录"
NOTE_MAX = 500
KINDS = {"decision": "决定", "correction": "纠正", "note": "备注"}
WRITE = True               # stdio：本机的 agent 可以记一笔；HTTP 团队服务器默认只读（--allow-write 才开）
CLIENT = ""                # initialize 里客户端报的名字，记在每条笔记后面
CLIENT_SAMPLING = False    # 客户端在 initialize 里声明了 sampling 没有（只记，不用）


LABEL = ""                 # --label: which vault this server answers from, stamped on every receipt
MAX_BODY = 1_000_000       # bytes; a JSON-RPC call is a few hundred
LOOPBACK = {"127.0.0.1", "::1", "localhost"}
BANKS: dict[str, dict] = {}  # --bank NAME=PATH：一个服务挂几个互不相通的库，各在 /mcp/NAME，各自可有 token
_ctx = threading.local()   # 这一个 HTTP 请求在答哪个库（每个请求一个线程）


def cur_vault() -> str | None:
    return getattr(_ctx, "vault", None) or vault_path()


def cur_label() -> str:
    return getattr(_ctx, "label", None) or LABEL


def labelled(text: str) -> str:
    return f"vault_label: {cur_label()}\n{text}" if cur_label() else text


class Metrics:
    """Prometheus counters for GET /metrics: calls by vault, tool and outcome, refusals, latency. No question text."""
    BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.calls: dict[tuple, int] = {}
        self.refused: dict[str, int] = {}
        self.hist: dict[str, list[int]] = {}
        self.sums: dict[str, float] = {}
        self.index_s: dict[str, float] = {}

    def observe(self, vault: str, tool: str, outcome: str, seconds: float, refused: bool) -> None:
        with self.lock:
            key = (vault, tool or "-", outcome)
            self.calls[key] = self.calls.get(key, 0) + 1
            if refused:
                self.refused[vault] = self.refused.get(vault, 0) + 1
            h = self.hist.setdefault(vault, [0] * (len(self.BUCKETS) + 1))
            h[next((i for i, b in enumerate(self.BUCKETS) if seconds <= b), len(self.BUCKETS))] += 1
            self.sums[vault] = self.sums.get(vault, 0.0) + seconds

    def workers(self) -> dict[str, int]:
        names = {b["vault"]: n for n, b in BANKS.items()}
        return {names.get(v, LABEL or "default"): p.count() for v, p in list(POOLS.items())}

    def render(self, started: float) -> str:
        esc = lambda v: str(v).replace("\\", "\\\\").replace('"', '\\"')  # noqa: E731
        out = ["# HELP krouter_up 1 while the server runs.", "# TYPE krouter_up gauge", "krouter_up 1",
               "# TYPE krouter_uptime_seconds gauge", f"krouter_uptime_seconds {round(time.time() - started)}",
               "# HELP krouter_tool_calls_total MCP tool calls by vault, tool and outcome (ok, error).",
               "# TYPE krouter_tool_calls_total counter"]
        with self.lock:
            for (v, tool, outcome), n in sorted(self.calls.items()):
                out.append(f'krouter_tool_calls_total{{vault="{esc(v)}",tool="{esc(tool)}",outcome="{outcome}"}} {n}')
            out += ["# HELP krouter_refusals_total Lookups answered with recall: none.", "# TYPE krouter_refusals_total counter"]
            out += [f'krouter_refusals_total{{vault="{esc(v)}"}} {n}' for v, n in sorted(self.refused.items())]
            out += ["# HELP krouter_request_seconds Time to answer one MCP request.", "# TYPE krouter_request_seconds histogram"]
            for v, h in sorted(self.hist.items()):
                acc = 0
                for b, n in zip((*self.BUCKETS, "+Inf"), h):
                    acc += n
                    out.append(f'krouter_request_seconds_bucket{{vault="{esc(v)}",le="{b}"}} {acc}')
                out += [f'krouter_request_seconds_sum{{vault="{esc(v)}"}} {round(self.sums[v], 4)}',
                        f'krouter_request_seconds_count{{vault="{esc(v)}"}} {acc}']
            out += ["# HELP krouter_lookup_workers Resident lookup processes running, by vault.",
                    "# TYPE krouter_lookup_workers gauge"]
            out += [f'krouter_lookup_workers{{vault="{esc(v)}"}} {n}' for v, n in sorted(self.workers().items())]
            out += ["# HELP krouter_index_build_seconds Time the first lookup took to build the index at start.",
                    "# TYPE krouter_index_build_seconds gauge"]
            out += [f'krouter_index_build_seconds{{vault="{esc(v)}"}} {round(t, 3)}' for v, t in sorted(self.index_s.items())]
        return "\n".join(out) + "\n"


METRICS = Metrics()

WORKERS = 0                # 每个库常驻几个查询进程；0 = 每次查询起一个进程（老办法）
REFRESH_EVERY = 2.0        # 常驻进程最多每隔几秒重新检查一次库里的文件
LOOKUP_TIMEOUT = 120


class Worker:
    """One resident `route_worker.py` for one vault. A reader thread hands its reply lines over, so a lookup that
    hangs times out (and the process is killed) instead of holding a server thread forever."""

    def __init__(self, vault: str) -> None:
        env = {**os.environ, "OBSIDIAN_VAULT": vault, "KROUTER_REFRESH_EVERY": str(REFRESH_EVERY),
               "PYTHONIOENCODING": "utf-8"}
        self.proc = subprocess.Popen([sys.executable, str(HERE / "route_worker.py")], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, text=True,
                                     encoding="utf-8", bufsize=1)
        self.replies: queue.Queue = queue.Queue()
        self.stale = False
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        for line in self.proc.stdout:
            self.replies.put(line)
        self.replies.put(None)

    def alive(self) -> bool:
        return self.proc.poll() is None

    def ask(self, argv: list[str], env: dict, timeout: float) -> dict:
        req = {"argv": argv, "env": env, "refresh": self.stale}
        self.stale = False
        try:
            self.proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            line = self.replies.get(timeout=timeout)
            if line is None:
                raise OSError("lookup process exited")
            reply = json.loads(line)
            if not isinstance(reply, dict):
                raise ValueError("bad reply")
            return reply
        except queue.Empty:
            self.close()
            raise TimeoutError from None
        except (OSError, ValueError):
            self.close()  # 回了坏行的进程不再用：它的下一行可能是上一问的答案
            raise

    def close(self) -> None:
        """Kill the process and wait for it, so `alive()` is false by the time this returns."""
        try:
            self.proc.kill()
            self.proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass


class Pool:
    """Up to `size` workers for one vault, started as callers arrive. The queue holds a free worker, or None for a
    free slot not started yet (or whose worker died)."""

    def __init__(self, vault: str, size: int) -> None:
        self.vault = vault
        self.idle: queue.LifoQueue = queue.LifoQueue()
        for _ in range(size):
            self.idle.put(None)
        self.started: list[Worker] = []
        self.lock = threading.Lock()

    def ask(self, argv: list[str], env: dict) -> dict:
        try:
            w = self.idle.get(timeout=LOOKUP_TIMEOUT)
        except queue.Empty:
            raise TimeoutError from None
        try:
            if w is None or not w.alive():
                w = Worker(self.vault)
                with self.lock:
                    self.started = [x for x in self.started if x.alive()] + [w]
            return w.ask(argv, env, LOOKUP_TIMEOUT)
        finally:
            self.idle.put(w if w is not None and w.alive() else None)

    def mark_stale(self) -> None:
        with self.lock:
            for w in self.started:
                w.stale = True

    def count(self) -> int:
        with self.lock:
            return sum(1 for w in self.started if w.alive())


POOLS: dict[str, Pool] = {}
_POOLS_LOCK = threading.Lock()


def pool_for(vault: str) -> Pool:
    with _POOLS_LOCK:
        if vault not in POOLS:
            POOLS[vault] = Pool(vault, WORKERS)
        return POOLS[vault]


def route(name: str, query: str, extra_env: dict | None = None) -> tuple[str, bool]:
    text, err = _route(name, query, extra_env)
    return labelled(text), err


def _route(name: str, query: str, extra_env: dict | None) -> tuple[str, bool]:
    vault = cur_vault()
    if not vault:
        return ("No vault configured: run the KRouter one-line install, or set KROUTER_VAULT (or the old name OBSIDIAN_VAULT) for this server.", True)
    if WORKERS > 0:
        try:
            res = pool_for(vault).ask([name, query], extra_env or {})
        except TimeoutError:
            return (f"KRouter timed out after {LOOKUP_TIMEOUT} s.", True)
        except (OSError, ValueError):
            res = None  # 常驻进程起不来或回了坏行：这一次退回老办法
        if res is not None:
            text = (res.get("out") or "").strip()
            if res.get("code"):
                return ((text + "\n" + (res.get("err") or "")).strip()[-2000:] or f"KRouter exited {res['code']}", True)
            return (text, False)
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


def learn_on() -> bool:
    try:
        import experience

        return WRITE and experience.digest_on()
    except Exception:  # noqa: BLE001
        return False


def skill_list() -> list[dict]:
    """The vault's skills as the digest lists them; [] when skills are off or there are none."""
    raw = cur_vault()
    if not raw:
        return []
    try:
        import skills

        return skills.listing(Path(raw).expanduser())
    except Exception:  # noqa: BLE001
        return []


def skills_description(found: list[dict]) -> str:
    rows = "; ".join(f"{s['id']} = {s['name']} ({'draft' if s['status'] == 'draft' else 'skill'}): {s['use_when']}"
                     for s in found)
    return ("Fetch the full steps of one of the user's skills: procedures grown from lessons they collected on other "
            "tasks, not facts about this project. Call it only when the user's task is exactly the situation a skill is "
            "for; then follow its steps and say once which skill you followed, with its id. A draft is not yet "
            f"confirmed. Skills: {rows}")


def tools() -> list[dict]:
    out = TOOLS + ([NOTE_TOOL, CORRECT_TOOL] if WRITE else [])
    if learn_on():
        import experience

        out = out + [{**LEARN_TOOL, "description": experience.LEARN_HELP}]
    found = skill_list()
    if found:
        out = out + [{**SKILL_TOOL, "description": skills_description(found)}]
    return out


def skill(args: dict) -> tuple[str, bool]:
    """The full text of one skill; a `fetched` line in the use records (stdio only: a team server stays read-only)."""
    import skills

    raw = cur_vault()
    if not raw:
        return ("No vault configured: run the KRouter one-line install, or set KROUTER_VAULT (or the old name OBSIDIAN_VAULT) for this server.", True)
    vault = Path(raw).expanduser()
    sid = str(args.get("id") or "").strip()
    text = skills.show(vault, sid) if sid else ""
    if not text:
        known = ", ".join(s["id"] for s in skills.listing(vault)) or "none"
        return (f"no skill {sid!r}; the skills are: {known}", True)
    if WRITE:
        try:
            skills.record_fetch(vault, skills.find(vault, sid)["id"], f"MCP（{CLIENT or 'unknown client'}）")
        except OSError:
            pass
    return (text, False)


def correct(args: dict) -> tuple[str, bool]:
    """One correction made to hold now (corrections.apply_now), in the ledger, one commit."""
    from datetime import datetime

    import capture_ledger
    import corrections
    import zones

    raw = cur_vault()
    if not raw:
        return ("No vault configured: run the KRouter one-line install, or set KROUTER_VAULT (or the old name OBSIDIAN_VAULT) for this server.", True)
    vault = Path(raw).expanduser()
    res = corrections.apply_now(vault, str(args.get("new") or ""), str(args.get("old") or ""),
                                str(args.get("page") or ""), f"MCP（{CLIENT or 'unknown client'}）")
    if "error" in res:
        return (res["error"], True)
    now = datetime.now()
    rid = capture_ledger.run_id(now)
    undo = f"python3 {HERE / 'import_sessions.py'} --vault '{vault}' --undo {rid}"
    what = {"page": "旧页整页标为 superseded", "line": "旧页那一行下面加了「已改」", "recorded": "没有指出旧页"}[res["mode"]]
    ledger = capture_ledger.append(vault, f"## {now.strftime('%Y-%m-%d %H:%M')} · run {rid}\n\n撤销这一轮：`{undo}`\n\n"
                                          f"- 会话内纠正（MCP，{CLIENT or '未知客户端'}）：[[{res['written'].removesuffix('.md')}]]"
                                          + (f"，取代 [[{res['superseded'].removesuffix('.md')}]]（{what}）" if res["superseded"] else "")
                                          + (f"；判定当天的纠正候选 {res['settled']} 条" if res["settled"] else "") + "\n")
    if str(raw) in POOLS:
        POOLS[str(raw)].mark_stale()  # 下一次查询就要看到取代
    sha = capture_ledger.commit(vault, rid, res["touched"], "会话内纠正 1 条")
    if sha:
        capture_ledger.commit(vault, rid, [ledger], f"变更记录 run {rid}", tagged=False)
    return (f"corrected: {res['written']}\nsuperseded: {res['superseded'] or '(none named)'} ({res['mode']})\nrun: {rid}"
            + (f"\nundo: {undo}" if sha else "\nundo: the vault is not a git repository; revert the pages by hand"), False)


def learn(args: dict) -> tuple[str, bool]:
    """One experience card the host agent wrote itself: checked, written, in the ledger, one commit."""
    from datetime import datetime

    import capture_ledger
    import experience
    import zones
    from krouter_redact import redact

    raw = cur_vault()
    if not raw:
        return ("No vault configured: run the KRouter one-line install, or set KROUTER_VAULT (or the old name OBSIDIAN_VAULT) for this server.", True)
    vault = Path(raw).expanduser()
    item = {k: (redact(v) if isinstance(v, str) else [redact(str(x)) for x in v] if isinstance(v, list) else v)
            for k, v in args.items()}
    path, why = experience.learn(vault, item, f"MCP（{CLIENT or 'unknown client'}）")
    if not path and why.startswith("again: "):
        return (f"recorded: the lesson of {why[7:]} came up again (no new card)", False)
    if not path:
        return (why, True)
    now = datetime.now()
    rid = capture_ledger.run_id(now)
    undo = f"python3 {HERE / 'import_sessions.py'} --vault '{vault}' --undo {rid}"
    rel = zones.canon(vault, str(path.relative_to(vault)).replace(os.sep, "/"))
    ledger = capture_ledger.append(vault, f"## {now.strftime('%Y-%m-%d %H:%M')} · run {rid}\n\n撤销这一轮：`{undo}`\n\n"
                                          f"- 经验卡：[[{rel.removesuffix('.md')}]]（MCP，{CLIENT or '未知客户端'}）\n")
    if str(raw) in POOLS:
        POOLS[str(raw)].mark_stale()
    sha = capture_ledger.commit(vault, rid, [path], "MCP 经验卡 1 张")
    if sha:
        capture_ledger.commit(vault, rid, [ledger], f"变更记录 run {rid}", tagged=False)
    return (f"learned: {rel}\nrun: {rid}" + (f"\nundo: {undo}" if sha else "\nundo: the vault is not a git repository; "
                                                                          "delete the card by hand"), False)


def note(args: dict) -> tuple[str, bool]:
    """One line on today's notes page, a ledger entry, and one commit (when the vault is a git repository)."""
    from datetime import datetime

    import capture_ledger
    import zones
    from krouter_redact import redact

    raw = cur_vault()
    if not raw:
        return ("No vault configured: run the KRouter one-line install, or set KROUTER_VAULT (or the old name OBSIDIAN_VAULT) for this server.", True)
    text = " ".join(str(args.get("text") or "").split())
    kind = str(args.get("kind") or "note")
    if not text:
        return ("text is required", True)
    if len(text) > NOTE_MAX:
        return (f"text is longer than {NOTE_MAX} characters: write one sentence", True)
    if kind not in KINDS:
        return (f"kind must be one of {', '.join(KINDS)}", True)
    vault = Path(raw).expanduser()
    now = datetime.now()
    page = zones.path(vault, NOTES) / f"{now.date().isoformat()}｜agent 记下.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    if not page.exists():
        page.write_text("---\n"
                        f"title: \"{now.date().isoformat()} agent 记下\"\n"
                        "type: agent-notes\n"
                        "status: provisional\n"
                        f"date: {now.date().isoformat()}\n"
                        "source: krouter-mcp\n"
                        "---\n\n"
                        f"# {now.date().isoformat()} agent 记下\n\n"
                        "你用的 AI 通过 MCP 记下的笔记（已脱敏）。这是线索，不是规则页；每条都在「记忆变更记录」里，"
                        "不对就按那里的命令撤销。\n\n", encoding="utf-8")
    line = f"- （{now.strftime('%H:%M')}）[{KINDS[kind]}] {redact(text)} — 来自 MCP（{CLIENT or '未知客户端'}）"
    with page.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    rid = capture_ledger.run_id(now)
    undo = f"python3 {HERE / 'import_sessions.py'} --vault '{vault}' --undo {rid}"
    ledger = capture_ledger.append(vault, f"## {now.strftime('%Y-%m-%d %H:%M')} · run {rid}\n\n"
                                          f"撤销这一轮：`{undo}`\n\n- MCP 记下（{CLIENT or '未知客户端'}）：{line[2:]}\n")
    if str(raw) in POOLS:
        POOLS[str(raw)].mark_stale()  # 刚写的这条，下一次查询就要查得到
    sha = capture_ledger.commit(vault, rid, [page], "MCP 记下 1 条")
    if sha:
        capture_ledger.commit(vault, rid, [ledger], f"变更记录 run {rid}", tagged=False)
    rel = zones.canon(vault, str(page.relative_to(vault)).replace(os.sep, "/"))
    return (f"noted: {rel}\nrun: {rid}" + (f"\nundo: {undo}" if sha else "\nundo: the vault is not a git repository; "
                                                                        "delete the line by hand"), False)


def call(name: str, args: dict) -> dict:
    if name == "krouter_note" and WRITE:
        text, err = note(args)
        return {"content": [{"type": "text", "text": text}], "isError": err}
    if name == "krouter_correct" and WRITE:
        text, err = correct(args)
        return {"content": [{"type": "text", "text": text}], "isError": err}
    if name == "krouter_learn" and learn_on():
        text, err = learn(args)
        return {"content": [{"type": "text", "text": text}], "isError": err}
    if name == "krouter_skill" and skill_list():
        text, err = skill(args)
        return {"content": [{"type": "text", "text": text}], "isError": err}
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
        text += ("\nclient_sampling: " + ("declared" if CLIENT_SAMPLING else "not declared")
                 + " (KRouter does not use MCP sampling; with no key it borrows the agent's own CLI, see llm.py)")
    else:
        return {"content": [{"type": "text", "text": f"unknown tool {name}"}], "isError": True}
    return {"content": [{"type": "text", "text": text}], "isError": err}


def handle(msg: dict) -> dict | None:
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:  # notification
        return None
    params = msg.get("params") or {}
    if method == "initialize":
        global CLIENT
        info = params.get("clientInfo") if isinstance(params.get("clientInfo"), dict) else {}
        CLIENT = " ".join(str(info.get("name") or "").split())[:60]
        caps = params.get("capabilities") if isinstance(params.get("capabilities"), dict) else {}
        # MCP sampling（服务端请客户端的模型来答）：只记客户端声明了没有，不用它（规范已弃用，Claude Code 不支持）
        global CLIENT_SAMPLING
        CLIENT_SAMPLING = "sampling" in caps
        asked = params.get("protocolVersion")
        result = {"protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
                  "capabilities": {"tools": {"listChanged": False}},
                  "serverInfo": {"name": "krouter", "title": f"KRouter ({cur_label()})" if cur_label() else "KRouter",
                                 "version": VERSION},
                  "instructions": INSTRUCTIONS + (CORRECT_INSTRUCTION if WRITE else "") + (LEARN_INSTRUCTION if learn_on() else "") + (SKILL_INSTRUCTION if skill_list() else "") + (f" This server answers from the '{cur_label()}' vault "
                                                  "(`vault_label:` in each receipt); say which vault an answer "
                                                  "came from." if cur_label() else "")}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": tools()}
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

        def _authorized(self, need: str | None = None) -> bool:
            """`need`: the token this request must carry (the bank's own, else the server's); none → open."""
            need = token if need is None else need
            if not need:
                return True
            got = self.headers.get("Authorization", "")
            return got.startswith("Bearer ") and hmac.compare_digest(got[7:].strip().encode(), need.encode())

        def _metrics_ok(self) -> bool:  # 计数里没有问题原文；有 token 时，服务的或任一库的 token 都可以读
            tokens = [t for t in [token, *(b["token"] for b in BANKS.values())] if t]
            return not tokens or any(self._authorized(t) for t in tokens)

        def _bank(self, path: str):
            """(name, settings) for /mcp/NAME when the server holds banks; ("", None) for /mcp; None for anything else."""
            path = path.rstrip("/")
            if not BANKS:
                return ("", None) if path == "/mcp" else None
            name = path[len("/mcp/"):] if path.startswith("/mcp/") else None
            return (name, BANKS[name]) if name in BANKS else None

        def do_GET(self):  # noqa: N802
            t0 = time.perf_counter()
            path = urlsplit(self.path).path
            if path == "/healthz":
                if BANKS:
                    banks = {n: Path(b["vault"]).is_dir() for n, b in BANKS.items()}
                    ok = all(banks.values())
                    body = {"ok": ok, "version": VERSION, "banks": banks, "uptime_s": round(time.time() - started)}
                else:
                    vault = vault_path()
                    ok = bool(vault) and Path(vault).expanduser().is_dir()
                    body = {"ok": ok, "version": VERSION, "label": LABEL or None, "uptime_s": round(time.time() - started)}
                self._json(200 if ok else 503, body)
                return self._log(200 if ok else 503, t0)
            if path == "/metrics":
                if not self._metrics_ok():
                    self._send(401, headers={"WWW-Authenticate": "Bearer"})
                    return self._log(401, t0)
                self._send(200, METRICS.render(started).encode("utf-8"), ctype="text/plain; version=0.0.4")
                return self._log(200, t0)
            if self._bank(path) is not None:  # no server-to-client stream: every reply comes back on its POST
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
            hit = self._bank(urlsplit(self.path).path)
            if hit is None:
                self._reject(404)
                return self._log(404, t0)
            name, bank = hit
            if not _origin_ok(self.headers.get("Origin", ""), allowed_origins):
                self._reject(403, {"error": "origin not allowed"})
                return self._log(403, t0)
            if not self._authorized(bank["token"] if bank and bank["token"] else None):
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
            _ctx.vault, _ctx.label = (bank["vault"], name) if bank else (None, None)
            try:
                replies = [r for r in (handle(m) if isinstance(m, dict) else
                                       {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
                                       for m in (msg if batch else [msg])) if r is not None]
            finally:
                _ctx.vault = _ctx.label = None
            summary = _rpc_summary(msg[0] if batch and msg else msg)
            if summary.get("rpc") == "tools/call":
                res = (replies[0].get("result") or {}) if replies else {}
                text = "".join(c.get("text", "") for c in res.get("content") or [] if isinstance(c, dict))
                METRICS.observe(name or LABEL or "default", str(summary.get("tool") or ""),
                                "error" if res.get("isError") else "ok", time.perf_counter() - t0, "recall: none" in text)
            if name:
                summary["bank"] = name
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
    open_banks = [n for n, b in BANKS.items() if not (b["token"] or token)]
    if host not in LOOPBACK and (open_banks or (not BANKS and not token)):
        print(f"refusing to listen on {host}: anyone who can reach it could read "
              + (f"the vaults {', '.join(open_banks)}" if open_banks else "the vault")
              + ". Pass --token-file (or --bank-token NAME=FILE for each), or bind to 127.0.0.1.", file=sys.stderr)
        return 2
    if not log_queries:  # 团队服务器默认不把同事的问题原文写进查询日志
        os.environ["KROUTER_NO_QUERY_LOG"] = "1"
    started = time.time()
    for name, bank in (BANKS.items() if BANKS else [("", None)]):  # 先建好索引，第一位提问的人不用等
        _ctx.vault = bank["vault"] if bank else None
        if cur_vault():
            t0 = time.perf_counter()
            _route("search", "krouter index warm-up", {"KROUTER_NO_QUERY_LOG": "1"})
            METRICS.index_s[name or LABEL or "default"] = time.perf_counter() - t0
            print(f"index ready{' for ' + name if name else ''} in {time.perf_counter() - t0:.1f} s", file=sys.stderr)
    _ctx.vault = None
    server = ThreadingHTTPServer((host, port_n), make_handler(token, allowed_origins, started))
    server.daemon_threads = True
    base = f"http://{host}:{server.server_address[1]}"
    print(json.dumps({"listening": f"{base}/mcp", "label": LABEL or None,
                      **({"banks": {n: f"{base}/mcp/{n}" for n in BANKS}} if BANKS else {}),
                      "auth": "bearer" if token or BANKS and not open_banks else "none (loopback only)"}),
          file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    global LABEL, WRITE, WORKERS, REFRESH_EVERY
    ap = argparse.ArgumentParser(description="KRouter MCP server: stdio by default, HTTP with --http.")
    ap.add_argument("--http", metavar="HOST:PORT", help="serve Streamable HTTP on this address instead of stdio")
    ap.add_argument("--token-file", default="", help="file holding the bearer token clients must send")
    ap.add_argument("--allow-origin", action="append", default=[], help="a browser Origin allowed to call (repeat)")
    ap.add_argument("--label", default=os.environ.get("KROUTER_LABEL", ""),
                    help="name of this vault, stamped on every receipt (e.g. team)")
    ap.add_argument("--vault", default="", help="the vault to serve (default: KROUTER_VAULT or OBSIDIAN_VAULT, else the installed one)")
    ap.add_argument("--log-queries", action="store_true", help="HTTP: also write question text to the query log")
    ap.add_argument("--allow-write", action="store_true", help="HTTP: offer krouter_note (off by default: read only)")
    ap.add_argument("--workers", type=int, default=None, metavar="N",
                    help="resident lookup processes per vault (default 4 over HTTP, 1 over stdio; 0: one process per lookup)")
    ap.add_argument("--refresh-every", type=float, default=None, metavar="SECONDS",
                    help="re-check the vault's files at most this often (default 2; 0: before every lookup)")
    ap.add_argument("--bank", action="append", default=[], metavar="NAME=PATH",
                    help="HTTP: serve this vault at /mcp/NAME (repeat for several; each is isolated: its own index, "
                         "its own label on every receipt)")
    ap.add_argument("--bank-token", action="append", default=[], metavar="NAME=FILE",
                    help="HTTP: the bearer token one bank needs (default: --token-file)")
    args = ap.parse_args(argv)
    LABEL = args.label.strip()
    env_workers = os.environ.get("KROUTER_WORKERS", "")
    WORKERS = max(0, args.workers if args.workers is not None else
                  int(env_workers) if env_workers.isdigit() else (4 if args.http else 1))
    REFRESH_EVERY = max(0.0, args.refresh_every if args.refresh_every is not None else
                        float(os.environ.get("KROUTER_REFRESH_EVERY") or 2))
    WRITE = (not args.http) or args.allow_write
    BANKS.clear()
    tokens = dict(t.split("=", 1) for t in args.bank_token if "=" in t)
    for spec in args.bank:
        name, sep, path = spec.partition("=")
        if not sep or not name or not all(c.isalnum() or c in "-_" for c in name):
            print(f"--bank takes NAME=PATH (NAME: letters, digits, - and _), got {spec!r}", file=sys.stderr)
            return 2
        tok = ""
        if name in tokens:
            try:
                tok = Path(tokens[name]).expanduser().read_text(encoding="utf-8").strip()
            except OSError as exc:
                print(f"cannot read --bank-token for {name}: {exc}", file=sys.stderr)
                return 2
            if len(tok) < 16:
                print(f"the token for bank {name} must be at least 16 characters", file=sys.stderr)
                return 2
        BANKS[name] = {"vault": str(Path(path).expanduser().resolve()), "token": tok}
    if BANKS and not args.http:
        print("--bank needs --http", file=sys.stderr)
        return 2
    if args.vault:
        os.environ["OBSIDIAN_VAULT"] = str(Path(args.vault).expanduser().resolve())
    if args.http:
        return serve_http(args.http, args.token_file, args.allow_origin, args.log_queries)
    return serve_stdio()


if __name__ == "__main__":
    raise SystemExit(main())
