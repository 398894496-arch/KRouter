"""Claude Code hooks: a new session gets this repository's recorded decisions; an ended one is imported. Both only
after the host said yes to importing. A repository is its git top level (else its directory), never its folder name."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "skill/krouter-obsidian/scripts/session_hook.py"
DIGEST = "## 定了什么、改了什么（模型提炼，待你确认）"


def _root(path: Path) -> str:
    sys.path.insert(0, str(REPO / "skill/krouter-obsidian/scripts"))
    from krouter_home import project_root

    return project_root(str(path))


def _page(folder: Path, name: str, root: str, lines: list[str], day: str | None = None, extra: str = "") -> None:
    day = day or date.today().isoformat()
    body = "\n".join(f"- {ln}" for ln in lines)
    (folder / f"{day}｜{name}.md").write_text(
        f"---\nsource: krouter-import\nstatus: imported\ndate: {day}\nproject: {Path(root).name}\n"
        f"project_root: {root}\n{extra}---\n\n# {name}\n\n{DIGEST}\n\n{body}\n\n## 摘录\n\n- **问**：…\n", encoding="utf-8")


def _setup(tmp_path: Path, consent: bool = True) -> dict:
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template", vault)
    folder = vault / "05 时间日志/会话摘录"
    folder.mkdir(parents=True)
    shop = tmp_path / "work/shop"
    shop.mkdir(parents=True)
    root = _root(shop)
    _page(folder, "发版", root, ["发版只从 main 打 tag（10:05）", "原来手动上传 → 改成 CI 发布（10:20）"])
    _page(folder, "已确认", root, ["数据库每晚 02:00 备份"], extra="confirmed: true\n")
    _page(folder, "旧事", root, ["原来 A → 改成 B（很久以前）"], day="2020-01-01")
    state = tmp_path / "state"
    state.mkdir()
    if consent:
        (state / "import.json").write_text(json.dumps({"consent": True}), encoding="utf-8")
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_STATE_DIR": str(state), "KROUTER_NO_QUERY_LOG": "1"}
    env.pop("KROUTER_INJECT", None)
    return {"vault": vault, "env": env, "state": state, "folder": folder, "shop": shop, "tmp": tmp_path}


def _hook(env: dict, which: str, payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(HOOK), which], input=json.dumps(payload), env=env,
                          capture_output=True, text=True, timeout=60)


def _ctx(res: subprocess.CompletedProcess) -> str:
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)["hookSpecificOutput"]["additionalContext"] if res.stdout.strip() else ""


def test_start_brings_every_distilled_decision_with_its_page_and_no_human_gate(tmp_path):
    """Distilling writes memory without a yes (the change ledger shows what it wrote), so every line is brought in,
    corrections first, none marked as awaiting confirmation."""
    s = _setup(tmp_path)
    ctx = _ctx(_hook(s["env"], "start", {"cwd": str(s["shop"])}))
    lines = ctx.splitlines()
    assert "shop" in lines[0] and "待确认" not in ctx
    assert lines[1].startswith("- 原来手动上传 → 改成 CI 发布") and "05 时间日志/会话摘录/" in lines[1]
    assert "- 数据库每晚 02:00 备份 〔" in ctx
    assert "- 发版只从 main 打 tag（10:05） 〔" in ctx
    assert "很久以前" not in ctx  # 30 天外
    assert "krouter_ask" in lines[-1]


def test_inject_confirmed_keeps_the_old_gate(tmp_path):
    s = _setup(tmp_path)
    strict = _ctx(_hook({**s["env"], "KROUTER_INJECT": "confirmed"}, "start", {"cwd": str(s["shop"])}))
    assert "发版只从 main 打 tag" not in strict  # 没确认、也不是纠错：不带
    assert "改成 CI 发布（10:20）（待确认）" in strict and "- 数据库每晚 02:00 备份 〔" in strict


def test_same_folder_name_in_two_repos_never_shares_decisions(tmp_path):
    """The outside review's repro: alpha/api and beta/api. A session in beta must not see alpha's decisions."""
    s = _setup(tmp_path)
    alpha, beta = tmp_path / "alpha/api", tmp_path / "beta-corp/api"
    for d in (alpha, beta):
        d.mkdir(parents=True)
    _page(s["folder"], "alpha 的约定", _root(alpha), ["原来 alpha 用 X → 改成 alpha 用 Y"])
    _page(s["folder"], "beta 的约定", _root(beta), ["原来 beta 用 P → 改成 beta 用 Q"])
    ctx = _ctx(_hook(s["env"], "start", {"cwd": str(beta)}))
    assert "beta 用 Q" in ctx and "alpha" not in ctx
    (beta / "src").mkdir()
    sub = _ctx(_hook(s["env"], "start", {"cwd": str(beta / "src")}))
    assert "alpha" not in sub  # 子目录不是 git 仓库时就是它自己，不会去匹配别人
    # 1.0.0 导入的旧页只有 project（文件夹名），没有 project_root：一律不带
    (s["folder"] / "2026-10-12｜旧版本页.md").write_text(
        f"---\nsource: krouter-import\ndate: {date.today().isoformat()}\nproject: api\n---\n\n{DIGEST}\n\n"
        "- 原来 旧 → 改成 新\n\n## 摘录\n", encoding="utf-8")
    assert "旧 → 改成 新" not in _ctx(_hook(s["env"], "start", {"cwd": str(beta)}))


def test_git_repo_is_matched_from_any_subdirectory(tmp_path):
    if not shutil.which("git"):
        return
    s = _setup(tmp_path)
    repo = tmp_path / "gitrepo"
    (repo / "pkg/deep").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _page(s["folder"], "仓库约定", _root(repo), ["原来 tabs → 改成 spaces"])
    assert "改成 spaces" in _ctx(_hook(s["env"], "start", {"cwd": str(repo / "pkg/deep")}))


def test_header_follows_the_language_of_the_lines(tmp_path):
    s = _setup(tmp_path)
    en = tmp_path / "en-repo"
    en.mkdir()
    _page(s["folder"], "english", _root(en), ["Was: manual uploads → now: CI uploads (10:20)"])
    ctx = _ctx(_hook(s["env"], "start", {"cwd": str(en)}))
    assert ctx.startswith("KRouter: decisions recorded") and "(unconfirmed)" not in ctx and "krouter_ask" in ctx
    assert not any("一" <= ch <= "鿿" for ch in ctx.replace("05 时间日志/会话摘录", ""))


def test_start_is_silent_without_consent_without_decisions_or_when_turned_off(tmp_path):
    s = _setup(tmp_path, consent=False)
    assert _hook(s["env"], "start", {"cwd": str(s["shop"])}).stdout == ""
    s = _setup(tmp_path / "b")
    assert _hook(s["env"], "start", {"cwd": str(tmp_path / "nowhere")}).stdout == ""
    assert _hook({**s["env"], "KROUTER_INJECT": "0"}, "start", {"cwd": str(s["shop"])}).stdout == ""
    bad = subprocess.run([sys.executable, str(HOOK), "start"], input="not json", env=s["env"], capture_output=True,
                         text=True, timeout=60)
    assert bad.returncode == 0  # hook 永远不让会话失败


def test_end_imports_the_session_that_just_ended(tmp_path):
    s = _setup(tmp_path)
    work = tmp_path / "work/api"
    work.mkdir(parents=True)
    projects = tmp_path / "projects/-work-api"
    projects.mkdir(parents=True)
    ts = datetime.now(timezone.utc).isoformat()
    transcript = projects / "dddd4444-s.jsonl"
    transcript.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
        {"type": "user", "timestamp": ts, "cwd": str(work), "message": {"role": "user", "content": "超时改成多少"}},
        {"type": "assistant", "timestamp": ts, "message": {"content": [{"type": "text", "text": "改成 10 秒。"}]}},
        {"type": "custom-title", "customTitle": "超时设置"}]) + "\n", encoding="utf-8")
    env = {**s["env"], "KROUTER_CLAUDE_PROJECTS": str(tmp_path / "projects")}
    res = _hook(env, "end", {"session_id": "dddd4444-s", "transcript_path": str(transcript), "cwd": str(work)})
    assert res.returncode == 0 and res.stdout == ""
    page = ""
    for _ in range(150):  # 导入在后台跑，不拖住 Claude Code；只认写完的 .md，不碰正在写的 .md.tmp
        found = list(s["folder"].glob("*超时设置*.md"))
        if found:
            try:
                page = found[0].read_text(encoding="utf-8")
                break
            except OSError:  # Windows：文件刚换上、还被占着
                pass
        time.sleep(0.1)
    assert "project: api" in page and f"project_root: {_root(work)}" in page and "改成 10 秒。" in page


def test_end_does_nothing_without_consent(tmp_path):
    s = _setup(tmp_path, consent=False)
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")
    assert _hook(s["env"], "end", {"transcript_path": str(transcript)}).returncode == 0
    time.sleep(0.5)
    assert not (s["state"] / "session-hook.log").exists()


def test_plugin_declares_its_hooks():
    # 纠正就记（UserPromptSubmit）和压缩前记一笔（PreCompact）也随插件装上；同意导入之前它们什么都不做
    hooks = json.loads((REPO / "hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]
    assert set(hooks) == {"SessionStart", "SessionEnd", "UserPromptSubmit", "PreCompact"}
    mode = {ev: hooks[ev][0]["hooks"][0]["command"].rsplit("\" ", 1)[1] for ev in hooks}
    assert mode == {"SessionStart": "start", "SessionEnd": "end", "UserPromptSubmit": "prompt", "PreCompact": "end"}
