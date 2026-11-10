"""claude-mem's memory comes into the vault: summaries as logs, decisions as pages to confirm, corrections sorted.

The databases here are built from claude-mem's own schema (src/services/sqlite/SessionStore.ts at b3e036fa13): the
current one (`memory_session_id`, epoch milliseconds) and the older one (`sdk_session_id`).
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter/scripts"
IMPORT = SCRIPTS / "import_claude_mem.py"
KEY = "sk-" + "Zyx987AbC" * 4
DAY = 86_400_000


def _db(path: Path, old: bool = False) -> Path:
    sid = "sdk_session_id" if old else "memory_session_id"
    con = sqlite3.connect(path)
    con.executescript(f"""
    CREATE TABLE sdk_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, content_session_id TEXT NOT NULL,
      {sid} TEXT UNIQUE, project TEXT NOT NULL, started_at TEXT NOT NULL, started_at_epoch INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'completed');
    CREATE TABLE observations (id INTEGER PRIMARY KEY AUTOINCREMENT, {sid} TEXT NOT NULL, project TEXT NOT NULL,
      text TEXT, type TEXT NOT NULL, title TEXT, subtitle TEXT, facts TEXT, narrative TEXT, concepts TEXT,
      files_read TEXT, files_modified TEXT, prompt_number INTEGER, discovery_tokens INTEGER DEFAULT 0,
      created_at TEXT NOT NULL, created_at_epoch INTEGER NOT NULL);
    CREATE TABLE session_summaries (id INTEGER PRIMARY KEY AUTOINCREMENT, {sid} TEXT NOT NULL, project TEXT NOT NULL,
      request TEXT, investigated TEXT, learned TEXT, completed TEXT, next_steps TEXT, files_read TEXT,
      files_edited TEXT, notes TEXT, prompt_number INTEGER, created_at TEXT NOT NULL, created_at_epoch INTEGER NOT NULL);
    """)
    now = int(time.time() * 1000)
    rows = [
        ("mem-aaaa1111", "shop", "decision", "Ship from any branch, tag by hand", ["Releases are tagged manually"], now - 9 * DAY),
        ("mem-aaaa1111", "shop", "discovery", "CI takes 12 minutes", ["The build step is the slow part"], now - 9 * DAY),
        ("mem-bbbb2222", "shop", "decision", "Ship only from a tag on main; CI publishes",
         ["Replaces manual tagging after a broken hotfix", "token was " + KEY], now - 2 * DAY),
        ("mem-cccc3333", "api", "decision", "Payments API timeout is 10 s with two retries", [], now - 1 * DAY),
        ("mem-cccc3333", "api", "bugfix", "Fixed double charge on retry", ["Idempotency key per request"], now - 1 * DAY),
    ]
    for s, proj, typ, title, facts, epoch in rows:
        con.execute(f"INSERT OR IGNORE INTO sdk_sessions (content_session_id, {sid}, project, started_at, started_at_epoch) "
                    "VALUES (?, ?, ?, '', ?)", ("c-" + s, s, proj, epoch))
        con.execute(f"INSERT INTO observations ({sid}, project, type, title, facts, created_at, created_at_epoch) "
                    "VALUES (?, ?, ?, ?, ?, '', ?)", (s, proj, typ, title, json.dumps(facts), epoch))
    con.execute(f"INSERT INTO session_summaries ({sid}, project, request, learned, completed, next_steps, created_at, "
                "created_at_epoch) VALUES ('mem-bbbb2222', 'shop', 'Fix the release process', 'Manual tags drift', "
                "'Release now runs from CI', 'Delete the old upload script', '', ?)", (now - 2 * DAY,))
    con.commit()
    con.close()
    return path


@pytest.fixture()
def env(tmp_path):
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template", vault)
    e = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_STATE_DIR": str(tmp_path / "state"),
         "KROUTER_NO_QUERY_LOG": "1", "KROUTER_CACHE_DIR": str(tmp_path / "cache"),
         "KROUTER_CLAUDE_MEM_DB": str(_db(tmp_path / "claude-mem.db"))}
    return {"vault": vault, "env": e, "tmp": tmp_path}


def _run(env: dict, *args: str, extra: dict | None = None) -> dict:
    res = subprocess.run([sys.executable, str(IMPORT), *args], env={**env["env"], **(extra or {})},
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stdout + res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


def _pages(vault: Path, folder: str) -> dict[str, str]:
    d = vault / folder
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(d.glob("*.md"))} if d.is_dir() else {}


@pytest.mark.parametrize("old", [False, True])
def test_import_both_schema_generations(env, old):
    if old:
        env["env"]["KROUTER_CLAUDE_MEM_DB"] = str(_db(env["tmp"] / "old.db", old=True))
    out = _run(env)
    assert out["sessions"] == 3 and out["projects"] == 2 and out["decisions"] == 4 and out["chars"] == 0  # 3 条 decision + 1 条 bugfix；discovery 不收
    logs = _pages(env["vault"], "05 时间日志/claude-mem")
    assert len(logs) == 3
    release = next(v for k, v in logs.items() if "Fix the release process" in k)
    assert "**完成了**：Release now runs from CI" in release and "**决定**" in release
    assert KEY not in release and "<redacted>" in release
    rules = _pages(env["vault"], "02 经验与方法/从 claude-mem 导入")
    shop = rules["shop 的决定（claude-mem）.md"]
    assert "status: candidate" in shop and "source: krouter-claude-mem" in shop
    assert shop.index("Ship only from a tag on main") < shop.index("Ship from any branch")  # 新的在前


def test_read_only_dry_run_and_foreign_pages(env):
    db = Path(env["env"]["KROUTER_CLAUDE_MEM_DB"])
    before = db.read_bytes()
    out = _run(env, "--dry-run")
    assert out["claude_mem"] == "dry-run" and not (env["vault"] / "05 时间日志/claude-mem").exists()
    _run(env)
    assert db.read_bytes() == before  # 只读打开，claude-mem 的库不变
    page = env["vault"] / "02 经验与方法/从 claude-mem 导入/api 的决定（claude-mem）.md"
    page.write_text("# 我自己改过\n", encoding="utf-8")
    again = _run(env)
    assert again["kept"] == 1 and page.read_text(encoding="utf-8") == "# 我自己改过\n"
    assert again["same"] == 4 and again["written"] == 0  # 3 个会话页 + shop 页都没变：不重写


def test_absent_database_and_nightly_consent(env):
    assert _run(env, extra={"KROUTER_CLAUDE_MEM_DB": str(env["tmp"] / "nope.db")})["claude_mem"] == "absent"
    assert _run(env, "--nightly")["claude_mem"] == "off"
    _run(env, "--consent")
    assert _run(env, "--nightly")["claude_mem"] == "done"
    _run(env, "--revoke")
    assert _run(env, "--nightly")["claude_mem"] == "off"


def test_distill_sorts_out_what_was_replaced(env, monkeypatch):
    sys.path.insert(0, str(SCRIPTS))
    import import_claude_mem as icm
    import llm

    sent = []
    monkeypatch.setattr(llm, "complete", lambda prompt, vault=None: sent.append(prompt) or
                        "- 只从 main 上的 tag 发版，CI 发布（#3，近日）\n- 原来手动打 tag → 改成 CI 发版（#1 → #3）\n以上")
    for k in ("OBSIDIAN_VAULT", "KROUTER_STATE_DIR", "KROUTER_CLAUDE_MEM_DB"):
        monkeypatch.setenv(k, env["env"][k])
    monkeypatch.setattr(sys, "argv", ["import_claude_mem.py", "--distill"])
    assert icm.main() == 0
    assert len(sent) == 2 and all(KEY not in p for p in sent)  # 每个项目一次，发出去的已脱敏
    shop = (env["vault"] / "02 经验与方法/从 claude-mem 导入/shop 的决定（claude-mem）.md").read_text(encoding="utf-8")
    assert "原来手动打 tag → 改成 CI 发版（#1 → #3）" in shop and "以上" not in shop
    assert "how: shop 在 claude-mem 里记下的 2 条决定和改动（待你确认），现在有效的和被取代的已整理在页首" in shop
    monkeypatch.setattr(sys, "argv", ["import_claude_mem.py", "--distill"])
    assert icm.main() == 0 and len(sent) == 2  # 决定没变：不重复整理


def test_router_answers_from_the_imported_decisions(env):
    _run(env)
    res = subprocess.run([sys.executable, str(SCRIPTS / "route_knowledge.py"), "search", "payments API timeout retries"],
                         env=env["env"], capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    top = res.stdout.split("recall:", 1)[1].splitlines()[1]
    assert "claude-mem" in top, res.stdout[-800:]


def test_same_project_name_in_two_repos_stays_two_pages(env):
    """claude-mem names a project by its folder; with its cwd column the import splits alpha/api from beta/api."""
    db = env["tmp"] / "two.db"
    con = sqlite3.connect(db)
    con.executescript("""
    CREATE TABLE sdk_sessions (id INTEGER PRIMARY KEY, content_session_id TEXT, memory_session_id TEXT UNIQUE,
      project TEXT, cwd TEXT, started_at TEXT, started_at_epoch INTEGER);
    CREATE TABLE observations (id INTEGER PRIMARY KEY, memory_session_id TEXT, project TEXT, type TEXT, title TEXT,
      facts TEXT, created_at TEXT, created_at_epoch INTEGER);
    """)
    now = int(time.time() * 1000)
    for i, who in enumerate(("alpha", "beta")):
        d = env["tmp"] / who / "api"
        d.mkdir(parents=True)
        con.execute("INSERT INTO sdk_sessions VALUES (?, ?, ?, 'api', ?, '', ?)", (i, f"c{i}", f"m{i}", str(d), now))
        con.execute("INSERT INTO observations VALUES (?, ?, 'api', 'decision', ?, '[]', '', ?)",
                    (i, f"m{i}", f"{who} decision", now))
    con.commit()
    con.close()
    out = _run(env, extra={"KROUTER_CLAUDE_MEM_DB": str(db)})
    assert out["projects"] == 2
    pages = _pages(env["vault"], "02 经验与方法/从 claude-mem 导入")
    assert len(pages) == 2
    for who in ("alpha", "beta"):
        page = next(v for v in pages.values() if f"{who} decision" in v)
        other = "beta" if who == "alpha" else "alpha"
        assert f"project_root: " in page and f"/{who}/api" in page and f"{other} decision" not in page
