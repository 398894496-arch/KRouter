#!/usr/bin/env python3
"""Collect what a person actually typed to their coding agents, from the agents' own local records.

The real-questions bench uses questions nobody wrote for a test: what the host asked Claude Code, Codex, Cursor,
DeepSeek Harness, Grok and Hermes over months of work. This reads each agent's local store, keeps only the human's
own messages (no injected context, tool output, subagents, headless or automation runs), redacts key-shaped text,
and writes one JSON line per message to a private file. Nothing leaves the machine; nothing is printed but counts.

    python3 bench/real_questions/extract_asks.py [--out ~/.local/state/krouter-eval/real/asks.jsonl]
        [--codex-root DIR ...] [--dsh-root DIR ...]

Sources (each skipped when absent):
- Claude Code: `~/.claude/projects/*/*.jsonl` and the prompt history `~/.claude/history.jsonl` (it outlives the
  30-day session cleanup);
- Codex: `~/.codex/sessions`, plus any `--codex-root` (e.g. restored archives); one session counts once;
- Cursor agent transcripts: `~/.cursor/projects/*/agent-transcripts/`;
- DeepSeek Harness: `~/.dsh*/**/sessions/*/session*.jsonl.zstd` (needs `zstd`), plus any `--dsh-root`;
- Grok: `~/.grok/sessions/*/…/*.jsonl` (typed prompts, not shell lines);
- Hermes: `~/.hermes/state.db` (CLI sessions).

Output rows: {id, source, session, ts (ISO, UTC), cwd, text}. `id` is a hash of source, session and text, so a
re-run gives the same ids. The file is written with mode 600.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "skill/krouter-obsidian/scripts"))
import import_sessions as imp  # noqa: E402
from krouter_redact import redact  # noqa: E402

HOME = Path.home()
# 自动化、测试、评测跑出来的会话：不是人说的话
AUTOMATION = re.compile(r"(/private/tmp|^/tmp|/var/folders|scratchpad|krouter-perm-test|krouter-grok-distill|"
                        r"krouter-learn-|krouter-tests-|krouter-train-)")


def iso(dt: datetime | None) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else ""


def from_ms(v) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(v) / 1000, timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def from_s(v) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(v), timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def from_iso(v) -> datetime | None:
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def row(source: str, session: str, ts: datetime | None, cwd: str, text: str) -> dict | None:
    text = imp.CURSOR_WRAP.sub("", imp.TAGS.sub("", text or "")).strip()
    if not text or imp.NOISE.match(text) or AUTOMATION.search(cwd or ""):
        return None
    text = redact(text)
    rid = hashlib.sha1(f"{source}\0{session}\0{text}".encode("utf-8")).hexdigest()[:16]
    return {"id": rid, "source": source, "session": session, "ts": iso(ts), "cwd": cwd or "", "text": text}


def transcripts(agent: str, root: Path, reader) -> list[dict]:
    out, seen = [], set()
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*.jsonl")):
        if "subagents" in path.parts or (agent == "cursor" and "agent-transcripts" not in path.parts):
            continue
        s = reader(path)
        if not s["turns"] or s["id"] in seen:
            continue
        seen.add(s["id"])
        for t in s["turns"]:
            r = row(agent, s["id"], from_iso(t["ts"]), s.get("cwd", ""), t["ask"])
            if r:
                out.append(r)
    return out


def claude_history(path: Path) -> list[dict]:
    out = []
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        text = str(d.get("display") or "")
        if text.startswith("/"):  # 斜杠命令
            continue
        r = row("claude-code-history", str(d.get("sessionId") or ""), from_ms(d.get("timestamp")),
                str(d.get("project") or ""), text)
        if r:
            out.append(r)
    return out


def dsh(roots: list[Path]) -> list[dict]:
    out = []
    files = sorted({f for root in roots for f in glob.glob(str(root / "**/sessions/*/*/session*.jsonl.zstd"),
                                                                recursive=True)})
    for f in files:
        try:
            raw = subprocess.run(["zstd", "-dc", f], capture_output=True, timeout=120).stdout.decode("utf-8", "replace")
        except (OSError, subprocess.TimeoutExpired):
            continue
        rows = [json.loads(x) for x in raw.splitlines() if x.startswith("{")]
        head = next((r for r in rows if r.get("type") == "session"), {})
        if head.get("delegationDepth"):  # 子 agent
            continue
        for r in rows:
            data = r.get("data") or {}
            src = data.get("source")
            if r.get("type") != "user/message" or not isinstance(src, dict) or src.get("kind") != "user":
                continue
            content = data.get("content")
            text = "\n".join(c.get("text", "") for c in content if isinstance(c, dict)) if isinstance(content, list) \
                else str(content or "")
            got = row("dsh", str(head.get("id") or f), from_ms(r.get("time")), str(head.get("cwd") or ""), text)
            if got:
                out.append(got)
    return out


def grok(root: Path) -> list[dict]:
    out = []
    for f in sorted(glob.glob(str(root / "*/*/*.jsonl")) + glob.glob(str(root / "*/*.jsonl"))):
        cwd = Path(f).relative_to(root).parts[0].replace("%2F", "/")
        for line in open(f, encoding="utf-8", errors="replace"):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if "prompt" not in d or d.get("is_bash"):
                continue
            ts = from_iso(d.get("timestamp")) or from_s(d.get("timestamp"))
            r = row("grok", str(d.get("session_id") or f), ts, cwd, str(d.get("prompt") or ""))
            if r:
                out.append(r)
    return out


def hermes(db: Path) -> list[dict]:
    out = []
    if not db.is_file():
        return out
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    q = ("select m.session_id, m.timestamp, m.content from messages m join sessions s on s.id = m.session_id "
         "where m.role = 'user' and s.source = 'cli'")
    for sid, ts, content in con.execute(q):
        r = row("hermes", str(sid), from_s(ts), "", str(content or ""))
        if r:
            out.append(r)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HOME / ".local/state/krouter-eval/real/asks.jsonl"))
    ap.add_argument("--codex-root", action="append", default=[])
    ap.add_argument("--dsh-root", action="append", default=[])
    args = ap.parse_args()
    roots = imp.roots()
    rows: list[dict] = []
    rows += transcripts("claude-code", roots["claude-code"], imp.read_claude)
    rows += claude_history(HOME / ".claude/history.jsonl")
    codex_sessions: list[dict] = []
    for root in [roots["codex"], *map(Path, args.codex_root)]:
        codex_sessions += transcripts("codex", root, imp.read_codex)
    rows += codex_sessions
    rows += transcripts("cursor", roots["cursor"], imp.read_cursor)
    rows += dsh([*sorted(Path(p) for p in glob.glob(str(HOME / ".dsh*"))), *map(Path, args.dsh_root)])
    rows += grok(HOME / ".grok/sessions")
    rows += hermes(HOME / ".hermes/state.db")
    # 同一句话在同一天出现在两个来源里（Claude Code 的会话记录和它的提示词历史重叠几天），只留一条
    seen: set[tuple[str, str]] = set()
    unique = []
    for r in sorted(rows, key=lambda r: r["ts"]):
        key = (re.sub(r"\s+", " ", r["text"]).strip(), r["ts"][:10])
        if key in seen or any(u["id"] == r["id"] for u in unique[-50:]):
            continue
        seen.add(key)
        unique.append(r)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in unique), encoding="utf-8")
    os.chmod(out, 0o600)
    from collections import Counter
    by = Counter(r["source"] for r in unique)
    days = sorted(r["ts"][:10] for r in unique if r["ts"])
    print(json.dumps({"asks": len(unique), "by_source": dict(by), "from": days[0] if days else "",
                      "through": days[-1] if days else "", "out": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
