"""Codex and Cursor get the same hooks as Claude Code: a session starts with this project's decisions, each turn is
recorded as it ends (locally, no model call), a correction is noted the moment it is typed. Each speaks its own
format (official docs, 2026-11-09; Codex's checked against codex-cli 0.155), and the installer merges them into the
app's hooks file without touching anyone else's entries."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter/scripts"
HOOK = SCRIPTS / "session_hook.py"
IMPORT = SCRIPTS / "import_sessions.py"
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(SCRIPTS))
import bootstrap  # noqa: E402

DIGEST = "## 定了什么、改了什么（模型提炼）"


def _jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return path


def _root(path: Path) -> str:
    from krouter_home import project_root

    return project_root(str(path))


@pytest.fixture()
def box(tmp_path):
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template", vault)
    folder = vault / "05 时间日志/会话摘录"
    folder.mkdir(parents=True)
    work = tmp_path / "work/api"
    work.mkdir(parents=True)
    state = tmp_path / "state"
    state.mkdir()
    (state / "import.json").write_text(json.dumps({"consent": True}), encoding="utf-8")
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_STATE_DIR": str(state), "KROUTER_NO_QUERY_LOG": "1",
           "KROUTER_CODEX_SESSIONS": str(tmp_path / "codex"), "KROUTER_CURSOR_PROJECTS": str(tmp_path / "cursor"),
           "KROUTER_CLAUDE_PROJECTS": str(tmp_path / "claude")}
    for k in ("KROUTER_INJECT", "KROUTER_IN_DISTILL"):
        env.pop(k, None)
    return {"vault": vault, "folder": folder, "work": work, "state": state, "env": env, "tmp": tmp_path}


def _hook(env: dict, which: str, agent: str, payload) -> subprocess.CompletedProcess:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOK), which, "--agent", agent], input=text, env=env,
                          capture_output=True, text=True, timeout=60)


def _decision(box, line: str = "原来手动上传 → 改成 CI 发布（10:20）") -> None:
    day = date.today().isoformat()
    (box["folder"] / f"{day}｜发版.md").write_text(
        f"---\nsource: krouter-import\nstatus: imported\ndate: {day}\nproject: api\nproject_root: {_root(box['work'])}\n"
        f"---\n\n# 发版\n\n{DIGEST}\n\n- {line}\n\n## 摘录\n\n- **问**：…\n", encoding="utf-8")


def _codex_rollout(box, asks: list[tuple[str, str]], sid: str = "019a7f00-aaaa-bbbb-cccc-0000000000c1") -> Path:
    # 同一场测试里再写一次 = 同一个会话又多了几轮：真的会话是往后追加，前面几轮的时间和文件名不变。
    # 每次都取当前时间的话，两次调用跨过一秒，第一轮的身份（时间 + 问题）就变了，留住旧提炼的那条测试会偶发失败
    day = box.setdefault("started", datetime.now().astimezone().replace(microsecond=0))
    ts = day.astimezone(timezone.utc).isoformat()
    rows = [{"type": "session_meta", "timestamp": ts,
             "payload": {"id": sid, "cwd": str(box["work"]), "originator": "codex_cli_rs"}}]
    for ask, answer in asks:
        rows += [{"type": "response_item", "timestamp": ts, "payload": {"type": "message", "role": "user",
                  "content": [{"type": "input_text", "text": ask}]}},
                 {"type": "response_item", "timestamp": ts, "payload": {"type": "message", "role": "assistant",
                  "content": [{"type": "output_text", "text": answer}]}}]
    return _jsonl(box["tmp"] / "codex" / day.strftime("%Y/%m/%d") / f"rollout-{day:%Y-%m-%dT%H-%M-%S}-{sid}.jsonl", rows)


def _cursor_transcript(box, asks: list[tuple[str, str]], sid: str = "c0ffee00-1111-2222-3333-4444555566aa") -> Path:
    slug = "-".join(p for p in box["work"].parts if p not in ("/", "\\") and not p.endswith(":\\"))
    rows = []
    for ask, answer in asks:
        rows += [{"role": "user", "message": {"content": [{"type": "text", "text": f"<user_query>\n{ask}\n</user_query>"}]}},
                 {"role": "assistant", "message": {"content": [{"type": "text", "text": answer}]}}]
    return _jsonl(box["tmp"] / "cursor" / slug / "agent-transcripts" / sid / f"{sid}.jsonl", rows)


def _wait_page(folder: Path, needle: str) -> str:
    for _ in range(200):  # 导入在后台跑；只认写完的 .md
        for page in folder.glob("*.md"):
            try:
                text = page.read_text(encoding="utf-8")
            except OSError:
                continue
            if needle in text and "source: krouter-import" in text:
                return text
        time.sleep(0.1)
    return ""


# ---------- Codex ----------

def test_codex_session_start_gets_the_projects_decisions_in_codex_format(box):
    _decision(box)
    res = _hook(box["env"], "start", "codex", {"session_id": "s", "cwd": str(box["work"]), "hook_event_name": "SessionStart",
                                               "source": "startup", "transcript_path": None})
    out = json.loads(res.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart" and "改成 CI 发布" in out["additionalContext"]


def test_codex_prompt_hook_prints_nothing_and_notes_the_correction_as_codex(box):
    # Codex 把 UserPromptSubmit 的纯文本输出加进上下文：这个钩子一个字都不能打
    res = _hook(box["env"], "prompt", "codex", {"session_id": "019a7f00-aaaa", "cwd": str(box["work"]),
                                                "prompt": "以后一律用 pnpm，不要再用 npm", "transcript_path": None})
    assert res.returncode == 0 and res.stdout == ""
    page = next(box["folder"].glob("*纠正候选.md")).read_text(encoding="utf-8")
    assert "会话 `codex:019a7f00`" in page and "项目 api" in page
    import corrections

    assert list(corrections.pending(box["folder"])) == [(date.today().isoformat(), "019a7f00")]


def test_codex_turn_end_records_the_turn_without_a_model_call(box):
    t = _codex_rollout(box, [("缓存过期时间改成多少？", "原来 30 分钟，改成 10 分钟。")])
    # 就算当初同意了提炼，每轮的导入也不调模型
    (box["state"] / "import.json").write_text(json.dumps({"consent": True, "distill": True, "cli": "claude"}), encoding="utf-8")
    res = _hook(box["env"], "turn", "codex", {"session_id": "019a7f00-aaaa-bbbb-cccc-0000000000c1", "transcript_path": str(t),
                                              "cwd": str(box["work"]), "hook_event_name": "Stop", "turn_id": "x",
                                              "stop_hook_active": False, "last_assistant_message": "…"})
    assert res.returncode == 0 and res.stdout == ""  # Codex：Stop 退出 0、不输出 = 照常结束
    page = _wait_page(box["folder"], "改成 10 分钟")
    assert "agent: codex" in page and f"project_root: {_root(box['work'])}" in page
    log = (box["state"] / "session-hook.log").read_text(encoding="utf-8")
    row = json.loads([ln for ln in log.splitlines() if ln.startswith("{")][-1])
    assert row["distilled"] == 0 and row["distill_failed"] == 0 and row["chars"] == 0


def test_codex_hook_finds_the_transcript_by_session_id(box):
    t = _codex_rollout(box, [("日志放哪？", "放 /var/log/api。")], sid="019a7f00-dddd-eeee-ffff-0000000000d2")
    res = _hook(box["env"], "end", "codex", {"session_id": "019a7f00-dddd-eeee-ffff-0000000000d2", "transcript_path": None,
                                             "cwd": str(box["work"]), "hook_event_name": "SessionEnd", "reason": "other"})
    assert res.returncode == 0 and t.is_file()
    assert "放 /var/log/api" in _wait_page(box["folder"], "放 /var/log/api")


# ---------- Cursor ----------

def test_cursor_session_start_prints_additional_context(box):
    _decision(box)
    res = _hook(box["env"], "start", "cursor", {"conversation_id": "c1", "session_id": "c1", "hook_event_name": "sessionStart",
                                                "workspace_roots": [str(box["work"])], "is_background_agent": False})
    out = json.loads(res.stdout)
    assert set(out) == {"additional_context"} and "改成 CI 发布" in out["additional_context"]


@pytest.mark.parametrize("payload", [
    {"conversation_id": "c0ffee00-1111", "prompt": "改成用 yarn，不要再用 npm", "workspace_roots": []},
    {"conversation_id": "c0ffee00-1111", "prompt": "这个函数是做什么的？"},
    "not json at all",
])
def test_cursor_prompt_hook_always_lets_the_prompt_through(box, payload):
    res = _hook(box["env"], "prompt", "cursor", payload)
    assert res.returncode == 0 and json.loads(res.stdout) == {"continue": True}


def test_cursor_prompt_hook_lets_it_through_without_consent_too(box):
    (box["state"] / "import.json").unlink()
    res = _hook(box["env"], "prompt", "cursor", {"conversation_id": "c", "prompt": "以后一律用 pnpm"})
    assert json.loads(res.stdout) == {"continue": True} and not list(box["folder"].glob("*纠正候选.md"))


def test_cursor_correction_is_noted_as_cursor(box):
    _hook(box["env"], "prompt", "cursor", {"conversation_id": "c0ffee00-1111", "prompt": "以后一律用 pnpm",
                                           "workspace_roots": [str(box["work"])], "transcript_path": None})
    page = next(box["folder"].glob("*纠正候选.md")).read_text(encoding="utf-8")
    assert "会话 `cursor:c0ffee00`" in page and "项目 api" in page


def test_cursor_turn_end_never_sends_a_follow_up_and_finds_the_transcript(box):
    _cursor_transcript(box, [("日志级别怎么定？", "定了：生产环境 info。")])
    res = _hook(box["env"], "turn", "cursor", {"conversation_id": "c0ffee00-1111-2222-3333-4444555566aa",
                                               "hook_event_name": "stop", "status": "completed", "loop_count": 0,
                                               "workspace_roots": [str(box["work"])]})
    assert json.loads(res.stdout) == {}  # followup_message 会被 Cursor 当成下一条提问
    page = _wait_page(box["folder"], "生产环境 info")
    assert "agent: cursor" in page


def test_a_session_marked_not_to_record_stays_out_codex_and_cursor(box):
    t = _codex_rollout(box, [("#不记 先试试", "好。")])
    _hook(box["env"], "prompt", "codex", {"session_id": "019a7f00", "prompt": "以后一律用 pnpm", "transcript_path": str(t)})
    c = _cursor_transcript(box, [("#nocapture just trying", "ok")])
    _hook(box["env"], "prompt", "cursor", {"conversation_id": "c0ffee00", "prompt": "from now on use pnpm",
                                           "transcript_path": str(c)})
    assert not list(box["folder"].glob("*纠正候选.md"))


@pytest.mark.parametrize("agent", ["codex", "cursor", "claude"])
def test_turn_and_end_do_nothing_under_a_krouter_model_call_or_without_consent(box, agent):
    t = _codex_rollout(box, [("x 改成 y", "好")])
    env = {**box["env"], "KROUTER_IN_DISTILL": "1"}
    for which in ("turn", "end"):
        assert _hook(env, which, agent, {"session_id": "s", "transcript_path": str(t)}).returncode == 0
    (box["state"] / "import.json").unlink()
    for which in ("turn", "end"):
        assert _hook(box["env"], which, agent, {"session_id": "s", "transcript_path": str(t)}).returncode == 0
    time.sleep(0.3)
    assert not (box["state"] / "session-hook.log").exists()


# ---------- 每轮导入留住之前的提炼 ----------

def test_a_local_import_keeps_the_digest_until_the_next_distill(box, monkeypatch):
    t = _codex_rollout(box, [("缓存过期时间改成多少？", "原来 30 分钟，改成 10 分钟。"), ("那重试呢？", "重试 3 次。")])
    monkeypatch.setenv("KROUTER_CODEX_SESSIONS", str(box["tmp"] / "codex"))
    import import_sessions as imp

    entries = imp.collect(date(1970, 1, 1), date.today(), [t])
    entries, _, _ = imp.dedupe_forks(entries, box["folder"])
    e = entries[0]
    page = box["folder"] / imp.file_name(e)
    page.write_text(imp.render(e, "- 缓存过期时间原来 30 分钟 → 改成 10 分钟"), encoding="utf-8")
    assert "digest_turns: 2" in page.read_text(encoding="utf-8")
    # 会话又多了一轮；这一轮结束时的本地导入不提炼
    t = _codex_rollout(box, [("缓存过期时间改成多少？", "原来 30 分钟，改成 10 分钟。"), ("那重试呢？", "重试 3 次。"),
                             ("超时呢？", "超时 5 秒。")])
    (box["state"] / "import.json").write_text(json.dumps({"consent": True, "distill": True, "cli": "claude"}), encoding="utf-8")
    res = subprocess.run([sys.executable, str(IMPORT), "--vault", str(box["vault"]), "--file", str(t), "--local"],
                         env=box["env"], capture_output=True, text=True, timeout=60)
    row = json.loads(res.stdout.strip().splitlines()[-1])
    assert row["distilled"] == 0 and row["chars"] == 0
    text = page.read_text(encoding="utf-8")
    assert "超时 5 秒" in text and "turns: 3" in text
    assert DIGEST in text and "改成 10 分钟" in text.split("## 摘录")[0]
    assert "digest_turns: 2" in text  # 提炼只覆盖到第 2 轮：下次提炼只发第 3 轮
    prior, done = imp.prior_digest(page, imp.dedupe_forks(imp.collect(date(1970, 1, 1), date.today(), [t]), box["folder"])[0][0])
    assert done == 2 and prior == ["- 缓存过期时间原来 30 分钟 → 改成 10 分钟"]


def test_plugin_hooks_also_record_each_claude_code_turn():
    hooks = json.loads((REPO / "hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]
    assert hooks["Stop"][0]["hooks"][0]["command"].endswith("session_hook.py\" turn")


# ---------- 安装：并进各家的钩子文件 ----------

@pytest.fixture()
def apps(tmp_path, monkeypatch):
    """A home with Codex and Cursor installed (their folders exist), nothing in their hooks files yet."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex"))
    monkeypatch.setenv("KROUTER_SKILL_HOME", str(tmp_path / "skill"))
    monkeypatch.delenv("KROUTER_NO_HOOKS", raising=False)
    for k in ("KROUTER_HOOKS_CONFIG_CODEX", "KROUTER_HOOKS_CONFIG_CURSOR"):
        monkeypatch.delenv(k, raising=False)
    (tmp_path / ".codex").mkdir()
    bootstrap.app_settings("Cursor").mkdir(parents=True)
    return {"codex": tmp_path / ".codex/hooks.json", "cursor": tmp_path / ".cursor/hooks.json", "home": tmp_path}


