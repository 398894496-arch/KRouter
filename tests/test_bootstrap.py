"""One-step install for anyone: new vault from the right template, existing vaults never overwritten, re-run = upgrade."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BOOT = REPO / "scripts/bootstrap.py"

pytestmark = pytest.mark.skipif(os.name == "nt", reason="the POSIX path calls install.sh")


def _env(tmp: Path) -> dict:
    home = tmp / "home"
    home.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.endswith(("_API_KEY", "_BASE_URL", "_MODEL"))}
    env.update({"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8",
                "KROUTER_KEYS_ENV": str(tmp / "keys.env"), "KROUTER_WRITER": "/nonexistent/grok",
                "KROUTER_SKIP_LAUNCHD": "1", "KROUTER_SKIP_TIMER": "1",
                # 每个测试自己的状态目录和应用设置目录：前一个测试记下的同意、真机上的应用都不串进来
                "KROUTER_STATE_DIR": str(tmp / "state"), "XDG_CONFIG_HOME": str(home / ".config"),
                "APPDATA": str(home / "AppData")})
    for k in ("OBSIDIAN_VAULT", "KROUTER_SKILL_HOME", "KROUTER_CURSOR_RULE", "KROUTER_ASK_RULE", "KROUTER_LEARN_CLI"):
        env.pop(k, None)
    return env


def _boot(env: dict, *args: str) -> tuple[subprocess.CompletedProcess, dict]:
    res = subprocess.run([sys.executable, str(BOOT), "--no-open", *args], env=env, capture_output=True, text=True,
                         timeout=600)
    last = res.stdout.strip().splitlines()[-1] if res.stdout.strip() else "{}"
    return res, (json.loads(last) if last.startswith("{") else {})


def test_new_chinese_vault_then_upgrade_keeps_the_table(tmp_path):
    env = _env(tmp_path)
    vault = tmp_path / "home/Documents/第二大脑"
    res, out = _boot(env, "--lang", "zh")
    assert res.returncode == 0, res.stdout[-1500:] + res.stderr[-1500:]
    assert out["vault"] == str(vault) and out["state"] == "new" and out["lang"] == "zh"
    assert (vault / "02 经验与方法/自动化/按日志文件判断封账.md").is_file()  # the Chinese template
    table = vault / "90 系统文件/canonical_sources.psv"
    assert "按日志文件判断封账" in table.read_text(encoding="utf-8")  # its own sample table, not the English one
    assert (tmp_path / "home/.agents/skills/krouter/scripts/route_knowledge.sh").is_file()
    assert "装好了" in res.stdout and "还没有可用的模型" in res.stdout  # plain-language next step, no model yet
    table.write_text(table.read_text(encoding="utf-8") + "Q99|我的名词|01 项目/项目.md|x\n", encoding="utf-8")
    res2, out2 = _boot(env, "--lang", "zh")
    assert res2.returncode == 0 and out2["state"] == "ours" and out2["added"] == 0
    assert "Q99|我的名词" in table.read_text(encoding="utf-8")


def test_existing_vault_only_gains_missing_files(tmp_path):
    env = _env(tmp_path)
    vault = tmp_path / "MyNotes"
    (vault / "Inbox").mkdir(parents=True)
    (vault / "Inbox/idea.md").write_text("# mine\n", encoding="utf-8")
    (vault / "Agent第二大脑.md").write_text("# my own home page\n", encoding="utf-8")
    res, out = _boot(env, "--lang", "en", "--vault", str(vault))
    assert res.returncode == 0, res.stderr[-1500:]
    assert out["state"] == "ours"  # it already has the home page name
    assert (vault / "Inbox/idea.md").read_text(encoding="utf-8") == "# mine\n"
    assert (vault / "Agent第二大脑.md").read_text(encoding="utf-8") == "# my own home page\n"  # never overwritten
    assert (vault / "90 系统文件/自动化/日更健康.md").is_file()  # the missing skeleton arrived


def test_dry_run_changes_nothing(tmp_path):
    env = _env(tmp_path)
    vault = tmp_path / "v"
    res, _ = _boot(env, "--lang", "en", "--vault", str(vault), "--dry-run")
    assert res.returncode == 0 and not vault.exists()
    assert not (tmp_path / "home/.agents").exists()


def test_chinese_template_alias_table_is_consistent():
    res = subprocess.run([sys.executable, str(REPO / "scripts/verify_canonical_map.py"), "--map",
                          str(REPO / "template-zh/90 系统文件/canonical_sources.psv"), "--vault", str(REPO / "template-zh")],
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0 and "failures=0" in res.stdout, res.stdout + res.stderr


def test_nightly_job_needs_an_explicit_yes(tmp_path):
    """Default → local capture on (no model, no nightly job), and it says how to stop it and how to turn the nightly
    job on; `--no-import` → lookup only; `--ask` with no terminal → no nightly job; `--timer` → installed. The nightly
    job is never installed silently."""
    env = {**_env(tmp_path), "KROUTER_NO_PROMPT": "1"}
    plist = tmp_path / "home/Library/LaunchAgents/local.dsh-krouter.daily-evolution.plist"
    res, out = _boot(env, "--lang", "en", "--vault", str(tmp_path / "v0"), "--no-import")
    assert res.returncode == 0 and "lookup only" in res.stdout and "keeps up by itself" not in res.stdout
    res, out = _boot(env, "--lang", "en", "--vault", str(tmp_path / "v1"))
    assert res.returncode == 0 and out["timer"] is False and out["distilled"] == 0
    assert "keeps up by itself" in res.stdout and "--revoke" in res.stdout and "--ask" in res.stdout
    res, out = _boot(env, "--lang", "en", "--vault", str(tmp_path / "v1"), "--ask")
    assert res.returncode == 0 and out["timer"] is False and "needs your yes" in res.stdout
    assert not plist.exists() and not (tmp_path / "home/.config/systemd").exists()
    res, out = _boot(env, "--lang", "en", "--vault", str(tmp_path / "v2"), "--timer")
    assert res.returncode == 0 and out["timer"] is True
    if sys.platform == "darwin":
        assert plist.is_file()


def test_consent_prompt_says_what_runs_and_what_is_sent(tmp_path, monkeypatch):
    sys.path.insert(0, str(REPO / "scripts"))
    import bootstrap as bs

    asked = []
    monkeypatch.setattr(bs, "nightly_preview", lambda vault: ("claude", "claude", 12, 4000))
    monkeypatch.setattr(bs, "ask_tty", lambda prompt: asked.append(prompt) or "y")
    args = bs.argparse.Namespace(timer=False, no_timer=False, ask=True)
    assert bs.decide_timer(args, tmp_path, bs.MSG["zh"]) == (True, True)
    assert "claude" in asked[0] and "12 页" in asked[0] and "4000" in asked[0]
    assert "API key" in asked[0].splitlines()[0]  # the safer lane is offered first
    assert "没有内核沙箱" in asked[0]  # and what the CLI lane can still do is said plainly
    monkeypatch.setattr(bs, "ask_tty", lambda prompt: "")
    assert bs.decide_timer(args, tmp_path, bs.MSG["en"]) == (False, True)  # Enter alone means no


@pytest.mark.skipif(__import__("shutil").which("npm") is None, reason="needs npm to build the release package")
def test_bootstrap_sh_verifies_the_release_checksum(tmp_path):
    """The one-line install unpacks the release package only when its SHA-256 matches SHA256SUMS."""
    import hashlib
    import shutil as sh
    import threading
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    pkg_dir = tmp_path / "srv"
    pkg_dir.mkdir()
    subprocess.run(["npm", "pack", "--pack-destination", str(pkg_dir)], cwd=REPO, capture_output=True, check=True)
    tgz = next(pkg_dir.glob("dsh-krouter-*.tgz"))
    ver = tgz.name[len("dsh-krouter-"):-len(".tgz")]
    digest = hashlib.sha256(tgz.read_bytes()).hexdigest()
    handler = partial(SimpleHTTPRequestHandler, directory=str(pkg_dir))
    handler.log_message = lambda *a: None
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    script = tmp_path / "bootstrap.sh"
    sh.copy(REPO / "scripts/bootstrap.sh", script)  # run outside the clone, as `curl | sh` would
    env = {**_env(tmp_path), "KROUTER_TAG": f"v{ver}", "KROUTER_RELEASE_BASE": base, "KROUTER_HOME": str(tmp_path / "kh"),
           "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}
    try:
        (pkg_dir / "SHA256SUMS").write_text("0" * 64 + f"  {tgz.name}\n", encoding="utf-8")
        bad = subprocess.run(["/bin/sh", str(script), "--dry-run"], env=env, capture_output=True, text=True, timeout=300)
        assert bad.returncode == 1 and "checksum mismatch" in bad.stdout
        assert not (tmp_path / "kh" / f"v{ver}").exists()
        (pkg_dir / "SHA256SUMS").unlink()  # no checksum file: stop, never fall back silently
        none = subprocess.run(["/bin/sh", str(script), "--dry-run"], env=env, capture_output=True, text=True, timeout=300)
        assert none.returncode == 1 and "KROUTER_ALLOW_UNVERIFIED" in none.stdout
        assert not (tmp_path / "kh" / f"v{ver}").exists()
        (pkg_dir / "SHA256SUMS").write_text(f"{digest}  {tgz.name}\n", encoding="utf-8")
        good = subprocess.run(["/bin/sh", str(script), "--dry-run", "--lang", "en", "--vault", str(tmp_path / "v")],
                              env=env, capture_output=True, text=True, timeout=300)
        assert good.returncode == 0, good.stdout[-800:] + good.stderr[-800:]
        assert "sha256 verified" in good.stdout
        assert (tmp_path / "kh" / f"v{ver}" / "scripts/bootstrap.py").is_file()
    finally:
        server.shutdown()


def test_powershell_scripts_are_ascii_and_never_exit_the_users_session():
    """PS 5.1 reads BOM-less scripts in the ANSI code page; `exit` under `irm | iex` closes the user's window."""
    for name in ("bootstrap.ps1", "install_windows_task.ps1"):
        data = (REPO / "scripts" / name).read_bytes()
        assert all(b < 128 for b in data), name
    lines = (REPO / "scripts/bootstrap.ps1").read_text(encoding="ascii").splitlines()
    assert not [ln for ln in lines if ln.strip().startswith("exit")]


