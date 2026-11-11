"""The read-only data layer behind `krouter view`: what the memory holds, as plain dicts.

Everything here reads: the Markdown folder (never written), the rebuildable recall cache (`recall_index`; its refresh is
the only thing this module ever writes, and it lives outside the memory folder), the experience cards and their use
records, the nightly report and the change ledger, and, when the folder is a git repository, `git log` / `git show`.
Page bodies go through `krouter_redact.redact` and a secret page is never shown, the same rule the router follows.

A list is always one page of it (`offset`/`limit`), whatever the size of the memory, so the browser never holds more
than it shows.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from . import router_dir

REFRESH_EVERY = 20.0  # seconds: a page edited while the viewer runs shows up after this at the latest
MAX_LIST = 200        # the most one list request returns
SEARCH_CAP = 1000     # a search ranks at most this many pages (the total says so when it hit the cap)
BODY_MAX = 400_000    # bytes of a page body sent to the browser
NEIGHBOR_CAP = 60     # edges listed for one page
PEER_CAP = 12         # pages of the same session / day listed per shared value
REPORT = "90 系统文件/自动化/夜间维护.md"  # nightly.REPORT (a test keeps the two equal)
CORRECTIONS = "90 系统文件/Agent记忆/纠错与取代记录.md"  # corrections.LOG_PAGE
LEARNED = "90 系统文件/自动化/下意识触发词-自学习.psv"  # reconsolidate.DEFAULT_OUT
CANDIDATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})｜(?:纠正候选|Correction candidates)\.md$")

_MODS: SimpleNamespace | None = None


def mods() -> SimpleNamespace:
    """The router's modules (recall index, edges, experience cards, …), imported once from the router directory."""
    global _MODS
    if _MODS is None:
        here = str(router_dir())
        if here not in sys.path:
            sys.path.insert(0, here)
        import associate
        import canonical_lookup
        import capture_ledger
        import compile_subconscious
        import experience
        import kb
        import krouter_redact
        import recall_index
        import recollect
        import skills
        import zones

        _MODS = SimpleNamespace(ri=recall_index, associate=associate, cl=canonical_lookup, ledger=capture_ledger,
                                experience=experience, redact=krouter_redact, zones=zones, skills=skills,
                                recollect=recollect, cs=compile_subconscious, kb=kb)
    return _MODS


