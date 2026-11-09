"""Day-one value: agent sessions already on the machine become vault pages — local, redacted, never someone's own page."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter-obsidian/scripts"
IMPORT = SCRIPTS / "import_sessions.py"
FOLDER = "05 时间日志/会话摘录"
KEY = "sk-" + "Abc123XyZ" * 4


def _ts(days_ago: int, hour: int = 10) -> str:
    day = datetime.now().astimezone() - timedelta(days=days_ago)
    return day.replace(hour=hour, minute=5, second=0, microsecond=0).astimezone(timezone.utc).isoformat()


def _jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return path


def _claude_session(root: Path, name: str, days_ago: int, entry: str = "claude-desktop", title: str = "") -> Path:
    ts = _ts(days_ago)
    rows = [
        {"type": "user", "entrypoint": entry, "cwd": "/work/shop", "timestamp": ts, "origin": {"kind": "human"},
         "message": {"role": "user", "content": "发版流程怎么定？key 是 " + KEY}},
        {"type": "user", "entrypoint": entry, "timestamp": ts, "isMeta": True,
         "message": {"role": "user", "content": "<command-name>/clear</command-name>"}},
        {"type": "assistant", "entrypoint": entry, "timestamp": ts,
         "message": {"content": [{"type": "thinking", "thinking": "secret plan"}, {"type": "tool_use", "name": "Bash"}]}},
        {"type": "user", "entrypoint": entry, "timestamp": ts,
         "message": {"content": [{"type": "tool_result", "content": "tool output here"}]}},
        {"type": "assistant", "entrypoint": entry, "timestamp": ts,
         "message": {"content": [{"type": "text", "text": "定了：发版只从 main 打 tag。"}]}},
        {"type": "user", "entrypoint": entry, "timestamp": ts, "isSidechain": True,
         "message": {"role": "user", "content": "subagent prompt"}},
        {"type": "user", "entrypoint": entry, "timestamp": ts, "origin": {"kind": "task-notification"},
         "message": {"role": "user", "content": "background task finished"}},
    ]
    if title:
        rows.append({"type": "custom-title", "customTitle": title})
    return _jsonl(root / "-work-shop" / f"{name}.jsonl", rows)


def _codex_session(root: Path, days_ago: int, originator: str = "codex_cli_rs") -> Path:
    ts = _ts(days_ago, 15)
    day = datetime.now().astimezone() - timedelta(days=days_ago)
    rows = [
        {"type": "session_meta", "timestamp": ts, "payload": {"id": "019a-codex-0001", "cwd": "/work/api", "originator": originator}},
        {"type": "response_item", "timestamp": ts, "payload": {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "<environment_context>cwd</environment_context>"},
            {"type": "input_text", "text": "缓存过期时间改成多少？"}]}},
        {"type": "response_item", "timestamp": ts, "payload": {"type": "function_call", "name": "shell"}},
        {"type": "response_item", "timestamp": ts, "payload": {"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": "原来 30 分钟，改成 10 分钟。"}]}},
    ]
    return _jsonl(root / day.strftime("%Y/%m/%d") / f"rollout-{originator}.jsonl", rows)


def _cursor_ask(days_ago: int, hour: int, text: str) -> str:
    """A Cursor question as Cursor writes it: local time with its UTC offset, the question in `<user_query>`."""
    local = (datetime.now().astimezone() - timedelta(days=days_ago)).replace(hour=hour, minute=7, second=0, microsecond=0)
    off = local.utcoffset() or timedelta(0)
    sign, mins = ("-" if off < timedelta(0) else "+"), abs(int(off.total_seconds() // 60))
    stamp = local.strftime("%A, %b %-d, %Y, %-I:%M %p") if os.name != "nt" else local.strftime("%A, %b %d, %Y, %I:%M %p")
    tz = f"(UTC{sign}{mins // 60}" + (f":{mins % 60:02d})" if mins % 60 else ")")
    return f"<timestamp>{stamp} {tz}</timestamp>\n<image_files>shot.png</image_files>\n<user_query>\n{text}\n</user_query>"


def _cursor_session(root: Path, project_dir: Path, days_ago: int) -> Path:
    slug = "-".join(p for p in project_dir.parts if p not in ("/", "\\") and not p.endswith(":\\"))
    sid = "c0ffee00-1111-2222-3333-444455556666"
    rows = [
        {"role": "user", "message": {"content": [{"type": "text", "text": _cursor_ask(days_ago, 9, "日志级别怎么定？token " + KEY)}]}},
        {"role": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"path": "x"}}]}},
        {"role": "assistant", "message": {"content": [{"type": "text", "text": "先看看配置。"}]}},
        {"role": "assistant", "message": {"content": [{"type": "text", "text": "定了：生产环境 info，debug 只在开关后面。"}]}},
        {"type": "turn_ended", "status": "success"},
    ]
    _jsonl(root / slug / "agent-transcripts" / sid / "subagents" / "sub.jsonl",
           [{"role": "user", "message": {"content": [{"type": "text", "text": "subagent prompt"}]}}])
    return _jsonl(root / slug / "agent-transcripts" / sid / f"{sid}.jsonl", rows)


@pytest.fixture()
def env(tmp_path):
    vault = tmp_path / "vault"
    (vault / "05 时间日志").mkdir(parents=True)
    claude, codex, cursor = tmp_path / "claude", tmp_path / "codex", tmp_path / "cursor"
    e = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_CLAUDE_PROJECTS": str(claude),
         "KROUTER_CODEX_SESSIONS": str(codex), "KROUTER_CURSOR_PROJECTS": str(cursor),
         "KROUTER_STATE_DIR": str(tmp_path / "state"), "KROUTER_NO_QUERY_LOG": "1"}
    return {"vault": vault, "claude": claude, "codex": codex, "cursor": cursor, "env": e}


def _run(env: dict, *args: str) -> dict:
    res = subprocess.run([sys.executable, str(IMPORT), *args], env=env["env"], capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stdout + res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


def _pages(env: dict) -> dict[str, str]:
    folder = env["vault"] / FOLDER
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(folder.glob("*.md"))} if folder.is_dir() else {}


def test_import_keeps_asks_and_closing_answers_only_and_redacts(env):
    _claude_session(env["claude"], "aaaa1111-s", 1, title="发版流程")
    _codex_session(env["codex"], 2)
    _claude_session(env["claude"], "bbbb2222-headless", 1, entry="sdk-cli")  # 夜间任务自己的 claude -p
    _codex_session(env["codex"], 1, originator="codex_exec")
    out = _run(env, "--days", "7")
    assert out["pages"] == 2 and out["agents"] == ["claude-code", "codex"] and out["chars"] == 0
    pages = _pages(env)
    claude_page = next(v for k, v in pages.items() if "发版流程" in k)
    assert "source: krouter-import" in claude_page and "title: 发版流程" in claude_page
    assert "发版流程怎么定" in claude_page and "定了：发版只从 main 打 tag。" in claude_page
    assert KEY not in claude_page and "<redacted>" in claude_page
    for noise in ("secret plan", "tool output here", "subagent prompt", "background task", "/clear"):
        assert noise not in claude_page
    codex_page = next(v for k, v in pages.items() if "缓存过期" in k)
    assert "原来 30 分钟，改成 10 分钟。" in codex_page and "environment_context" not in codex_page


def test_cursor_sessions_import_with_their_own_time_and_project(env, tmp_path):
    project = tmp_path / "work" / "log-svc"
    project.mkdir(parents=True)
    _cursor_session(env["cursor"], project, 2)
    out = _run(env, "--days", "7")
    assert out["pages"] == 1 and out["agents"] == ["cursor"]
    name, page = next(iter(_pages(env).items()))
    day = (datetime.now().astimezone() - timedelta(days=2)).date().isoformat()
    assert name.startswith(day) and "日志级别怎么定" in name  # 日子取自 <timestamp>，不是文件时间
    assert "agent: cursor" in page and "（09:07）" in page
    assert "定了：生产环境 info，debug 只在开关后面。" in page and "先看看配置" not in page
    assert KEY not in page and "<redacted>" in page
    for noise in ("<user_query>", "<timestamp>", "image_files", "subagent prompt"):
        assert noise not in page
    if os.name != "nt":  # 目录名里的 `-` 有歧义：按磁盘上真实存在的路径还原
        assert "project: log-svc" in page


def test_cursor_timestamp_parsing():
    sys.path.insert(0, str(SCRIPTS))
    import import_sessions as imp

    assert imp._cursor_ts("<timestamp>Wednesday, Oct 8, 2026, 10:42 PM (UTC-7)</timestamp>") == "2026-10-09T05:42:00.000Z"
    assert imp._cursor_ts("<timestamp>Monday, Jan 05, 2026, 12:03 AM (UTC+5:30)</timestamp>") == "2026-01-04T18:33:00.000Z"
    assert imp._cursor_ts("no stamp here") == ""


def test_dry_run_writes_nothing_and_foreign_pages_are_never_touched(env):
    _claude_session(env["claude"], "aaaa1111-s", 1, title="发版流程")
    out = _run(env, "--dry-run")
    assert out["import"] == "dry-run" and out["pages"] == 1 and not (env["vault"] / FOLDER).exists()
    _run(env)
    name = next(iter(_pages(env)))
    mine = env["vault"] / FOLDER / name
    mine.write_text("# my own notes\n", encoding="utf-8")  # 宿主把这页改成了自己的
    again = _run(env)
    assert again["kept_foreign"] == [name] and mine.read_text(encoding="utf-8") == "# my own notes\n"


def test_renamed_session_replaces_its_page(env):
    path = _claude_session(env["claude"], "aaaa1111-s", 1)
    _run(env)
    assert len(_pages(env)) == 1
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "custom-title", "customTitle": "新标题"}, ensure_ascii=False) + "\n")
    _run(env)
    names = list(_pages(env))
    assert len(names) == 1 and "新标题" in names[0]


def test_nightly_imports_only_after_consent(env):
    _claude_session(env["claude"], "aaaa1111-s", 1, title="昨天")
    off = _run(env, "--nightly")
    assert off["import"] == "off" and not _pages(env)
    _run(env, "--consent", "--dry-run")  # dry-run 不记同意
    assert _run(env, "--nightly")["import"] == "off"
    _run(env, "--consent", "--days", "1")
    on = _run(env, "--nightly")
    assert on["import"] == "done" and on["pages"] == 1
    _run(env, "--revoke")
    assert _run(env, "--nightly")["import"] == "off"


def test_distill_puts_decisions_on_top_and_keeps_them(env, monkeypatch):
    path = _claude_session(env["claude"], "aaaa1111-s", 1, title="发版流程")
    ts = _ts(1, 11)
    with path.open("a", encoding="utf-8") as fh:  # 一轮的会话不提炼：至少两轮
        fh.write(json.dumps({"type": "user", "timestamp": ts, "message": {"role": "user", "content": "那就这么定"}}) + "\n")
    sys.path.insert(0, str(SCRIPTS))
    import import_sessions as imp
    import llm

    sent = []
    monkeypatch.setattr(llm, "complete", lambda prompt, vault=None: sent.append(prompt) or
                        "好的：\n- 发版只从 main 打 tag（10:05）\n- 原来手动发 → 改成 CI 发（10:05）\n总结完毕")
    for k in ("OBSIDIAN_VAULT", "KROUTER_CLAUDE_PROJECTS", "KROUTER_CODEX_SESSIONS", "KROUTER_CURSOR_PROJECTS",
              "KROUTER_STATE_DIR"):
        monkeypatch.setenv(k, env["env"][k])
    monkeypatch.setattr(sys, "argv", ["import_sessions.py", "--distill"])
    assert imp.main() == 0
    page = next(iter(_pages(env).values()))
    calls = len(sent)  # 每段一次，外加整段找改主意的一次
    assert calls == 2 and not any(KEY in p for p in sent)  # 发出去的也是脱敏后的
    assert "## 定了什么、改了什么" in page and "- 发版只从 main 打 tag（10:05）" in page and "总结完毕" not in page
    digest = page.split("## 定了什么、改了什么", 1)[1].split("\n## ", 1)[0]
    assert digest.count("原来手动发 → 改成 CI 发") == 1  # 两遍都找到的同一次改主意只留一条
    assert "how: 原来手动发 → 改成 CI 发（10:05）" in page  # 改主意的排在最前
    monkeypatch.setattr(sys, "argv", ["import_sessions.py", "--distill"])
    assert imp.main() == 0 and len(sent) == calls  # 会话没变：不重复提炼，也不丢掉已有的提炼


def test_imported_page_answers_a_question_through_the_router(env, tmp_path):
    vault = env["vault"]
    import shutil

    shutil.rmtree(vault)
    shutil.copytree(REPO / "template-zh", vault)
    _claude_session(env["claude"], "aaaa1111-s", 1, title="发版流程")
    _run(env)
    res = subprocess.run([sys.executable, str(SCRIPTS / "route_knowledge.py"), "search", "发版只从 main 打 tag 吗"],
                         env={**env["env"], "KROUTER_CACHE_DIR": str(tmp_path / "cache")},
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    assert "05 时间日志/会话摘录/" in res.stdout.split("recall:", 1)[1].splitlines()[1]


def test_long_sessions_are_distilled_in_segments():
    sys.path.insert(0, str(SCRIPTS))
    import import_sessions as imp

    turn = "- **问**（10:{:02d}）：问题 {}\n  **答**：" + "回答内容。" * 400 + "\n"
    body = "".join(turn.format(i, i) for i in range(10))
    parts = imp.segments(body)
    assert len(parts) > 1 and "".join(parts) == body  # 按轮切开，不丢内容
    assert all(p.startswith("- **问**") for p in parts)
    lines = ["- （这段会话没有定下来的事）", "- 发版只从 main 打 tag（10:05）", "- 原来手动发 → 改成 CI 发（10:06）",
             "- 原来是手动发版 → 改成用 CI 发版（10:06）", "- 日志级别用 info（10:07）"]
    assert imp.merge_digest(lines) == ["- 原来手动发 → 改成 CI 发（10:06）", "- 发版只从 main 打 tag（10:05）",
                                       "- 日志级别用 info（10:07）"]


def _claude_turns(root: Path, sid: str, turns: list[tuple[str, str, str]]) -> Path:
    """A Claude Code transcript of (timestamp, question, answer) turns."""
    rows = []
    for ts, ask, answer in turns:
        rows.append({"type": "user", "entrypoint": "claude-desktop", "cwd": "/work/shop", "timestamp": ts,
                     "origin": {"kind": "human"}, "message": {"role": "user", "content": ask}})
        rows.append({"type": "assistant", "entrypoint": "claude-desktop", "timestamp": ts,
                     "message": {"content": [{"type": "text", "text": answer}]}})
    return _jsonl(root / "-work-shop" / f"{sid}.jsonl", rows)


def _meta(page: str) -> dict[str, str]:
    head = page.split("\n---", 1)[0]
    return dict(line.split(": ", 1) for line in head.splitlines()[1:] if ": " in line)


def test_forked_session_keeps_only_its_own_turns_and_a_copy_inside_another_gets_no_page(env):
    """A fork or resume copies the earlier turns verbatim (same time, same question): they land on one page only."""
    t1, t2, t3 = _ts(1, 9), _ts(1, 10), _ts(1, 11)
    base = [(t1, "发版流程怎么定？", "只从 main 打 tag。")]
    _claude_turns(env["claude"], "aaaa0000-parent", base + [(t2, "测试要全跑吗？", "要，全跑。")])
    _claude_turns(env["claude"], "bbbb0000-fork", base + [(t2, "换个思路：先灰度？", "先灰度 10%。"),
                                                         (t3, "灰度多久？", "一天。")])
    _claude_turns(env["claude"], "cccc0000-copy", base)  # wholly inside the others
    _claude_turns(env["claude"], "dddd0000-same-question", [(t3, "发版流程怎么定？", "另一次问。")])  # asked again later
    out = _run(env, "--days", "7")
    assert out["fork_duplicates"] == 1 and out["pages"] == 3
    pages = {_meta(p)["session"]: p for p in _pages(env).values()}
    assert set(pages) == {"aaaa0000-parent", "bbbb0000-fork", "dddd0000-same-question"}
    assert pages["bbbb0000-fork"].count("发版流程怎么定") >= 1 and "forked_from" not in pages["bbbb0000-fork"]
    parent = pages["aaaa0000-parent"]
    assert _meta(parent)["forked_from"] == "bbbb0000-fork" and "测试要全跑吗" in parent
    assert "- **问**（" in parent and "只从 main 打 tag" not in parent  # the shared turn lives on the fork's page
    assert _meta(parent)["first_turn"] == _meta(pages["bbbb0000-fork"])["first_turn"]
    assert "另一次问" in pages["dddd0000-same-question"]  # same words, different time: not a fork


def test_session_end_of_a_longer_fork_replaces_the_earlier_page(env):
    """Hook mode imports one file; the earlier half's page, written the night before, is read back and removed."""
    t1, t2 = _ts(1, 9), _ts(1, 10)
    base = [(t1, "缓存过期时间改成多少？", "改成 10 分钟。")]
    _claude_turns(env["claude"], "aaaa0000-parent", base)
    _run(env, "--consent", "--days", "7")
    assert [_meta(p)["session"] for p in _pages(env).values()] == ["aaaa0000-parent"]
    fork = _claude_turns(env["claude"], "bbbb0000-fork", base + [(t2, "那 CDN 呢？", "CDN 一小时。")])
    out = _run(env, "--file", str(fork))
    assert out["fork_duplicates"] == 1
    assert [_meta(p)["session"] for p in _pages(env).values()] == ["bbbb0000-fork"]