def test_install_records_from_now_by_default_and_imports_past_sessions_only_when_asked(tmp_path):
    """`--no-import` → lookup only; the default (no terminal, no flag) → nothing from the past is imported, turns are
    recorded from now on (consent recorded), and the last line says the one command that imports the last 7 days;
    `--all` imports them (the old default), with no model call. The vault path is recorded so agents and the MCP
    server find it without an environment variable."""
    projects = tmp_path / "projects/-work"
    projects.mkdir(parents=True)
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).isoformat()
    (projects / "s1.jsonl").write_text(json.dumps({"type": "user", "timestamp": ts, "cwd": "/work", "message": {
        "role": "user", "content": "缓存过期改成多少"}}, ensure_ascii=False) + "\n", encoding="utf-8")
    vf = tmp_path / "vault-file"
    env = {**_env(tmp_path), "KROUTER_NO_PROMPT": "1", "KROUTER_CLAUDE_PROJECTS": str(tmp_path / "projects"),
           "KROUTER_VAULT_FILE": str(vf)}
    res, out = _boot(env, "--lang", "zh", "--vault", str(tmp_path / "v1"), "--no-timer", "--no-import")
    assert res.returncode == 0 and out["imported"] == 0 and "只查询" in res.stdout and "--ask" in res.stdout
    assert not (tmp_path / "v1/05 时间日志/会话摘录").exists()
    assert vf.read_text(encoding="utf-8").strip() == str((tmp_path / "v1").resolve())
    res, out = _boot(env, "--lang", "zh", "--vault", str(tmp_path / "v2"), "--no-timer")
    assert res.returncode == 0 and out["imported"] == 0, res.stdout[-1500:]
    assert "从现在起它自己记" in res.stdout and "以前的会话没有导入" in res.stdout and "--consent" in res.stdout
    assert not list((tmp_path / "v2/05 时间日志/会话摘录").glob("*.md"))
    assert json.loads((tmp_path / "state/import.json").read_text(encoding="utf-8"))["consent"] is True  # 钩子从现在起记
    res, out = _boot(env, "--lang", "zh", "--vault", str(tmp_path / "v3"), "--no-timer", "--all")
    assert res.returncode == 0 and out["imported"] == 1 and out["distilled"] == 0, res.stdout[-1500:]
    assert "从现在起它自己记" in res.stdout and "不调任何模型" in res.stdout
    assert len(list((tmp_path / "v3/05 时间日志/会话摘录").glob("*.md"))) == 1
    assert "现在就可以问你的 agent" in res.stdout


