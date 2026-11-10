#!/usr/bin/env python3
"""Count sealed days and gaps in 05 时间日志/.

A day is sealed when a DD｜*.md file exists, is not empty, and is not the
to-summarize stub. That is the protocol in ARCHITECTURE.md. A runner receipt
is not consulted.

Any host can run this on their vault. It does not verify the historical claim
that the author sealed 72 consecutive days.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAY_FILE = re.compile(r"^(\d{2})[|｜](.+)\.md$")
STUB_MARKERS = ("待总结", "to-summarize", "to_summarize")
LOG_DIR = "05 时间日志"


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    found: dict[str, str] = {}
    for raw in parts[1].splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        name, val = line.split(":", 1)
        found[name.strip()] = val.strip().strip('"').strip("'")
    return found, parts[2]


def is_stub(path: Path, fm: dict[str, str]) -> bool:
    name = path.name
    lowered = name.lower()
    if any(marker in name or marker in lowered for marker in STUB_MARKERS):
        return True
    status = fm.get("status", "").lower().replace("_", "-")
    return status == "to-summarize"


def is_empty_body(body: str) -> bool:
    return not body.strip()


def iter_day_files(vault: Path) -> list[tuple[date, Path]]:
    root = vault / LOG_DIR
    if not root.is_dir():
        return []
    found: list[tuple[date, Path]] = []
    for month_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        month_name = month_dir.name
        if not re.match(r"^\d{4}-\d{2}$", month_name):
            continue
        year, month = (int(x) for x in month_name.split("-"))
        for path in sorted(month_dir.glob("*.md")):
            match = DAY_FILE.match(path.name)
            if not match:
                continue
            day_n = int(match.group(1))
            try:
                day = date(year, month, day_n)
            except ValueError:
                continue
            found.append((day, path))
    return found


def classify_day(paths: list[Path]) -> tuple[str, str | None]:
    """sealed | stub | empty. If a real note exists, the day is sealed."""
    kinds: list[tuple[str, Path]] = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        fm, body = parse_frontmatter(text)
        if is_stub(path, fm):
            kinds.append(("stub", path))
        elif is_empty_body(body):
            kinds.append(("empty", path))
        else:
            kinds.append(("sealed", path))
    for kind, path in kinds:
        if kind == "sealed":
            return "sealed", path.name
    if any(kind == "empty" for kind, _ in kinds):
        empty = next(path for kind, path in kinds if kind == "empty")
        return "empty", empty.name
    stub = kinds[0][1]
    return "stub", stub.name


def streaks(days: list[date]) -> list[tuple[date, date, int]]:
    if not days:
        return []
    ordered = sorted(set(days))
    out: list[tuple[date, date, int]] = []
    start = prev = ordered[0]
    length = 1
    for day in ordered[1:]:
        if day == prev + timedelta(days=1):
            length += 1
            prev = day
            continue
        out.append((start, prev, length))
        start = prev = day
        length = 1
    out.append((start, prev, length))
    return out


def measure(
    vault: Path,
    from_date: date | None = None,
    through_date: date | None = None,
) -> dict:
    files = iter_day_files(vault)
    by_day: dict[date, list[Path]] = {}
    for day, path in files:
        by_day.setdefault(day, []).append(path)

    classified: dict[date, tuple[str, str | None]] = {}
    for day, paths in by_day.items():
        classified[day] = classify_day(paths)

    present = sorted(classified)

    if from_date is None:
        from_date = present[0] if present else None
    if through_date is None:
        through_date = present[-1] if present else None

    window_days: list[date] = []
    missing: list[str] = []
    stubs: list[dict] = []
    empties: list[dict] = []
    if from_date and through_date and from_date <= through_date:
        cur = from_date
        while cur <= through_date:
            window_days.append(cur)
            kind_file = classified.get(cur)
            if kind_file is None:
                missing.append(cur.isoformat())
            elif kind_file[0] == "stub":
                stubs.append({"date": cur.isoformat(), "file": kind_file[1]})
            elif kind_file[0] == "empty":
                empties.append({"date": cur.isoformat(), "file": kind_file[1]})
            cur += timedelta(days=1)

    sealed_in_window_dates = [
        day
        for day in window_days
        if classified.get(day, (None, None))[0] == "sealed"
    ]
    run_list = streaks(sealed_in_window_dates)
    longest = max(run_list, key=lambda item: item[2], default=None)

    current = 0
    if through_date:
        cursor = through_date
        while classified.get(cursor, (None, None))[0] == "sealed":
            current += 1
            cursor -= timedelta(days=1)

    return {
        "vault": str(vault),
        "log_dir": str(vault / LOG_DIR),
        "from_date": from_date.isoformat() if from_date else None,
        "through_date": through_date.isoformat() if through_date else None,
        "expected_days": len(window_days),
        "sealed": len(sealed_in_window_dates),
        "stub": len(stubs),
        "empty": len(empties),
        "missing": len(missing),
        "longest_streak": longest[2] if longest else 0,
        "longest_streak_from": longest[0].isoformat() if longest else None,
        "longest_streak_through": longest[1].isoformat() if longest else None,
        "current_streak_through_end": current,
        "missing_dates": missing[:40],
        "missing_dates_truncated": max(0, len(missing) - 40),
        "stub_dates": stubs[:40],
        "stub_dates_truncated": max(0, len(stubs) - 40),
        "empty_dates": empties[:40],
        "empty_dates_truncated": max(0, len(empties) - 40),
        "note": (
            "Measures this vault. Does not verify the author's 72 consecutive seals."
        ),
    }


def default_vault() -> Path:
    env = os.environ.get("OBSIDIAN_VAULT")
    if env:
        return Path(env)
    return ROOT / "template"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Count sealed days and gaps in 05 时间日志/. "
            "Measures this vault; does not verify the author's 72 consecutive seals."
        )
    )
    parser.add_argument("--vault", type=Path, default=None)
    parser.add_argument("--from-date", default=None)
    parser.add_argument("--through-date", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    vault = args.vault or default_vault()
    from_date = date.fromisoformat(args.from_date) if args.from_date else None
    through_date = date.fromisoformat(args.through_date) if args.through_date else None
    result = measure(vault, from_date, through_date)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"vault={result['vault']}")
        print(
            f"window={result['from_date']}..{result['through_date']} "
            f"expected={result['expected_days']}"
        )
        print(
            f"sealed={result['sealed']} stub={result['stub']} "
            f"empty={result['empty']} missing={result['missing']}"
        )
        print(
            f"longest_streak={result['longest_streak']} "
            f"({result['longest_streak_from']}..{result['longest_streak_through']}) "
            f"current_streak={result['current_streak_through_end']}"
        )
        gaps = (
            [("missing", d, None) for d in result["missing_dates"]]
            + [("stub", row["date"], row["file"]) for row in result["stub_dates"]]
            + [("empty", row["date"], row["file"]) for row in result["empty_dates"]]
        )
        gaps.sort(key=lambda item: item[1])
        if gaps:
            print("gaps:")
            for kind, day, name in gaps[:40]:
                extra = f"  {name}" if name else ""
                print(f"  {day} {kind}{extra}")
            extra_n = (
                result["missing_dates_truncated"]
                + result["stub_dates_truncated"]
                + result["empty_dates_truncated"]
            )
            if extra_n:
                print(f"  … {extra_n} more")
        print(result["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