T = bootstrap.MSG["en"]


def _commands(cfg: Path, codex: bool) -> dict[str, list[str]]:
    hooks = json.loads(cfg.read_text(encoding="utf-8"))["hooks"]
    if codex:
        return {ev: [h["command"] for g in groups for h in g["hooks"]] for ev, groups in hooks.items()}
    return {ev: [h["command"] for h in groups] for ev, groups in hooks.items()}


def test_installer_writes_each_apps_own_format(apps, capsys):
    assert bootstrap.register_hooks(T, dry=False) == ["codex", "cursor"]
    codex = json.loads(apps["codex"].read_text(encoding="utf-8"))
    assert set(codex) == {"hooks"}  # Codex 只认顶层 "hooks"
    assert set(codex["hooks"]) == {"SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"}
    end = codex["hooks"]["SessionEnd"][0]["hooks"][0]
    assert end["type"] == "command" and end["timeout"] == 3 and end["command"].endswith("session_hook.py end --agent codex")
    cursor = json.loads(apps["cursor"].read_text(encoding="utf-8"))
    assert cursor["version"] == 1 and set(cursor["hooks"]) == {"sessionStart", "beforeSubmitPrompt", "stop", "sessionEnd"}
    stop = cursor["hooks"]["stop"][0]
    assert stop["command"].endswith("session_hook.py turn --agent cursor") and "failClosed" not in stop
    out = capsys.readouterr().out
    assert "/hooks" in out  # Codex 要先在 /hooks 里信任