def head_of(path: Path, limit: int = 6000) -> tuple[dict, str]:
    """(frontmatter, text after it) from the first `limit` bytes of a page."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(limit)
    except OSError:
        return {}, ""
    return mods().ri.split_frontmatter(raw.decode("utf-8", errors="replace"))


def first_heading(body: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def iso(ts_ns: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts_ns / 1e9)) if ts_ns else ""


# The nightly report and the change ledger are written in Chinese by the job; for an English reader the fixed phrases are
# put into English here (page names, quoted sentences and commands are left as they are).
_EN = [
    (re.compile(r"^会话导入没开（(.*?) 开启）$"), r"session import is off (switch it on with \1)"),
    (re.compile(r"^claude-mem 导入没开，或本机没有 claude-mem（(.*?) 开启）$"), r"claude-mem import is off, or claude-mem is not on this machine (\1)"),
    (re.compile(r"^备份没开（(.*?) 开启）$"), r"backup is off (switch it on with \1)"),
    (re.compile(r"^提炼全部失败（(\d+) 个会话），摘录照常写了$"), r"every distill failed (\1 sessions); the excerpts were written as usual"),
    (re.compile(r"^备份只写成了一部分位置：(.*)$"), r"backup reached only some locations: \1"),
    (re.compile(r"^- 新增 (.*?)（会话 (`.*?`)）$"), r"- Added \1 (session \2)"),
    (re.compile(r"^- 取代 (.*?) → (.*?)（.*）$"), r"- Replaced \1 → \2 (everything decided on that page was later changed)"),
    (re.compile(r"^- 删除 (`.*?`)（.*）$"), r"- Deleted \1 (marked not to keep, a headless call, or fully contained in another session)"),
    (re.compile(r"^- 纠正候选判定：成立 (\d+)，补记 (\d+)，不成立 (\d+)$"), r"- Correction candidates judged: held \1, added \2, did not hold \3"),
    (re.compile(r"^\s*- 取代：(.*)$"), r"  - replaced: \1"),
    (re.compile(r"^\s*- 成立：(.*)$"), r"  - held: \1"),
    (re.compile(r"^\s*- 补记：(.*?)（.*）$"), r"  - added: \1 (the distill missed it; added in your words)"),
    (re.compile(r"^\s*- 不成立：(.*)$"), r"  - did not hold: \1"),
    (re.compile(r"^提交 (`.*?`)；撤销这一轮：(`.*?`)$"), r"commit \1; undo this run: \2"),
    (re.compile(r"^库不是 git 仓库，没有提交可撤；撤销这一轮：(`.*?`)$"), r"the memory is not a git repository, no commit to undo; \1"),
    (re.compile(r"^结果：\*\*(.*?)\*\*（通道：(.*?)）$"), r"result: \1 (lane: \2)"),
    (re.compile(r"^(\d+) 次 / (\d+) 字 / (\d+) tokens$"), r"\1 calls / \2 chars / \3 tokens"),
    (re.compile(r"^(\d+) 次 / (\d+) 字$"), r"\1 calls / \2 chars"),
    (re.compile(r"^发出的内容：.*$"), "What is sent: rule and topic pages in full (answer cards), topic evidence (topic dossiers), the text of "
     "queries the router did not answer well (nightly learning); with session import on and distilling chosen, also "
     "yesterday's redacted session excerpts. KROUTER_NIGHTLY=0 turns it off; run.sh --dry-run shows what would be sent first."),
    (re.compile(r"^没有可用的模型通道（.*?），这些功能没开：(.*?)。召回.*$"), r"No model lane (no API key and no logged-in agent command line): off: \1. "
     "Recall, correction capture, the experience digest and cards and notes the agent writes itself work as usual."),
    (re.compile(r"^借用已登录的 agent 命令行（订阅额度）：(.*?)，今天 (\d+) / (\d+) 次，每次见 (`.*?`)。$"),
     r"Borrowing the logged-in agent command line (subscription quota): \1, \2 / \3 calls today, each one logged in \4."),
]
_FEATURES = {"会话提炼（定了什么、改了什么）": "session distilling", "经验卡的模型抽取": "model extraction of experience cards",
             "主题档案整合": "topic dossiers", "问答卡": "answer cards", "触发词提议": "trigger proposals",
             "claude-mem 导入的提炼": "claude-mem import distilling", "夜间学习": "nightly learning", "主题档案": "topic dossiers"}


def to_english(line: str) -> str:
    line = line.replace("<会同步到别处的文件夹>", "<a folder that syncs elsewhere>")
    for zh, en in _FEATURES.items():
        if line.startswith("没有可用的模型通道"):
            line = line.replace(zh, en)
    for rx, rep in _EN:
        new, n = rx.subn(rep, line)
        if n:
            return new.replace("、", ", ") if new.startswith("No model lane") else new
    return line


class Store:
    """One memory folder, read only."""

    def __init__(self, vault: Path | str):
        self.vault = Path(vault).expanduser()
        self.m = mods()
        self.lang = self.m.zones.lang(self.vault)
        self._lock = threading.Lock()
        self._last = 0.0

    # ---- the cache ----

    def connect(self):
        return self.m.ri.connect(self.m.ri.cache_path(self.vault))

    @contextlib.contextmanager
    def con(self):
        con = self.connect()
        try:
            yield con
        finally:
            con.close()

    def refresh(self, force: bool = False) -> dict:
        """Bring the cache up to date with the folder (at most once per REFRESH_EVERY seconds unless forced)."""
        with self._lock:
            if not force and self._last and time.monotonic() - self._last < REFRESH_EVERY:
                return {}
            with self.con() as con:
                stats = self.m.ri.refresh(self.vault, con)
            self._last = time.monotonic()
            return stats

    def path(self, default_rel: str) -> Path:
        return self.m.zones.path(self.vault, default_rel)

    # ---- pages ----

    def title_of(self, rel: str) -> str:
        meta, body = head_of(self.vault / rel)
        return meta.get("title") or first_heading(body) or Path(rel).stem

    def _decorate(self, rel: str, tier: str, status: str, mtime_ns: int = 0, size: int = 0) -> dict:
        meta, body = head_of(self.vault / rel, 3000)
        return {"rel": rel, "title": meta.get("title") or first_heading(body) or Path(rel).stem, "tier": tier,
                "status": status, "date": meta.get("date", ""), "modified": iso(mtime_ns), "size": size,
                "kb": self.m.kb.reason(self.vault, rel)}  # 知识库的页（参考资料）：列表里标出来

    def stats(self) -> dict:
        with self.con() as con:
            total = con.execute("SELECT count(*) FROM files").fetchone()[0]
            tiers = dict(con.execute("SELECT tier, count(*) FROM docs GROUP BY tier").fetchall())
            statuses = {k or "": v for k, v in con.execute("SELECT status, count(*) FROM docs GROUP BY status")}
            built = (con.execute("SELECT v FROM meta WHERE k='built_at'").fetchone() or [""])[0]
            edges = con.execute("SELECT count(*) FROM edges").fetchone()[0]
        return {"vault": str(self.vault), "lang": self.lang, "pages": total, "tiers": tiers, "statuses": statuses,
                "edges": edges, "indexed_at": built, "kb_folders": self.m.kb.declared(self.vault)}

    def pages(self, q: str = "", tier: str = "", status: str = "", sort: str = "path", offset: int = 0,
              limit: int = 50) -> dict:
        """One page of the page list. `q` searches path and title first, then the words of every page; `sort` is
        `path` or `recent` (only without `q`, which ranks by relevance)."""
        limit = max(1, min(int(limit), MAX_LIST))
        offset = max(0, int(offset))
        q = (q or "").strip()
        with self.con() as con:
            if q:
                return self._search(con, q, tier, status, offset, limit)
            where, args = [], []
            if tier:
                where.append("d.tier=?")
                args.append(tier)
            if status:
                where.append("d.status=?")
                args.append("" if status == "-" else status)
            cond = (" WHERE " + " AND ".join(where)) if where else ""
            join = "FROM files f JOIN docs d ON d.rowid=f.rid" + cond
            total = con.execute(f"SELECT count(*) {join}", args).fetchone()[0]
            order = "f.mtime_ns DESC, f.rel" if sort == "recent" else "f.rel"
            rows = con.execute(f"SELECT f.rel, d.tier, d.status, f.mtime_ns, f.size {join} ORDER BY {order} LIMIT ? OFFSET ?",
                               args + [limit, offset]).fetchall()
        return {"total": total, "offset": offset, "limit": limit, "capped": False,
                "items": [self._decorate(*r) for r in rows]}

    def _search(self, con, q: str, tier: str, status: str, offset: int, limit: int) -> dict:
        ri = self.m.ri
        found: dict[str, tuple] = {}
        like = "%" + q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        for rel, t, s, mt, sz in con.execute(
                "SELECT f.rel, d.tier, d.status, f.mtime_ns, f.size FROM files f JOIN docs d ON d.rowid=f.rid "
                "WHERE lower(f.rel) LIKE ? ESCAPE '\\' ORDER BY length(f.rel), f.rel LIMIT ?", (like, SEARCH_CAP)):
            found[rel] = (rel, t, s, mt, sz)
        toks = [t for t in ri.tokens(q) if not (len(t) == 1 and ri.CJK_RE.fullmatch(t))] or ri.tokens(q)
        if toks:
            match = "{title triggers body} : (" + " OR ".join('"' + t.replace('"', "") + '"' for t in toks) + ")"
            try:
                rows = con.execute(
                    "SELECT d.rel, d.tier, d.status, f.mtime_ns, f.size FROM docs d JOIN files f ON f.rid=d.rowid "
                    "WHERE docs MATCH ? ORDER BY bm25(docs, 0, 4.0, 4.0, 1.0, 0, 0, 0, 0, 0) LIMIT ?",
                    (match, SEARCH_CAP)).fetchall()
            except Exception:  # noqa: BLE001  an odd query FTS cannot parse: the path matches stand
                rows = []
            for r in rows:
                found.setdefault(r[0], r)
        items = [r for r in found.values() if (not tier or r[1] == tier) and (not status or r[2] == ("" if status == "-" else status))]
        total = len(items)
        return {"total": total, "offset": offset, "limit": limit, "capped": total >= SEARCH_CAP,
                "items": [self._decorate(*r) for r in items[offset:offset + limit]]}

    def known(self, con, rel: str):
        """The cache row of a page, or None: only pages the index knows can be read through the viewer."""
        return con.execute("SELECT f.rid, d.tier, d.status, f.mtime_ns, f.size FROM files f JOIN docs d ON d.rowid=f.rid "
                           "WHERE f.rel=?", (rel,)).fetchone()

    def resolve(self, con, target: str) -> str:
        """The page a `[[link]]` names, or ''."""
        keys = self.m.associate.name_keys(target)
        for key in keys:
            row = con.execute("SELECT rel FROM names WHERE key=? ORDER BY length(rel) LIMIT 1", (key,)).fetchone()
            if row:
                return row[0]
        return ""

    def supersede_sides(self, con, rel: str) -> dict:
        """{replaces: [rel], replaced_by: [rel]} for one page, from both pages' frontmatter (the edge table does not
        keep the direction)."""
        assoc = self.m.associate
        out: dict[str, list] = {"replaces": [], "replaced_by": []}
        for a, b, kind in assoc._resolved_links(con, [rel]):
            if kind != "supersedes":
                continue
            head = ""
            try:
                text = (self.vault / a).read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
                head = text.split("\n---", 1)[0] if text.startswith("---\n") else ""
            except OSError:
                pass
            keys_b = set(assoc.name_keys(b))
            side = ""
            for key in assoc.SUPERSEDE_KEYS:
                refs = {assoc.norm_key(r) for v in assoc._fm_values(head, key) for r in assoc._refs(v)}
                if refs & keys_b:
                    side = "replaces" if key in ("supersedes", "replaces") else "replaced_by"
                    break
            if not side:
                continue
            declarer, target = a, b
            if side == "replaces":
                pair = (declarer, target)     # declarer replaces target
            else:
                pair = (target, declarer)     # declarer is replaced by target → target replaces declarer
            if pair[0] == rel and pair[1] != rel:
                out["replaces"].append(pair[1])
            elif pair[1] == rel and pair[0] != rel:
                out["replaced_by"].append(pair[0])
        for k in out:
            out[k] = list(dict.fromkeys(out[k]))
        return out

    def page(self, rel: str) -> dict | None:
        with self.con() as con:
            row = self.known(con, rel)
            if not row:
                return None
            _rid, tier, status, mtime, size = row
            path = self.vault / rel
            meta, body_text = {}, ""
            secret = False
            try:
                raw = path.read_bytes()[:BODY_MAX]
                text = raw.decode("utf-8", errors="replace")
                meta, _b = self.m.ri.split_frontmatter(text)
                secret = self.m.redact.is_secret_page(self.m.zones.canon(self.vault, rel), meta)
                body_text = "" if secret else self.m.redact.redact(text)
            except OSError:
                text = ""
            links = {}
            if body_text:
                for target in dict.fromkeys(self.m.associate.WIKILINK.findall(body_text)):
                    links[target] = self.resolve(con, target)
            sides = self.supersede_sides(con, rel)
            sup = {k: [self._decorate_known(con, r) for r in v] for k, v in sides.items()}
            return {"rel": rel, "title": meta.get("title") or first_heading(body_text) or Path(rel).stem, "tier": tier,
                    "status": status, "date": meta.get("date", ""), "modified": iso(mtime), "size": size,
                    "secret": secret, "truncated": size > BODY_MAX, "kb": self.m.kb.reason(self.vault, rel),
                    "meta": {k: self.m.redact.redact(v) for k, v in meta.items()} if not secret else {},
                    "body": body_text, "links": links, **sup}

    def _decorate_known(self, con, rel: str) -> dict:
        row = self.known(con, rel)
        return self._decorate(rel, row[1], row[2], row[3], row[4]) if row else {"rel": rel, "title": Path(rel).stem,
                                                                              "tier": "", "status": ""}

    # ---- connections ----

    def neighbors(self, rel: str) -> dict | None:
        """The pages connected to `rel`: each with the edges between them and how strong recall's associative path
        takes each edge to be (the number it would add from this page, before its hub split and query weighting)."""
        assoc = self.m.associate
        with self.con() as con:
            row = self.known(con, rel)
            if not row:
                return None
            found: dict[str, dict] = {}

            def add(other: str, kind: str, strength: float, detail: str = "", direction: str = "") -> None:
                if other == rel:
                    return
                e = found.setdefault(other, {"rel": other, "edges": []})
                e["edges"].append({"kind": kind, "strength": round(strength, 3), "detail": detail, "direction": direction})

            sides = self.supersede_sides(con, rel)
            for r in sides["replaces"]:
                add(r, "supersedes", assoc.WEIGHTS["supersedes"], "", "replaces")
            for r in sides["replaced_by"]:
                add(r, "supersedes", assoc.WEIGHTS["supersedes"], "", "replaced_by")
            for a, b, kind in assoc._resolved_links(con, [rel]):
                if kind != "link":
                    continue
                add(b if a == rel else a, "link", assoc.WEIGHTS["link"], "", "out" if a == rel else "in")
            for kind, key in con.execute("SELECT kind, key FROM edges WHERE rel=? AND kind IN ('session','day')", (rel,)):
                peers = [r for (r,) in con.execute("SELECT rel FROM edges WHERE kind=? AND key=? AND rel<>? ORDER BY rel",
                                                   (kind, key, rel))]
                strength = assoc.WEIGHTS[kind] / max(1, len(peers)) ** 0.5
                for r in peers[:PEER_CAP]:
                    add(r, kind, strength, key if kind == "day" else f"{len(peers)} pages")
            for other, w in con.execute("SELECT b, w FROM cocite WHERE a=? UNION ALL SELECT a, w FROM cocite WHERE b=?",
                                        (rel, rel)):
                add(other, "cocite", assoc.WEIGHTS["cocite"] * min(1.0, w / assoc.COCITE_SAT), f"{w:g}×")
            try:
                for p in assoc.spread(con, [{"rel": rel, "score": 1.0}], {rel}):
                    for step in p["via"]:
                        if step["kind"] == "words":
                            add(p["rel"], "words", p["score"], ", ".join(step.get("words") or []))
                            break
            except Exception:  # noqa: BLE001  the shared-words edges are a bonus; the explicit ones stand without them
                pass
            order = sorted(found.values(), key=lambda e: (-max(x["strength"] for x in e["edges"]), -len(e["edges"]), e["rel"]))
            total = len(order)
            nodes = []
            for e in order[:NEIGHBOR_CAP]:
                info = self._decorate_known(con, e["rel"])
                nodes.append({**info, "edges": e["edges"], "strength": max(x["strength"] for x in e["edges"])})
            center = self._decorate_known(con, rel)
            return {"center": center, "neighbors": nodes, "total": total, "capped": total > NEIGHBOR_CAP,
                    "unused_kinds": [k for k, w in assoc.WEIGHTS.items() if not w]}

    # ---- experience ----

    def experience(self) -> dict:
        exp = self.m.experience
        out: dict = {"on": exp.digest_on(), "digest_max": getattr(exp, "DIGEST_MAX_LINES", 0), "cards": [], "events": [],
                     "drafts": [], "skills": []}
        try:
            cards = exp.load_cards(self.vault)
            used = exp.usage(self.vault)
        except Exception:  # noqa: BLE001
            cards, used = [], {}
        for rank, c in enumerate(exp.ranked(cards, used)):
            u = used.get(c["id"], {})
            out["cards"].append({
                "id": c["id"], "rel": c["rel"], "title": c["title"], "lesson": c["lesson"], "when": c["when"],
                "status": c["status"], "date": c["date"], "source": self.m.redact.redact(c["source"] or ""),
                "offered": u.get("offered", 0), "adopted": u.get("adopted", 0), "again": u.get("again", 0),
                "last_offered": u.get("last_offered", ""), "last_adopted": u.get("last_adopted", ""),
                "last_again": u.get("last_again", ""), "rank": rank + 1,
                "in_digest": bool(out["digest_max"]) and rank < out["digest_max"]})
        path = self.path(exp.USES)
        if path.is_file():
            rows = []
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                rows.append({"at": str(d.get("at", ""))[:19], "card": str(d.get("card", "")), "kind": d.get("kind", ""),
                             "why": self.m.redact.redact(str(d.get("why", ""))), "session": str(d.get("session", ""))[:40]})
            out["events"] = sorted(rows, key=lambda r: r["at"], reverse=True)[:30]
        # Skills grown from cards (`skills.py`): kept out of recall, so read from their folder; the counts come from the
        # same use records as the cards'. A skill folder that is not there, or a page that does not parse, is left out.
        sk = self.m.skills
        out["skills_on"] = sk.on()
        try:
            found = sk.load(self.vault)
        except Exception:  # noqa: BLE001
            found = []
        for s in found:
            u = used.get(s["id"], {})
            item = {"id": s["id"], "rel": s["rel"], "title": s["name"], "use_when": s.get("use_when", ""),
                    "status": s["status"], "drafted": str(s.get("drafted") or ""), "promoted": str(s.get("promoted") or ""),
                    "offered": u.get("offered", 0), "adopted": u.get("adopted", 0),
                    "last_adopted": u.get("last_adopted", ""), "path": s["rel"]}
            (out["skills"] if s["status"] == "active" else out["drafts"]).append(item)
        return out

    # ---- what the prompt hook brought ----

    def recalled(self, limit: int = 50) -> dict:
        """The prompt hook's deliveries (`recalled.jsonl` in the state folder, written by `recollect.log`), newest first.
        Empty, not an error, when the file is not there or a line does not parse."""
        rc = self.m.recollect
        out: dict = {"on": bool(rc.routes()), "index_on": rc.index_on(), "rows": [], "file": ""}
        path = rc.state_dir() / "recalled.jsonl"
        out["file"] = str(path)
        if not path.is_file():
            return out
        rows = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-2000:]:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict) or not d.get("page"):
                continue
            rows.append({"ts": str(d.get("ts", ""))[:20], "agent": str(d.get("agent", "")),
                         "session": str(d.get("session", ""))[:8], "route": str(d.get("route", "")),
                         "word": self.m.redact.redact(str(d.get("word", ""))),
                         "sentence": self.m.redact.redact(str(d.get("sentence", ""))),
                         "page": self.m.zones.real(self.vault, str(d["page"])),
                         "notes": [list(n) for n in d.get("notes") or [] if isinstance(n, (list, tuple))]})
        out["rows"] = sorted(rows, key=lambda r: r["ts"], reverse=True)[:limit]
        out["total"] = len(rows)
        return out

    # ---- last night ----

    def _report(self, text: str) -> dict:
        meta, body = self.m.ri.split_frontmatter(text)
        steps, notes = [], []
        for line in body.splitlines():
            s = line.strip()
            if s.startswith("|") and not s.startswith(("| 步骤", "|---", "| step", "| Step")):
                cells = [c.strip() for c in s.strip("|").split("|")]
                if len(cells) >= 5:
                    steps.append({"step": cells[0], "state": cells[1], "calls": cells[2], "seconds": cells[3],
                                  "reason": cells[4]})
            elif s and not s.startswith(("#", "|", "---", "机器生成", "结果：")):
                notes.append(s)
        return {"at": meta.get("nightly_at", ""), "state": meta.get("nightly", ""), "lane": meta.get("lane", ""),
                "steps": steps, "notes": notes}

    def _git(self, *args: str) -> str:
        try:
            r = subprocess.run(["git", "-C", str(self.vault), *args], capture_output=True, text=True, timeout=15,
                               stdin=subprocess.DEVNULL)
            return r.stdout if r.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            return ""

    def nightly(self, nights: int = 6, runs: int = 10, lang: str = "") -> dict:
        report_path = self.path(REPORT)
        out: dict = {"report": None, "history": [], "runs": [], "corrections": [], "learned": {"count": 0, "recent": []},
                     "off": [], "pending_candidates": 0, "git": bool(self.vault.joinpath(".git").exists())}
        if report_path.is_file():
            out["report"] = self._report(report_path.read_text(encoding="utf-8", errors="replace"))
            rel = self.m.zones.real(self.vault, REPORT)
            seen = {out["report"]["at"]}
            for line in self._git("log", f"-n{nights * 3}", "--format=%H", "--", rel).split():
                if len(out["history"]) >= nights:
                    break
                old = self._report(self._git("show", f"{line}:{rel}"))
                if old["at"] and old["at"] not in seen:
                    seen.add(old["at"])
                    out["history"].append(old)
            out["off"] = [{"step": s["step"], "state": s["state"], "reason": s["reason"]} for s in out["report"]["steps"]
                          if s["state"] in ("off", "skipped", "failed", "partial", "missing")]
        led = self.path(self.m.ledger.LEDGER)
        if led.is_file():
            cur = None
            for line in led.read_text(encoding="utf-8", errors="replace").splitlines():
                m = re.match(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) · (.*)$", line)
                if m:
                    cur = {"at": m.group(1), "title": m.group(2), "added": 0, "superseded": 0, "removed": 0, "lines": []}
                    out["runs"].append(cur)
                elif cur is not None and line.strip():
                    text = self.m.redact.redact(line.rstrip())
                    cur["lines"].append(text)
                    s = text.strip()
                    cur["added"] += s.startswith("- 新增")
                    cur["superseded"] += s.startswith("- 取代")
                    cur["removed"] += s.startswith("- 删除")
            out["runs"] = out["runs"][-runs:][::-1]
        cor = self.path(CORRECTIONS)
        if cor.is_file():
            rows = [self.m.redact.redact(ln.strip()) for ln in cor.read_text(encoding="utf-8", errors="replace").splitlines()
                    if re.match(r"^- \d{4}-\d{2}-\d{2} ", ln)]
            out["corrections"] = rows[-10:][::-1]
        learned = self.path(LEARNED)
        if learned.is_file():
            rows = [ln for ln in learned.read_text(encoding="utf-8", errors="replace").splitlines()
                    if ln.strip() and not ln.startswith("#") and "|" in ln]
            out["learned"] = {"count": len(rows), "recent": [
                {"page": r.split("|", 1)[0], "query": self.m.redact.redact(r.split("|", 1)[1])} for r in rows[-10:][::-1]]}
        folder = self.path("05 时间日志/会话摘录")
        if folder.is_dir():
            try:
                import corrections

                out["pending_candidates"] = sum(len(v) for v in corrections.pending(folder).values())
            except Exception:  # noqa: BLE001
                pass
        return self._localize(out) if lang == "en" else out

    def _localize(self, out: dict) -> dict:
        def fix(rep):
            for st in rep["steps"]:
                st["reason"] = to_english(st["reason"])
                st["calls"] = to_english(st["calls"])
            rep["notes"] = [to_english(n) for n in rep["notes"]]

        if out["report"]:
            fix(out["report"])
        for h in out["history"]:
            fix(h)
        for o in out["off"]:
            o["reason"] = to_english(o["reason"])
        for r in out["runs"]:
            r["lines"] = [to_english(ln) for ln in r["lines"]]
        return out
