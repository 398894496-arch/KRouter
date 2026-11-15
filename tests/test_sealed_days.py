import os
from datetime import date

import pytest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_sealed_days import measure  # noqa: E402


def _write_day(root: Path, day: date, name: str, body: str, status: str = "active") -> None:
    month = root / "05 时间日志" / day.strftime("%Y-%m")
    month.mkdir(parents=True, exist_ok=True)
    (month / f"{day.strftime('%d')}｜{name}.md").write_text(
        f"---\ntitle: {name}\nstatus: {status}\n---\n\n{body}\n",
        encoding="utf-8",
    )


def test_template_has_one_sealed_sample_day():
    result = measure(ROOT / "template")
    assert result["sealed"] == 1
    assert result["longest_streak"] == 1
    assert result["from_date"] == "2026-01-01"
    assert result["through_date"] == "2026-01-01"
    assert result["missing"] == 0
    assert "does not verify" in result["note"].lower()


def test_streak_and_gaps(tmp_path: Path):
    vault = tmp_path / "vault"
    _write_day(vault, date(2026, 6, 10), "one", "sealed one")
    _write_day(vault, date(2026, 6, 11), "two", "sealed two")
    _write_day(vault, date(2026, 6, 12), "three", "sealed three")
    _write_day(vault, date(2026, 6, 14), "待总结", "left a gap", status="to-summarize")
    empty_month = vault / "05 时间日志" / "2026-06"
    (empty_month / "15｜empty.md").write_text("---\nstatus: active\n---\n\n", encoding="utf-8")
    (vault / "05 时间日志" / "时间日志入口.md").write_text("# index\n", encoding="utf-8")

    result = measure(vault, date(2026, 6, 10), date(2026, 6, 15))
    assert result["sealed"] == 3
    assert result["longest_streak"] == 3
    assert result["longest_streak_from"] == "2026-06-10"
    assert result["longest_streak_through"] == "2026-06-12"
    assert result["missing"] == 1
    assert result["missing_dates"] == ["2026-06-13"]
    assert result["stub"] == 1
    assert result["empty"] == 1
    assert result["current_streak_through_end"] == 0


def test_real_note_beats_stub_on_same_day(tmp_path: Path):
    vault = tmp_path / "vault"
    month = vault / "05 时间日志" / "2026-07"
    month.mkdir(parents=True)
    (month / "01｜待总结.md").write_text("---\nstatus: to-summarize\n---\n\nstub\n", encoding="utf-8")
    (month / "01｜actual.md").write_text("---\nstatus: active\n---\n\nreal note\n", encoding="utf-8")
    result = measure(vault)
    assert result["sealed"] == 1
    assert result["stub"] == 0


def test_longest_streak_stays_inside_window(tmp_path: Path):
    vault = tmp_path / "vault"
    _write_day(vault, date(2026, 5, 1), "early-a", "a")
    _write_day(vault, date(2026, 5, 2), "early-b", "b")
    _write_day(vault, date(2026, 5, 3), "early-c", "c")
    _write_day(vault, date(2026, 6, 10), "late-a", "a")
    _write_day(vault, date(2026, 6, 11), "late-b", "b")
    result = measure(vault, date(2026, 6, 10), date(2026, 6, 11))
    assert result["sealed"] == 2
    assert result["longest_streak"] == 2
    assert result["longest_streak_from"] == "2026-06-10"


@pytest.mark.skipif(os.name == "nt", reason="'|' is not allowed in Windows file names")
def test_ascii_pipe_filename_counts(tmp_path: Path):
    vault = tmp_path / "vault"
    month = vault / "05 时间日志" / "2026-08"
    month.mkdir(parents=True)
    (month / "21|ascii-pipe.md").write_text(
        "---\nstatus: active\n---\n\nsealed via ascii pipe\n",
        encoding="utf-8",
    )
    result = measure(vault)
    assert result["sealed"] == 1
