#!/usr/bin/env python3
"""Import the agent sessions already on this machine, so the vault is useful on day one.

Reads Claude Code (`~/.claude/projects/*/*.jsonl`), Codex (`~/.codex/sessions/YYYY/MM/DD/*.jsonl`) and Cursor agent
(`~/.cursor/projects/*/agent-transcripts/<id>/<id>.jsonl`) transcripts and writes one page per session and day under `05 时间日志/会话摘录/`, named after the session's title (or its first
question): what you asked and the agent's closing answer, turn by turn. Tool calls, tool output, thinking, injected
context and headless runs (`claude -p`, `codex exec`, the nightly job itself) are dropped; every line goes through
`redact()` first, so a key that once scrolled past in a session prints as `<redacted>`.

Local by default: nothing leaves the machine, no model is called. `--distill` sends each session's excerpt (already
redacted) to the nightly model lane and puts "what was decided / what changed" at the top of its page — that line is
what an agent's question lands on. `--dry-run` says how many characters that would send before anything is sent.

A page this script did not write is never touched (`source: krouter-import` in its frontmatter marks ours). Re-running
rewrites only our pages, so the excerpt follows the transcript; a page already distilled keeps its digest until the
session grows. `--consent` records your yes for the nightly job, which then imports yesterday on its own; `--revoke`
takes it back. The nightly job imports nothing without that yes.

Living next to another collector. A host that already logs its sessions day by day (a `type: daily-log` page under
`05 时间日志/`, such as the one a daily-evolution job writes) gets no second copy of that work: a session the log
lists by id (`` `claude:<id>` ``, or an 8+ hex prefix) or a day the log's collector covered is matched, and
`--overlap` says what to do with it: `link` (the default) writes the turn-by-turn page and links it to the day's log
(`covered_by`), `skip` writes nothing for it. A forked or resumed session that copied an earlier one's turns is
matched by content: turns are keyed by their time and question, the longer session keeps the shared turns and the
other keeps only its own (`forked_from`); one wholly inside another gets no page.

Keeping a session out. A session with `#不记` (or `#nocapture`) in any of its questions is neither imported nor
distilled, and a page already written for it is removed; so is every session whose project root is on the
`--exclude-root` list (saved with `--consent`). `--intraday` is what a daytime timer runs: like `--nightly` it does
nothing without consent and uses the lane and distill choice recorded then, over today and yesterday.

Every turn. `--file X --local` is what the turn-end hooks (Claude Code `Stop`, Codex `Stop`, Cursor `stop`) run: the
page follows the session turn by turn, with no model call even when distilling was turned on; the session-end hook
distills. A page that was distilled when the session was shorter keeps that digest (and the turn count it covers)
until the next distill, which then sends only the new turns.

Env: `KROUTER_CLAUDE_PROJECTS`, `KROUTER_CODEX_SESSIONS`, `KROUTER_CURSOR_PROJECTS` point at other transcript roots
(tests, other machines).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import zones  # noqa: E402
from krouter_home import project_root, vault_path  # noqa: E402
from krouter_redact import redact  # noqa: E402

FOLDER = "05 时间日志/会话摘录"
MARK = "krouter-import"
ASK_MAX = 600        # 每条提问最多保留的字数
ANSWER_MAX = 900     # 每条回答最多保留的字数
PAGE_MAX = 40_000    # 一页（一个会话的一天）的摘录上限
DISTILL_MAX = 24_000
DISTILL_MIN_TURNS = 2
DISTILL_SESSIONS = 40  # 一次最多提炼多少个会话（最新的优先）
# 提问里带这个标记的会话：不导入、不提炼，已写的页删掉
NO_CAPTURE = re.compile(r"#(不记|nocapture)(?![0-9A-Za-z_])", re.I)
# 注入的上下文、命令回显、系统提醒：不是用户说的话
NOISE = re.compile(r"^\s*(<(environment_context|user_instructions|system-reminder|command-|local-command|"
                   r"task-notification|turn_aborted|permissions)|# AGENTS\.md|Caveat: The messages below|"
                   r"This session is being continued)", re.I)
TAGS = re.compile(r"<(system-reminder|ide_selection|ide_opened_file)>.*?</\1>", re.S)
UNSAFE = re.compile(r"[\\/:*?\"<>|#^\[\]\n\r\t]+")


def state_file() -> Path:
    base = Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local/state/krouter")
    return base / "import.json"


def load_state() -> dict:
    try:
        return json.loads(state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(data: dict) -> None:
    path = state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def roots() -> dict[str, Path]:
    home = Path.home()
    return {"claude-code": Path(os.environ.get("KROUTER_CLAUDE_PROJECTS") or home / ".claude/projects"),
            "codex": Path(os.environ.get("KROUTER_CODEX_SESSIONS") or home / ".codex/sessions"),
            "cursor": Path(os.environ.get("KROUTER_CURSOR_PROJECTS") or home / ".cursor/projects")}


def _dt(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
    except (ValueError, AttributeError):
        return None


def local_day(ts: str) -> date | None:
    dt = _dt(ts)
    return dt.date() if dt else None


def local_hm(ts: str) -> str:
    dt = _dt(ts)
    return dt.strftime("%H:%M") if dt else "--:--"


def clean(text: str, limit: int) -> str:
    text = TAGS.sub("", text or "").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = redact(text)
    if len(text) > limit:
        text = text[:limit].rstrip() + " …"
    return text


def _texts(content, kinds: tuple[str, ...]) -> list[str]:
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        return [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") in kinds]
    return []


def _lines(path: Path):
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if isinstance(d, dict):
                    yield d
    except OSError:
        return


def read_claude(path: Path) -> dict:
    """{turns: [{ts, ask, answer}], cwd, title, id} of one Claude Code transcript; empty turns for a headless run."""
    s = {"turns": [], "cwd": "", "title": "", "id": path.stem}
    modern = human = False  # 新版 transcript 会给你打的每一轮标 origin.kind=human
    for d in _lines(path):
        if d.get("type") == "queue-operation":
            modern = True
        if d.get("type") == "custom-title" and d.get("customTitle"):
            s["title"] = str(d["customTitle"])
            continue
        if d.get("isSidechain") or d.get("isMeta") or d.get("isCompactSummary"):
            continue
        if str(d.get("entrypoint") or "").startswith("sdk-"):
            return {**s, "turns": []}  # 无头调用（夜间任务、脚本里的 claude -p）：是自动化，不是你说的话
        origin = d.get("origin")
        if isinstance(origin, dict) and origin.get("kind") not in (None, "human"):
            continue  # 后台任务通知之类
        if isinstance(origin, dict) and origin.get("kind") == "human" and d.get("type") == "user":
            human = True
        s["cwd"] = d.get("cwd") or s["cwd"]
        msg = d.get("message") or {}
        if d.get("type") == "user":
            asks = [t for t in _texts(msg.get("content"), ("text",)) if t.strip() and not NOISE.match(t)]
            if asks:
                s["turns"].append({"ts": d.get("timestamp", ""), "ask": "\n".join(asks), "answer": ""})
        elif d.get("type") == "assistant" and s["turns"]:
            said = [t for t in _texts(msg.get("content"), ("text",)) if t.strip()]
            if said:
                s["turns"][-1]["answer"] = said[-1]  # 这一轮最后说的那段，通常是结论
    if modern and not human:
        # 在桌面会话的 shell 里跑的 `claude -p` 继承了 entrypoint=claude-desktop，认不出是 sdk；但它没有一轮是人打的
        return {**s, "turns": []}
    return s


def read_codex(path: Path) -> dict:
    s = {"turns": [], "cwd": "", "title": "", "id": path.stem}
    for d in _lines(path):
        p = d.get("payload")
        if not isinstance(p, dict):
            continue
        if d.get("type") == "session_meta":
            s["cwd"] = p.get("cwd") or s["cwd"]
            s["id"] = str(p.get("id") or s["id"])
            if "exec" in str(p.get("originator") or ""):
                return {**s, "turns": []}  # codex exec：无头自动化
            continue
        if d.get("type") != "response_item" or p.get("type") != "message":
            continue
        if p.get("role") == "user":
            asks = [t for t in _texts(p.get("content"), ("input_text",)) if t.strip() and not NOISE.match(t)]
            if asks:
                s["turns"].append({"ts": d.get("timestamp", ""), "ask": "\n".join(asks), "answer": ""})
        elif p.get("role") == "assistant" and s["turns"]:
            said = [t for t in _texts(p.get("content"), ("output_text",)) if t.strip()]
            if said:
                s["turns"][-1]["answer"] = said[-1]
    return s


# Cursor 在每条提问前面加 `<timestamp>Wednesday, Oct 8, 2026, 10:42 PM (UTC-7)</timestamp>`，问题本身包在
# `<user_query>` 里；记录本身没有时间字段
CURSOR_TS = re.compile(r"<timestamp>\s*\w+,\s*(\w{3})\w*\s+(\d{1,2}),\s*(\d{4}),\s*(\d{1,2}):(\d{2})\s*([AP]M)?"
                       r"\s*(?:\(UTC([+-]\d{1,2})(?::?(\d{2}))?\))?\s*</timestamp>", re.I)
CURSOR_QUERY = re.compile(r"<user_query>(.*?)</user_query>", re.S)
CURSOR_WRAP = re.compile(r"<(timestamp|image_files|attached_files|user_info|rules|agent_requestable_workspace_rules|"
                         r"open_and_recently_viewed_files|system_reminder|git_status)>.*?</\1>", re.S)
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                      "dec"), 1)}


def _cursor_ts(text: str) -> str:
    """The `<timestamp>` Cursor puts on a question, as an ISO string in UTC; "" when there is none."""
    m = CURSOR_TS.search(text)
    if not m or m.group(1).lower()[:3] not in MONTHS:
        return ""
    mon, day, year, hh, mm, ampm, oh, om = m.groups()
    hour = int(hh) % 12 + (12 if (ampm or "").upper() == "PM" else 0) if ampm else int(hh)
    off = timedelta(hours=int(oh or 0), minutes=(int(om or 0) * (-1 if (oh or "").startswith("-") else 1)))
    try:
        local = datetime(int(year), MONTHS[mon.lower()[:3]], int(day), hour, int(mm), tzinfo=timezone(off))
    except ValueError:
        return ""
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def cursor_cwd(slug: str) -> str:
    """`Users-fe1-Cursor-dsh-saas` → `/Users/fe1/Cursor/dsh-saas`: Cursor names a project folder after its path with
    `/` turned into `-`, so a name that itself has a `-` is ambiguous. Walk the disk and take the path that exists."""
    parts = [p for p in slug.split("-") if p]

    def walk(base: Path, i: int) -> Path | None:
        if i == len(parts):
            return base
        for j in range(len(parts), i, -1):  # 先试最长的名字
            nxt = base / "-".join(parts[i:j])
            if nxt.is_dir():
                found = walk(nxt, j)
                if found:
                    return found
        return None

    root = Path(Path.home().anchor or "/")
    found = walk(root, 0)
    return str(found) if found else ""


def read_cursor(path: Path) -> dict:
    """{turns, cwd, title, id} of one Cursor agent transcript (`agent-transcripts/<id>/<id>.jsonl`)."""
    s = {"turns": [], "cwd": "", "title": "", "id": path.stem}
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except OSError:
        mtime = ""
    for d in _lines(path):
        msg = d.get("message") or {}
        if d.get("role") == "user":
            raw = "\n".join(t for t in _texts(msg.get("content"), ("text",)) if t.strip())
            qs = CURSOR_QUERY.findall(raw)
            ask = "\n".join(q.strip() for q in qs) if qs else CURSOR_WRAP.sub("", raw).strip()
            if ask and not NOISE.match(ask):
                # 没有 <timestamp> 的提问记在文件最后修改的时刻上
                s["turns"].append({"ts": _cursor_ts(raw) or mtime, "ask": ask, "answer": ""})
        elif d.get("role") == "assistant" and s["turns"]:
            said = [t for t in _texts(msg.get("content"), ("text",)) if t.strip()]
            if said:
                s["turns"][-1]["answer"] = said[-1]
    # 记录在 `<项目目录名>/agent-transcripts/<id>/<id>.jsonl`
    up = path.parents
    if len(up) >= 3 and up[1].name == "agent-transcripts":
        s["cwd"] = cursor_cwd(up[2].name)
        s["project"] = "" if s["cwd"] or up[2].name == "empty-window" else up[2].name  # 目录已删：用记录目录名
    return s


def transcripts(since: date) -> list[tuple[str, Path]]:
    """Transcript files touched on or after `since` (mtime), oldest first."""
    cut = datetime.combine(since, datetime.min.time()).timestamp()
    found: list[tuple[float, str, Path]] = []
    for agent, root in roots().items():
        if not root.is_dir():
            continue
        for path in root.rglob("*.jsonl"):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime < cut or "subagents" in path.parts:
                continue
            if agent == "cursor" and "agent-transcripts" not in path.parts:
                continue  # ~/.cursor/projects 下还有别的 JSONL（工具输出之类），只要会话记录
            found.append((mtime, agent, path))
    return [(a, p) for _, a, p in sorted(found)]


def agent_of(path: Path) -> str:
    """Which agent wrote a transcript, from where it lives (or, failing that, its first lines)."""
    for agent, root in roots().items():
        try:
            path.resolve().relative_to(root.resolve())
            return agent
        except ValueError:
            pass
    if "agent-transcripts" in path.parts:
        return "cursor"
    return "codex" if path.name.startswith("rollout-") else "claude-code"


READERS = {"claude-code": read_claude, "codex": read_codex, "cursor": read_cursor}


def excluded(s: dict, roots_out: list[str]) -> bool:
    """`#不记` in any question of the session, or its project root on the exclude list."""
    if any(NO_CAPTURE.search(t["ask"] or "") for t in s["turns"]):
        return True
    root = project_root(s["cwd"]) if s["cwd"] and roots_out else ""
    return bool(root) and any(_within(root, r) for r in roots_out)


def _within(path: str, base: str) -> bool:
    """`path` is `base` or under it, by path parts (Windows separators and case included), never by string prefix."""
    try:
        Path(path).relative_to(base)
        return True
    except ValueError:
        return False


def collect(since: date, until: date, files: list[Path] | None = None, roots_out: list[str] | None = None,
            dropped: dict[str, str] | None = None) -> list[dict]:
    """One entry per (session, local day): {agent, id, day, project, title, turns}. Sessions kept out (`excluded`)
    and headless runs are left out, `dropped` maps their ids to why ("kept out" / "headless")."""
    out: list[dict] = []
    for agent, path in ([(agent_of(f), f) for f in files] if files else transcripts(since)):
        s = READERS[agent](path)
        if not s["turns"]:
            if dropped is not None:
                dropped[s["id"]] = "headless"  # 无头调用：以前误导入过的页这一轮删掉
            continue
        if excluded(s, roots_out or []):
            if dropped is not None:
                dropped[s["id"]] = "kept out"
            continue
        by_day: dict[date, list[dict]] = defaultdict(list)
        for t in s["turns"]:
            day = local_day(t["ts"])
            if day and since <= day <= until:
                by_day[day].append(t)
        for day, turns in by_day.items():
            out.append({"agent": agent, "id": s["id"], "day": day, "turns": turns,
                        "project": Path(s["cwd"]).name if s["cwd"] else s.get("project", ""),
                        "root": project_root(s["cwd"]),
                        "title": s["title"] or clean(turns[0]["ask"], 60).split("\n")[0]})
    out.sort(key=lambda e: (e["day"], e["turns"][0]["ts"]))
    return out


def turn_key(t: dict) -> str:
    """A turn's identity: when it was asked and what. A fork copies both verbatim; two sessions that merely start with
    the same question ("再来一轮") were asked at different times."""
    import hashlib

    return hashlib.sha1(f"{t['ts']}|{t['ask'][:400]}".encode("utf-8")).hexdigest()[:12]


def find_transcript(agent: str, sid: str) -> Path | None:
    """The transcript file of one session, from its id: only used when a fork's earlier half has to be re-read."""
    root = roots().get(agent)
    if not root or not root.is_dir() or not re.fullmatch(r"[0-9A-Za-z._-]+", sid):
        return None
    pattern = {"claude-code": f"*/{sid}.jsonl", "codex": f"**/*{sid}.jsonl",
               "cursor": f"*/agent-transcripts/{sid}/{sid}.jsonl"}[agent]
    return next(iter(sorted(root.glob(pattern))), None)