def test_installer_keeps_every_hook_already_there_and_is_idempotent(apps):
    apps["codex"].write_text(json.dumps({"description": "mine", "hooks": {"Stop": [{"hooks": [
        {"type": "command", "command": "/usr/bin/python3 /me/stop.py"}]}]}}), encoding="utf-8")
    apps["cursor"].parent.mkdir(parents=True, exist_ok=True)
    mine = {"version": 1, "hooks": {
        "beforeShellExecution": [{"command": "python3 /me/exec-gate.py", "failClosed": True}],
        "beforeSubmitPrompt": [{"command": "python3 /me/ask-product.py", "failClosed": False}]}}
    apps["cursor"].write_text(json.dumps(mine), encoding="utf-8")
    bootstrap.register_hooks(T, dry=False)
    first = {k: p.read_text(encoding="utf-8") for k, p in apps.items() if k != "home"}
    bootstrap.register_hooks(T, dry=False)  # 再装一次：不重复
    assert {k: p.read_text(encoding="utf-8") for k, p in apps.items() if k != "home"} == first
    codex = _commands(apps["codex"], True)
    assert codex["Stop"][0] == "/usr/bin/python3 /me/stop.py" and len(codex["Stop"]) == 2
    assert json.loads(first["codex"])["description"] == "mine"
    cursor = json.loads(first["cursor"])["hooks"]
    assert cursor["beforeShellExecution"] == mine["hooks"]["beforeShellExecution"]
    assert cursor["beforeSubmitPrompt"][0] == mine["hooks"]["beforeSubmitPrompt"][0] and len(cursor["beforeSubmitPrompt"]) == 2
    assert apps["cursor"].with_name("hooks.json.krouter-bak").is_file()


