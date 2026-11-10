#!/usr/bin/env python3
"""Ask-as-product: at most one provisional method per utterance.

record does not write active. promote does, after adopt + this task accepted.
Triggers live on the page (triggers: a; b) or in vault
90 系统文件/自动化/ask-triggers.json. Longest substring wins.
^foo is whole-query exact. Two pages at the same length refuse.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKIP_STATUS = {
    "rejected",
    "superseded",
    "superseded-promoted",
    "provisional-index",
    "active",
}
SKIP_STEMS = {"准经验入口", "Provisional index"}
PROV_REL = Path("02 经验与方法") / "准经验"
LEDGER_REL = Path("90 系统文件") / "自动化" / "ask-ledger.jsonl"
SIDECAR_REL = Path("90 系统文件") / "自动化" / "ask-triggers.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import zones as _zones  # noqa: E402

PENDING = Path.home() / ".dsh-krouter-ask-pending.json"


def vault_root() -> Path:
    raw = os.environ.get("KROUTER_VAULT") or os.environ.get("OBSIDIAN_VAULT") or ""
    if not raw:
        raise SystemExit("set KROUTER_VAULT (or OBSIDIAN_VAULT) to your memory folder")
    return Path(raw).expanduser().resolve()


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    meta: dict[str, str] = {}
    for raw in parts[1].splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        name, val = line.split(":", 1)
        meta[name.strip()] = val.strip().strip('"').strip("'")
    return meta


def _split_triggers(raw: str) -> list[str]:
    return [p.strip() for p in re.split(r"[;；]", raw) if p.strip()]


def load_sidecar(vault: Path) -> dict[str, list[str]]:
    path = _zones.path(vault, SIDECAR_REL.as_posix())
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    out: dict[str, list[str]] = {}
    if not isinstance(raw, dict):
        return {}
    for key, val in raw.items():
        if isinstance(val, list):
            out[str(key)] = [str(t).strip() for t in val if str(t).strip()]
    return out


def load_catalog(vault: Path | None = None) -> list[dict]:
    vault = vault or vault_root()
    sidecar = load_sidecar(vault)
    folder = _zones.path(vault, PROV_REL.as_posix())
    out: list[dict] = []
    if not folder.is_dir():
        return out
    for path in sorted(folder.glob("*.md")):
        if path.stem in SKIP_STEMS:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")[:4000]
        meta = _frontmatter(text)
        status = meta.get("status") or ""
        if status in SKIP_STATUS or status.startswith("superseded"):
            continue
        triggers = _split_triggers(meta.get("triggers") or "")
        for extra in sidecar.get(path.name, []):
            if extra not in triggers:
                triggers.append(extra)
        out.append(
            {
                "file": path.name,
                "title": meta.get("title") or path.stem,
                "next_ask": meta.get("next_ask") or "",
                "status": status,
                "triggers": triggers,
            }
        )
    return out


def coverage(catalog: list[dict] | None = None) -> dict:
    catalog = catalog if catalog is not None else load_catalog()
    missing = [i["file"] for i in catalog if not i["triggers"]]
    return {
        "provisional_n": len(catalog),
        "with_triggers": len(catalog) - len(missing),
        "missing": missing,
        "ok": not missing,
    }


def _trigger_hit(query: str, trig: str) -> tuple[bool, int]:
    q = query.strip()
    qlow = q.lower()
    t = trig.strip()
    if not t:
        return False, 0
    if t.startswith("^"):
        exact = t[1:].strip()
        if q == exact or qlow == exact.lower():
            return True, 1000 + len(exact)
        return False, 0
    if t.lower() in qlow or t in q:
        return True, len(t)
    return False, 0


def match_trigger(query: str, catalog: list[dict]) -> dict:
    hits: list[tuple[int, str, dict, str]] = []
    for item in catalog:
        for trig in item["triggers"]:
            ok, weight = _trigger_hit(query, trig)
            if ok:
                hits.append((weight, item["file"], item, trig))
    if not hits:
        return {"ask": None, "reason": "trigger-miss", "trigger": None}
    hits.sort(key=lambda x: (-x[0], x[1]))
    best_len = hits[0][0]
    pages = []
    seen: set[str] = set()
    for h in hits:
        if h[0] != best_len:
            continue
        if h[1] not in seen:
            seen.add(h[1])
            pages.append(h)
    if len(pages) > 1:
        return {
            "ask": None,
            "reason": "trigger-ambiguous",
            "candidates": [p[1] for p in pages],
        }
    item = pages[0][2]
    prompt = item["next_ask"] or f"Adopt this provisional method: {item['title']}?"
    return {
        "ask": item["file"],
        "title": item["title"],
        "next_ask": item["next_ask"],
        "reason": "trigger-hit",
        "trigger": pages[0][3],
        "prompt": prompt,
    }


def _ledger_path(vault: Path) -> Path:
    return _zones.path(vault, LEDGER_REL.as_posix())


def append_ledger(vault: Path, row: dict) -> None:
    path = _ledger_path(vault)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = dict(row)
    row.setdefault("at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_ledger(vault: Path) -> list[dict]:
    path = _ledger_path(vault)
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def already_asked(vault: Path, filename: str, within_hours: int = 24) -> bool:
    if not filename:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(hours=within_hours)
    asked = False
    for row in _read_ledger(vault):
        at = row.get("at") or ""
        try:
            ts = datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if ts < cutoff:
            continue
        if row.get("kind") == "ask" and row.get("ask") == filename:
            asked = True
        if row.get("kind") == "record" and row.get("file") == filename:
            asked = False
    return asked


def last_decision(vault: Path, filename: str) -> str | None:
    for row in reversed(_read_ledger(vault)):
        if row.get("file") != filename:
            continue
        if row.get("kind") == "promote":
            return "promoted"
        if row.get("kind") == "record":
            return row.get("decision")
    return None


def patch_status(path: Path, new_status: str) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path.name} has no frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{path.name} has no frontmatter end")
    head = parts[1].lstrip("\n")
    body = parts[2].lstrip("\n")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if re.search(r"^status:", head, re.M):
        head = re.sub(r"^status:.*$", f"status: {new_status}", head, count=1, flags=re.M)
    else:
        head = f"status: {new_status}\n" + head
    if re.search(r"^verified_at:", head, re.M):
        head = re.sub(r"^verified_at:.*$", f"verified_at: {today}", head, count=1, flags=re.M)
    else:
        head = head.rstrip() + f"\nverified_at: {today}\n"
    path.write_text("---\n" + head.rstrip() + "\n---\n" + body, encoding="utf-8")
    return new_status


def promote(vault: Path, filename: str) -> dict:
    name = Path(filename).name
    if not name.endswith(".md"):
        name = name + ".md"
    decision = last_decision(vault, name)
    if decision != "adopt":
        return {"file": name, "active": False, "reason": "need-adopt-first", "last_decision": decision}
    path = _zones.path(vault, PROV_REL.as_posix()) / name
    if not path.is_file():
        return {"file": name, "active": False, "reason": "missing-page"}
    meta = _frontmatter(path.read_text(encoding="utf-8", errors="replace")[:4000])
    status = meta.get("status") or ""
    if status == "active":
        return {"file": name, "active": True, "reason": "already-active"}
    if status in SKIP_STATUS or status.startswith("superseded"):
        return {"file": name, "active": False, "reason": "not-provisional", "status": status}
    patch_status(path, "active")
    append_ledger(
        vault,
        {"kind": "promote", "file": name, "decision": "adopt", "adopt": "adopt", "active": True},
    )
    return {"file": name, "active": True, "reason": "promoted"}


def ask_once(
    query: str,
    catalog: list[dict],
    vault: Path,
    *,
    skip_repeat: bool = True,
) -> dict:
    trig = match_trigger(query, catalog)
    if skip_repeat and trig.get("ask") and already_asked(vault, trig["ask"]):
        trig = {
            "ask": None,
            "reason": "already-asked",
            "previous": trig.get("ask"),
            "title": trig.get("title"),
        }
    return {"query": query, "trigger": trig}


def write_pending(result: dict) -> None:
    PENDING.parent.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def hook_from_payload(payload: dict, catalog: list[dict], vault: Path) -> dict:
    prompt = str(
        payload.get("prompt")
        or payload.get("text")
        or payload.get("content")
        or ""
    )
    result = ask_once(prompt, catalog, vault, skip_repeat=True)
    result["kind"] = "hook"
    write_pending(result)
    append_ledger(
        vault,
        {
            "kind": "ask",
            "query": prompt[:500],
            "ask": result["trigger"].get("ask"),
            "reason": result["trigger"].get("reason"),
            "source": "hook",
        },
    )
    return {"continue": True}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["ask", "coverage", "record", "hook", "promote"])
    p.add_argument("--query", default="")
    p.add_argument("--out", default="")
    p.add_argument("--file", default="")
    p.add_argument("--decision", default="", help="adopt|reject|defer")
    p.add_argument("--no-skip", action="store_true")
    args = p.parse_args()
    vault = vault_root()
    catalog = load_catalog(vault)
    if args.cmd == "coverage":
        out = coverage(catalog)
        if not out["ok"]:
            print(json.dumps(out, ensure_ascii=False, indent=2))
            sys.exit(1)
    elif args.cmd == "record":
        if not args.file or args.decision not in {"adopt", "reject", "defer"}:
            raise SystemExit("record needs --file NAME.md --decision adopt|reject|defer")
        name = Path(args.file).name
        out = {"file": name, "decision": args.decision, "active": False}
        append_ledger(
            vault,
            {
                "kind": "record",
                "file": name,
                "decision": args.decision,
                "adopt": args.decision,
            },
        )
    elif args.cmd == "promote":
        if not args.file:
            raise SystemExit("promote needs --file NAME.md")
        out = promote(vault, args.file)
        if not out.get("active"):
            print(json.dumps(out, ensure_ascii=False, indent=2))
            sys.exit(1)
    elif args.cmd == "hook":
        try:
            payload = json.load(sys.stdin)
        except Exception:
            payload = {}
        out = hook_from_payload(
            payload if isinstance(payload, dict) else {},
            catalog,
            vault,
        )
    else:
        out = ask_once(
            args.query,
            catalog,
            vault,
            skip_repeat=not args.no_skip,
        )
        write_pending(out)
        append_ledger(
            vault,
            {
                "kind": "ask",
                "query": args.query[:500],
                "ask": out["trigger"].get("ask"),
                "reason": out["trigger"].get("reason"),
                "adopt": None,
            },
        )
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