def test_sessions_a_daily_log_already_has_are_linked_or_skipped(env):
    """collect_day-style daily logs: the session is matched by id (or the log's collector covered the day)."""
    t1 = _ts(1, 9)
    day = (datetime.now().astimezone() - timedelta(days=1)).date()
    _claude_turns(env["claude"], "5ee9241f-19e4-49d4-a24c-019946080791", [(t1, "再来一轮对标监控！", "好。")])
    _claude_turns(env["claude"], "77770000-other-day", [(_ts(3, 9), "别的日子", "嗯。")])
    log = env["vault"] / "05 时间日志" / day.strftime("%Y-%m") / f"{day.strftime('%d')}｜待总结.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(f"---\ntitle: \"{day.strftime('%d')}｜待总结\"\ntype: daily-log\ndate: {day.isoformat()}\n"
                   "source_kind: collector-stub\n---\n\n## 会话索引\n\n"
                   "- `claude:5ee9241f-19e4-49d4-a24c-019946080791` 再来一轮对标监控！\n", encoding="utf-8")
    note = env["vault"] / "05 时间日志" / "随手记.md"
    note.write_text("---\ntype: note\n---\n\n`77770000-other-day`\n", encoding="utf-8")  # not a daily log
    out = _run(env, "--days", "7")
    assert out["overlap"] == "link" and out["covered_by_daily_log"] == 1 and out["pages"] == 2
    page = next(p for p in _pages(env).values() if "对标监控" in p)
    rel = f"05 时间日志/{day.strftime('%Y-%m')}/{day.strftime('%d')}｜待总结"
    assert f'covered_by: "[[{rel}]]"' in page and f"当天的日更：[[{rel}]]" in page
    assert "covered_by" not in next(p for p in _pages(env).values() if "别的日子" in p)
    for p in (env["vault"] / FOLDER).glob("*.md"):
        p.unlink()
    out = _run(env, "--days", "7", "--overlap", "skip")
    assert out["skipped_covered"] == 1 and [_meta(p)["session"] for p in _pages(env).values()] == ["77770000-other-day"]
    # a distilled log keeps only short ids; the day itself is still covered by its collector
    log.write_text(f"---\ntype: daily-log\ndate: {day.isoformat()}\nsource_kind: multi-agent-extract\n---\n\n"
                   "冲突未决：见（`5ee9241f`）。\n", encoding="utf-8")
    assert _run(env, "--days", "7", "--overlap", "skip")["skipped_covered"] == 1


