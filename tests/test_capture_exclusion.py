"""Keeping sessions out of the vault (`#不记`, `--exclude-root`) and the daytime import (`--intraday`)."""

from __future__ import annotations

import json
import subprocess
import sys

from test_import_sessions import FOLDER, IMPORT, _jsonl, _pages, _run, _ts, env  # noqa: F401  env 是 fixture


def _session(root, name: str, days_ago: int, ask: str, cwd: str = "/work/shop"):
    ts = _ts(days_ago)
    rows = [
        {"type": "user", "entrypoint": "claude-desktop", "cwd": cwd, "timestamp": ts, "origin": {"kind": "human"},
         "message": {"role": "user", "content": ask}},
        {"type": "assistant", "entrypoint": "claude-desktop", "timestamp": ts,
         "message": {"content": [{"type": "text", "text": "定了：照这个办。"}]}},
    ]
    return _jsonl(root / "-work-shop" / f"{name}.jsonl", rows)


def test_marked_session_is_not_imported_and_its_old_page_goes(env):
    path = _session(env["claude"], "s-private", 0, "体检报告怎么看？")
    _session(env["claude"], "s-open", 0, "发版流程怎么定？")
    first = _run(env, "--days", "1")
    assert first["pages"] == 2 and len(_pages(env)) == 2
    rows = path.read_text(encoding="utf-8").splitlines()
    later = json.loads(rows[0])
    later["message"]["content"] = "这段 #不记"
    later["timestamp"] = _ts(0, 11)
    path.write_text("\n".join(rows + [json.dumps(later, ensure_ascii=False)]) + "\n", encoding="utf-8")
    second = _run(env, "--days", "1")
    assert second["kept_out"] == 1 and second["removed_kept_out"] == 1
    names = list(_pages(env))
    assert len(names) == 1 and "发版" in names[0]


def test_exclude_root_is_saved_with_consent(env, tmp_path):
    secret = tmp_path / "clients" / "acme"
    secret.mkdir(parents=True)
    _session(env["claude"], "s-acme", 0, "合同条款怎么改？", cwd=str(secret))
    _session(env["claude"], "s-shop", 0, "发版流程怎么定？")
    row = _run(env, "--consent", "--days", "1", "--exclude-root", str(tmp_path / "clients"))
    assert row["kept_out"] == 1 and row["pages"] == 1
    st = json.loads((tmp_path / "state" / "import.json").read_text(encoding="utf-8"))
    assert st["exclude_roots"] == [str((tmp_path / "clients").resolve())]
    again = _run(env, "--nightly")  # 夜间按同意时记下的名单
    assert again["import"] in ("done", "off")


def test_intraday_needs_consent(env):
    _session(env["claude"], "s1", 0, "发版流程怎么定？")
    row = _run(env, "--intraday")
    assert row["import"] == "off" and not _pages(env)


def test_intraday_covers_today_and_yesterday_only(env):
    _session(env["claude"], "s-today", 0, "今天的问题？")
    _session(env["claude"], "s-yday", 1, "昨天的问题？")
    _session(env["claude"], "s-old", 3, "三天前的问题？")
    _run(env, "--consent", "--days", "1")
    for p in (env["vault"] / FOLDER).glob("*.md"):
        p.unlink()
    row = _run(env, "--intraday")
    assert row["import"] == "done" and row["pages"] == 2
    assert not any("三天前" in name for name in _pages(env))


def test_help_lists_the_new_flags():
    out = subprocess.run([sys.executable, str(IMPORT), "--help"], capture_output=True, text=True, timeout=60).stdout
    assert "--intraday" in out and "--exclude-root" in out


def test_headless_run_inside_a_desktop_shell_is_not_imported(env):
    """`claude -p` run from a desktop session's shell inherits entrypoint=claude-desktop; no turn of it is human."""
    ts = _ts(0)
    rows = [{"type": "queue-operation", "operation": "enqueue", "timestamp": ts, "content": "只回复 OK"},
            {"type": "user", "entrypoint": "claude-desktop", "cwd": "/private/tmp", "timestamp": ts, "userType": "external",
             "message": {"role": "user", "content": "只回复 OK"}},
            {"type": "assistant", "entrypoint": "claude-desktop", "timestamp": ts,
             "message": {"content": [{"type": "text", "text": "OK"}]}}]
    _jsonl(env["claude"] / "-private-tmp" / "21f269cc-headless.jsonl", rows)
    _session(env["claude"], "s-real", 0, "发版流程怎么定？")
    row = _run(env, "--days", "1")
    assert row["pages"] == 1 and not any("只回复" in n for n in _pages(env))


def test_nightly_reads_a_done_import_as_ok_not_skipped():
    """`skipped_covered` in the import's summary is a count, not a skipped step."""
    sys.path.insert(0, str(IMPORT.parent))
    import nightly

    out = json.dumps({"import": "done", "pages": 9, "distilled": 8, "distill_failed": 0, "skipped_covered": 0})
    assert nightly.classify(0, out) == ("ok", "")
    failed = json.dumps({"import": "done", "pages": 3, "distilled": 0, "distill_failed": 3, "skipped_covered": 0})
    assert nightly.classify(0, failed)[0] == "partial"


def test_exclude_root_matches_by_path_parts_not_by_prefix():
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill/krouter/scripts"))
    from import_sessions import _within
    assert _within("/work/clients/acme", "/work/clients") and _within("/work/clients", "/work/clients")
    assert not _within("/work/clients-old/acme", "/work/clients")  # a longer name is another folder

