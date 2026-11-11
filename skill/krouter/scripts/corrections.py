#!/usr/bin/env python3
"""Settling the correction candidates `session_hook.py prompt` wrote down, without asking you.

When the session a candidate came from is distilled, the candidate is matched against that session's digest by
content words (correction wording and times left out): a digest line that shares a distinctive term (a model, a
number, a name) or enough Chinese terms settles it as 成立, with that line. When no line does, the distill missed what
the person said, so the candidate is written into the digest in their own words and settled as 补记. No extra model
call. The candidate line on its page records the verdict, and the run's
ledger entry lists it (`capture_ledger.py`). A candidate whose session was not distilled in this run stays pending.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PENDING_EN = "pending the next distill"
PENDING = ("待下次蒸馏判定", "待蒸馏确认", PENDING_EN)
LINE = re.compile(r"^- （(\d{2}:\d{2})）(.*) — 项目 (.*?)，会话 `(?:claude|codex|cursor):([0-9A-Za-z?-]+)`，命中「(.*?)」，(.+)$")
# 英文库（zones.lang == en）里 session_hook 写的同一行
LINE_EN = re.compile(r"^- \((\d{2}:\d{2})\) (.*) — project (.*?), session `(?:claude|codex|cursor):([0-9A-Za-z?-]+)`, "
                     r"cue \"(.*?)\", (.+)$")
PAGE = re.compile(r"^(\d{4}-\d{2}-\d{2})｜(?:纠正候选|Correction candidates)\.md$")
PAGE_NAME = {"zh": "纠正候选", "en": "Correction candidates"}
MIN_CJK = 3         # 没有共同的专有词时，至少要共有这么多个中文词组
MIN_SHARE = 0.3     # 而且占候选词组的这么大比例
# 纠正用语和虚词不算内容："改成"两边都有，说明不了是同一件事（2026-11 本机倒推：10 条判定 7 条挂错了行）
GENERIC = re.compile(r"改成|改为|改回|改用|换成|换回|换用|以后都|以后一律|一律|锁死|不要再|别再|记住|纠正|纠错|搞错|说错|弄错|"
                     r"你错了|不对|应该是|原来|现在|之前|以后|然后|另外|可以的话|帮我|一下|这个|那个|那就|就|好的|"
                     r"from now on|instead of|that'?s wrong|don'?t|never|always|use", re.I)
TIME = re.compile(r"[（(]\s*\d{1,2}:\d{2}\s*[)）]|\b\d{1,2}:\d{2}\b")
TERM = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_-]*")
CJK = re.compile(r"[\u4e00-\u9fff]+")


def words(text: str) -> tuple[set[str], set[str]]:
    """(distinctive terms, CJK bigrams) of a line, after dropping correction wording, function words and times.
    A distinctive term is a model, number or name (`1.92tb`, `22.8`, `512k`, `nekobox`), never a lone 1–2 digit."""
    text = GENERIC.sub(" ", TIME.sub(" ", text))
    terms = {t.lower().rstrip(".-") for t in TERM.findall(text)}
    terms = {t for t in terms if len(t) > 1 and not (t.isdigit() and len(t) <= 2)}
    grams = {run[i:i + 2] for run in CJK.findall(text) for i in range(len(run) - 1)}
    return terms, grams


def pending(folder: Path) -> dict[tuple[str, str], list[dict]]:
    """{(date, id8): [{page, n, time, said, cue}]} for every candidate line still waiting."""
    out: dict[tuple[str, str], list[dict]] = {}
    if not folder.is_dir():
        return out
    for page in sorted(folder.glob("*｜*.md")):
        m = PAGE.match(page.name)
        if not m:
            continue
        for n, raw in enumerate(page.read_text(encoding="utf-8").splitlines()):
            hit = LINE.match(raw) or LINE_EN.match(raw)
            if hit and hit.group(6) in PENDING:
                out.setdefault((m.group(1), hit.group(4)[:8]), []).append(
                    {"page": page, "n": n, "time": hit.group(1), "said": hit.group(2), "cue": hit.group(5)})
    return out


def settle(cands: list[dict], digest: list[str]) -> list[dict]:
    """Each candidate with `ok`, the matching digest `line` (when 成立) and `why` (when 不成立)."""
    out = []
    for c in cands:
        ct, cg = words(c["said"])
        best, score = "", (0, 0.0)
        for ln in digest:
            lt, lg = words(ln)
            terms, grams = len(ct & lt), len(cg & lg)
            share = grams / max(1, len(cg))
            if not (terms or (grams >= MIN_CJK and share >= MIN_SHARE)):
                continue
            if (terms, share) > score:
                best, score = ln.lstrip("-* ").strip(), (terms, share)
        out.append({**c, "ok": bool(best), "line": best,
                    "why": "" if best else "这一轮提炼里没有对应的决定或改动"})
    return out


def own_line(c: dict) -> str:
    """A candidate the digest did not cover, as a digest line in the person's own words."""
    return f"- 你说：{c['said'].strip()}（{c.get('time') or '?'}，当场记下的纠正，提炼里没有）"