def test_a_daily_log_covers_only_its_own_day(env):
    """A session that ran past midnight: the first day's log names it, the next day's turns are not covered."""
    d1 = (datetime.now().astimezone() - timedelta(days=2)).date()
    sid = "5ee9241f-19e4-49d4-a24c-019946080791"
    _claude_turns(env["claude"], sid, [(_ts(2, 22), "第一天问", "答。"), (_ts(1, 9), "第二天问", "答。")])
    log = env["vault"] / "05 时间日志" / d1.strftime("%Y-%m") / f"{d1.strftime('%d')}｜待总结.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(f"---\ntype: daily-log\ndate: {d1.isoformat()}\n---\n\n- `claude:{sid}` 第一天问\n", encoding="utf-8")
    out = _run(env, "--days", "7", "--overlap", "skip")
    assert out["skipped_covered"] == 1
    assert ["第二天问" in p for p in _pages(env).values()] == [True]


def test_a_session_that_grew_sends_only_its_new_turns(env, monkeypatch):
    """Session-end distilling: a session ends many times; each end sends the new turns, not the whole excerpt again."""
    sys.path.insert(0, str(SCRIPTS))
    import import_sessions as imp
    import llm

    t = [_ts(1, h) for h in (9, 10, 11, 12)]
    path = _claude_turns(env["claude"], "aaaa0000-grow", [(t[0], "发版流程怎么定？", "只从 main 打 tag。"),
                                                         (t[1], "那就这么定", "好。")])
    sent = []
    reply = {"n": 0}

    def fake(prompt, vault=None):
        sent.append(prompt)
        reply["n"] += 1
        return "- 发版只从 main 打 tag（09:05）" if reply["n"] <= 2 else "- 灰度先放 10%（11:05）"

    monkeypatch.setattr(llm, "complete", fake)
    for k in ("OBSIDIAN_VAULT", "KROUTER_CLAUDE_PROJECTS", "KROUTER_CODEX_SESSIONS", "KROUTER_CURSOR_PROJECTS",
              "KROUTER_STATE_DIR"):
        monkeypatch.setenv(k, env["env"][k])
    monkeypatch.setattr(sys, "argv", ["import_sessions.py", "--distill"])
    assert imp.main() == 0
    first = len(sent)
    _claude_turns(env["claude"], "aaaa0000-grow", [(t[0], "发版流程怎么定？", "只从 main 打 tag。"),
                                                  (t[1], "那就这么定", "好。"), (t[2], "灰度放多少？", "先放 10%。"),
                                                  (t[3], "就这样", "好。")])
    sent.clear()
    assert imp.main() == 0
    segment_prompts, change_prompt = sent[:-1], sent[-1]
    assert segment_prompts and all("发版流程怎么定" not in p for p in segment_prompts)  # old turns not re-sent
    assert all("灰度放多少" in p for p in segment_prompts)
    assert "这段会话前面已经记下" in change_prompt and "发版只从 main 打 tag" in change_prompt
    page = next(iter(_pages(env).values()))
    assert "digest_turns: 4" in page
    assert "- 发版只从 main 打 tag（09:05）" in page and "- 灰度先放 10%（11:05）" in page  # both halves kept
    assert first == 2 and path.exists()