def test_install_offers_claude_mem_and_imports_it_on_a_yes(tmp_path):
    from test_import_claude_mem import _db

    db = _db(tmp_path / "claude-mem.db")
    env = {**_env(tmp_path), "KROUTER_NO_PROMPT": "1", "KROUTER_CLAUDE_MEM_DB": str(db),
           "KROUTER_VAULT_FILE": str(tmp_path / "vf")}
    res, out = _boot(env, "--lang", "zh", "--vault", str(tmp_path / "v1"), "--no-timer", "--no-import")
    assert res.returncode == 0 and out["claude_mem"] == 0  # --no-import：不导
    res, out = _boot(env, "--lang", "zh", "--vault", str(tmp_path / "v2"), "--no-timer")  # 默认：不导以前的
    assert res.returncode == 0 and out["claude_mem"] == 0, res.stdout[-1500:]
    res, out = _boot(env, "--lang", "zh", "--vault", str(tmp_path / "v2"), "--no-timer", "--all")  # --all：导
    assert res.returncode == 0 and out["claude_mem"] == 3, res.stdout[-1500:]
    assert "从 claude-mem 导入了 3 个会话、4 条决定和改动" in res.stdout
    assert (tmp_path / "v2/02 经验与方法/从 claude-mem 导入/shop 的决定（claude-mem）.md").is_file()


