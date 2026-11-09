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
from pathlib import Path

PENDING = ("待下次蒸馏判定", "待蒸馏确认")
LINE = re.compile(r"^- （(\d{2}:\d{2})）(.*) — 项目 (.*?)，会话 `(?:claude|codex|cursor):([0-9A-Za-z?-]+)`，命中「(.*?)」，(.+)$")
PAGE = re.compile(r"^(\d{4}-\d{2}-\d{2})｜纠正候选\.md$")
MIN_CJK = 3         # 没有共同的专有词时，至少要共有这么多个中文词组
MIN_SHARE = 0.3     # 而且占候选词组的这么大比例
# 纠正用语和虚词不算内容："改成"两边都有，说明不了是同一件事（2026-11 本机倒推：10 条判定 7 条挂错了行）
GENERIC = re.compile(r"改成|改为|改回|换成|换回|以后都|以后一律|一律|锁死|不要再|别再|记住|纠正|纠错|搞错|说错|弄错|"
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
    for page in folder.glob("*｜纠正候选.md"):
        m = PAGE.match(page.name)
        if not m:
            continue
        for n, raw in enumerate(page.read_text(encoding="utf-8").splitlines()):
            hit = LINE.match(raw)
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