def mark(results: list[dict]) -> list[Path]:
    """Write each verdict (with the digest page's `link`) over its candidate's pending mark; returns the pages changed."""
    by_page: dict[Path, list[dict]] = {}
    for r in results:
        by_page.setdefault(r["page"], []).append(r)
    for page, rs in by_page.items():
        lines = page.read_text(encoding="utf-8").splitlines()
        for r in rs:
            old = lines[r["n"]]
            for p in PENDING:
                if old.endswith(p) and p == PENDING_EN:
                    if r.get("kind") == "补记":
                        verdict = f"verdict: added → {r['link']}: {r['line']}"
                    elif r["ok"]:
                        verdict = f"verdict: holds → {r['link']}: {r['line']}"
                    else:
                        verdict = "verdict: does not hold (no matching decision or change in this distill)"
                    lines[r["n"]] = old[: -len(p)] + verdict
                    break
                if old.endswith(p):
                    if r.get("kind") == "补记":
                        verdict = f"判定：补记 → {r['link']}：{r['line']}"
                    elif r["ok"]:
                        verdict = f"判定：成立 → {r['link']}：{r['line']}"
                    else:
                        verdict = f"判定：不成立（{r['why']}）"
                    lines[r["n"]] = old[: -len(p)] + verdict
                    break
        page.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return list(by_page)


# ---------- 会话内落实一条纠正（宿主通道第 1 级：agent 当轮就做，不等夜间提炼，不要模型） ----------

NOTES = "05 时间日志/会话摘录"
LOG_PAGE = "90 系统文件/Agent记忆/纠错与取代记录.md"
SMALL_PAGE = 12        # 正文不超过这么多行的页，整页就是那个旧决定：整页标 superseded
TEXT_MAX = 500
SKIP_PREFIXES = ("90 系统文件/自动化/", "90 系统文件/Agent记忆/", ".")


def _frontmatter_set(text: str, fields: dict[str, str]) -> str:
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n") or "\n---" not in text[4:]:
        return "---\n" + "".join(f"{k}: {v}\n" for k, v in fields.items()) + "---\n\n" + text
    end = text.index("\n---", 4)
    lines = text[4:end].splitlines()
    for key, val in fields.items():
        for i, line in enumerate(lines):
            if line.startswith(key + ":"):
                lines[i] = f"{key}: {val}"
                break
        else:
            lines.append(f"{key}: {val}")
    return "---\n" + "\n".join(lines) + text[end:]


def _grounded(old: str, text: str) -> int:
    """The line number (0-based) on the page that states `old`, or -1: the whole sentence, or most of its content
    words (terms, or Chinese bigrams) on one line."""
    lines = text.splitlines()
    flat = " ".join(old.split())
    for i, ln in enumerate(lines):
        if flat and flat in " ".join(ln.split()):
            return i
    ot, og = words(old)
    best, at = 0.0, -1
    for i, ln in enumerate(lines):
        lt, lg = words(ln)
        share = (len(ot & lt) + len(og & lg)) / max(1, len(ot) + len(og))
        if share > best:
            best, at = share, i
    return at if best >= 0.6 else -1


WIKI = re.compile(r"\[\[([^\]|#]+)")


def _write(path: Path, text: str) -> None:
    """Replace the page in one step: a lookup reading it meanwhile sees the old page or the new one, never half."""
    import os
    import threading

    import time

    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    for attempt in range(100):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # Windows：别的进程（一次查询）正开着这一页，稍等再换
            if attempt == 99:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.02)


def _meta(text: str) -> dict[str, str]:
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n") or "\n---" not in text[4:]:
        return {}
    out = {}
    for line in text[4:text.index("\n---", 4)].splitlines():
        if ":" in line and not line.startswith((" ", "-", "\t")):
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _small(text: str) -> bool:
    body = text.split("\n---", 1)[-1] if text.startswith("---") else text
    return len([ln for ln in body.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]) <= SMALL_PAGE


def _rel(vault: Path, p: Path) -> str:
    return str(p.relative_to(vault)).replace("\\", "/")


