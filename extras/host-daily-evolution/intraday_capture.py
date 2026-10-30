#!/usr/bin/env python3
"""Daytime capture: import and distill today's agent sessions at a few fixed times, on top of the nightly job.

A timer (launchd `StartInterval`, cron, systemd) runs this every hour; it does the work only when a slot is due.
Slots are wall-clock times in one time zone (default `12:10,18:10` in `Asia/Shanghai`), so a daylight-saving change on
the machine does not move them, and a machine that slept through a slot runs it once on the next tick after it wakes
(only the latest missed slot, never a backlog). A slot that failed is tried once more on the next tick, then left to
the nightly job: no retry storm.

The work is `import_sessions.py --intraday`: nothing happens before you said yes to importing (`--consent`), the
lane and the distill choice are the ones recorded then, and only turns added since a page was last distilled are sent.

    python3 intraday_capture.py --dry-run        # is a slot due, and what would the import send (sends nothing)
    python3 intraday_capture.py                  # what the timer runs

State and log: `~/.local/state/krouter/intraday.json` and `intraday.log` (or `KROUTER_STATE_DIR`). The log holds the
importer's one-line summary per run (counts, page names), never session text.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SLOTS = "12:10,18:10"
TZ = "Asia/Shanghai"
ATTEMPTS = 2           # 一个槽位最多跑几次（失败后下一次整点再试一次）
RUN_TIMEOUT = 45 * 60  # 一次导入加提炼最多跑多久


def state_dir() -> Path:
    return Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local/state/krouter")


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def parse_slots(text: str) -> list[tuple[int, int]]:
    out = []
    for part in text.split(","):
        h, m = part.strip().split(":")
        out.append((int(h), int(m)))
    return sorted(out)


def due_slot(now: datetime, slots: list[tuple[int, int]]) -> datetime | None:
    """The latest slot at or before `now` (today's, else yesterday's last one)."""
    today = [now.replace(hour=h, minute=m, second=0, microsecond=0) for h, m in slots]
    past = [s for s in today if s <= now]
    if past:
        return past[-1]
    h, m = slots[-1]
    return (now - timedelta(days=1)).replace(hour=h, minute=m, second=0, microsecond=0)


def decide(now: datetime, slots: list[tuple[int, int]], st: dict) -> tuple[datetime | None, str]:
    """(slot to run, why) — slot is None when there is nothing to do."""
    slot = due_slot(now, slots)
    if slot is None:
        return None, "no slot"
    key = slot.isoformat()
    if st.get("slot") == key:
        if st.get("ok"):
            return None, f"slot {key} already ran"
        if int(st.get("attempts", 0)) >= ATTEMPTS:
            return None, f"slot {key} failed {st.get('attempts')} times; left to the nightly job"
    return slot, f"slot {key} due"


def router_dir(arg: str) -> Path:
    if arg:
        return Path(arg).expanduser()
    env = os.environ.get("KROUTER_ROUTER")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".agents/skills/krouter-obsidian/scripts"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--slots", default=os.environ.get("KROUTER_INTRADAY_SLOTS", SLOTS), help=f"default {SLOTS}")
    ap.add_argument("--tz", default=os.environ.get("KROUTER_INTRADAY_TZ", TZ), help=f"default {TZ}")
    ap.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT", ""))
    ap.add_argument("--router", default="", help="the krouter-obsidian scripts folder (default: the installed skill)")
    ap.add_argument("--dry-run", action="store_true", help="say whether a slot is due and what the import would send")
    ap.add_argument("--force", action="store_true", help="run now even when no slot is due")
    args = ap.parse_args()

    now = datetime.now(ZoneInfo(args.tz))
    sdir = state_dir()
    state_path, log_path = sdir / "intraday.json", sdir / "intraday.log"
    st = load(state_path)
    slot, why = decide(now, parse_slots(args.slots), st)
    if args.force:
        slot, why = now.replace(second=0, microsecond=0), "forced"
    row: dict = {"at": now.isoformat(timespec="seconds"), "decision": why}
    if slot is None:
        print(json.dumps(row, ensure_ascii=False))
        return 0

    script = router_dir(args.router) / "import_sessions.py"
    argv = [sys.executable, str(script), "--intraday"] + (["--vault", args.vault] if args.vault else [])
    if args.dry_run:
        argv.append("--dry-run")
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=RUN_TIMEOUT, stdin=subprocess.DEVNULL,
                              env={**os.environ, "KROUTER_NO_QUERY_LOG": "1"})
        ok = proc.returncode == 0
        last = (proc.stdout.strip().splitlines() or [""])[-1]
        try:
            row["import"] = json.loads(last)
        except ValueError:
            row["import"] = last[:300]
        if not ok:
            row["error"] = (proc.stderr.strip().splitlines() or [""])[-1][:300]
    except (OSError, subprocess.TimeoutExpired) as exc:
        ok = False
        row["error"] = str(exc)[:300]
    row["ok"] = ok
    if not args.dry_run:
        key = slot.isoformat()
        attempts = int(st.get("attempts", 0)) + 1 if st.get("slot") == key else 1
        sdir.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({"slot": key, "ok": ok, "attempts": attempts, "at": row["at"]},
                                         ensure_ascii=False) + "\n", encoding="utf-8")
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps(row, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
