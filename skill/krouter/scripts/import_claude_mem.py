#!/usr/bin/env python3
"""Bring claude-mem's memory into the vault: its session summaries as log pages, its decisions as pages to confirm.

claude-mem (github.com/thedotmack/claude-mem) keeps what happened in each Claude Code session in a local SQLite
database (`~/.claude-mem/claude-mem.db`, or `$CLAUDE_MEM_DATA_DIR/claude-mem.db`): AI-written observations typed
`decision` / `bugfix` / `feature` / `refactor` / `discovery` / `change`, and a summary per session. Keep using it.
This copies what it learned into plain Markdown you own, where a correction can replace an old decision:

- one page per claude-mem session under `05 时间日志/claude-mem/`: the summary (request, learned, completed, next
  steps) and its observations, each with title, facts and type. These are clues, ranked as logs.
- one page per project under `02 经验与方法/从 claude-mem 导入/`: that project's decisions and changes, newest
  first, with date, type and session. claude-mem files most decisions as `change` (seen on 13.35.0: only the reversal
  of an earlier decision came out as `decision`), so `decision`, `change`, `feature`, `bugfix` and `refactor` all go
  in; `discovery` does not. `status: candidate` until you confirm it.
- `--distill` sends each project's decision list (redacted) to the model lane, once, and puts on top of that page the
  decisions still in force and the ones a later decision replaced ("原来 A → 改成 B"). This is the part claude-mem
  does not do: it remembers both and returns whichever matches.

The database is opened read-only; claude-mem is never changed. Pages carry `source: krouter-claude-mem`; a page
without it is never touched. Every text goes through `redact()`. Nothing leaves the machine without `--distill`.
`--consent` lets the nightly job re-import (it runs with `--nightly`); `--revoke` stops it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import zones  # noqa: E402
from krouter_home import project_root, vault_path  # noqa: E402
import hashlib  # noqa: E402
from krouter_redact import redact  # noqa: E402

MARK = "krouter-claude-mem"
LOG_FOLDER = "05 时间日志/claude-mem"
RULE_FOLDER = "02 经验与方法/从 claude-mem 导入"
DECISIONS_MAX = 120   # 一个项目最多列多少条决定（最新的优先）
# 实测（claude-mem 13.35.0）：明确说"我们决定"的事大多被它记成 change，只有推翻旧决定那条记成 decision。
# 所以决定页收这几类；discovery（"某文件不存在"之类）不收
DECISION_TYPES = ("decision", "change", "feature", "bugfix", "refactor")
DISTILL_MAX = 20_000
UNSAFE = re.compile(r"[\\/:*?\"<>|#^\[\]\n\r\t]+")
TYPE_ZH = {"decision": "决定", "bugfix": "修复", "feature": "功能", "refactor": "重构", "discovery": "发现",
           "change": "改动"}


def db_path() -> Path:
    raw = os.environ.get("KROUTER_CLAUDE_MEM_DB")
    if raw:
        return Path(raw).expanduser()
    data = os.environ.get("CLAUDE_MEM_DATA_DIR")
    if not data:
        try:
            settings = json.loads((Path.home() / ".claude-mem/settings.json").read_text(encoding="utf-8"))
            data = settings.get("CLAUDE_MEM_DATA_DIR") or ""
        except (OSError, ValueError):
            data = ""
    return Path(data).expanduser() / "claude-mem.db" if data else Path.home() / ".claude-mem/claude-mem.db"


def state_file() -> Path:
    return Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local/state/krouter") / "import-claude-mem.json"


def load_state() -> dict:
    try:
        return json.loads(state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(data: dict) -> None:
    path = state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}


def when(epoch, text: str = "") -> datetime | None:
    """claude-mem stores epoch milliseconds (older rows: seconds) and an ISO string."""
    try:
        e = float(epoch)
        return datetime.fromtimestamp(e / 1000 if e > 1e11 else e, tz=timezone.utc).astimezone()
    except (TypeError, ValueError, OSError):
        pass
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def _list(raw) -> list[str]:
    if not raw:
        return []
    try:
        val = json.loads(raw)
    except (TypeError, ValueError):
        return [str(raw)]
    if isinstance(val, list):
        return [str(x) for x in val if str(x).strip()]
    return [str(val)]


def clean(text, limit: int = 600) -> str:
    text = redact(re.sub(r"\s+\n", "\n", str(text or "")).strip())
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


def read(con: sqlite3.Connection, since: datetime | None) -> dict[str, dict]:
    """{session id: {project, start, summary, observations}} — column names differ across claude-mem versions
    (`sdk_session_id` → `memory_session_id`), so they are looked up, not assumed."""
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "observations" not in tables:
        raise SystemExit("not a claude-mem database (no observations table)")
    ocols = columns(con, "observations")
    sid = "memory_session_id" if "memory_session_id" in ocols else "sdk_session_id"
    want = [c for c in ("id", sid, "project", "type", "title", "subtitle", "narrative", "text", "facts", "concepts",
                        "files_modified", "created_at", "created_at_epoch") if c in ocols]
    sessions: dict[str, dict] = defaultdict(lambda: {"project": "", "root": "", "start": None, "summary": None, "obs": []})
    for row in con.execute(f"SELECT {', '.join(want)} FROM observations ORDER BY created_at_epoch"):
        r = dict(row)
        at = when(r.get("created_at_epoch"), r.get("created_at"))
        if since and at and at < since:
            continue
        s = sessions[str(r.get(sid))]
        s["project"] = s["project"] or str(r.get("project") or "")
        s["start"] = s["start"] or at
        r["at"] = at
        s["obs"].append(r)
    if "session_summaries" in tables:
        scols = columns(con, "session_summaries")
        ssid = "memory_session_id" if "memory_session_id" in scols else "sdk_session_id"
        want = [c for c in (ssid, "project", "request", "investigated", "learned", "completed", "next_steps", "notes",
                            "created_at", "created_at_epoch") if c in scols]
        for row in con.execute(f"SELECT {', '.join(want)} FROM session_summaries ORDER BY created_at_epoch"):
            r = dict(row)
            at = when(r.get("created_at_epoch"), r.get("created_at"))
            if since and at and at < since:
                continue
            s = sessions[str(r.get(ssid))]
            s["project"] = s["project"] or str(r.get("project") or "")
            s["start"] = s["start"] or at
            s["summary"] = r  # 一个会话可能有多份总结：留最后一份
    # 新版 claude-mem 在 sdk_sessions 里记了 cwd：用它的仓库根路径区分同名项目（两个仓库都叫 `api`）。
    # 老版本没有 cwd，这些会话就不知道属于哪个仓库：照样导入、能查到，但不会被自动带进新会话
    if "sdk_sessions" in tables:
        kcols = columns(con, "sdk_sessions")
        ksid = next((c for c in ("memory_session_id", "sdk_session_id") if c in kcols), "")
        if ksid and "cwd" in kcols:
            for sid_val, cwd in con.execute(f"SELECT {ksid}, cwd FROM sdk_sessions WHERE cwd IS NOT NULL AND cwd != ''"):
                if str(sid_val) in sessions:
                    sessions[str(sid_val)]["root"] = project_root(str(cwd))
    return {k: v for k, v in sessions.items() if v["start"]}


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


def write(path: Path, text: str, dry: bool) -> str:
    """'written' / 'kept' (a page that is not ours) / 'same'."""
    if path.exists():
        if frontmatter(path).get("source") != MARK:
            return "kept"
        if path.read_text(encoding="utf-8") == text:
            return "same"
    if not dry:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    return "written"


def session_title(s: dict) -> str:
    summ = s["summary"] or {}
    first = next((o.get("title") for o in s["obs"] if o.get("title")), "")
    return clean(summ.get("request") or first or "claude-mem 会话", 60).split("\n")[0]


def session_page(key: str, s: dict) -> tuple[str, str]:
    day = s["start"].date().isoformat()
    title = session_title(s)
    name = f"{day}｜{UNSAFE.sub(' ', title)[:40].strip()}（{key[:8]}）.md"
    decisions = [o for o in s["obs"] if o.get("type") == "decision" and o.get("title")]
    how = clean(decisions[0]["title"], 120) if decisions else f"claude-mem 会话：{title}"
    out = ["---", "type: session-excerpt", f"source: {MARK}", "status: imported", f"date: {day}",
           f"session: {key}", f"project: {s['project'] or '-'}", *([f"project_root: {s['root']}"] if s["root"] else []),
           f"title: {title}", f"how: {how}", "---", "",
           f"# {title}", "", f"由 claude-mem 记录（项目 {s['project'] or '?'}，{day}），KRouter 导入，已脱敏。这是线索，不是结论。", ""]
    summ = s["summary"] or {}
    parts = [(lbl, summ.get(k)) for k, lbl in (("request", "要做的事"), ("learned", "学到了"), ("completed", "完成了"),
                                                ("next_steps", "下一步"), ("notes", "备注")) if summ.get(k)]
    if parts:
        out += ["## 会话总结", ""] + [f"- **{lbl}**：{clean(v).replace(chr(10), ' ')}" for lbl, v in parts] + [""]
    if s["obs"]:
        out += ["## 记录", ""]
        for o in s["obs"]:
            kind = TYPE_ZH.get(str(o.get("type")), str(o.get("type") or ""))
            hm = o["at"].strftime("%H:%M") if o.get("at") else ""
            head = clean(o.get("title") or o.get("subtitle") or o.get("text") or "", 160).replace("\n", " ")
            out.append(f"- **{kind}**（{hm}）：{head}")
            for fact in _list(o.get("facts"))[:6]:
                out.append(f"  - {clean(fact, 300)}")
            if not o.get("facts") and o.get("narrative"):
                out.append(f"  - {clean(o['narrative'], 300)}")
        out.append("")
    return name, "\n".join(out).rstrip() + "\n"


def project_decisions(sessions: dict[str, dict]) -> dict[tuple[str, str], list[dict]]:
    """{(project name, repo root or ""): decisions}. Two repos both named `api` stay two pages."""
    by: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for key, s in sessions.items():
        for o in s["obs"]:
            if o.get("type") in DECISION_TYPES and o.get("title"):
                by[(s["project"] or "?", s["root"])].append({**o, "session": key, "session_title": session_title(s)})
    for rows in by.values():
        rows.sort(key=lambda o: o.get("at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return by


DISTILL_PROMPT = """下面是项目「{project}」里 claude-mem 记下的决定和改动，按时间从新到旧，每条带编号、日期和类型（已脱敏）。
其中「改动」类多半是做了什么事（改了哪个文件、提交了什么），只有体现了一个规则或做法的才算决定。

