#!/usr/bin/env python3
"""Zone names are configurable: map the default layout onto a vault that already has its own.

The code speaks the default layout (`01 项目`, `02 经验与方法`, `03 资料与证据`, `04 已完成与复盘`,
`05 时间日志`, `90 系统文件`, `Agent第二大脑.md`). A vault with other names puts one file at its root,
`krouter-zones.psv`, one `default prefix|your prefix` per line, e.g.

    90 系统文件|System
    05 时间日志|Journal
    02 经验与方法|Methods
    Agent第二大脑.md|Home.md
    02 经验与方法/Agent/用户偏好与工作约束.md|Methods/Preferences.md

The longest matching prefix wins, on path-segment boundaries. `real()` turns a default path into the
vault's path; `canon()` turns a vault path back into the default one, so tiering and log detection
keep working on the default names. No file → identity. `KROUTER_ZONES` points at another file.

A row `@lang|en` says the vault speaks English: pages KRouter creates by name (correction candidates, session
excerpts' receipts) get English names. A new English vault is laid down with `zones_en.psv` (`lay_out()`), so it
has English folder and file names from the start; a vault with the default names keeps working unchanged.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

ZONES_FILE = "krouter-zones.psv"
_CACHE: dict[str, tuple[float, list[tuple[str, str]]]] = {}


def _file(vault: Path) -> Path:
    raw = os.environ.get("KROUTER_ZONES", "").strip()
    return Path(raw) if raw else Path(vault) / ZONES_FILE


def pairs(vault: Path | None) -> list[tuple[str, str]]:
    """[(default prefix, vault prefix)], longest default first. Cached per file mtime."""
    if vault is None:
        return []
    path = _file(vault)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return []
    key = str(path)
    if key in _CACHE and _CACHE[key][0] == mtime:
        return _CACHE[key][1]
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "|" not in line:
            continue
        default, mine = (x.strip().strip("/") for x in line.split("|", 1))
        if default and mine and not default.startswith("@"):
            out.append((default, mine))
    out.sort(key=lambda p: -len(p[0]))
    _CACHE[key] = (mtime, out)
    return out


def _swap(rel: str, table: list[tuple[str, str]]) -> str:
    rel = rel.replace("\\", "/")
    for src, dst in table:
        if rel == src or rel.startswith(src + "/"):
            return dst + rel[len(src):]
    return rel


def real(vault: Path | None, rel: str) -> str:
    """Default-layout path → this vault's path."""
    return _swap(rel, pairs(vault))


def canon(vault: Path | None, rel: str) -> str:
    """This vault's path → default-layout path (for tiering and log detection)."""
    table = sorted(((b, a) for a, b in pairs(vault)), key=lambda p: -len(p[0]))
    return _swap(rel, table)


def path(vault: Path, rel: str) -> Path:
    """Absolute path in this vault for a default-layout path."""
    return Path(vault) / real(vault, rel)


EN_TABLE = Path(__file__).with_name("zones_en.psv")


def lang(vault: Path | None) -> str:
    """`en` when the vault's zones file says `@lang|en`, else `zh` (the default layout's names are Chinese)."""
    if vault is None:
        return "zh"
    try:
        text = _file(vault).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "zh"
    for line in text.splitlines():
        key, _, val = line.partition("|")
        if key.strip() == "@lang":
            return "en" if val.strip().lower().startswith("en") else "zh"
    return "zh"


def _rows(table: Path) -> list[tuple[str, str]]:
    out = []
    for line in table.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith(("#", "@")) and "|" in line:
            a, b = (x.strip().strip("/") for x in line.split("|", 1))
            out.append((a, b))
    return sorted(out, key=lambda p: -len(p[0]))


def _rewrite(text: str, table: list[tuple[str, str]]) -> str:
    """Links and quoted paths in a template page, default names → this layout's (`[[90 系统文件/x]]`, `[[x]]`)."""
    pairs = []
    for a, b in table:
        pairs.append((a, b))
        if a.endswith(".md"):
            pairs.append((a[:-3], b[:-3]))
            pairs.append((Path(a).stem, Path(b).stem))
            pairs.append((Path(a).name, Path(b).name))
    for a, b in sorted(set(pairs), key=lambda p: -len(p[0])):
        text = text.replace(a, b)
    return text


def lay_out(template: Path, vault: Path, dry: bool = False, table: Path = EN_TABLE,
            alias_sample: Path | None = None) -> list[str]:
    """Copy the template into `vault` under the layout `table` names, never overwriting a file; rewrite links in
    the copied pages; write `krouter-zones.psv` and the alias table (`alias_sample`, paths mapped, aliases in other
    scripts dropped) when they are missing. Returns the vault-relative paths added."""
    rows = _rows(table)
    added = []
    for src in sorted(Path(template).rglob("*")):
        if not src.is_file() or src.name == ".DS_Store":
            continue
        rel = _swap(src.relative_to(template).as_posix(), rows)
        dst = Path(vault) / rel
        if dst.exists():
            continue
        added.append(rel)
        if dry:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix == ".md":
            dst.write_text(_rewrite(src.read_text(encoding="utf-8"), rows), encoding="utf-8")
        else:
            shutil.copy2(src, dst)
    zf = Path(vault) / ZONES_FILE
    if not zf.exists():
        added.append(ZONES_FILE)
        if not dry:
            zf.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(table, zf)
    if alias_sample is not None and Path(alias_sample).is_file():
        rel = _swap("90 系统文件/canonical_sources.psv", rows)
        dst = Path(vault) / rel
        if not dst.exists():
            added.append(rel)
            if not dry:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(map_aliases(Path(alias_sample).read_text(encoding="utf-8"), rows), encoding="utf-8")
    return added


CJK = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff01-\uff0f\uff1a-\uff20]")


def map_aliases(text: str, rows: list[tuple[str, str]]) -> str:
    """The sample alias table for this layout: source paths mapped; aliases written in Chinese dropped."""
    out = []
    for line in text.splitlines():
        parts = line.split("|")
        if len(parts) == 4 and not line.startswith("#"):
            parts[1] = ";".join(a for a in parts[1].split(";") if a and not CJK.search(a))
            parts[2] = _swap(parts[2], rows)
        out.append("|".join(parts))
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    """`zones.py real VAULT REL` prints the vault path for a default path (for the shell scripts);
    `zones.py lang VAULT` prints en or zh."""
    if len(argv) == 3 and argv[0] == "real":
        print(path(Path(argv[1]), argv[2]))
        return 0
    if len(argv) == 2 and argv[0] == "lang":
        print(lang(Path(argv[1])))
        return 0
    print("usage: zones.py real VAULT REL | zones.py lang VAULT", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