def _link_path(vault: Path, link: str) -> Path | None:
    import zones

    link = link.strip().removesuffix(".md")
    for cand in (vault / (link + ".md"), zones.path(vault, zones.canon(vault, link + ".md"))):
        if cand.is_file():
            return cand
    return None


CHAIN_MAX = 100_000  # 取代链最长走这么多步；只防环和坏链，不是上限（2026-11-10：原来 100 步，30 分钟压测里第 101 条纠正起就悄悄并存）


def _head(vault: Path, page: Path | None, memo: dict | None = None) -> Path | None:
    """The page in force at the end of `page`'s `superseded_by` chain (itself when it is not superseded); None when
    the chain ends nowhere (a link to a page that is gone) or goes round. `memo` (page → head) is shared by the walks
    of one correction, so many `⚠ 已改` notes on one line cost one walk, not one each."""
    memo = {} if memo is None else memo
    seen: list[Path] = []
    head = None
    while page is not None and len(seen) < CHAIN_MAX:
        if page in memo:
            head = memo[page]
            break
        if page in seen:
            break
        seen.append(page)
        meta = _meta(page.read_text(encoding="utf-8"))
        if meta.get("status", "").lower() != "superseded":
            head = page
            break
        links = WIKI.findall(meta.get("superseded_by", ""))
        page = _link_path(vault, links[-1]) if links else None
    for p in seen:
        memo[p] = head
    return head


def _unfind(meta: dict) -> dict:
    """A correction page that is replaced stops answering the old page's questions: its `topic_terms` (the replaced
    page's title, given when it was written) is cleared, so hundreds of replaced corrections of one decision do not
    crowd the one in force out of a lookup's candidates. Only correction pages; a page of yours keeps its fields."""
    return {"topic_terms": '""'} if meta.get("type") == "correction" and meta.get("topic_terms") else {}


def _now_line(text: str) -> str:
    for ln in text.splitlines():
        if ln.startswith(("- 现在：", "- Now: ")):
            return ln.split("：", 1)[-1].split(": ", 1)[-1].strip()[:200]
    return ""