只做一件事：整理出这个项目**现在还有效的决定**，以及**被后来的决定取代了的**。
- 现在有效的：每条一行，写成能直接照做的一句话，行尾标来源编号，例如（#12，2026-10-03）。
- 被取代的：写成「原来 A → 改成 B」，行尾标两条的编号，例如（#4 → #12）。
- 只用下面列出的内容，不推测、不补充；拿不准是不是取代关系的，两条都按「现在有效」列出。
- 最多 15 行。输出纯 Markdown 列表，先列现在有效的，再列被取代的，不要前言和总结。

决定：

{text}
"""


def project_page(project: str, rows: list[dict], digest: str = "", root: str = "") -> tuple[str, str]:
    tag = f"，{hashlib.sha1(root.encode('utf-8')).hexdigest()[:6]}" if root else ""
    name = f"{UNSAFE.sub(' ', project)[:60].strip() or '未命名项目'} 的决定（claude-mem{tag}）.md"
    rows = rows[:DECISIONS_MAX]
    # 一页装着一个项目的很多决定：how 不挑其中一条（多半对不上问题），对得上的那一行由召回的 L 行给出
    first = (f"{project} 在 claude-mem 里记下的 {len(rows)} 条决定和改动（待你确认）"
             + ("，现在有效的和被取代的已整理在页首" if digest else ""))
    out = ["---", f"title: {project} 的决定（claude-mem）", "type: method", f"source: {MARK}", "status: candidate",
           f"project: {project}", *([f"project_root: {root}"] if root else []), f"decisions: {len(rows)}", f"how: {first}"]
    if digest:
        out.append(f"digest_decisions: {len(rows)}")
    out += ["---", "", f"# {project} 的决定（来自 claude-mem）", "", *([f"仓库：`{root}`", ""] if root else []),
            "claude-mem 自动记下的决定和改动（它把多数决定记成「改动」），KRouter 导入。**待你确认**：确认过、要长期遵守的，挪进你自己的规则页，"
            "或把这页的 `status` 改成 `active`。", ""]
    if digest:
        out += ["## 现在有效的、被取代的（模型整理，待你确认）", "", digest.strip(), ""]
    out += ["## 全部决定（新的在前）", ""]
    for o in rows:
        day = o["at"].date().isoformat() if o.get("at") else "?"
        kind = TYPE_ZH.get(str(o.get("type")), str(o.get("type") or ""))
        out.append(f"- #{o.get('id')} {day} {kind}：{clean(o['title'], 200).replace(chr(10), ' ')}（会话：{o['session_title']}）")
        if o.get("subtitle"):
            out.append(f"  - {clean(o['subtitle'], 300)}")
        for fact in _list(o.get("facts"))[:3]:
            out.append(f"  - {clean(fact, 240)}")
    return name, "\n".join(out).rstrip() + "\n"


def old_digest(path: Path, n: int) -> str:
    if not path.is_file() or frontmatter(path).get("digest_decisions") != str(n):
        return ""
    m = re.search(r"\n## 现在有效的、被取代的（模型整理，待你确认）\n\n(.*?)\n\n## ", path.read_text(encoding="utf-8"), re.S)
    return m.group(1).strip() if m else ""


def distill(project: str, rows: list[dict], vault: Path, dry: bool) -> tuple[str, int]:
    lines = []
    for o in rows[:DECISIONS_MAX]:
        day = o["at"].date().isoformat() if o.get("at") else "?"
        facts = "；".join(_list(o.get("facts"))[:3])
        kind = str(o.get("type") or "")
        detail = "；".join(x for x in (clean(o.get("subtitle") or "", 300), clean(facts, 300)) if x)
        lines.append(f"#{o.get('id')} {day} [{kind}] {clean(o['title'], 200)}" + (f"（{detail}）" if detail else ""))
    prompt = DISTILL_PROMPT.format(project=project, text="\n".join(lines)[:DISTILL_MAX])
    if dry:
        return "", len(prompt)
    import llm

    text = llm.complete(prompt, vault)
    keep = [ln.rstrip() for ln in redact(text).splitlines() if ln.strip().startswith(("-", "*"))]
    return "\n".join(keep[:15]), len(prompt)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--vault", default=vault_path())
    ap.add_argument("--db", default="", help="claude-mem database (default: ~/.claude-mem/claude-mem.db)")
    ap.add_argument("--days", type=int, default=0, help="only the last N days (default: everything)")
    ap.add_argument("--distill", action="store_true", help="have the model lane sort each project's decisions")
    ap.add_argument("--dry-run", action="store_true", help="write nothing, send nothing: say what would happen")
    ap.add_argument("--consent", action="store_true", help="record your yes for the nightly job, then import")
    ap.add_argument("--revoke", action="store_true")
    ap.add_argument("--nightly", action="store_true", help="run only when consent was given (used by nightly.py)")
    ap.add_argument("--cli", default="", help=argparse.SUPPRESS)
    ap.add_argument("--model", default="", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.cli:
        os.environ["KROUTER_LEARN_CLI"] = args.cli
    if args.model:
        os.environ["KROUTER_LEARN_MODEL"] = args.model
    if args.revoke:
        save_state({**load_state(), "consent": False})
        print(json.dumps({"claude_mem": "revoked"}))
        return 0
    path = Path(args.db).expanduser() if args.db else db_path()
    st = load_state()
    if args.nightly and not st.get("consent"):
        print(json.dumps({"claude_mem": "off", "reason": "no consent yet (import_claude_mem.py --consent)", "chars": 0,
                          "writes": []}))
        return 0
    if not path.is_file():
        print(json.dumps({"claude_mem": "absent", "db": str(path), "chars": 0, "writes": []}))
        return 0
    if not args.vault:
        print("set KROUTER_VAULT (or OBSIDIAN_VAULT) to your memory folder, or pass --vault", file=sys.stderr)
        return 2
    vault = Path(args.vault).expanduser()
    since = None
    if args.days:
        from datetime import timedelta

        since = datetime.now().astimezone() - timedelta(days=args.days)
    with connect(path) as con:
        sessions = read(con, since)
    distill_on = args.distill or bool(args.nightly and st.get("distill"))
    log_dir, rule_dir = zones.path(vault, LOG_FOLDER), zones.path(vault, RULE_FOLDER)
    counts = {"written": 0, "same": 0, "kept": 0}
    writes, sent, calls, failed = [], 0, 0, 0
    for key, s in sorted(sessions.items(), key=lambda kv: kv[1]["start"]):
        name, page = session_page(key, s)
        res = write(log_dir / name, page, args.dry_run)
        counts[res] += 1
        if res == "written":
            writes.append(f"{LOG_FOLDER}/{name}")
    decisions = project_decisions(sessions)
    for (project, root), rows in sorted(decisions.items()):
        name, _ = project_page(project, rows, root=root)
        target = rule_dir / name
        digest = old_digest(target, len(rows[:DECISIONS_MAX]))
        if not digest and distill_on:
            try:
                digest, n = distill(project, rows, vault, args.dry_run)
                sent += n
                calls += 1
            except Exception as exc:  # noqa: BLE001  模型失败不影响本地导入
                failed += 1
                print(f"distill {project}: {str(exc)[:200]}", file=sys.stderr)
        _, page = project_page(project, rows, digest, root)
        res = write(target, page, args.dry_run)
        counts[res] += 1
        if res == "written":
            writes.append(f"{RULE_FOLDER}/{name}")
    if not args.days and not args.dry_run and rule_dir.is_dir():
        # 全量导入时，名字已经不再产生的决定页（比如以前没分仓库、现在分了）是旧版本留下的：删掉，免得两份
        made = {f"{RULE_FOLDER}/{project_page(pr, rw, root=rt)[0]}" for (pr, rt), rw in decisions.items()}
        for page in rule_dir.glob("*.md"):
            if frontmatter(page).get("source") == MARK and f"{RULE_FOLDER}/{page.name}" not in made:
                page.unlink()
    if args.consent and not args.dry_run:
        save_state({**st, "consent": True, "distill": bool(args.distill),
                    "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    print(json.dumps({"claude_mem": "dry-run" if args.dry_run else "done", "db": str(path), "sessions": len(sessions),
                      "observations": sum(len(s["obs"]) for s in sessions.values()),
                      "projects": len(decisions), "decisions": sum(len(v) for v in decisions.values()),
                      "distilled": calls, "distill_failed": failed, "chars": sent, **counts,
                      "writes": writes if len(writes) <= 20 else writes[:20] + [f"… {len(writes) - 20} more"]},
                     ensure_ascii=False))
    return 1 if failed and not calls else 0


if __name__ == "__main__":
    raise SystemExit(main())