def dedupe_forks(entries: list[dict], folder: Path) -> tuple[list[dict], list[Path], int]:
    """Entries with turns copied from another session removed: (entries to write, our pages to delete, how many dropped).

    Sessions of one day whose first turns are the same turn (same time, same question) are one conversation split by
    a fork or resume. The one with the most turns keeps everything; each other keeps only the turns nobody before it
    kept, and points at the session that has the rest; one with nothing of its own gets no page (and its old page, if
    we wrote one, goes). A page of ours for such a session that is not in this run is read back from its transcript."""
    for e in entries:
        e["keys"] = [turn_key(t) for t in e["turns"]]
        e["first_key"] = e["keys"][0]  # 切掉共有轮次后仍按原来的第一轮归组（写进页面的 first_turn）
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for e in entries:
        groups[(e["day"].isoformat(), e["keys"][0])].append(e)
    if folder.is_dir():
        mine = {(e["id"], e["day"].isoformat()) for e in entries}
        for path in folder.glob("*.md"):
            meta = frontmatter(path)
            key = (meta.get("date", ""), meta.get("first_turn", ""))
            if meta.get("source") != MARK or key not in groups or (meta.get("session"), key[0]) in mine:
                continue
            found = find_transcript(meta.get("agent", ""), meta.get("session", ""))
            if not found:
                continue
            day = date.fromisoformat(key[0])
            for e in collect(day, day, [found]):
                e["keys"] = [turn_key(t) for t in e["turns"]]
                e["first_key"] = e["keys"][0] if e["keys"] else ""
                if e["keys"] and e["keys"][0] == key[1]:
                    groups[key].append(e)
                    entries.append(e)
                    mine.add((e["id"], key[0]))
    drop, delete = set(), []
    for group in groups.values():
        if len({e["id"] for e in group}) < 2:
            continue
        taken: set[str] = set()
        owner = ""
        for e in sorted(group, key=lambda x: (-len(x["turns"]), x["turns"][-1]["ts"], x["id"])):
            own = [(k, t) for k, t in zip(e["keys"], e["turns"]) if k not in taken]
            if not own:
                drop.add(id(e))
                continue
            if len(own) < len(e["turns"]):
                e["forked_from"], e["shared_turns"] = owner, len(e["turns"]) - len(own)
                e["keys"], e["turns"] = [k for k, _ in own], [t for _, t in own]
            owner = owner or e["id"]
            taken.update(e["keys"])
    if drop:
        have = existing(folder)
        delete = [have[(e["id"], e["day"].isoformat())] for e in entries
                  if id(e) in drop and (e["id"], e["day"].isoformat()) in have]
    return [e for e in entries if id(e) not in drop], delete, len(drop)