def test_default_install_asks_nothing_and_an_upgrade_keeps_what_is_on(tmp_path, monkeypatch):
    """Without `--ask` no question is put: nothing from the past is imported (no preview, no model; `main` records
    consent so turns are kept from now on), `--no-import` records nothing; a host who said yes before is not told it
    is off."""
    sys.path.insert(0, str(REPO / "scripts"))
    import bootstrap as bs
    import import_sessions

    monkeypatch.setattr(bs, "ask_tty", lambda prompt: pytest.fail("asked: " + prompt))
    monkeypatch.setattr(bs, "run_import", lambda *a: pytest.fail("previewed an import"))
    monkeypatch.setattr(bs, "run_claude_mem", lambda *a: pytest.fail("previewed claude-mem"))
    args = bs.argparse.Namespace(timer=False, no_timer=False, ask=False, no_import=False, import_sessions=False,
                                 import_distill=False)
    assert bs.decide_timer(args, tmp_path, bs.MSG["en"]) == (False, True)
    assert bs.decide_import(args, tmp_path, bs.MSG["en"], "claude") == (False, False, False)  # 不导以前的
    assert bs.offer_claude_mem(args, tmp_path, bs.MSG["en"], False) == {}
    off = bs.argparse.Namespace(**{**vars(args), "no_import": True})
    assert bs.decide_import(off, tmp_path, bs.MSG["en"], "claude") == (False, False, False)
    assert bs.offer_claude_mem(off, tmp_path, bs.MSG["en"], False) == {}
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(bs.shutil, "which", lambda name: None)
    monkeypatch.setattr(import_sessions, "load_state", lambda: {"consent": True})
    assert bs.remembering_already()
    monkeypatch.setattr(import_sessions, "load_state", lambda: {})
    assert not bs.remembering_already()
    plist = tmp_path / "Library/LaunchAgents/local.dsh-krouter.daily-evolution.plist"
    plist.parent.mkdir(parents=True)
    plist.write_text("", encoding="utf-8")
    assert bs.remembering_already()