def test_a_codex_file_codex_cannot_read_is_left_alone(apps, capsys):
    # 事件名直接放在顶层：Codex 报 unknown field 并跳过整份文件。不替人改，说清楚
    old = json.dumps({"Stop": [{"hooks": [{"type": "command", "command": "python3 /me/stop.py"}]}]})
    apps["codex"].write_text(old, encoding="utf-8")
    assert "codex" not in bootstrap.register_hooks(T, dry=False)
    assert apps["codex"].read_text(encoding="utf-8") == old
    assert "top-level \"hooks\"" in capsys.readouterr().out


@pytest.mark.parametrize("which", ["codex", "cursor"])
def test_a_file_that_is_not_json_is_left_alone(apps, which):
    apps[which].parent.mkdir(parents=True, exist_ok=True)
    apps[which].write_text("{ // comment\n}", encoding="utf-8")
    assert which not in bootstrap.register_hooks(T, dry=False)
    assert apps[which].read_text(encoding="utf-8") == "{ // comment\n}"


def test_an_app_that_is_not_installed_gets_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex"))
    monkeypatch.delenv("KROUTER_NO_HOOKS", raising=False)
    (tmp_path / ".cursor").mkdir()  # install.sh 放 Cursor 规则时会建它：不算 Cursor 装了
    assert bootstrap.register_hooks(T, dry=False) == []
    assert not any(tmp_path.rglob("hooks.json"))


