#!/usr/bin/env python3
"""Ten people with their own agents on one team server: concurrent reads and writes, then a check of what landed.

Starts `mcp_server.py --http` on 127.0.0.1 with `--allow-write` and a users file of N personal tokens, on a copy of a
vault made into a git repository, seeded with three things to fight over:

- `01 项目/数据库选型.md` ("数据库用 SQLite"): every client keeps correcting it to something else, always naming the
  original page (as an agent does that asked a while ago) — contradicting corrections;
- `01 项目/团队约定.md`, a long page: one line ("发布窗口：周四下午") everyone corrects at once, and one line per client
  that its owner corrects again and again — concurrent corrections of one page;
- today's notes page, that every note lands on.

Then N clients (threads, each with its own token and client name) run: four bursts where all of them do the same thing
at once (ask, note, correct the shared line, correct the topic), then a seeded random mix of asks, notes, line
corrections and topic corrections, for `--ops` operations each or for `--duration` seconds.

The check (`verify`) reads the vault, the journal, git and every reply: no acknowledged write is missing, no page is
broken, every change is attributed to the token that made it (page, journal, git author), each contested thing ends
with exactly one correction in force (the last one to arrive) and a chain through all the others, every conflict
reply names the correction it replaced, and every answer names its vault and a page (or says `recall: none`).

    python3 bench/team/load.py --pages 0 --ops 40                    # template vault only
    python3 bench/team/load.py --vault /tmp/v10000 --ops 60          # bench/scale/gen.py 10000 /tmp/v10000
    python3 bench/team/load.py --vault /tmp/v10000 --duration 1800 --rss-every 30 --out sustained.json

No model is called and nothing leaves the machine. Tokens are generated into the work folder (mode 600), never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "skill/krouter/scripts/mcp_server.py"
sys.path.insert(0, str(REPO / "skill/krouter/scripts"))
sys.path.insert(0, str(REPO / "bench/scale"))

import team  # noqa: E402
from gen import EN, ZH  # noqa: E402

TOPIC = "01 项目/数据库选型.md"
SHARED = "01 项目/团队约定.md"
WINDOW = "发布窗口：周四下午"
PER_CLIENT_LINES = 3
CHOICES = ("Postgres", "MySQL", "SQLite", "DuckDB")
DAYS = "一二三四五"
NOTES_GLOB = "05 时间日志/会话摘录"
SOURCE_LINE = re.compile(r"^- \S.*\.md tier=", re.M)


def own_line(i: int, j: int) -> str:
    return f"约定 c{i:02d}-{j}：用方案甲{i:02d}{j}"


# ---------- setup ----------

def clean_env(work: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.endswith(("_API_KEY", "_BASE_URL"))}
    env.update({"KROUTER_CACHE_DIR": str(work / "cache"), "KROUTER_STATE_DIR": str(work / "state"),
                "KROUTER_VAULT_FILE": str(work / "no-vault-file"), "KROUTER_NO_QUERY_LOG": "1",
                "HOME": str(work / "home"), "GIT_CONFIG_GLOBAL": str(work / "home/.gitconfig"),
                "GIT_CONFIG_NOSYSTEM": "1"})
    env.pop("OBSIDIAN_VAULT", None)
    env.pop("KROUTER_VAULT", None)
    (work / "home").mkdir(parents=True, exist_ok=True)
    return env


def git(vault: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(vault), *args], capture_output=True, text=True, env=env, timeout=600)


def prepare(work: Path, source: Path | None, clients: int) -> tuple[Path, list[dict], Path]:
    """A git vault (copy of `source`, or the template) with the seeded pages, a users file, one token file per client."""
    vault = work / "vault"
    shutil.copytree(source or REPO / "template", vault, symlinks=True)
    shutil.rmtree(vault / ".git", ignore_errors=True)
    (vault / "01 项目").mkdir(parents=True, exist_ok=True)
    (vault / TOPIC).write_text("---\ntitle: 数据库选型\nstatus: active\ndate: 2026-11-01\n---\n\n# 数据库选型\n\n"
                               "- 数据库用 SQLite\n", encoding="utf-8")
    lines = [f"- {WINDOW}"] + [f"- {own_line(i, j)}" for i in range(clients) for j in range(PER_CLIENT_LINES)]
    (vault / SHARED).write_text("---\ntitle: 团队约定\nstatus: active\ndate: 2026-11-01\n---\n\n# 团队约定\n\n"
                                + "\n".join(lines) + "\n", encoding="utf-8")
    env = clean_env(work)
    git(vault, "init", "-q", env=env)
    git(vault, "add", "-A", env=env)
    git(vault, "-c", "user.name=seed", "-c", "user.email=seed@krouter.invalid", "commit", "-q", "-m", "seed", env=env)
    users = work / "users"
    tokdir = work / "tokens"
    tokdir.mkdir(mode=0o700)
    people = []
    for i in range(clients):
        name = f"dev{i:02d}"
        tf = tokdir / f"{name}.token"
        team.add_user(users, name, "write", "*", tf)
        people.append({"i": i, "name": name, "token": tf.read_text(encoding="utf-8").strip(),
                       "client": f"agent-{('claude-code', 'codex', 'cursor', 'langgraph', 'script')[i % 5]}-{i:02d}"})
    return vault, people, users


def start(work: Path, vault: Path, users: Path, extra: list[str] | None = None) -> tuple[subprocess.Popen, str, float]:
    t0 = time.perf_counter()
    log = open(work / "server.log", "w", encoding="utf-8", buffering=1)  # noqa: SIM115  一行一写，读的人不用等缓冲
    proc = subprocess.Popen([sys.executable, str(SERVER), "--http", "127.0.0.1:0", "--vault", str(vault),
                             "--label", "team", "--users", str(users), "--allow-write", *(extra or [])],
                            env=clean_env(work), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    url = None
    while True:
        line = proc.stderr.readline()
        if not line:
            break
        log.write(line)
        if line.startswith("{") and "listening" in line:
            url = json.loads(line)["listening"]
            break
    if not url:
        log.close()
        raise RuntimeError("server did not start; see " + str(work / "server.log"))
    ready = time.perf_counter() - t0

    def drain():
        for ln in proc.stderr:
            log.write(ln)
        log.close()

    proc.drain = threading.Thread(target=drain, daemon=True)  # 读 server.log 之前先 stop()：日志写完、文件关上
    proc.drain.start()
    return proc, url, ready


def _stop_server(proc: subprocess.Popen) -> None:
    """End the server and wait until everything it logged is in server.log."""
    proc.terminate()
    proc.wait(timeout=30)
    drain = getattr(proc, "drain", None)
    if drain is not None:
        drain.join(timeout=30)


# ---------- the clients ----------

def post(url: str, token: str, body: dict, timeout: float = 180) -> tuple[int, dict | None]:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}",
                                          "Accept": "application/json, text/event-stream"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as err:
        return err.code, None
    except (OSError, ValueError):
        return 0, None


class Client:
    def __init__(self, person: dict, url: str, seed: int, results: list, lock: threading.Lock,
                 write_share: float = 0.4) -> None:
        self.p, self.url, self.results, self.lock = person, url, results, lock
        self.write_share = write_share
        self.phase = ""
        self.rng = random.Random(seed * 1000 + person["i"])
        self.k = 0
        self.mid = 0

    def call(self, kind: str, tool: str, args: dict, meta: dict | None = None) -> dict:
        self.mid += 1
        t = time.perf_counter()
        code, reply = post(self.url, self.p["token"], {"jsonrpc": "2.0", "id": self.mid, "method": "tools/call",
                                                         "params": {"name": tool, "arguments": args}})
        dt = time.perf_counter() - t
        res = (reply or {}).get("result") or {}
        text = "".join(c.get("text", "") for c in res.get("content") or [] if isinstance(c, dict))
        ok = code == 200 and bool(res) and not res.get("isError")
        rec = {"who": self.p["name"], "kind": kind, "tool": tool, "args": args, "ok": ok, "code": code,
               "ms": round(dt * 1000, 2), "at": time.time(), "phase": self.phase, "text": text, **(meta or {})}
        if tool == "krouter_ask":  # 出处当场核对，回执不留（30 分钟的运行里攒下来有上百 MB）
            rec["sourced"] = text.startswith("vault_label: team\n") and ("recall: none" in text or bool(SOURCE_LINE.search(text)))
            rec["recall_none"] = "recall: none" in text
            rec["text"] = ""
        with self.lock:
            self.results.append(rec)
        return rec

    def hello(self) -> None:
        post(self.url, self.p["token"], {"jsonrpc": "2.0", "id": 0, "method": "initialize",
                                          "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                                     "clientInfo": {"name": self.p["client"], "version": "1"}}})

    def ask(self) -> dict:
        r = self.rng.random()
        if r < 0.3:
            q = "数据库选型现在用什么"
        elif r < 0.45:
            q = "发布窗口是什么时候"
        elif r < 0.6:
            i, j = self.rng.randrange(10), self.rng.randrange(PER_CLIENT_LINES)
            q = f"约定 c{i:02d}-{j} 用什么方案"
        elif r < 0.8:
            q = f"{self.rng.choice(ZH)}{self.rng.choice(ZH)}现在用什么？"
        else:
            q = f"what did we decide about {self.rng.choice(EN)} {self.rng.choice(EN)}"
        return self.call("ask", "krouter_ask", {"query": q})

    def note(self) -> dict:
        self.k += 1
        marker = f"mk-{self.p['name']}-{self.k:05d}"
        return self.call("note", "krouter_note", {"text": f"{self.p['name']} 记下：发版前先跑冒烟测试 {marker}",
                                                  "kind": "decision"}, {"marker": marker})

    def correct_window(self) -> dict:
        self.k += 1
        day = DAYS[(self.p["i"] + self.k) % 5]
        return self.call("correct_window", "krouter_correct",
                         {"new": f"发布窗口改成周{day}上午（{self.p['name']} 第 {self.k} 次）", "old": WINDOW, "page": SHARED},
                         {"subject": "window"})

    def correct_own(self) -> dict:
        self.k += 1
        j = self.rng.randrange(PER_CLIENT_LINES)
        i = self.p["i"]
        return self.call("correct_line", "krouter_correct",
                         {"new": f"约定 c{i:02d}-{j}：改用方案乙{i:02d}{j}-{self.k}", "old": own_line(i, j), "page": SHARED},
                         {"subject": f"line-{i:02d}-{j}"})

    def contradict(self) -> dict:
        self.k += 1
        pick = CHOICES[(self.p["i"] + self.k) % len(CHOICES)]
        return self.call("contradict", "krouter_correct",
                         {"new": f"数据库改用 {pick}（{self.p['name']} 第 {self.k} 次）", "old": "数据库用 SQLite",
                          "page": TOPIC}, {"subject": "topic"})

    def mixed(self) -> dict:
        """Asks, and `write_share` of writes: half notes, a quarter own-line corrections, an eighth each contradicting
        topic corrections and shared-line corrections (0.4 by default: 60 % asks, 20 % notes, 10 %, 5 %, 5 %)."""
        r = self.rng.random()
        if r >= self.write_share:
            return self.ask()
        w = r / self.write_share
        if w < 0.5:
            return self.note()
        if w < 0.75:
            return self.correct_own()
        if w < 0.875:
            return self.contradict()
        return self.correct_window()


def run(url: str, people: list[dict], ops: int, duration: float, seed: int, results: list,
        write_share: float = 0.4) -> dict:
    lock = threading.Lock()
    clients = [Client(p, url, seed, results, lock, write_share) for p in people]
    for c in clients:
        c.hello()
    phases = {}
    for name, fn in (("burst_ask", Client.ask), ("burst_note", Client.note),
                     ("burst_same_line", Client.correct_window), ("burst_contradict", Client.contradict)):
        gate = threading.Barrier(len(clients))

        def one(c, fn=fn, gate=gate, name=name):
            c.phase = name
            gate.wait()
            fn(c)

        t = time.perf_counter()
        ths = [threading.Thread(target=one, args=(c,)) for c in clients]
        for th in ths:
            th.start()
        for th in ths:
            th.join()
        phases[name] = round(time.perf_counter() - t, 3)
    stop = time.monotonic() + duration if duration else None

    def loop(c):
        c.phase = "mixed"
        n = 0
        while (stop is None and n < ops) or (stop is not None and time.monotonic() < stop):
            c.mixed()
            n += 1

    t = time.perf_counter()
    ths = [threading.Thread(target=loop, args=(c,)) for c in clients]
    for th in ths:
        th.start()
    for th in ths:
        th.join()
    phases["mixed"] = round(time.perf_counter() - t, 3)
    return phases


# ---------- the check ----------

def _meta(text: str) -> dict:
    import corrections

    return corrections._meta(text)


def _links(value: str) -> list[str]:
    return re.findall(r"\[\[([^\]|#]+)", value or "")


def verify(vault: Path, results: list[dict], env: dict | None = None) -> dict:
    checks: dict[str, dict] = {}
    writes = [r for r in results if r["tool"] in ("krouter_note", "krouter_correct")]
    acked = [r for r in writes if r["ok"]]
    journal = team.read_journal(vault)

    # 1. 每个确认过的写入都在日志里，seq 连续，run 不重复
    seqs = [j["seq"] for j in journal]
    runs = [j["run"] for j in journal]
    checks["journal_complete"] = {
        "ok": len(journal) == len(acked) and seqs == list(range(1, len(journal) + 1)) and len(set(runs)) == len(runs),
        "acked_writes": len(acked), "journal_rows": len(journal), "unique_runs": len(set(runs))}

    # 2. 笔记：每条确认过的都在当天的页上，正好一次，署名对
    notes_dir = vault / NOTES_GLOB
    note_text = "".join(p.read_text(encoding="utf-8") for p in notes_dir.glob("*agent 记下.md")) if notes_dir.is_dir() else ""
    bad_notes = []
    for r in (x for x in acked if x["tool"] == "krouter_note"):
        lines = [ln for ln in note_text.splitlines() if r["marker"] in ln]
        if len(lines) != 1 or f"— 来自 {r['who']}（MCP，" not in lines[0]:
            bad_notes.append({"marker": r["marker"], "found": len(lines)})
    checks["notes_all_there_once_attributed"] = {"ok": not bad_notes, "notes": sum(1 for x in acked if x["tool"] == "krouter_note"),
                                                  "bad": bad_notes[:5]}

    # 3. 归属：日志、页面、git 作者都指向发起写入的那个令牌
    by_run = {j["run"]: j for j in journal}
    log = git(vault, "log", "--format=%an%x1f%B%x1e", env=env).stdout
    git_author = {}
    for block in log.split("\x1e"):
        if "\x1f" not in block:
            continue
        an, body = block.split("\x1f", 1)
        m = re.search(r"\[krouter-run ([^\]]+)\]", body)
        if m:
            git_author[m.group(1)] = an.strip()
    wrong = []
    for r in acked:
        rid = (re.search(r"^run: (\S+)$", r["text"], re.M) or [None, None])[1]
        j = by_run.get(rid)
        if not j or j.get("who") != r["who"] or git_author.get(rid) != r["who"] or f"by: {r['who']}" not in r["text"]:
            wrong.append({"who": r["who"], "run": rid, "journal": j and j.get("who"), "git": git_author.get(rid)})
            continue
        if r["tool"] == "krouter_correct":
            page = vault / r["text"].split("\n", 1)[0].removeprefix("corrected: ").strip()
            if not page.is_file() or _meta(page.read_text(encoding="utf-8")).get("author") != r["who"]:
                wrong.append({"who": r["who"], "run": rid, "page_author": page.is_file() and _meta(page.read_text(encoding="utf-8")).get("author")})
    checks["attribution"] = {"ok": not wrong, "checked": len(acked), "wrong": wrong[:5]}

    # 4. 页面没坏：都是 UTF-8、frontmatter 闭合、没有残留的临时文件、git 里没有没提交的改动
    broken = []
    for p in vault.rglob("*"):
        if ".git" in p.parts:
            continue
        if p.name.endswith(".tmp"):
            broken.append(f"leftover {p.name}")
        if p.suffix != ".md" or not p.is_file():
            continue
        try:
            t = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            broken.append(f"not utf-8: {p.relative_to(vault)}")
            continue
        if t.startswith("---\n") and "\n---" not in t[4:]:
            broken.append(f"open frontmatter: {p.relative_to(vault)}")
        m = _meta(t)
        if m.get("type") == "correction" and m.get("status") not in ("active", "superseded"):
            broken.append(f"bad status: {p.relative_to(vault)}")
    dirty = [ln for ln in git(vault, "status", "--porcelain", env=env).stdout.splitlines() if ln.strip()]
    fsck = git(vault, "fsck", "--no-progress", env=env)
    checks["pages_intact"] = {"ok": not broken and not dirty and fsck.returncode == 0, "broken": broken[:5],
                              "uncommitted": dirty[:5], "git_fsck": fsck.returncode}

    # 5. 每件被争的事：恰好一条纠正生效，是最后到的那条；其余按到达顺序串成取代链；冲突回执点名上一条
    order = {j["pages"][0]: j["seq"] for j in journal if j.get("tool") == "krouter_correct"}
    subjects: dict[str, list[dict]] = {}
    for r in acked:
        if r["tool"] == "krouter_correct":
            r["page"] = r["text"].split("\n", 1)[0].removeprefix("corrected: ").strip()
            subjects.setdefault(r["subject"], []).append(r)
    diverged = []
    for subj, rs in subjects.items():
        rs.sort(key=lambda r: order.get(r["page"], 10 ** 9))
        metas = [_meta((vault / r["page"]).read_text(encoding="utf-8")) for r in rs]
        active = [r["page"] for r, m in zip(rs, metas) if m.get("status") == "active"]
        problems = []
        if active != [rs[-1]["page"]]:
            problems.append({"active": active, "last": rs[-1]["page"]})
        for a, b, ma in zip(rs, rs[1:], metas):
            if _links(ma.get("superseded_by", ""))[-1:] != [b["page"].removesuffix(".md")]:
                problems.append({"page": a["page"], "superseded_by": ma.get("superseded_by"), "expected": b["page"]})
        for a, b in zip(rs, rs[1:]):
            named = re.findall(r"^conflict: (\S.*?\.md) by (\S+)", b["text"], re.M)
            if (a["page"], a["who"]) not in named:
                problems.append({"page": b["page"], "conflict_lines": named, "expected": a["page"]})
        if rs[0]["text"].count("\nconflict: ") and subj in ("topic", "window"):
            problems.append({"first": rs[0]["page"], "has_conflict": True})
        if problems:
            diverged.append({"subject": subj, "n": len(rs), "problems": problems[:3]})
    topic = _meta((vault / TOPIC).read_text(encoding="utf-8"))
    first_topic = subjects.get("topic", [{}])[0].get("page", "")
    if topic.get("status") != "superseded" or _links(topic.get("superseded_by", ""))[-1:] != [first_topic.removesuffix(".md")]:
        diverged.append({"subject": "topic page", "status": topic.get("status"), "superseded_by": topic.get("superseded_by")})
    shared = (vault / SHARED).read_text(encoding="utf-8")
    for subj, rs in subjects.items():  # 长页上的「已改」：每条都在，按到达顺序
        if subj == "topic":
            continue
        pos = [shared.find(f"→ [[{r['page'].removesuffix('.md')}]]") for r in rs]
        if any(p < 0 for p in pos) or pos != sorted(pos):
            diverged.append({"subject": subj, "annotations": "missing or out of order"})
    checks["conflicts_converge"] = {"ok": not diverged, "subjects": len(subjects),
                                    "corrections": sum(len(v) for v in subjects.values()),
                                    "conflict_replies": sum(r["text"].count("\nconflict: ") for v in subjects.values() for r in v),
                                    "diverged": diverged[:5]}

    # 6. 读到的结果都带出处：库名，以及一页路径或 recall: none
    asks = [r for r in results if r["tool"] == "krouter_ask"]
    unsourced = [r["args"]["query"] for r in asks if r["ok"] and not r["sourced"]]
    checks["reads_sourced"] = {"ok": not unsourced and all(r["ok"] for r in asks), "asks": len(asks),
                               "failed": sum(1 for r in asks if not r["ok"]),
                               "recall_none": sum(1 for r in asks if r["recall_none"]), "unsourced": unsourced[:5]}
    checks["no_failed_writes"] = {"ok": len(acked) == len(writes), "writes": len(writes),
                                  "failed": [{"who": r["who"], "code": r["code"], "text": r["text"][:200]}
                                             for r in writes if not r["ok"]][:5]}
    return checks


def final_answer(url: str, token: str, vault: Path, results: list[dict]) -> dict:
    """After the run, a lookup on the contested topic: the first correction page it lists must be the one in force,
    its `how` must give the new decision, and no replaced correction may be listed as active. (The first page overall
    may be the corrections log, a rule page; that is reported, not judged.)"""
    journal = team.read_journal(vault)
    heads = [j["pages"][0] for j in journal if j.get("tool") == "krouter_correct" and "数据库改用" in (j.get("text") or "")]
    code, reply = post(url, token, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                     "params": {"name": "krouter_ask", "arguments": {"query": "数据库选型现在用什么"}}})
    text = "".join(c.get("text", "") for c in ((reply or {}).get("result") or {}).get("content") or [])
    hits = re.findall(r"^- (\S.*?\.md) tier=\S+ status=(\S+)[^\n]*\n  how: ([^\n]*)", text, re.M)
    fixes = [(rel, st, how) for rel, st, how in hits if "｜纠正｜数据库改用" in rel]
    head = heads[-1] if heads else ""
    return {"head": head, "first_hit": hits[0][0] if hits else "", "first_correction": fixes[0][0] if fixes else "",
            "first_correction_how": fixes[0][2] if fixes else "",
            "replaced_listed_active": [rel for rel, st, _ in fixes if rel != head and st == "active"],
            "ok": bool(fixes) and fixes[0][0] == head and fixes[0][2].startswith("现在：")
                  and not [rel for rel, st, _ in fixes if rel != head and st == "active"]}


# ---------- numbers ----------

def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(round(p * len(xs) + 0.5)) - 1))] if xs else 0.0


def stats(results: list[dict], wall: float) -> dict:
    """Latency over every call (bursts and mix); `per_second` over the mixed phase only (its calls / its wall time)."""
    out = {}
    groups = {"read": [r for r in results if r["tool"] == "krouter_ask"],
              "write": [r for r in results if r["tool"] != "krouter_ask"]}
    for kind in sorted({r["kind"] for r in results}):
        groups[kind] = [r for r in results if r["kind"] == kind]
    for name, rs in groups.items():
        ms = [r["ms"] for r in rs]
        if not ms:
            continue
        out[name] = {"n": len(rs), "errors": sum(1 for r in rs if not r["ok"]),
                     "error_rate": round(sum(1 for r in rs if not r["ok"]) / len(rs), 4),
                     "p50_ms": round(statistics.median(ms), 1), "p95_ms": round(pct(ms, 0.95), 1),
                     "p99_ms": round(pct(ms, 0.99), 1), "max_ms": round(max(ms), 1),
                     "per_second": round(sum(1 for r in rs if r.get("phase") == "mixed") / wall, 2) if wall else None}
    return out


def rss_mb(pid: int) -> float:
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,rss="], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return 0.0
    rows = [tuple(int(x) for x in ln.split()) for ln in out.splitlines() if len(ln.split()) == 3]
    kids, total, todo = {}, 0, [pid]
    for p, pp, _ in rows:
        kids.setdefault(pp, []).append(p)
    rss = {p: r for p, _, r in rows}
    while todo:
        p = todo.pop()
        total += rss.get(p, 0)
        todo += kids.get(p, [])
    return round(total / 1024, 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--vault", help="a vault to copy (default: the template)")
    ap.add_argument("--pages", type=int, default=0, help="without --vault: add this many generated pages (gen.py)")
    ap.add_argument("--clients", type=int, default=10)
    ap.add_argument("--ops", type=int, default=40, help="mixed operations per client after the bursts")
    ap.add_argument("--duration", type=float, default=0, help="run the mix for this many seconds instead of --ops")
    ap.add_argument("--seed", type=int, default=20261110)
    ap.add_argument("--write-share", type=float, default=0.4, help="share of writes in the mix (0: asks only)")
    ap.add_argument("--rss-every", type=float, default=0, help="sample the server's memory this often (seconds)")
    ap.add_argument("--work", help="work folder (default: a new temporary one, removed unless --keep)")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--out", help="also write the report here (JSON)")
    ap.add_argument("--server-arg", action="append", default=[])
    args = ap.parse_args()
    work = Path(args.work or tempfile.mkdtemp(prefix="krouter-team-load-")).resolve()
    work.mkdir(parents=True, exist_ok=True)
    src = Path(args.vault).resolve() if args.vault else None
    if src is None and args.pages:
        gen_dir = work / "gen"
        subprocess.run([sys.executable, str(REPO / "bench/scale/gen.py"), str(args.pages), str(gen_dir)], check=True,
                       capture_output=True)
        src = gen_dir
    t = time.perf_counter()
    vault, people, users = prepare(work, src, args.clients)
    prep_s = time.perf_counter() - t
    proc, url, ready = start(work, vault, users, args.server_arg)
    samples: list[tuple[float, float]] = []
    stop = threading.Event()
    t_start = time.time()

    def sampler():
        while not stop.wait(args.rss_every):
            samples.append((round(time.time() - t_start, 1), rss_mb(proc.pid)))

    if args.rss_every:
        samples.append((0.0, rss_mb(proc.pid)))
        threading.Thread(target=sampler, daemon=True).start()
    results: list[dict] = []
    try:
        t = time.perf_counter()
        phases = run(url, people, args.ops, args.duration, args.seed, results, args.write_share)
        wall = time.perf_counter() - t
        stop.set()
        final = final_answer(url, people[0]["token"], vault, results)
        rss_end = rss_mb(proc.pid)
    finally:
        stop.set()
        _stop_server(proc)  # the log is complete before it is read below
    env = clean_env(work)
    checks = verify(vault, results, env)
    errors_in_log = sum(1 for ln in (work / "server.log").read_text(encoding="utf-8").splitlines()
                        if ln.startswith("{") and '"status": 5' in ln)
    tokens_in_log = any(p["token"] in (work / "server.log").read_text(encoding="utf-8") for p in people)
    pages = sum(1 for _ in vault.rglob("*.md"))
    report = {"pages": pages, "clients": args.clients, "ops_per_client": args.ops, "duration_s": args.duration,
              "write_share": args.write_share,
              "prepare_s": round(prep_s, 1), "ready_s": round(ready, 2), "wall_s": round(wall, 1), "phases_s": phases,
              "ops": len(results),
              "per_second_mixed": round(sum(1 for r in results if r["phase"] == "mixed") / phases["mixed"], 2),
              "latency": stats(results, phases["mixed"]),
              "checks": checks, "final_answer": final, "server_5xx": errors_in_log, "token_in_server_log": tokens_in_log,
              "rss_end_mb": rss_end, **({"rss_samples": samples} if samples else {}),
              "ok": all(c["ok"] for c in checks.values()) and final["ok"] and not tokens_in_log and not errors_in_log}
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    if not args.keep and not args.work:
        shutil.rmtree(work, ignore_errors=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


stop = _stop_server  # tests call load.stop(proc); inside long_run a local named stop (an Event) shadows it