def test_timer_that_did_not_install_is_not_reported_as_installed(monkeypatch, capsys):
    """A machine with no scheduler (a Linux container: no systemd user session, no crontab) gets no nightly job; the
    install said "HOST ACTION" but its summary, the health page and `doctor` then claimed one ran (found in the
    2.0.0 container test). `timer_took` is the check after the installer ran; the tests' explicit skip is trusted."""
    sys.path.insert(0, str(REPO / "scripts"))
    import bootstrap as bs

    t = bs.MSG["en"]
    monkeypatch.delenv("KROUTER_SKIP_TIMER", raising=False)
    monkeypatch.setattr(bs, "remembering_timer", lambda: False)
    assert bs.timer_took(t) is False
    assert "NOT installed" in capsys.readouterr().out
    monkeypatch.setattr(bs, "remembering_timer", lambda: True)
    assert bs.timer_took(t) is True
    monkeypatch.setattr(bs, "remembering_timer", lambda: False)
    monkeypatch.setenv("KROUTER_SKIP_TIMER", "1")
    assert bs.timer_took(t) is True
    assert bs.MSG["zh"]["timer_failed"] and bs.MSG["zh"]["capture_how_timer"]


def test_windows_upgrade_keeps_the_table_and_falls_back_to_a_junction(tmp_path, monkeypatch):
    """The Windows branch of the 2.0 move, run on any OS: the pre-2.0 `krouter-obsidian` folder is replaced by the new
    skill with the user's alias table carried over, and when a symlink cannot be made (Windows without developer mode
    or admin) the old path is made a directory junction with `cmd /c mklink /J`. Not run on a real Windows machine
    (none was reachable for 2.0.0); this pins the logic, `docs/VERIFY.md` says what was and was not run there."""
    sys.path.insert(0, str(REPO / "scripts"))
    import bootstrap as bs

    home = tmp_path / "home"
    old = home / ".agents/skills/krouter-obsidian"
    (old / "scripts").mkdir(parents=True)
    (old / "scripts/canonical_sources.psv").write_text("Q99|我的名词|01 项目/项目.md|x\n", encoding="utf-8")
    (old / "scripts/route_knowledge.py").write_text("# the 1.x router\n", encoding="utf-8")
    vault = tmp_path / "vault"
    (vault / "90 系统文件").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for k in ("KROUTER_SKILL_HOME", "KROUTER_CURSOR_RULE", "KROUTER_ASK_RULE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("KROUTER_NO_CURSOR_RULES", "1")
    real_symlink, real_run = os.symlink, subprocess.run
    calls = []

    def no_symlink(*a, **k):
        raise OSError("A required privilege is not held by the client")

    def fake_run(argv, *a, **k):
        if isinstance(argv, list) and argv[:3] == ["cmd", "/c", "mklink"]:
            calls.append(argv)
            real_symlink(argv[5], argv[4], target_is_directory=True)  # stand in for the junction
            return subprocess.CompletedProcess(argv, 0, "", "")
        return real_run(argv, *a, **k)

    monkeypatch.setattr(bs.os, "symlink", no_symlink)
    monkeypatch.setattr(bs.subprocess, "run", fake_run)
    assert bs.legacy_skill_home() == old
    assert bs.install_windows(vault, False, False) == 0
    new = home / ".agents/skills/krouter"
    assert (new / "SKILL.md").is_file()
    assert "Q99|我的名词" in (new / "scripts/canonical_sources.psv").read_text(encoding="utf-8")
    assert "Q99|我的名词" in (vault / "90 系统文件/canonical_sources.psv").read_text(encoding="utf-8")
    assert calls == [["cmd", "/c", "mklink", "/J", str(old), str(new)]]
    assert old.is_symlink() and old.resolve() == new.resolve()  # the old path leads to the new folder
    assert bs.legacy_skill_home() is None  # a second run sees an upgraded install
