"""The daytime timer: runs `import_sessions.py --intraday` once per due slot (wall-clock time in one zone), catches up
the latest missed slot after sleep, and gives a failing slot one more try, not a storm."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "extras/host-daily-evolution/intraday_capture.py"
sys.path.insert(0, str(SCRIPT.parent))
import intraday_capture as ic  # noqa: E402

SH = ic.zone("Asia/Shanghai")  # 没有系统时区库的 Windows 上是固定 +8
SLOTS = ic.parse_slots("12:10,18:10")


def _at(h: int, m: int, day: int = 30) -> datetime:
    return datetime(2026, 10, day, h, m, tzinfo=SH)


def test_due_slot_is_the_latest_one_passed():
    assert ic.due_slot(_at(12, 9), SLOTS) == _at(18, 10, 29)
    assert ic.due_slot(_at(12, 10), SLOTS) == _at(12, 10)
    assert ic.due_slot(_at(23, 59), SLOTS) == _at(18, 10)


def test_a_slot_runs_once_and_a_missed_one_catches_up_once():
    slot, _ = ic.decide(_at(12, 15), SLOTS, {})
    assert slot == _at(12, 10)
    done = {"slot": _at(12, 10).isoformat(), "ok": True, "attempts": 1}
    assert ic.decide(_at(13, 15), SLOTS, done)[0] is None
    # 睡过了 18:10，22:40 醒来：只补 18:10 这一个
    assert ic.decide(_at(22, 40), SLOTS, done)[0] == _at(18, 10)


def test_a_failing_slot_gets_one_more_try():
    once = {"slot": _at(12, 10).isoformat(), "ok": False, "attempts": 1}
    assert ic.decide(_at(13, 10), SLOTS, once)[0] == _at(12, 10)
    twice = {**once, "attempts": 2}
    slot, why = ic.decide(_at(14, 10), SLOTS, twice)
    assert slot is None and "nightly" in why


def test_slots_follow_the_zone_not_the_machine_clock():
    # 同一个 UTC 时刻，机器在夏令时前后换了偏移，上海的槽位不变
    before = datetime(2026, 10, 31, 4, 15, tzinfo=timezone.utc).astimezone(SH)
    after = datetime(2026, 11, 2, 4, 15, tzinfo=timezone.utc).astimezone(SH)
    assert ic.due_slot(before, SLOTS).strftime("%H:%M") == ic.due_slot(after, SLOTS).strftime("%H:%M") == "12:10"


@pytest.fixture()
def fake(tmp_path):
    router = tmp_path / "router"
    router.mkdir()
    calls = tmp_path / "calls.txt"
    (router / "import_sessions.py").write_text(
        "import json, os, sys\n"
        f"open({str(calls)!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
        "code = int(os.environ.get('FAKE_EXIT', '0'))\n"
        "print(json.dumps({'import': 'dry-run' if '--dry-run' in sys.argv else 'done', 'pages': 3}))\n"
        "sys.exit(code)\n", encoding="utf-8")
    env = {**os.environ, "KROUTER_STATE_DIR": str(tmp_path / "state"), "KROUTER_ROUTER": str(router)}
    return {"env": env, "calls": calls, "state": tmp_path / "state"}


def _run(fake: dict, *args: str, **extra: str) -> tuple[int, dict]:
    res = subprocess.run([sys.executable, str(SCRIPT), *args], env={**fake["env"], **extra},
                         capture_output=True, text=True, timeout=60)
    return res.returncode, json.loads(res.stdout.strip().splitlines()[-1])


def test_run_calls_intraday_import_and_records_the_slot(fake):
    code, row = _run(fake, "--force")
    assert code == 0 and row["ok"] and row["import"]["pages"] == 3
    assert "--intraday" in fake["calls"].read_text(encoding="utf-8")
    st = json.loads((fake["state"] / "intraday.json").read_text(encoding="utf-8"))
    assert st["ok"] and st["attempts"] == 1
    log = (fake["state"] / "intraday.log").read_text(encoding="utf-8").splitlines()
    assert len(log) == 1 and json.loads(log[0])["ok"]


def test_dry_run_passes_dry_run_and_records_nothing(fake):
    code, row = _run(fake, "--force", "--dry-run")
    assert code == 0 and row["import"]["import"] == "dry-run"
    assert "--dry-run" in fake["calls"].read_text(encoding="utf-8")
    assert not (fake["state"] / "intraday.json").exists()


def test_failure_is_logged_with_exit_code(fake):
    code, row = _run(fake, "--force", FAKE_EXIT="1")
    assert code == 1 and row["ok"] is False
    st = json.loads((fake["state"] / "intraday.json").read_text(encoding="utf-8"))
    assert st["ok"] is False


def test_zone_falls_back_to_a_fixed_offset_without_a_tz_database(monkeypatch):
    def missing(name):
        raise ic.ZoneInfoNotFoundError(name)
    monkeypatch.setattr(ic, "ZoneInfo", missing)
    sh = ic.zone("Asia/Shanghai")
    assert datetime(2026, 11, 1, 4, 10, tzinfo=timezone.utc).astimezone(sh).strftime("%H:%M") == "12:10"
    with pytest.raises(SystemExit):
        ic.zone("America/New_York")  # has daylight saving: no fixed offset is right, so say what to install