def apply_now(vault: Path, new: str, old: str = "", page: str = "", source: str = "", author: str = "") -> dict:
    """Make a correction hold now, with the vault's own supersede rule: a new correction page that `supersedes` the
    old one, and the old page marked `status: superseded` when it is only that decision (≤ SMALL_PAGE lines), or the
    old line annotated when the page says other things too. Plus a line in 纠错与取代记录 and today's matching
    pending candidates settled. Returns {written, superseded, mode, touched, settled, conflicts} or {error}.

    Two corrections of the same thing (two people, or one person twice) never leave two answers in force, and neither
    is lost: the later one holds. When the named page was already superseded, the correction replaces the page now in
    force at the end of its `superseded_by` chain instead; when the old line already carries a `⚠ 已改` note, the
    correction pages those notes point to are replaced too. Each replaced page stays, marked superseded, and is listed
    in `conflicts` (who wrote it, when, why). `author` (a team server's user) goes on the new page and on each page it
    marks superseded."""
    from datetime import datetime

    import zones
    from krouter_redact import is_secret_page, redact

    new, old = " ".join(redact(new or "").split()), " ".join(redact(old or "").split())
    if not new:
        return {"error": "new is required: the decision as it stands now, in the user's words"}
    if len(new) > TEXT_MAX or len(old) > TEXT_MAX:
        return {"error": f"new and old are at most {TEXT_MAX} characters each"}
    now = datetime.now()
    day = now.date().isoformat()
    zh = bool(CJK.search(new + old))
    target, line_no, rel_old = None, -1, ""
    if page:
        rel_old = zones.canon(vault, page.strip().lstrip("/").removesuffix(".md") + ".md")
        target = zones.path(vault, rel_old)
        try:
            inside = target.resolve().is_relative_to(vault.resolve())
        except (OSError, ValueError):
            inside = False
        if not inside or not target.is_file() or rel_old.startswith(SKIP_PREFIXES) or is_secret_page(rel_old):
            return {"error": f"page {page!r} is not a note in this vault that a correction can supersede"}
        if not old:
            return {"error": "old is required with page: the sentence on that page that no longer holds"}
        line_no = _grounded(old, target.read_text(encoding="utf-8"))
        if line_no < 0:
            return {"error": f"the old sentence is not on {rel_old}; nothing was superseded (pass the page that says it)"}
    slug = re.sub(r'[\\/:*?"<>|#^\[\]\n]', "", new)[:24].strip() or "纠正"
    rel_new = f"{NOTES}/{day}｜{'纠正' if zh else 'correction'}｜{slug}.md"
    new_path = zones.path(vault, rel_new)
    if new_path.exists():  # 同一句纠正同一天又来一次（或两个人同一秒）：编号，不覆盖前一页
        stem, n = new_path.stem + f"-{now.strftime('%H%M%S')}", 1
        new_path = new_path.with_name(stem + ".md")
        while new_path.exists():
            n += 1
            new_path = new_path.with_name(f"{stem}-{n}.md")
        rel_new = zones.canon(vault, str(new_path.relative_to(vault)).replace("\\", "/"))
    # 链接和回报用这个库自己的路径（英文库是 05 Journal/Sessions/…），不用默认布局的逻辑路径
    real_new, real_old = zones.real(vault, rel_new), zones.real(vault, rel_old) if rel_old else ""
    link_new, link_old = f"[[{real_new.removesuffix('.md')}]]", f"[[{real_old.removesuffix('.md')}]]" if real_old else ""
    hm = now.strftime("%H:%M")
    if zh:
        body = (f"# 纠正：{new}\n\n" + (f"- 原来：{old}\n" if old else "") + f"- 现在：{new}\n"
                + (f"- 原来 {old} → 改成 {new}（{hm}）\n" if old else "")
                + f"- 出处：会话内由 agent 当轮落实（{source or '未知'}{'，' + author if author else ''}），没等夜间提炼；"
                + (f"取代 {link_old}" if link_old else "没有指出旧页") + "。不对就按「记忆变更记录」里的命令撤销。\n")
    else:
        body = (f"# Correction: {new}\n\n" + (f"- Was: {old}\n" if old else "") + f"- Now: {new}\n"
                + (f"- was {old} → now {new} ({hm})\n" if old else "")
                + f"- Source: made to hold in session by the agent ({source or 'unknown'}{', ' + author if author else ''}), not waiting for the nightly "
                + (f"distill; supersedes {link_old}" if link_old else "distill; no old page named")
                + ". Undo it with the command in the change ledger.\n")
    fm = {"title": f"\"{'纠正：' if zh else 'Correction: '}{new[:40]}\"", "type": "correction", "status": "active",
          "date": day, "source": "krouter-correct"}
    # how 给现在的说法：正文第一条是「原来」，不写的话回执的 how 会把作废的那句当答案
    fm["how"] = "\"" + (f"现在：{new}" if zh else f"Now: {new}").replace('"', "'") + "\""
    if target is not None:  # 取代哪一页，就用那一页的标题词也能找到这一页：问旧页那件事的人看得到新说法
        tm = _meta(target.read_text(encoding="utf-8"))
        topic = " ".join(x for x in (tm.get("title") or target.stem, tm.get("topic_terms", "")) if x)
        fm["topic_terms"] = "\"" + topic.replace('"', "'")[:120] + "\""
    if author:
        fm["author"] = author
    fm["written_at"] = now.astimezone().isoformat(timespec="milliseconds")
    # 先找出眼下对这件事生效的旧纠正：命名的页已被别人取代，或那一行下面已有「已改」
    prior: list[tuple[Path, str]] = []
    already = False
    overrides: dict | None = None
    unresolved: dict | None = None
    memo: dict = {}
    if target is not None:
        meta_old = _meta(target.read_text(encoding="utf-8"))
        if meta_old.get("status", "").lower() == "superseded":
            already = True
            head = _head(vault, target, memo)
            if head is not None and head != target:
                prior.append((head, "stale: the page named was already superseded"))
            elif head is None:  # 链断了或绕回来了：照样写下，但说清楚，不让两条纠正悄悄并存
                unresolved = {"page": _rel(vault, target), "author": meta_old.get("superseded_by_author", ""),
                              "at": meta_old.get("superseded_at", ""), "said": "",
                              "why": "unresolved: the page named is superseded, but its superseded_by chain is broken "
                                     "or goes round, so the correction in force could not be found",
                              "left_active": True}
        else:
            if meta_old.get("type") == "correction" and meta_old.get("author") and meta_old.get("author") != author:
                overrides = {"page": _rel(vault, target), "author": meta_old.get("author", ""),
                             "at": meta_old.get("written_at") or meta_old.get("date", ""),
                             "said": _now_line(target.read_text(encoding="utf-8")),
                             "why": "overrides: the page named is another person's correction"}
            lines_old = target.read_text(encoding="utf-8").splitlines()
            j = line_no + 1
            while j < len(lines_old) and lines_old[j].lstrip().startswith(("- ⚠ 已改", "- ⚠ changed")):
                for link in WIKI.findall(lines_old[j]):
                    head = _head(vault, _link_path(vault, link), memo)
                    if head is not None and all(head != p for p, _ in prior):
                        prior.append((head, "same line: an earlier correction of this line was in force"))
                j += 1
    links_prior = [f"[[{zones.real(vault, zones.canon(vault, _rel(vault, p))).removesuffix('.md')}]]" for p, _ in prior]
    sup = [link_old] if link_old else []
    sup += [lk for lk in links_prior if lk not in sup]
    if sup:
        fm["supersedes"] = "\"" + " ".join(sup) + "\""
    if prior:
        body += ("- 取代仍在生效的旧纠正（后到的生效）：" if zh else "- Replaces the corrections still in force (the later one holds): ") \
            + "、".join(links_prior) + "\n"
    new_path.parent.mkdir(parents=True, exist_ok=True)
    _write(new_path, _frontmatter_set("", fm).rstrip("\n") + "\n\n" + body)
    touched, mode, conflicts = [new_path], "recorded", [x for x in (overrides, unresolved) if x]
    stamp = {"superseded_by": f"\"{link_new}\"", "superseded_at": day,
             **({"superseded_by_author": author} if author else {})}
    for p, why in prior:
        ptext = p.read_text(encoding="utf-8")
        pm = _meta(ptext)
        entry = {"page": _rel(vault, p), "author": pm.get("author", ""), "at": pm.get("written_at") or pm.get("date", ""),
                 "said": _now_line(ptext), "why": why}
        if _small(ptext):
            _write(p, _frontmatter_set(ptext, {"status": "superseded", **stamp, **_unfind(pm)}))
            touched.append(p)
        else:
            entry["left_active"] = True  # 长页不整页作废：两页都还在，回执里说清
        conflicts.append(entry)
    if target is not None and already:
        mode = "page"  # 命名的页本来就作废了；它的 superseded_by 链不改，新页接在链尾
    elif target is not None:
        text = target.read_text(encoding="utf-8")
        if _small(text):
            text = _frontmatter_set(text, {"status": "superseded", **stamp, **_unfind(_meta(text))})
            mode = "page"
        else:
            lines = text.splitlines()
            note = (f"  - ⚠ 已改（{day}）：{new} → {link_new}" if zh else f"  - ⚠ changed ({day}): {new} → {link_new}")
            at = line_no + 1
            while at < len(lines) and lines[at].lstrip().startswith(("- ⚠ 已改", "- ⚠ changed")):
                at += 1  # 接在这一行已有的「已改」后面：从上往下按时间
            lines.insert(at, note)
            text = "\n".join(lines) + "\n"
            mode = "line"
        _write(target, text)
        touched.append(target)
    log = zones.path(vault, LOG_PAGE)
    if log.is_file():
        entry = (f"- {day} 原来 {old or '（没说）'}{('（' + link_old + '）') if link_old else ''} → 改成 {new}（{link_new}）；"
                 "会话内由 agent 落实，没人核对过\n") if zh else \
                (f"- {day} was {old or '(not said)'}{(' (' + link_old + ')') if link_old else ''} → now {new} ({link_new}); "
                 "made to hold in session by the agent, not checked by anyone\n")
        with log.open("a", encoding="utf-8") as fh:
            fh.write(("\n" if not log.read_text(encoding="utf-8").endswith("\n") else "") + entry)
        touched.append(log)
    settled = []
    folder = zones.path(vault, NOTES)
    today = [c for (d, _sid), cs in pending(folder).items() if d == day for c in cs]
    if today:
        hits = [r for r in settle(today, [new]) if r["ok"]]
        settled = [{**r, "link": link_new} for r in hits]
        touched += mark(settled)
    return {"written": real_new, "superseded": real_old, "mode": mode, "touched": touched, "settled": len(settled),
            "conflicts": conflicts}


def main() -> int:
    import argparse
    import json

    from krouter_home import vault_path

    ap = argparse.ArgumentParser(description="Make one correction hold now (no model): `apply`.")
    ap.add_argument("--vault", default=vault_path())
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("apply", help="new decision; optionally the old sentence and the page that says it")
    a.add_argument("--new", required=True)
    a.add_argument("--old", default="")
    a.add_argument("--page", default="", help="vault-relative path of the page with the old answer")
    args = ap.parse_args()
    if not args.vault:
        print("set KROUTER_VAULT (or the older name OBSIDIAN_VAULT)", file=sys.stderr)
        return 2
    res = apply_now(Path(args.vault).expanduser(), args.new, args.old, args.page, "corrections.py apply")
    res.pop("touched", None)
    print(json.dumps(res, ensure_ascii=False))
    return 1 if "error" in res else 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
