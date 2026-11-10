"""Personal tokens on a team server: only hashes kept, the old shared token still works, read-only people cannot
write, a token opens only its banks, the users file is re-read without a restart, every write says who made it (page,
ledger, journal, git author, `krouter_changes`), and two contradicting corrections follow the later-one-holds rule."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter/scripts"
SERVER = SCRIPTS / "mcp_server.py"
sys.path.insert(0, str(SCRIPTS))
import corrections  # noqa: E402
import team  # noqa: E402

SHARED = "shared-token-for-tests-0123456789"


def _env(tmp: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.endswith(("_API_KEY", "_BASE_URL"))}
    env.update({"HOME": str(tmp / "home"), "KROUTER_CACHE_DIR": str(tmp / "cache"),
                "KROUTER_STATE_DIR": str(tmp / "state"), "KROUTER_VAULT_FILE": str(tmp / "no-vault-file"),
                "KROUTER_NO_QUERY_LOG": "1", "GIT_CONFIG_GLOBAL": str(tmp / "home/.gitconfig"),
                "GIT_CONFIG_NOSYSTEM": "1"})
    env.pop("OBSIDIAN_VAULT", None)
    (tmp / "home").mkdir(exist_ok=True)
    return env


def _git(vault: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(vault), *args], capture_output=True, text=True, check=True).stdout


def _vault(tmp: Path, name: str = "vault") -> Path:
    vault = tmp / name
    shutil.copytree(REPO / "template", vault)
    (vault / "01 项目/数据库选型.md").write_text(
        "---\ntitle: 数据库选型\nstatus: active\n---\n\n# 数据库选型\n\n- 数据库用 SQLite\n", encoding="utf-8")
    _git(vault, "init", "-q")
    _git(vault, "add", "-A")
    _git(vault, "-c", "user.name=seed", "-c", "user.email=seed@x.invalid", "commit", "-qm", "seed")
    return vault


def _start(tmp: Path, *argv: str):
    proc = subprocess.Popen([sys.executable, str(SERVER), "--http", "127.0.0.1:0", *argv], env=_env(tmp),
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    for _ in range(80):
        line = proc.stderr.readline()
        if line.startswith("{") and "listening" in line:
            return proc, json.loads(line)
        if not line:
            break
    raise AssertionError("server did not start")


def _post(url: str, token: str | None, method: str, params: dict | None = None):
    req = urllib.request.Request(url, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                                                       "params": params or {}}).encode(),
                                 method="POST", headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, None


def _tool(url, token, name, **args) -> tuple[str, bool]:
    code, reply = _post(url, token, "tools/call", {"name": name, "arguments": args})
    assert code == 200, code
    res = reply["result"]
    return res["content"][0]["text"], res["isError"]


@pytest.fixture()
def team_server(tmp_path):
    vault = _vault(tmp_path)
    users = tmp_path / "users"
    tokens = {}
    for name, role in (("alice", "write"), ("bob", "write"), ("carol", "read")):
        team.add_user(users, name, role, "*", tmp_path / f"{name}.token")
        tokens[name] = (tmp_path / f"{name}.token").read_text(encoding="utf-8").strip()
    shared = tmp_path / "shared.token"
    shared.write_text(SHARED + "\n", encoding="utf-8")
    shared.chmod(0o600)
    proc, info = _start(tmp_path, "--vault", str(vault), "--label", "team", "--users", str(users),
                        "--token-file", str(shared), "--allow-write")
    yield {"url": info["listening"], "vault": vault, "tokens": tokens, "users": users, "proc": proc, "tmp": tmp_path,
           "info": info}
    proc.terminate()
    proc.wait(timeout=10)


def test_users_file_keeps_only_hashes_and_token_files_are_private(team_server):
    text = team_server["users"].read_text(encoding="utf-8")
    assert all(tok not in text for tok in team_server["tokens"].values())
    assert text.count("|sha256:") == 3 and "carol|" in text and "|read|" in text
    if os.name != "nt":
        assert (team_server["tmp"] / "alice.token").stat().st_mode & 0o077 == 0
    assert team_server["info"]["auth"] == "personal tokens + shared" and team_server["info"]["users"] == 3


def test_who_is_recorded_on_page_ledger_journal_and_git(team_server):
    url, vault, tok = team_server["url"], team_server["vault"], team_server["tokens"]
    _post(url, tok["alice"], "initialize", {"protocolVersion": "2025-06-18", "clientInfo": {"name": "claude-code"}})
    _post(url, tok["bob"], "initialize", {"protocolVersion": "2025-06-18", "clientInfo": {"name": "codex"}})
    text, err = _tool(url, tok["alice"], "krouter_note", text="发版前先跑冒烟测试", kind="decision")
    assert not err and "by: alice" in text
    text, err = _tool(url, tok["bob"], "krouter_note", text="周会改到周二")
    assert not err and "by: bob" in text
    text, err = _tool(url, SHARED, "krouter_note", text="共享令牌也能记")
    assert not err and "by:" not in text
    page = next((vault / "05 时间日志/会话摘录").glob("*agent 记下.md")).read_text(encoding="utf-8")
    assert "发版前先跑冒烟测试 — 来自 alice（MCP，claude-code）" in page  # 各人的客户端名不串
    assert "周会改到周二 — 来自 bob（MCP，codex）" in page
    assert "共享令牌也能记 — 来自 共享令牌（MCP，" in page
    ledger = (vault / "90 系统文件/自动化/记忆变更记录.md").read_text(encoding="utf-8")
    assert "MCP 记下（alice，claude-code）" in ledger
    rows = team.read_journal(vault)
    assert [(r["who"], r["auth"]) for r in rows] == [("alice", "user"), ("bob", "user"), ("", "shared-token")]
    assert [r["via"] for r in rows[:2]] == ["claude-code", "codex"]
    assert [r["seq"] for r in rows] == [1, 2, 3] and len({r["run"] for r in rows}) == 3
    authors = _git(vault, "log", "--format=%an", "-6").split()
    assert authors.count("alice") == 2 and authors.count("bob") == 2  # 笔记的提交和变更记录的提交
    text, _ = _tool(url, tok["carol"], "krouter_changes", who="alice")
    assert text.startswith("vault_label: team\n") and "changes: 1" in text and "alice via claude-code: krouter_note" in text
    text, _ = _tool(url, tok["carol"], "krouter_changes", text="周会")
    assert "bob via codex" in text and "alice" not in text


def test_read_role_cannot_write_and_tokens_never_reach_the_log(team_server):
    url, tok = team_server["url"], team_server["tokens"]
    code, reply = _post(url, tok["carol"], "tools/list")
    names = {t["name"] for t in reply["result"]["tools"]}
    assert "krouter_note" not in names and "krouter_correct" not in names and "krouter_changes" in names
    text, err = _tool(url, tok["carol"], "krouter_note", text="不该写进去")
    assert err and "read-only" in text
    code, reply = _post(url, tok["alice"], "tools/list")
    assert {"krouter_note", "krouter_correct", "krouter_changes"} <= {t["name"] for t in reply["result"]["tools"]}
    assert _post(url, "not-a-token-of-anyone-at-all", "ping")[0] == 401
    assert _post(url, None, "ping")[0] == 401
    team_server["proc"].terminate()
    log = team_server["proc"].stderr.read()
    assert '"who": "carol"' in log and not any(t in log for t in [*tok.values(), SHARED])


def test_users_file_is_reread_without_restart(team_server):
    url, users, tmp = team_server["url"], team_server["users"], team_server["tmp"]
    team.add_user(users, "dave", "write", "*", tmp / "dave.token")
    dave = (tmp / "dave.token").read_text(encoding="utf-8").strip()
    time.sleep(0.05)
    assert _post(url, dave, "ping")[0] == 200
    assert team.remove_user(users, "dave")
    assert _post(url, dave, "ping")[0] == 401


def test_a_token_opens_only_its_banks(tmp_path):
    a, b = _vault(tmp_path, "a"), _vault(tmp_path, "b")
    users = tmp_path / "users"
    team.add_user(users, "ann", "read", "alpha", tmp_path / "ann.token")
    ann = (tmp_path / "ann.token").read_text(encoding="utf-8").strip()
    proc, info = _start(tmp_path, "--bank", f"alpha={a}", "--bank", f"beta={b}", "--users", str(users))
    try:
        assert _post(info["banks"]["alpha"], ann, "ping")[0] == 200
        assert _post(info["banks"]["beta"], ann, "ping")[0] == 403
        assert _post(info["banks"]["beta"], None, "ping")[0] == 401
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_contradicting_corrections_later_one_holds_and_both_are_kept(team_server):
    url, vault, tok = team_server["url"], team_server["vault"], team_server["tokens"]
    old = dict(old="数据库用 SQLite", page="01 项目/数据库选型.md")
    first, err = _tool(url, tok["alice"], "krouter_correct", new="数据库改用 Postgres", **old)
    assert not err and "conflict:" not in first
    # bob 也是照着原来那页（他早先查到的）改的：那页已被 alice 取代
    second, err = _tool(url, tok["bob"], "krouter_correct", new="数据库改用 MySQL", **old)
    assert not err
    a_page = first.split("\n", 1)[0].removeprefix("corrected: ")
    b_page = second.split("\n", 1)[0].removeprefix("corrected: ")
    assert f"conflict: {a_page} by alice at " in second and 'said "数据库改用 Postgres"' in second
    assert "the later correction holds" in second
    a_meta = corrections._meta((vault / a_page).read_text(encoding="utf-8"))
    b_meta = corrections._meta((vault / b_page).read_text(encoding="utf-8"))
    p_meta = corrections._meta((vault / "01 项目/数据库选型.md").read_text(encoding="utf-8"))
    assert (a_meta["status"], a_meta["author"], a_meta["superseded_by_author"]) == ("superseded", "alice", "bob")
    assert a_meta["superseded_by"] == f"[[{b_page.removesuffix('.md')}]]"
    assert (b_meta["status"], b_meta["author"], b_meta["how"]) == ("active", "bob", "现在：数据库改用 MySQL")
    assert a_page.removesuffix(".md") in b_meta["supersedes"] and "01 项目/数据库选型" in b_meta["supersedes"]
    assert p_meta["superseded_by"] == f"[[{a_page.removesuffix('.md')}]]"  # 原页的链不改：P → alice → bob
    text, _ = _tool(url, tok["carol"], "krouter_changes", page="01 项目/数据库选型.md")
    assert "changes: 2" in text and "conflict: replaced" in text and text.index("bob") < text.index("alice")
    ask, _ = _tool(url, tok["carol"], "krouter_ask", query="数据库选型现在用什么")
    assert f"- {b_page} " in ask and "how: 现在：数据库改用 MySQL" in ask
    assert f"- {a_page} tier=" not in ask or f"- {a_page} tier=dead status=superseded" in ask  # alice 那页只能以作废出现


def test_same_line_of_a_long_page_corrected_twice(tmp_path):
    vault = tmp_path / "v"
    shutil.copytree(REPO / "template", vault)
    lines = "\n".join(f"- 规则 {i}：保持原样" for i in range(15))
    page = vault / "01 项目/团队约定.md"
    page.write_text(f"---\ntitle: 团队约定\nstatus: active\n---\n\n# 团队约定\n\n- 发布窗口：周四下午\n{lines}\n",
                    encoding="utf-8")
    a = corrections.apply_now(vault, "发布窗口改成周一", "发布窗口：周四下午", "01 项目/团队约定.md", "t", author="alice")
    b = corrections.apply_now(vault, "发布窗口改成周五", "发布窗口：周四下午", "01 项目/团队约定.md", "t", author="bob")
    assert (a["mode"], b["mode"]) == ("line", "line") and a["written"] != b["written"]
    assert [c["page"] for c in b["conflicts"]] == [a["written"]] and b["conflicts"][0]["author"] == "alice"
    text = page.read_text(encoding="utf-8")
    assert text.index(a["written"].removesuffix(".md")) < text.index(b["written"].removesuffix(".md"))
    assert corrections._meta((vault / a["written"]).read_text(encoding="utf-8"))["status"] == "superseded"
    assert corrections._meta((vault / b["written"]).read_text(encoding="utf-8"))["status"] == "active"
    # 同一句同一天再来一遍：编号，不覆盖
    c = corrections.apply_now(vault, "发布窗口改成周五", "发布窗口：周四下午", "01 项目/团队约定.md", "t", author="bob")
    assert c["written"] != b["written"] and (vault / b["written"]).is_file()


def test_unique_run_ids_within_one_second(tmp_path):
    from datetime import datetime

    vault = tmp_path / "v"
    (vault / "90 系统文件/自动化").mkdir(parents=True)
    now = datetime(2026, 11, 10, 9, 0, 0)
    runs = []
    for _ in range(3):
        rid = team.unique_run(vault, now)
        team.record(vault, {"who": "x", "run": rid})
        runs.append(rid)
    assert runs == ["20261110T090000", "20261110T090000-2", "20261110T090000-3"]


def test_a_long_chain_of_corrections_still_converges(tmp_path):
    # 30 分钟压测里第 101 条纠正起两条并存：取代链走到 100 步就放弃了。现在走到底，而且一次纠正只走一遍
    vault = tmp_path / "v"
    shutil.copytree(REPO / "template", vault)
    (vault / "01 项目/数据库选型.md").write_text(
        "---\ntitle: 数据库选型\nstatus: active\n---\n\n# 数据库选型\n\n- 数据库用 SQLite\n", encoding="utf-8")
    written = []
    t0 = time.perf_counter()
    for i in range(160):
        res = corrections.apply_now(vault, f"数据库改用 第{i}版", "数据库用 SQLite", "01 项目/数据库选型.md", "t",
                                    author=f"p{i % 3}")
        assert "error" not in res
        if i:
            assert [c["page"] for c in res["conflicts"]] == [written[-1]], i
        written.append(res["written"])
    active = [w for w in written if corrections._meta((vault / w).read_text(encoding="utf-8"))["status"] == "active"]
    assert active == [written[-1]]
    assert time.perf_counter() - t0 < 60
    # 被取代的纠正页不再带原页的标题词：160 条几乎一样的页里，生效的那条仍是第一条纠正页
    metas = [corrections._meta((vault / w).read_text(encoding="utf-8")) for w in written]
    assert metas[-1]["topic_terms"] == "数据库选型" and all(m["topic_terms"] == "" for m in metas[:-1])


def test_a_broken_chain_is_reported_not_silent(tmp_path):
    vault = tmp_path / "v"
    shutil.copytree(REPO / "template", vault)
    (vault / "01 项目/数据库选型.md").write_text(
        "---\ntitle: 数据库选型\nstatus: superseded\nsuperseded_by: \"[[05 时间日志/会话摘录/已经删掉的一页]]\"\n---\n\n"
        "# 数据库选型\n\n- 数据库用 SQLite\n", encoding="utf-8")
    res = corrections.apply_now(vault, "数据库改用 Postgres", "数据库用 SQLite", "01 项目/数据库选型.md", "t", author="a")
    assert "error" not in res and res["conflicts"] and res["conflicts"][0]["why"].startswith("unresolved")


def test_the_change_ledger_moves_to_an_archive_page_when_big(tmp_path, monkeypatch):
    # 30 分钟压测里变更记录长到 1.6 MB，每次写入重建它的索引要近 1 秒，查询排在后面等
    import capture_ledger

    monkeypatch.setattr(capture_ledger, "ROTATE_AT", 3000)
    vault = _vault(tmp_path)
    for i in range(30):
        ledger = capture_ledger.append(vault, f"## run {i}\n\n- 第 {i} 条 " + "一句话" * 40 + "\n")
        capture_ledger.commit(vault, f"r{i}", [ledger], f"变更记录 run {i}", tagged=False)
    archive = sorted((vault / capture_ledger.ARCHIVE).glob("*.md"))
    assert len(archive) >= 3 and ledger.stat().st_size < 3000 + 400
    text = "".join(p.read_text(encoding="utf-8") for p in [*archive, ledger])
    assert all(f"## run {i}\n" in text for i in range(30))
    assert "更早的记录：[[90 系统文件/自动化/记忆变更记录/" in ledger.read_text(encoding="utf-8")
    assert _git(vault, "status", "--porcelain").strip() == ""
