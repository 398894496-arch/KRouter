#!/usr/bin/env python3
"""Mechanical vault gates. Read-only. Requires KROUTER_VAULT (or the older name OBSIDIAN_VAULT)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill/krouter-obsidian/scripts"))
import zones  # noqa: E402  区名按库自己的（krouter-zones.psv）

env = os.environ.get("KROUTER_VAULT") or os.environ.get("OBSIDIAN_VAULT")
if not env:
    raise SystemExit("set KROUTER_VAULT (or the older name OBSIDIAN_VAULT)")
VAULT = Path(env)
CLIPPINGS_LEDGER = zones.path(VAULT, "90 系统文件/Clippings 整理记录.json")
LOG_ROOT = zones.path(VAULT, "05 时间日志")
WIKI = re.compile(r"\[\[([^\]|#]+)")
SKIP_DIR = {"迁移备份", ".git", "KG机器资料", "冷层", ".obsidian"}
HUMAN_ROOTS = [zones.real(VAULT, x) for x in ("01 项目", "02 经验与方法", "03 资料与证据", "04 已完成与复盘", "05 时间日志",
                                               "90 系统文件")]


def parse_frontmatter(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("frontmatter not closed")
    return yaml.safe_load(text[4:end]) or {}, text


def walk_md() -> list[Path]:
    out = []
    roots = [VAULT / x for x in HUMAN_ROOTS if (VAULT / x).is_dir()]
    for base in roots:
        for root, dirs, files in os.walk(base):
            rp = Path(root)
            dirs[:] = [d for d in dirs if d not in SKIP_DIR and not (rp / d).is_symlink()]
            for name in files:
                if name.endswith(".md"):
                    p = rp / name
                    if not p.is_symlink():
                        out.append(p)
    return out


def wiki_index() -> set[str]:
    names = set()
    for p in walk_md():
        rel = p.relative_to(VAULT).as_posix()
        names.add(rel[:-3] if rel.endswith(".md") else rel)
        names.add(p.stem)
    return names


def check_yaml() -> dict:
    files = 0
    errors = []
    for p in walk_md():
        try:
            fm, _ = parse_frontmatter(p)
            if fm is not None:
                files += 1
        except Exception as e:
            errors.append(f"{p.relative_to(VAULT)}: {e}")
    return {"ok": not errors, "yaml_files": files, "errors": errors[:20], "error_count": len(errors)}


def check_clippings() -> dict:
    ledger = json.loads(CLIPPINGS_LEDGER.read_text(encoding="utf-8"))
    verified = 0
    mismatches = []
    missing = []
    for entry in ledger.get("entries", []):
        src = VAULT / entry["source"]
        if not src.exists():
            missing.append(entry["source"])
            continue
        digest = hashlib.sha256(src.read_bytes()).hexdigest()
        if digest == entry.get("sha256"):
            verified += 1
        else:
            mismatches.append(entry["source"])
    originals = list((VAULT / "Clippings").glob("*.md")) if (VAULT / "Clippings").is_dir() else []
    return {
        "ok": not mismatches and not missing and verified == len(ledger.get("entries", [])),
        "hash_verified": verified,
        "ledger_entries": len(ledger.get("entries", [])),
        "originals_on_disk": len(originals),
        "mismatches": mismatches,
        "missing": missing,
    }


def check_date_continuity(start: str, end: str) -> dict:
    sealed = {}
    for month_dir in LOG_ROOT.iterdir():
        if not month_dir.is_dir() or not month_dir.name[:4].isdigit():
            continue
        for p in month_dir.glob("[0-3][0-9]｜*.md"):
            if "待总结" in p.name:
                continue
            sealed[f"{month_dir.name}-{p.name[:2]}"] = p.name
    cur = date.fromisoformat(start)
    last = date.fromisoformat(end)
    missing = []
    while cur <= last:
        key = cur.isoformat()
        if key not in sealed:
            missing.append(key)
        cur += timedelta(days=1)
    expected = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    return {
        "ok": not missing,
        "expected_days": expected,
        "log_files": expected - len(missing),
        "missing_dates": missing,
    }


def check_links(changed: list[str]) -> dict:
    names = wiki_index()
    missing = []
    total = 0
    for rel in changed:
        path = VAULT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in WIKI.finditer(text):
            total += 1
            target = m.group(1).strip()
            if target.startswith("http") or target.startswith("file://"):
                continue
            stem = Path(target).name
            if target in names or stem in names:
                continue
            candidate = VAULT / target
            if candidate.exists() or (VAULT / f"{target}.md").exists():
                continue
            missing.append(f"{rel} -> {target}")
    return {"ok": not missing, "checked": total, "missing": missing[:30], "missing_count": len(missing)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--from-date", default="2026-01-01")
    p.add_argument("--through-date", default="2026-01-01")
    p.add_argument("--changed", nargs="*", default=[])
    args = p.parse_args()
    result = {
        "yaml": check_yaml(),
        "clippings_hash": check_clippings(),
        "date_continuity": check_date_continuity(args.from_date, args.through_date),
        "links": check_links(args.changed) if args.changed else {"ok": None, "skipped": True},
    }
    result["all_runnable_ok"] = all(
        result[k].get("ok") for k in ("yaml", "clippings_hash", "date_continuity")
    ) and (result["links"].get("ok") is not False)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["all_runnable_ok"] else 1)


if __name__ == "__main__":
    main()
