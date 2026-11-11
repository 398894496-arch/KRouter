#!/usr/bin/env python3
"""Who did what on a team server: a personal token per person (or per agent), one writer at a time per vault, and a
journal of every change with who made it and when.

**Users file** (`mcp_server.py --users FILE`), one person or agent per line, only the token's SHA-256 kept:

    # name|token hash|role|banks
    alice|sha256:9f2c…|write|*
    bob-codex|sha256:41aa…|read|team,ops

`role` is `write` (may use the write tools when the server runs with `--allow-write`) or `read`; `banks` is `*` or
the bank names this token opens. The server re-reads the file when it changes, so adding or removing someone needs no
restart. Make a token and its line with

    python3 team.py add-user --users /etc/krouter/users alice --token-out ~/alice.token [--role read] [--banks team]

which writes the new token only to `--token-out` (mode 600) for you to hand over, and only its hash to the users file.

**One writer at a time.** Every write through the server (a note, a correction, a lesson) holds `writing(vault)`: a
lock inside the server and a file lock (`$KROUTER_STATE_DIR/locks/`) against other processes, so two writes never
interleave on one page, in the change ledger or in git. Order is arrival at the lock; the journal's `seq` records it.

**Journal.** `90 系统文件/自动化/团队变更.jsonl` in the vault (committed with the change ledger), one JSON line per
write: `seq`, `at` (UTC, milliseconds), `who`, `via` (the client's name), `auth` (`user`, `shared-token`, `open`),
`tool`, `run`, `pages`, `text` (redacted, at most 200 characters), `supersedes` and `conflicts`. `changes()` (the
`krouter_changes` tool, `team.py changes`) answers "who changed this page, and when".
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

JOURNAL = "90 系统文件/自动化/团队变更.jsonl"
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@/+-]{0,63}$")
ROLES = ("write", "read")
MIN_TOKEN = 16


def hash_token(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


class Users:
    """The users file, re-read when its modification time or size changes. `match(token)` → the user's entry or None;
    every entry's hash is compared in constant time, so the time taken does not say which entry came close."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self.lock = threading.Lock()
        self.sig: tuple | None = None
        self.entries: list[dict] = []
        self.errors: list[str] = []
        self.load()

    def load(self) -> None:
        try:
            st = self.path.stat()
        except OSError as exc:
            raise OSError(f"cannot read the users file: {exc}") from None
        sig = (st.st_mtime_ns, st.st_size)
        with self.lock:
            if sig == self.sig:
                return
            entries, errors, names = [], [], set()
            for n, raw in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split("|")]
                parts += [""] * (4 - len(parts))
                name, digest, role, banks = parts[:4]
                role = role or "write"
                if not NAME.match(name) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest) or role not in ROLES \
                        or name in names:
                    errors.append(f"line {n}: expected name|sha256:<64 hex>|write or read|* or bank names"
                                  + (" (name used twice)" if name in names else ""))
                    continue
                names.add(name)
                entries.append({"name": name, "hash": digest, "role": role,
                                "banks": {b.strip() for b in (banks or "*").split(",") if b.strip()} or {"*"}})
            self.entries, self.errors, self.sig = entries, errors, sig

    def match(self, token: str) -> dict | None:
        try:
            self.load()
        except OSError:
            pass  # 文件暂时读不到（正在被替换）：沿用上一次读到的
        got = hash_token(token).encode()
        found = None
        for e in self.entries:  # 不提前返回：每一条都比一遍
            if hmac.compare_digest(got, e["hash"].encode()):
                found = e
        return found

    @staticmethod
    def opens(entry: dict, bank: str) -> bool:
        return "*" in entry["banks"] or (bank or "") in entry["banks"]


def add_user(users: Path, name: str, role: str, banks: str, token_out: Path, token_in: Path | None = None) -> str:
    """Append a line for `name`; the token goes only to `token_out` (new file, mode 600), never to the users file."""
    if not NAME.match(name):
        raise ValueError("name: letters, digits and . _ @ / + -, at most 64 characters")
    if role not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    if users.exists() and any(ln.split("|")[0].strip() == name for ln in users.read_text(encoding="utf-8").splitlines()):
        raise ValueError(f"{name} is already in {users}")
    if token_in:
        token = token_in.read_text(encoding="utf-8").strip()
        if len(token) < MIN_TOKEN:
            raise ValueError(f"the token must be at least {MIN_TOKEN} characters")
    else:
        if token_out.exists():
            raise ValueError(f"{token_out} exists; pick another --token-out")
        token = secrets.token_hex(24)
        fd = os.open(token_out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(token + "\n")
    users.parent.mkdir(parents=True, exist_ok=True)
    new = not users.exists()
    with users.open("a", encoding="utf-8") as fh:
        if new:
            fh.write("# KRouter team users: name|token hash|role|banks (the tokens themselves are not kept here)\n")
        fh.write(f"{name}|{hash_token(token)}|{role}|{banks or '*'}\n")
    if new and os.name != "nt":
        users.chmod(0o600)
    return name


def remove_user(users: Path, name: str) -> bool:
    lines = users.read_text(encoding="utf-8").splitlines()
    keep = [ln for ln in lines if ln.split("|")[0].strip() != name or ln.lstrip().startswith("#")]
    if len(keep) == len(lines):
        return False
    tmp = users.with_name(users.name + ".tmp")
    tmp.write_text("\n".join(keep) + "\n", encoding="utf-8")
    os.replace(tmp, users)
    return True


# ---------- one writer at a time ----------

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _state_dir() -> Path:
    raw = os.environ.get("KROUTER_STATE_DIR") or ""
    return Path(raw).expanduser() if raw else Path.home() / ".local/state/krouter"


@contextlib.contextmanager
def writing(vault: str | Path):
    """Hold the vault's write lock: a thread lock inside this process, and an exclusive file lock against other
    processes on the same machine (another server, the nightly job when it learns to take it)."""
    key = str(Path(vault).expanduser().resolve())
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(key, threading.Lock())
    with lock:
        fh = None
        try:
            import fcntl  # noqa: PLC0415  Windows 上没有：只用进程内的锁

            d = _state_dir() / "locks"
            d.mkdir(parents=True, exist_ok=True)
            fh = open(d / (hashlib.sha256(key.encode()).hexdigest()[:16] + ".lock"), "a+")  # noqa: SIM115
            fcntl.flock(fh, fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass  # 拿不到文件锁（Windows、只读的状态目录）：进程内的锁照样保证这个服务一次只写一个
        try:
            yield
        finally:
            if fh is not None:
                fh.close()  # 关掉就放锁


# ---------- the journal ----------

def journal_path(vault: Path) -> Path:
    import zones

    return zones.path(vault, JOURNAL)


def _last(vault: Path) -> dict:
    p = journal_path(vault)
    try:
        with p.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 65536))
            tail = fh.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    for line in reversed(tail):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return {}


