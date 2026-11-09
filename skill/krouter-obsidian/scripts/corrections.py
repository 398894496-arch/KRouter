#!/usr/bin/env python3
"""Settling the correction candidates `session_hook.py prompt` wrote down, without asking you.

When the session a candidate came from is distilled, the candidate is matched against that session's digest by
content words: a digest line that carries enough of the candidate's words settles it as 成立 (with that line);
none settles it as 不成立. No extra model call. The candidate line on its page records the verdict, and the run's
ledger entry lists it (`capture_ledger.py`). A candidate whose session was not distilled in this run stays pending.
"""

from __future__ import annotations

import re
from pathlib import Path

PENDING = ("待下次蒸馏判定", "待蒸馏确认")
LINE = re.compile(r"^- （(\d{2}:\d{2})）(.*) — 项目 (.*?)，会话 `(?:claude|codex|cursor):([0-9A-Za-z?-]+)`，命中「(.*?)」，(.+)$")
PAGE = re.compile(r"^(\d{4}-\d{2}-\d{2})｜纠正候选\.md$")
MIN_SHARED = 2      # 候选和提炼行至少共有这么多个实词
MIN_SHARE = 0.3     # 或者占候选实词的这么大比例


def words(text: str) -> set[str]:
    import recall_index as ri

    return {t for t in ri.question_terms(text) if t not in ri.EN_FUNCTION and len(t) > 1}


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
        cw = words(c["said"])
        best, score = "", 0.0
        for ln in digest:
            shared = len(cw & words(ln))
            share = shared / max(1, len(cw))
            if (shared >= MIN_SHARED or share >= MIN_SHARE) and share > score:
                best, score = ln.lstrip("-* ").strip(), share
        out.append({**c, "ok": bool(best), "line": best,
                    "why": "" if best else "这一轮提炼里没有对应的决定或改动"})
    return out


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
                    verdict = f"判定：成立 → {r['link']}：{r['line']}" if r["ok"] else f"判定：不成立（{r['why']}）"
                    lines[r["n"]] = old[: -len(p)] + verdict
                    break
        page.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return list(by_page)