DAILY_ID = re.compile(r"`(?:(claude|claude-code|codex|cursor|dsh|sygj):)?([0-9A-Za-z][0-9A-Za-z._-]{7,})`")


def daily_coverage(vault: Path) -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    """What another collector already logged: ({(session id or 8+ char prefix, day): log page}, {day: log page}).
    A log covers only its own day: a session it names that ran on past midnight is not covered for the next day.

    A `type: daily-log` page under `05 时间日志/` counts; it covers its whole day when a collector wrote it
    (`source_kind` in its frontmatter), and covers a session it names by id (`` `claude:5ee9241f-…` ``, or a bare
    hex prefix such as `` `f8f9e03e` ``, which is how a distilled log cites sessions). Our own pages never count."""
    ids: dict[tuple[str, str], str] = {}
    days: dict[str, str] = {}
    base = zones.path(vault, "05 时间日志")
    if not base.is_dir():
        return ids, days
    for path in base.glob("*/*.md"):
        if path.parent.name == Path(FOLDER).name:
            continue
        meta = frontmatter(path)
        if meta.get("type", "").strip("\"'") != "daily-log":
            continue
        rel = zones.canon(vault, str(path.relative_to(vault)).replace(os.sep, "/"))
        day = meta.get("date", "").strip("\"'")
        if not day:
            continue
        if meta.get("source_kind"):
            days.setdefault(day, rel)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for agent, sid in DAILY_ID.findall(text):
            if agent or re.fullmatch(r"[0-9a-f]{8,}", sid):
                ids.setdefault((sid, day), rel)
    return ids, days