def unique_run(vault: Path, now: datetime) -> str:
    """A run id (`capture_ledger.run_id`) no earlier write of this vault used: two writes in one second get `-2`, `-3`
    (the undo command finds a run by its id). Call while holding `writing(vault)`."""
    import capture_ledger

    base = capture_ledger.run_id(now)
    last = str(_last(vault).get("run") or "")
    if last == base or last.startswith(base + "-"):
        n = int(last.rsplit("-", 1)[1]) + 1 if last.startswith(base + "-") else 2
        return f"{base}-{n}"
    return base


def record(vault: Path, entry: dict) -> tuple[dict, Path]:
    """Append one change to the journal with the next `seq`; call while holding `writing(vault)`."""
    p = journal_path(vault)
    p.parent.mkdir(parents=True, exist_ok=True)
    row = {"seq": int(_last(vault).get("seq") or 0) + 1,
           "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), **entry}
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row, p


def read_journal(vault: Path) -> list[dict]:
    out = []
    try:
        lines = journal_path(vault).read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _page_key(p: str) -> str:
    return p.strip().lstrip("/").removesuffix(".md").replace("\\", "/")


def changes(vault: Path, page: str = "", who: str = "", text: str = "", limit: int = 20) -> list[dict]:
    """Journal rows, newest first: those touching `page` (path, or its name without folders), by `who`, or whose text
    holds `text`."""
    rows = read_journal(vault)
    if page:
        want = _page_key(page)
        rows = [r for r in rows if any(_page_key(p) == want or _page_key(p).rsplit("/", 1)[-1] == want
                                       for p in [*(r.get("pages") or []), *(r.get("supersedes") or [])])]
    if who:
        rows = [r for r in rows if r.get("who") == who]
    if text:
        rows = [r for r in rows if text in str(r.get("text") or "")]
    return list(reversed(rows))[:max(1, limit)]


def describe(rows: list[dict]) -> str:
    if not rows:
        return "changes: none recorded"
    out = [f"changes: {len(rows)} (newest first)"]
    for r in rows:
        line = (f"- #{r.get('seq')} {r.get('at')} {r.get('who') or '(' + str(r.get('auth') or 'unknown') + ')'}"
                f" via {r.get('via') or '?'}: {r.get('tool')} → {', '.join(r.get('pages') or []) or '-'} (run {r.get('run')})")
        if r.get("supersedes"):
            line += f"; superseded {', '.join(r['supersedes'])}"
        for c in r.get("conflicts") or []:
            line += (f"; conflict: replaced {c.get('page')} by {c.get('author') or '?'} at {c.get('at') or '?'}"
                     f" ({c.get('why')})")
        out.append(line)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="KRouter team users and the change journal.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add-user", help="make a personal token and add its hash to the users file")
    a.add_argument("--users", required=True)
    a.add_argument("name")
    a.add_argument("--role", default="write", choices=ROLES)
    a.add_argument("--banks", default="*", help="* or comma-separated bank names")
    a.add_argument("--token-out", help="new file for the generated token (mode 600)")
    a.add_argument("--token-from", help="hash an existing token from this file instead of generating one")
    r = sub.add_parser("remove-user", help="remove a user's line (their token stops working at once)")
    r.add_argument("--users", required=True)
    r.add_argument("name")
    c = sub.add_parser("changes", help="who changed what, newest first")
    c.add_argument("--vault", required=True)
    c.add_argument("--page", default="")
    c.add_argument("--who", default="")
    c.add_argument("--text", default="")
    c.add_argument("--limit", type=int, default=20)
    c.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.cmd == "add-user":
        if not args.token_out and not args.token_from:
            print("pass --token-out FILE (the new token is written only there) or --token-from FILE", file=sys.stderr)
            return 2
        try:
            add_user(Path(args.users).expanduser(), args.name, args.role, args.banks,
                     Path(args.token_out).expanduser() if args.token_out else Path(os.devnull),
                     Path(args.token_from).expanduser() if args.token_from else None)
        except (ValueError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"added {args.name} ({args.role}, banks {args.banks})"
              + (f"; token in {args.token_out}" if args.token_out and not args.token_from else ""))
        return 0
    if args.cmd == "remove-user":
        ok = remove_user(Path(args.users).expanduser(), args.name)
        print(f"removed {args.name}" if ok else f"{args.name} is not in {args.users}")
        return 0 if ok else 1
    rows = changes(Path(args.vault).expanduser(), args.page, args.who, args.text, args.limit)
    print(json.dumps(rows, ensure_ascii=False, indent=1) if args.json else describe(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