def test_uninstall_takes_out_only_ours(apps):
    apps["cursor"].parent.mkdir(parents=True, exist_ok=True)
    apps["cursor"].write_text(json.dumps({"version": 1, "hooks": {"stop": [{"command": "python3 /me/audit.py"}]}}),
                              encoding="utf-8")
    bootstrap.register_hooks(T, dry=False)
    assert sorted(bootstrap.unregister_hooks(dry=False)) == ["codex", "cursor"]
    assert json.loads(apps["cursor"].read_text(encoding="utf-8"))["hooks"] == {"stop": [{"command": "python3 /me/audit.py"}]}
    assert json.loads(apps["codex"].read_text(encoding="utf-8"))["hooks"] == {}
    assert bootstrap.unregister_hooks(dry=False) == []


def test_codex_hooks_turned_off_is_reported(apps, capsys):
    (apps["home"] / ".codex/config.toml").write_text('model = "x"\n\n[features]\nhooks = false\n', encoding="utf-8")
    assert bootstrap.codex_hooks_off()
    bootstrap.register_hooks(T, dry=False)
    assert "hooks = false" in capsys.readouterr().out
    (apps["home"] / ".codex/config.toml").write_text('[features]\nmemories = true\n', encoding="utf-8")
    assert not bootstrap.codex_hooks_off()


def test_the_hook_command_runs_as_written(apps, box):
    """The command the installer writes is a real command line: run it the way the app would (through a shell)."""
    skill = apps["home"] / "skill"
    shutil.copytree(SCRIPTS, skill / "scripts")
    bootstrap.register_hooks(T, dry=False)
    cmd = _commands(apps["cursor"], False)["beforeSubmitPrompt"][0]
    res = subprocess.run(cmd, shell=True, input=json.dumps({"conversation_id": "c", "prompt": "hi"}), env=box["env"],
                         capture_output=True, text=True, timeout=60)
    assert json.loads(res.stdout) == {"continue": True}
