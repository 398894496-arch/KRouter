#!/usr/bin/env python3
"""Compile the L0 standing index (下意识) from the alias map + source frontmatter.

Read-only on sources. Writes one generated page. Expired / not-yet-valid rows stay out of L0.
Agents load that page; they open a vault page only after a lock hit.
"""

from __future__ import annotations

import argparse
import re
from datetime import date, datetime
from pathlib import Path

import zones
from canonical_lookup import in_force, load_rows, map_for, parse_frontmatter

REL = "90 系统文件/自动化/下意识.md"
HOW_MAX = 80
CLASSES = {"constraint", "result", "method", "evidence", "episodic"}


def kind_for(source: str, fm: dict[str, str]) -> str:
    tagged = (fm.get("memory_class") or "").strip()
    if tagged in CLASSES:
        return tagged
    if tagged in {"router", "preference", "correction"}:
        return "constraint"
    if "纠错" in source:
        return "constraint"
    if "偏好" in source or "约束" in source:
        return "constraint"
    if "准经验" in source:
        return "method"
    if source.startswith("02 "):
        return "method"
    if source.startswith("01 "):
        return "result"
    if source.startswith("04 "):
        return "result"
    if source.startswith("03 "):
        return "evidence"
    if source.startswith("05 "):
        return "episodic"
    return "constraint"


def pipe_safe(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("|", "/")).strip()


def how_for(anchor: str, fm: dict[str, str]) -> str:
    # Map evidence anchor is the standing one-liner. Page title is just the file name.
    raw = fm.get("how") or anchor or fm.get("title") or ""
    text = pipe_safe(raw)
    if len(text) > HOW_MAX:
        text = text[: HOW_MAX - 1].rstrip() + "…"
    return text


def nonempty_meta(raw: str) -> bool:
    v = (raw or "").strip().lower()
    return v not in {"", "[]", "{}", "none", "null", "false", "no", "0", "-"}


def correction_flag(source: str, fm: dict[str, str], aliases: list[str]) -> str:
    if "纠错" in source:
        return "yes"
    if nonempty_meta(fm.get("correction", "")):
        return "yes"
    if nonempty_meta(fm.get("supersedes", "")):
        return "yes"
    joined = ";".join(aliases).lower()
    if "correction" in joined or "supersedes" in joined or "纠错" in joined:
        return "yes"
    return "no"


def compile_rows(
    vault: Path,
    map_path: Path,
    today: date | None = None,
) -> list[str]:
    today = today or date.today()
    lines: list[str] = []
    for case_id, aliases, source, anchor in load_rows(map_path):
        path = vault / source
        fm = parse_frontmatter(path)
        live, valid_from, invalid_at = in_force(fm, today)
        if not live:
            continue
        if not path.is_file():
            continue
        kind = kind_for(zones.canon(vault, source), fm)
        how = how_for(anchor, fm)
        flag = correction_flag(source, fm, aliases)
        alias_s = pipe_safe(";".join(aliases))
        lines.append(
            "|".join(
                [
                    case_id,
                    kind,
                    alias_s,
                    how,
                    flag,
                    valid_from,
                    invalid_at,
                    source,
                ]
            )
        )
    return lines


def render(lines: list[str], map_sha: str, generated_at: str) -> str:
    body = [
        "---",
        "title: 下意识",
        "status: generated",
        f"generated_at: {generated_at}",
        f"row_count: {len(lines)}",
        f"canonical_map_sha256: {map_sha}",
        "---",
        "",
        "# 下意识",
        "",
        "L0 standing index. Load this page. Open a vault page only after a lock hit.",
        "Do not dump the vault into context. `correction:yes` → run the correction route first.",
        "No lock → the router answers with L1 recall (ranked pages + one-line `how`, rule pages first).",
        "`recall: none` means no page covers the question: say so, do not guess.",
        "",
        "# id|kind|aliases|how|correction|valid_from|invalid_at|source",
        *lines,
        "",
    ]
    return "\n".join(body)


def file_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_vault(
    vault: Path,
    map_path: Path | None = None,
    out: Path | None = None,
    today: date | None = None,
) -> Path:
    vault = vault.resolve()
    map_path = (map_path or map_for(vault)).resolve()
    dest = out or zones.path(vault, REL)
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = compile_rows(vault, map_path, today=today)
    map_sha = file_sha256(map_path) if map_path.is_file() else ""
    generated_at = datetime.now().isoformat(timespec="seconds")
    dest.write_text(render(lines, map_sha, generated_at), encoding="utf-8")
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile KRouter L0 下意识 index")
    parser.add_argument("--vault", required=True)
    parser.add_argument("--map", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--today", default="")
    args = parser.parse_args()
    today = date.fromisoformat(args.today) if args.today else None
    dest = compile_vault(
        Path(args.vault),
        Path(args.map) if args.map else None,
        Path(args.out) if args.out else None,
        today=today,
    )
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