def covered_by(e: dict, ids: dict[str, str], days: dict[str, str]) -> str:
    """The daily log that already has this session-day, or ''."""
    sid, day = e["id"], e["day"].isoformat()
    if (sid, day) in ids:
        return ids[(sid, day)]
    for (known, d), rel in ids.items():
        if d == day and sid.startswith(known):
            return rel
    return days.get(day, "")


def file_name(e: dict) -> str:
    title = UNSAFE.sub(" ", e["title"]).strip(" .") or "会话"
    return f"{e['day'].isoformat()}｜{title[:40].strip()}（{e['id'][:8]}）.md"


def frontmatter(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")[:800].replace("\r\n", "\n")
    except OSError:
        return {}
    if not text.startswith("---\n"):
        return {}
    meta = {}
    for line in text[4:].split("\n---", 1)[0].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta


def existing(folder: Path) -> dict[tuple[str, str], Path]:
    """Our pages by (session id, day), so a renamed session replaces its old page instead of adding one."""
    found: dict[tuple[str, str], Path] = {}
    if folder.is_dir():
        for path in folder.glob("*.md"):
            meta = frontmatter(path)
            if meta.get("source") == MARK and meta.get("session"):
                found[(meta["session"], meta.get("date", ""))] = path
    return found


def old_digest(path: Path | None, turns: int) -> str:
    """Keep a digest already made for this page unless the session has grown since."""
    if not path or not path.is_file():
        return ""
    meta = frontmatter(path)
    if meta.get("digest_turns") != str(turns):
        return ""
    text = path.read_text(encoding="utf-8")
    m = re.search(r"\n(?:" + "|".join(re.escape(h) for h in DIGEST_HEADS) + r")\n\n(.*?)\n\n## ", text, re.S)
    return m.group(1).strip() if m else ""


DIGEST_HEAD = "## 定了什么、改了什么（模型提炼）"
# 旧页的标题（1.2 及以前要人确认）：读的时候照样认
DIGEST_HEADS = (DIGEST_HEAD, "## 定了什么、改了什么（模型提炼，待你确认）")
CONTEXT_TURNS = 2  # 续提炼时往前多带几轮：改主意常常跨过上次提炼停下的地方


def prior_digest(path: Path | None, e: dict) -> tuple[list[str], int]:
    """(lines, turns they cover) of a digest made when this session was shorter, so only the new turns are sent.
    A session ends many times (closing a window, `/clear`, a resume that ends again); re-sending the whole excerpt each
    time would multiply the cost by the number of ends. Only when the first turn is the same and nothing was cut."""
    if not path or not path.is_file() or e.get("forked_from"):
        return [], 0
    meta = frontmatter(path)
    try:
        done = int(meta.get("digest_turns", ""))
    except ValueError:
        return [], 0
    if not 0 < done < len(e["turns"]) or meta.get("first_turn") != e.get("first_key"):
        return [], 0
    text = path.read_text(encoding="utf-8")
    head = next((h for h in DIGEST_HEADS if h in text), "")
    block = text.split(head, 1)[1].split("\n## ", 1)[0] if head else ""
    lines = [ln.strip() for ln in block.splitlines() if ln.strip().startswith(("-", "*"))]
    return (lines, done) if lines else ([], 0)


def render(e: dict, digest: str = "", covers: int | None = None) -> str:
    """The page for one session and day. `covers`: how many turns the digest was made from (all of them by default)."""
    turns = e["turns"]
    meta = ["---", "type: session-excerpt", f"source: {MARK}", "status: imported", f"date: {e['day'].isoformat()}",
            f"agent: {e['agent']}", f"session: {e['id']}", f"project: {e['project'] or '-'}",
            *([f"project_root: {e['root']}"] if e.get("root") else []), f"turns: {len(turns)}",
            f"first_turn: {e.get('first_key') or turn_key(turns[0])}"]
    if e.get("forked_from"):
        meta.append(f"forked_from: {e['forked_from']}")
    if e.get("covered_by"):
        meta.append(f'covered_by: "[[{e["covered_by"].removesuffix(".md")}]]"')
    title = clean(e["title"], 80).replace("\n", " ")
    meta.append(f"title: {title}")
    if digest:
        meta.append(f"digest_turns: {len(turns) if covers is None else covers}")
        first = re.sub(r"^[-*]\s*", "", digest.strip().splitlines()[0])
        meta.append(f"how: {first}")  # 召回命中这页时先给的那一句：这段会话定下来的第一件事
    else:
        meta.append(f"how: 会话摘录（{len(turns)} 轮，还没提炼）：{title}")
    out = meta + ["---", "", f"# {title}", ""]
    if digest:
        out += [DIGEST_HEAD, "", digest.strip(), ""]
    out += [f"## 摘录（{e['day'].isoformat()} · {e['project'] or '?'} · {e['agent']} · {len(turns)} 轮）", "",
            "只留你的提问和每轮最后的回答，已脱敏。上面的提炼由模型自动写入，每一轮改了什么记在「记忆变更记录」里，不对可以一条命令撤销。", ""]
    if e.get("covered_by"):
        out[-1:-1] = [f"当天的日更：[[{e['covered_by'].removesuffix('.md')}]]（那页是当天总结，这页是逐轮原话）。"]
    if e.get("forked_from"):
        out[-1:-1] = [f"这段会话的前 {e['shared_turns']} 轮和会话 `{e['forked_from'][:8]}` 共有，在那一页。"]
    size = sum(len(x) for x in out)
    for i, t in enumerate(turns):
        if size > PAGE_MAX:
            out.append(f"- （还有 {len(turns) - i} 轮，超出一页的摘录上限，未展开）")
            break
        block = [f"- **问**（{local_hm(t['ts'])}）：" + clean(t["ask"], ASK_MAX).replace("\n", "\n  ")]
        if t["answer"]:
            block.append("  **答**：" + clean(t["answer"], ANSWER_MAX).replace("\n", "\n  "))
        out += block
        size += sum(len(b) for b in block)
    return "\n".join(out).rstrip() + "\n"


DISTILL_PROMPT = """下面是一个人和他的编程 agent 在 {day} 的一段会话摘录（项目：{project}；只有提问和每轮最后的回答，已脱敏）。

只做一件事：列出这段会话里**定下来的事**和**改主意的事**，每条一行，最多 8 条。
- 定下来的事：一个决定、一条规则、一个做法，写成能直接照做的一句话（例：「发版只从 main 打 tag」）。
- 改主意的事：先定了 A，后来改成 B，写成「原来 A → 改成 B」。
- 每条行尾用括号标出处：那一轮提问的时间，例如（14:05）。
- 只写摘录里明确出现的内容，不推测、不补充；没有就只回一行「- （这段会话没有定下来的事）」。
- agent 提议、这个人接受了或接着照做的，也算定下来的事。
- 不算的（不要列）：操作步骤和执行过程（「先跑一下测试」「重启服务」）；排查和讨论（「可能是缓存问题」），除非最后选定了
  其中一个；一次性的事（「把这段文字翻译一下」）。
- 输出纯 Markdown 列表，不要前言和总结。

摘录：

{text}
"""
CHANGES_PROMPT = """下面是一个人和他的编程 agent 在 {day} 的一段会话摘录（项目：{project}；只有提问和每轮最后的回答，已脱敏）。

只做一件事：找出这段会话里**改主意**的地方：先定了（或在用）A，后来改成了 B。每条一行，写成「原来 A → 改成 B」，行尾用括号
标出改的那一轮的提问时间，例如（14:05）。最多 8 条。
- 只写摘录里明确出现的改动；A 和 B 都要写清楚，让人不看原文也知道改了什么。
- agent 提议改、这个人接受了或接着照做的，也算。
- 没有就只回一行「- （这段会话没有改主意的事）」。
- 输出纯 Markdown 列表，不要前言和总结。

摘录：

{text}
"""
SEGMENT_CHARS = 6_000   # 长会话按轮切成这么长的段分别提炼：一次只看整段，写满 8 条就把后面的决定挤掉了
DIGEST_LINES = 24       # 一页最多留这么多条；开新会话时只带 8 条，改主意的排在最前
NONE_LINES = ("没有定下来的事", "没有改主意的事")
TURN_MARK = re.compile(r"(?m)^- \*\*问\*\*（")


def segments(body: str) -> list[str]:
    """The excerpt cut at turn boundaries into pieces of about SEGMENT_CHARS."""
    starts = [m.start() for m in TURN_MARK.finditer(body)]
    if not starts:
        return [body]
    head, out, cur = body[: starts[0]], [], ""
    for a, b in zip(starts, starts[1:] + [len(body)]):
        turn = body[a:b]
        if cur and len(cur) + len(turn) > SEGMENT_CHARS:
            out.append(head + cur)
            cur = ""
        cur += turn
    return out + ([head + cur] if cur else [])


def merge_digest(lines: list[str]) -> list[str]:
    """Drop "nothing decided" lines and near-duplicates (the same change found in a segment and by the change pass),
    put changes of mind first, keep at most DIGEST_LINES."""
    import recall_index as ri

    def words(s: str) -> set[str]:
        return {t for t in ri.question_terms(s) if t not in ri.EN_FUNCTION}

    kept: list[str] = []
    for ln in lines:
        if any(n in ln for n in NONE_LINES):
            continue
        w = words(ln)
        if any(len(w & words(k)) / max(1, len(w | words(k))) >= 0.5 for k in kept):
            continue
        kept.append(ln)
    return sorted(kept, key=lambda ln: "→" not in ln)[:DIGEST_LINES]


def from_turn(body: str, n: int) -> str:
    """The excerpt from its n-th turn on (the heading kept)."""
    starts = [m.start() for m in TURN_MARK.finditer(body)]
    if not starts or n <= 0:
        return body
    return body[: starts[0]] + (body[starts[n]:] if n < len(starts) else "")


def distill(e: dict, page: str, vault: Path, dry: bool, start: int = 0, prior: list[str] | None = None
            ) -> tuple[str, int]:
    """What was decided and what changed, from one session-day: each segment distilled, plus one pass over the whole
    excerpt for changes of mind (a change often spans segments: decided early, changed later).

    `start` > 0 continues an earlier digest (`prior`, made from the first `start` turns): only the new turns are
    segmented, the change pass sees them with CONTEXT_TURNS before and the earlier lines, and the lines are merged."""
    whole = page.split("\n## 摘录", 1)[-1]
    body = from_turn(whole, start)[:DISTILL_MAX]
    fill = {"day": e["day"].isoformat(), "project": e["project"] or "?"}
    prompts = [DISTILL_PROMPT.format(**fill, text=seg) for seg in segments(body)]
    changes = from_turn(whole, start - CONTEXT_TURNS)[:DISTILL_MAX] if start else body
    if prior:
        changes = "这段会话前面已经记下：\n" + "\n".join(prior) + "\n\n" + changes
    prompts.append(CHANGES_PROMPT.format(**fill, text=changes))
    chars = sum(len(p) for p in prompts)
    if dry:
        return "", chars
    import llm

    lines: list[str] = []
    for prompt in prompts:
        text = llm.complete(prompt, vault)
        lines += [ln.rstrip() for ln in redact(text).splitlines() if ln.strip().startswith(("-", "*"))]
    merged = merge_digest(list(prior or []) + lines)
    return "\n".join(merged) if merged else "- （这段会话没有定下来的事）", chars


_LOCK = None


def old_lines(path: Path | None) -> list[str]:
    """The digest lines a page had before this run (any heading version)."""
    if not path or not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    head = next((h for h in DIGEST_HEADS if h in text), "")
    block = text.split(head, 1)[1].split("\n## ", 1)[0] if head else ""
    return [ln.strip() for ln in block.splitlines() if ln.strip().startswith(("-", "*"))]


def log_run(vault: Path, rid: str, pages: list[dict], verdicts: list[dict], gone: list[Path],
            touched: list[Path]) -> None:
    """Make the run observable: one commit with exactly what it wrote, then its entry in the change ledger."""
    import capture_ledger

    if not (pages or verdicts or gone):
        return
    added = sum(len(p["added"]) for p in pages)
    sha = capture_ledger.commit(vault, rid, touched, f"run {rid}（{len(pages)} 页新增 {added} 条，判定纠正 {len(verdicts)} 条）")
    undo = f"python3 {Path(__file__).resolve()} --vault '{vault}' --undo {rid}"
    entry = capture_ledger.section(vault, rid, pages, verdicts, gone, undo, sha)
    ledger = capture_ledger.append(vault, entry)
    capture_ledger.commit(vault, rid, [ledger], f"变更记录 run {rid}", tagged=False)


def hold_lock() -> None:
    """One import at a time (a session-end hook and the nightly run, or two windows closing together): the second waits
    and then finds the first one's digest, instead of both sending the same session to the model."""
    global _LOCK
    try:
        import fcntl
    except ImportError:  # Windows：不加锁，最坏是同一会话提炼两次
        return
    path = state_file().with_name("import.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    _LOCK = path.open("w")
    fcntl.flock(_LOCK, fcntl.LOCK_EX)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--vault", default=vault_path())
    ap.add_argument("--days", type=int, default=7, help="how many days back, today included (default 7)")
    ap.add_argument("--yesterday", action="store_true", help="only yesterday (what the nightly job runs)")
    ap.add_argument("--distill", action="store_true", help="also ask the model lane what each session decided")
    ap.add_argument("--dry-run", action="store_true", help="write nothing, send nothing: say what would happen")
    ap.add_argument("--consent", action="store_true", help="record your yes for the nightly job, then import")
    ap.add_argument("--revoke", action="store_true", help="the nightly job stops importing")
    ap.add_argument("--nightly", action="store_true", help="run only when consent was given (used by nightly.py)")
    ap.add_argument("--file", action="append", default=[], help="import this transcript only, all its days "
                    "(the session-end hook); runs only when consent was given")
    ap.add_argument("--overlap", choices=("link", "skip"), default="",
                    help="a session another collector's daily log already has: link the page to that log (default), or "
                         "write no page; saved with --consent")
    ap.add_argument("--local", action="store_true", help="write the excerpt only, never call a model (what the "
                    "turn-end hooks run; the session-end hook distills)")
    ap.add_argument("--intraday", action="store_true", help="today and yesterday, only when consent was given, with the "
                    "lane recorded then (what a daytime timer runs)")
    ap.add_argument("--undo", default="", metavar="RUN", help="take back everything run RUN wrote (its id is in "
                    "90 系统文件/自动化/记忆变更记录.md)")
    ap.add_argument("--exclude-root", action="append", default=[], help="never import sessions under this project "
                    "root; repeatable, saved with --consent")
    ap.add_argument("--distill-max", type=int, default=DISTILL_SESSIONS, help="distill at most this many sessions, newest first")
    ap.add_argument("--cli", default="", help=argparse.SUPPRESS)
    ap.add_argument("--model", default="", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.cli:
        os.environ["KROUTER_LEARN_CLI"] = args.cli
    if args.model:
        os.environ["KROUTER_LEARN_MODEL"] = args.model
    if args.revoke:
        save_state({**load_state(), "consent": False})
        print(json.dumps({"import": "revoked"}))
        return 0
    if not args.vault:
        print("set OBSIDIAN_VAULT", file=sys.stderr)
        return 2
    vault = Path(args.vault).expanduser()
    if args.undo:
        import capture_ledger

        res = capture_ledger.undo(vault, args.undo)
        print(json.dumps(res, ensure_ascii=False))
        return 0 if res.get("undo") == "done" else 1
    st = load_state()
    scheduled = args.nightly or args.intraday or bool(args.file)
    if scheduled and not st.get("consent"):
        print(json.dumps({"import": "off", "reason": "no consent yet (import_sessions.py --consent)",
                          "chars": 0, "writes": []}))
        return 0
    distill_on = (args.distill or bool(scheduled and st.get("distill"))) and not args.local
    if scheduled and st.get("cli") and not args.cli:
        # 会话结束时在会话自己的环境里跑：shell 里碰巧有哪个 API key 就发给谁，不该由它决定。用同意时点名的那条
        os.environ["KROUTER_LEARN_CLI"] = st["cli"]
    if not args.dry_run:
        hold_lock()
    today = date.today()
    if args.yesterday or args.nightly:
        since = until = today - timedelta(days=1)
    elif args.intraday:
        since, until = today - timedelta(days=1), today
    else:
        since, until = today - timedelta(days=max(args.days, 1) - 1), today
    files = [Path(f).expanduser() for f in args.file if Path(f).expanduser().is_file()]
    if args.file:
        since, until = date(1970, 1, 1), today
        if not files:
            print(json.dumps({"import": "skipped", "reason": "transcript not found", "chars": 0, "writes": []}))
            return 0
    roots_out = [str(Path(r).expanduser().resolve()) for r in args.exclude_root] or list(st.get("exclude_roots") or [])
    dropped: dict[str, str] = {}
    entries = collect(since, until, files or None, roots_out, dropped)
    folder = zones.path(vault, FOLDER)
    entries, forked_pages, forks_dropped = dedupe_forks(entries, folder)
    overlap = args.overlap or st.get("overlap") or "link"
    ids, days = daily_coverage(vault)
    covered = skipped_covered = 0
    for e in entries:
        e["covered_by"] = covered_by(e, ids, days)
        covered += bool(e["covered_by"])
    if overlap == "skip":
        skipped_covered = sum(1 for e in entries if e["covered_by"])
        entries = [e for e in entries if not e["covered_by"]]
    have = existing(folder)
    removed = [path for (sid, _day), path in have.items() if sid in dropped]
    to_distill = {id(e) for e in sorted((e for e in entries if len(e["turns"]) >= DISTILL_MIN_TURNS),
                                        key=lambda e: e["turns"][-1]["ts"], reverse=True)[:max(args.distill_max, 0)]}
    import capture_ledger
    import corrections

    rid = capture_ledger.run_id()
    cands = corrections.pending(folder)
    changed_pages: list[dict] = []   # 这一轮新写进提炼的行，记进变更记录
    verdicts: list[dict] = []
    touched: list[Path] = []          # 这一轮写过或删过的文件，进同一个提交
    written, kept, sent, calls, failed, incremental = [], [], 0, 0, 0, 0
    exp_cards = exp_failed = exp_uses = 0
    import experience
    uses_on = experience.digest_on() and not args.dry_run
    for e in entries:
        if uses_on:
            # 经验卡被提出、被采纳（回复里带了卡号、下一句说照做了）：只读记录，不调模型，摘要按它排序
            try:
                exp_uses += experience.record_uses(vault, f"{e['agent']}:{e['id'][:8]}", e["turns"])
            except Exception as exc:  # noqa: BLE001
                print(f"experience uses: {str(exc)[:200]}", file=sys.stderr)
        target = folder / file_name(e)
        if target.exists() and frontmatter(target).get("source") != MARK:
            kept.append(target.name)
            continue
        before = have.get((e["id"], e["day"].isoformat()))
        page = render(e)
        digest = old_digest(before, len(e["turns"]))
        covers = len(e["turns"])
        fresh = False
        if not digest and distill_on and id(e) in to_distill:
            prior, done = prior_digest(before, e)
            incremental += bool(done)
            try:
                digest, n = distill(e, page, vault, args.dry_run, start=done, prior=prior)
                sent += n
                calls += 1
                fresh = bool(digest)
            except Exception as exc:  # noqa: BLE001  模型失败不影响本地摘录
                failed += 1
                print(f"distill {target.name}: {str(exc)[:200]}", file=sys.stderr)
            if (fresh or args.dry_run) and experience.enabled():
                # 经验卡（实验，KROUTER_EXPERIENCE=1）：同一段摘录再问一次「遇到什么、怎么做、结果如何」；没有模型就安静跳过
                link = f"[[{zones.canon(vault, str(target.relative_to(vault)).replace(os.sep, '/')).removesuffix('.md')}]]"
                try:
                    excerpt = from_turn(page.split("\n## 摘录", 1)[-1], done)[:DISTILL_MAX]
                    cards, n = experience.extract(e, excerpt, vault, link, args.dry_run)
                    sent += n
                    for card in cards:
                        touched.append(card)
                        changed_pages.append({"path": card, "agent": e["agent"], "session": e["id"],
                                              "added": ["经验卡：" + card.stem.removeprefix("经验｜")]})
                    exp_cards += len(cards)
                except Exception as exc:  # noqa: BLE001
                    exp_failed += 1
                    print(f"experience {target.name}: {str(exc)[:200]}", file=sys.stderr)
        mine = cands.pop((e["day"].isoformat(), e["id"][:8]), []) if fresh and not args.dry_run else []
        if mine:
            # 你当场说的纠正，提炼里有对应的行就挂上那一行；没有就用你的原话补记进提炼（提炼漏掉的往往正是这一句）
            link = f"[[{zones.canon(vault, str(target.relative_to(vault)).replace(os.sep, '/')).removesuffix('.md')}]]"
            settled = corrections.settle(mine, [ln for ln in digest.splitlines() if ln.strip().startswith(("-", "*"))])
            extra = [corrections.own_line(r) for r in settled if not r["ok"] and r["said"].strip()]
            if extra:
                digest = digest.rstrip("\n") + "\n" + "\n".join(extra) + "\n"
            verdicts += [{**r, "link": link} if r["ok"] or not r["said"].strip()
                         else {**r, "link": link, "ok": True, "kind": "补记", "line": corrections.own_line(r)[2:]}
                         for r in settled]
        if not digest:
            # 这次没提炼（每轮的本地导入、提炼失败、超出这一轮的上限）：上次提炼的留着，并照实记它只覆盖到第几轮，
            # 下次提炼只发新增的那几轮
            prior, done = prior_digest(before, e)
            if prior:
                digest, covers = "\n".join(prior), done
        if digest:
            page = render(e, digest, covers)
        if fresh and not args.dry_run:
            had = set(old_lines(before))
            new = [ln for ln in digest.splitlines() if ln.strip().startswith(("-", "*"))]
            added = [ln for ln in new if ln not in had and not any(x in ln for x in NONE_LINES)]
            if added:
                changed_pages.append({"path": target, "agent": e["agent"], "session": e["id"], "added": added})
        if not args.dry_run:
            folder.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".tmp")
            tmp.write_text(page, encoding="utf-8")
            os.replace(tmp, target)
            if before and before != target and before.exists():
                before.unlink()  # 会话改了标题：换成新文件名，不留两份
                touched.append(before)
            touched.append(target)
        written.append(zones.canon(vault, str(target.relative_to(vault)).replace(os.sep, "/")))
    if not args.dry_run:
        gone = []
        for path in forked_pages + removed:  # 整段都在另一个会话里的旧页；标了不记的会话以前写过的页
            if path.exists() and frontmatter(path).get("source") == MARK:
                path.unlink()
                gone.append(path)
        if verdicts:
            # hook 当场记下的候选先原样进一次提交：撤销这一轮时候选回到"待判定"，而不是跟着消失
            capture_ledger.commit(vault, rid, sorted({v["page"] for v in verdicts}), "纠正候选（hook 记下）", tagged=False)
        touched += corrections.mark(verdicts)
        log_run(vault, rid, changed_pages, verdicts, gone, touched + gone)
    if args.consent and not args.dry_run:
        save_state({**st, "consent": True, "distill": bool(args.distill), "overlap": overlap, "cli": args.cli,
                    "exclude_roots": roots_out,
                    "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    row = {"import": "dry-run" if args.dry_run else "done", "from": since.isoformat(), "through": until.isoformat(),
           "sessions": len({e["id"] for e in entries}), "pages": len(entries),
           "turns": sum(len(e["turns"]) for e in entries), "agents": sorted({e["agent"] for e in entries}),
           "distilled": calls, "distill_incremental": incremental, "distill_failed": failed, "chars": sent, "overlap": overlap,
           "covered_by_daily_log": covered, "skipped_covered": skipped_covered, "fork_duplicates": forks_dropped,
           "kept_out": sum(1 for v in dropped.values() if v == "kept out"), "removed_kept_out": len(removed),
           "writes": written if len(written) <= 20 else written[:20] + [f"… {len(written) - 20} more"],
           "kept_foreign": kept,
           **({"experience_cards": exp_cards, "experience_failed": exp_failed} if experience.enabled() else {}),
           **({"experience_uses": exp_uses} if exp_uses else {})}
    print(json.dumps(row, ensure_ascii=False))
    return 1 if failed and not calls else 0


if __name__ == "__main__":
    raise SystemExit(main())
