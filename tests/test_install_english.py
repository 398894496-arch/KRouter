"""English installs have English names end to end; the install is light and says what it changes; uninstall takes
the Claude Code plugin out; `krouter doctor` gives one verdict. Chinese and default-layout vaults keep working."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter/scripts"
BOOT = REPO / "scripts/bootstrap.py"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(REPO / "scripts"))
import zones  # noqa: E402

CJK = re.compile(r"[　-〿一-鿿！-／：-＠]")
POSIX = pytest.mark.skipif(os.name == "nt", reason="POSIX install scripts")


def _english_vault(tmp: Path) -> Path:
    vault = tmp / "vault"
    zones.lay_out(REPO / "template", vault, alias_sample=SCRIPTS / "canonical_sources.psv")
    return vault


def test_english_layout_has_no_chinese_paths_and_its_links_and_alias_table_resolve(tmp_path):
    v = _english_vault(tmp_path)
    files = [p.relative_to(v).as_posix() for p in v.rglob("*") if p.is_file()]
    assert files and not [f for f in files if CJK.search(f)]
    assert zones.lang(v) == "en" and zones.real(v, "05 时间日志/会话摘录") == "05 Journal/Sessions"
    for p in v.rglob("*.md"):
        assert not CJK.search(p.read_text(encoding="utf-8").replace("｜", "")), p  # links rewritten too
    rows = [ln.split("|") for ln in (v / "90 System/canonical_sources.psv").read_text(encoding="utf-8").splitlines()
            if ln and not ln.startswith("#")]
    for row in rows:
        assert (v / row[2]).is_file(), row  # every alias points at a page that exists under its English name
        assert not CJK.search(row[1])
    assert zones.lay_out(REPO / "template", v) == []  # re-running adds nothing, overwrites nothing


def test_a_default_layout_vault_is_untouched_by_the_english_table(tmp_path):
    v = tmp_path / "v"
    shutil.copytree(REPO / "template", v)
    assert zones.lang(v) == "zh" and zones.real(v, "90 系统文件") == "90 系统文件"
    import bootstrap as bs

    assert bs.layout_for(v, "en") is None  # an English user's vault that already uses the default names keeps them
    assert bs.layout_for(tmp_path / "new", "en") == zones.EN_TABLE
    assert bs.layout_for(tmp_path / "new", "zh") is None


@POSIX
@pytest.mark.parametrize("sh_only", ["0", "1"])
def test_router_status_and_search_on_an_english_vault_are_english(tmp_path, sh_only):
    v = _english_vault(tmp_path)
    env = {**os.environ, "OBSIDIAN_VAULT": str(v), "KROUTER_SH_ONLY": sh_only, "KROUTER_NO_QUERY_LOG": "1",
           "KROUTER_CACHE_DIR": str(tmp_path / "cache"), "HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path / "cfg")}
    env.pop("KROUTER_MAP", None)

    def route(*a: str) -> str:
        return subprocess.run(["/bin/sh", str(SCRIPTS / "route_knowledge.sh"), *a], env=env, capture_output=True,
                              text=True, timeout=60).stdout

    status = route("status")
    assert f"source: {v}/Home.md" in status and "90 System/Automation/Model key.md" in status
    assert not CJK.search(status), status
    hit = route("search", "home")
    assert "canonical_id: Q01" in hit and f"{v}/Home.md" in hit and not CJK.search(hit)


def test_language_order_flag_then_locale_then_system(monkeypatch):
    import bootstrap as bs

    for k in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(bs.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(bs.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, '(\n    "zh-Hans-CN"\n)', ""))
    assert bs.system_lang() == "zh"  # nothing in the environment: the Mac's language
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert bs.system_lang() == "en"  # an English terminal on a Chinese Mac gets English
    monkeypatch.setenv("LC_ALL", "zh_CN.UTF-8")
    assert bs.system_lang() == "zh"  # LC_ALL outranks LANG
    monkeypatch.setenv("LC_ALL", "C")
    assert bs.system_lang() == "en"  # C says nothing; LANG decides


def test_obsidian_opens_only_for_a_person_at_a_terminal(monkeypatch):
    import bootstrap as bs

    ns = lambda **k: bs.argparse.Namespace(**{"open": False, "no_open": False, **k})  # noqa: E731
    monkeypatch.setattr(bs, "interactive", lambda: False)
    assert not bs.should_open(ns())  # run by an agent: never
    assert bs.should_open(ns(open=True))
    monkeypatch.setattr(bs, "interactive", lambda: True)
    assert bs.should_open(ns()) and not bs.should_open(ns(no_open=True))


def _env(tmp: Path) -> dict:
    home = tmp / "home"
    home.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.endswith(("_API_KEY", "_BASE_URL", "_MODEL"))}
    env.update({"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8",
                "LC_ALL": "en_US.UTF-8", "KROUTER_KEYS_ENV": str(tmp / "keys.env"), "KROUTER_WRITER": "/nonexistent/grok",
                "KROUTER_SKIP_LAUNCHD": "1", "KROUTER_SKIP_TIMER": "1", "KROUTER_NO_PROMPT": "1",
                "KROUTER_STATE_DIR": str(tmp / "state"), "XDG_CONFIG_HOME": str(home / ".config"),
                "APPDATA": str(home / "AppData"), "KROUTER_NO_QUERY_LOG": "1"})
    for k in ("OBSIDIAN_VAULT", "KROUTER_SKILL_HOME", "KROUTER_CURSOR_RULE", "KROUTER_ASK_RULE", "KROUTER_LEARN_CLI"):
        env.pop(k, None)
    return env


def _boot(env: dict, *args: str) -> tuple[subprocess.CompletedProcess, dict]:
    res = subprocess.run([sys.executable, str(BOOT), "--no-open", *args], env=env, capture_output=True, text=True,
                         timeout=600)
    last = res.stdout.strip().splitlines()[-1] if res.stdout.strip() else "{}"
    return res, (json.loads(last) if last.startswith("{") else {})


@POSIX
def test_english_install_writes_no_chinese_path_or_line_and_the_lamp_tells_the_truth(tmp_path):
    env = _env(tmp_path)
    res, out = _boot(env, "--lang", "en")
    assert res.returncode == 0, res.stdout[-1500:] + res.stderr[-1500:]
    vault = Path(out["vault"])
    assert vault.name == "Second Brain" and (vault / zones.ZONES_FILE).is_file()
    made = [p.relative_to(vault).as_posix() for p in vault.rglob("*") if p.is_file()]
    assert not [f for f in made if CJK.search(f)]
    printed = "\n".join(ln for ln in res.stdout.splitlines() if not ln.startswith("{"))
    assert not CJK.search(printed), [ln for ln in printed.splitlines() if CJK.search(ln)]
    # what still holds a change of mind with no model, and what does not, not just the gap
    assert "Without a model" in printed and "krouter_correct" in printed and "leave the older page first" in printed
    assert "scripts/krouter doctor" in printed and "uninstall.sh" in printed
    health = (vault / "90 System/Automation/Daily health.md").read_text(encoding="utf-8")
    assert "lamp: unused" in health  # no nightly job was installed, so it is not shown as running


@POSIX
def test_minimal_install_only_looks_up(tmp_path):
    env = _env(tmp_path)
    res, out = _boot(env, "--lang", "en", "--minimal")
    assert res.returncode == 0, res.stderr[-1500:]
    home = tmp_path / "home"
    assert out["mcp"] == [] and out["hooks"] == [] and out["imported"] == 0 and out["timer"] is False
    assert not (home / ".cursor").exists()  # no Cursor rules unless Cursor is named
    assert (home / ".agents/skills/krouter/scripts/route_knowledge.sh").is_file()
    assert "Minimal install" in res.stdout and "keeps up by itself" not in res.stdout


@POSIX
def test_dry_run_lists_every_file_and_setting_and_changes_nothing(tmp_path):
    env = _env(tmp_path)
    vault = tmp_path / "v"
    res, _ = _boot(env, "--lang", "en", "--vault", str(vault), "--dry-run")
    assert res.returncode == 0 and not vault.exists() and not (tmp_path / "home/.agents").exists()
    for want in ("Home.md", "krouter-zones.psv", ".agents/skills/krouter", ".cursor/rules/krouter.mdc",
                 "where the vault is", "Daily health.md", "session import:", "nightly job:", "open in Obsidian:"):
        assert want in res.stdout, want


def _fake_claude(tmp: Path) -> Path:
    """A `claude` that has the plugin and a folder marketplace, and logs what it is asked."""
    bin_ = tmp / "bin"
    bin_.mkdir()
    log = tmp / "claude.log"
    (bin_ / "claude").write_text(
        "#!/bin/sh\n"
        f"echo \"$*\" >> '{log}'\n"
        "case \"$*\" in\n"
        "  'plugin list --json') echo '[{\"id\": \"krouter@krouter\", \"enabled\": true}]' ;;\n"
        "  'plugin marketplace list --json') echo '[{\"name\": \"krouter\", \"source\": \"directory\", \"path\": \"/x\"},"
        " {\"name\": \"other\", \"source\": \"github\"}]' ;;\n"
        "esac\n", encoding="utf-8")
    (bin_ / "claude").chmod(0o755)
    return log


@POSIX
def test_uninstall_takes_out_the_plugin_and_the_folder_marketplace(tmp_path):
    log = _fake_claude(tmp_path)
    env = {**_env(tmp_path), "PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin:/usr/sbin:/sbin"}
    env.pop("KROUTER_NO_MCP", None)  # conftest turns app wiring off; this HOME is a throwaway one
    res = subprocess.run(["/bin/sh", str(REPO / "scripts/uninstall.sh"), "--dry-run"], env=env, capture_output=True,
                         text=True, timeout=120)
    assert res.returncode == 0 and "would: claude plugin uninstall krouter@krouter" in res.stdout
    assert "plugin uninstall" not in log.read_text(encoding="utf-8")
    res = subprocess.run(["/bin/sh", str(REPO / "scripts/uninstall.sh")], env=env, capture_output=True, text=True,
                         timeout=120)
    calls = log.read_text(encoding="utf-8")
    assert res.returncode == 0 and "plugin uninstall krouter@krouter" in calls
    assert "plugin marketplace remove krouter" in calls and "remove other" not in calls


def test_corrections_read_and_settle_english_candidates(tmp_path):
    import corrections

    folder = tmp_path / "Sessions"
    folder.mkdir()
    page = folder / "2026-11-09｜Correction candidates.md"
    page.write_text("# 2026-11-09 Correction candidates\n\n"
                    "- (14:05) from now on the demo app uses SQLite — project demo, session `claude:abcd1234`, "
                    "cue \"from now on\", pending the next distill\n", encoding="utf-8")
    got = corrections.pending(folder)
    [(key, cands)] = got.items()
    assert key == ("2026-11-09", "abcd1234") and cands[0]["said"].startswith("from now on the demo app uses SQLite")
    settled = corrections.settle(cands, ["- the demo app uses SQLite now (14:05)"])
    assert settled[0]["ok"]
    corrections.mark([{**settled[0], "link": "[[x]]"}])
    assert "verdict: holds → [[x]]" in page.read_text(encoding="utf-8")


@POSIX
def test_doctor_says_ok_or_names_the_fix(tmp_path):
    v = _english_vault(tmp_path)
    env = {**_env(tmp_path), "PYTHONPATH": str(REPO / "sdk"), "OBSIDIAN_VAULT": str(v)}

    def doctor() -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "krouter.cli", "doctor"], env=env, capture_output=True, text=True,
                              timeout=120)

    health = v / "90 System/Automation/Daily health.md"
    text = health.read_text(encoding="utf-8")
    assert "lamp: running" in text  # the template's default, with no nightly job installed in this HOME
    res = doctor()
    assert res.returncode == 1 and "verdict: NOT OK" in res.stdout and "lamp: unused" in res.stdout, res.stdout
    health.write_text(text.replace("lamp: running", "lamp: unused"), encoding="utf-8")  # what the installer sets
    res = doctor()
    assert res.returncode == 0 and "verdict: OK" in res.stdout, res.stdout + res.stderr
    assert "model: none" in res.stdout and "old answer" in res.stdout  # what is off without a key, and the consequence
    env["OBSIDIAN_VAULT"] = str(tmp_path / "missing")
    res = doctor()
    assert res.returncode == 1 and "verdict: NOT OK" in res.stdout and "Fix:" in res.stdout


@POSIX
def test_first_run_in_english_needs_no_ripgrep_and_prints_no_chinese(tmp_path):
    env = {**_env(tmp_path), "TMPDIR": str(tmp_path)}
    res = subprocess.run(["/bin/sh", str(REPO / "scripts/first_run.sh")], env=env, capture_output=True, text=True,
                         timeout=300)
    assert res.returncode == 0, res.stdout[-2000:] + res.stderr[-2000:]
    assert "ok status -> Home.md" in res.stdout and not CJK.search(res.stdout), res.stdout
    assert not list(tmp_path.glob("krouter-first-run.*"))  # the throwaway copy is gone


def test_excerpt_receipt_is_english_in_an_english_vault(monkeypatch):
    import datetime as dt

    import import_sessions as imp

    e = {"turns": [{"ask": "q", "answer": "a", "ts": "2026-11-09T10:00:00+00:00"}], "day": dt.date(2026, 11, 9),
         "agent": "claude", "id": "abcd", "project": "demo", "title": "Pick a database", "first_key": "k"}
    monkeypatch.setattr(imp, "PAGE_LANG", "en")
    assert "how: session excerpt (1 turns, not distilled yet): Pick a database" in imp.render(e)
    monkeypatch.setattr(imp, "PAGE_LANG", "zh")
    assert "how: 会话摘录（1 轮，还没提炼）" in imp.render(e)


def test_a_codex_folder_left_by_a_login_probe_is_not_a_codex_install(tmp_path, monkeypatch):
    import bootstrap as bs

    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex"))
    (tmp_path / ".codex/tmp/arg0").mkdir(parents=True)  # what probing the Codex app's login leaves behind
    assert not bs.codex_used().is_dir()
    (tmp_path / ".codex/config.toml").write_text("", encoding="utf-8")
    assert bs.codex_used() == tmp_path / ".codex"


@POSIX
def test_krouter_vault_is_the_name_and_wins_over_obsidian_vault(tmp_path):
    a, b = _english_vault(tmp_path / "a"), tmp_path / "b"
    shutil.copytree(REPO / "template", b)
    env = {**os.environ, "KROUTER_NO_QUERY_LOG": "1", "KROUTER_CACHE_DIR": str(tmp_path / "cache"), "HOME": str(tmp_path),
           "XDG_CONFIG_HOME": str(tmp_path / "cfg"), "KROUTER_VAULT_FILE": str(tmp_path / "none")}
    env.pop("OBSIDIAN_VAULT", None)
    router = ["/bin/sh", str(SCRIPTS / "route_knowledge.sh"), "status"]
    for sh_only in ("0", "1"):
        out = subprocess.run(router, env={**env, "KROUTER_SH_ONLY": sh_only, "KROUTER_VAULT": str(a)},
                             capture_output=True, text=True, timeout=60).stdout
        assert f"source: {a}/Home.md" in out  # the new name alone
        out = subprocess.run(router, env={**env, "KROUTER_SH_ONLY": sh_only, "KROUTER_VAULT": str(a), "OBSIDIAN_VAULT": str(b)},
                             capture_output=True, text=True, timeout=60).stdout
        assert f"source: {a}/Home.md" in out  # both set: KROUTER_VAULT wins
        out = subprocess.run(router, env={**env, "KROUTER_SH_ONLY": sh_only, "OBSIDIAN_VAULT": str(b)},
                             capture_output=True, text=True, timeout=60).stdout
        assert f"source: {b}/Agent第二大脑.md" in out  # the older name alone still works
    gone = subprocess.run(router, env={**env, "KROUTER_SH_ONLY": "1"}, capture_output=True, text=True, timeout=60)
    assert gone.returncode == 2 and "KROUTER_VAULT" in gone.stderr
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import krouter; "
            "print(krouter.ask('home', vault=sys.argv[2]).page)")
    out = subprocess.run([sys.executable, "-c", code, str(REPO / "sdk"), str(b)], env={**env, "KROUTER_VAULT": str(a)},
                         capture_output=True, text=True, timeout=60)
    assert out.stdout.strip() == f"{b}/Agent第二大脑.md", out.stderr  # an explicit vault= beats KROUTER_VAULT


@POSIX
def test_default_install_lists_and_backs_up_each_settings_file_it_changes(tmp_path):
    env = _env(tmp_path)
    env.pop("KROUTER_NO_MCP", None)  # wire the apps found in this throwaway HOME (no claude / codex on PATH)
    gemini = tmp_path / "home/.gemini/settings.json"
    gemini.parent.mkdir(parents=True)
    gemini.write_text('{"theme": "dark"}\n', encoding="utf-8")
    res, out = _boot(env, "--lang", "en")
    assert res.returncode == 0 and "gemini-cli" in out["mcp"], res.stdout[-1500:]
    assert json.loads((gemini.parent / "settings.json.krouter-bak").read_text(encoding="utf-8")) == {"theme": "dark"}
    listed = res.stdout.split("Files changed", 1)[1]
    assert str(gemini) in listed.split("Done.", 1)[0]
    assert "Files and folders created:" in res.stdout and "Second Brain" in res.stdout
    assert out["imported"] == 0 and "Past sessions were not imported" in res.stdout and "--consent" in res.stdout


@POSIX
@pytest.mark.skipif(not shutil.which("npm"), reason="npm packs the release")
def test_release_pack_attaches_what_the_readmes_link_and_what_a_release_install_runs(tmp_path):
    res = subprocess.run(["/bin/sh", str(REPO / "scripts/release_pack.sh"), str(tmp_path / "out")], capture_output=True,
                         text=True, timeout=300)
    assert res.returncode == 0 and "release assets OK" in res.stdout, res.stdout[-1500:] + res.stderr[-1500:]
    names = {p.name for p in (tmp_path / "out").iterdir()}
    assert {"bootstrap.sh", "bootstrap.ps1", "SHA256SUMS"} <= names and any(n.endswith(".tgz") for n in names)


def _desktop_env(tmp: Path, running: str) -> dict:
    env = _env(tmp)
    env.pop("KROUTER_NO_MCP", None)
    cfg = tmp / "home/Library/Application Support/Claude/claude_desktop_config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text('{"mcpServers": {"other": {"command": "x"}}}\n', encoding="utf-8")
    env.update({"KROUTER_CLAUDE_DESKTOP_CONFIG": str(cfg), "KROUTER_CLAUDE_DESKTOP_RUNNING": running,
                "KROUTER_VAULT_FILE": str(tmp / "home/.config/krouter/vault")})
    return env


@POSIX
def test_claude_desktop_running_is_left_alone_and_gets_an_extension_instead(tmp_path):
    env = _desktop_env(tmp_path, "1")
    cfg = Path(env["KROUTER_CLAUDE_DESKTOP_CONFIG"])
    before = cfg.read_text(encoding="utf-8")
    res, out = _boot(env, "--lang", "en", "--no-import")
    assert res.returncode == 0, res.stdout[-1500:] + res.stderr[-1500:]
    assert cfg.read_text(encoding="utf-8") == before  # written while running, it would be lost on quit
    assert "claude-desktop" not in out["mcp"] and "Claude Desktop is running" in res.stdout
    assert "--connect claude-desktop" in res.stdout
    mcpb = Path(out["claude_desktop_extension"])
    import build_mcpb

    assert mcpb.is_file() and build_mcpb.check(mcpb) == []
    import zipfile

    m = json.loads(zipfile.ZipFile(mcpb).read("manifest.json"))
    assert m["user_config"]["memory_folder"]["default"] == out["vault"]  # the folder the install recorded
    env["KROUTER_CLAUDE_DESKTOP_RUNNING"] = "0"  # quit the app, then the one command the install printed
    res = subprocess.run([sys.executable, str(BOOT), "--connect", "claude-desktop"], env=env, capture_output=True,
                         text=True, timeout=120)
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert res.returncode == 0 and "mcp_server.py" in json.dumps(data["mcpServers"]["krouter"]), res.stdout
    assert data["mcpServers"]["other"] == {"command": "x"} and (cfg.parent / (cfg.name + ".krouter-bak")).is_file()
    env["KROUTER_CLAUDE_DESKTOP_RUNNING"] = "1"  # uninstall while it runs: left alone, and told why
    res = subprocess.run([sys.executable, str(BOOT), "--unregister-mcp"], env=env, capture_output=True, text=True,
                         timeout=120)
    assert "krouter" in json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"] and "Quit Claude Desktop" in res.stdout


def test_claude_desktop_detection_tells_the_app_from_claude_code(monkeypatch):
    import bootstrap as bs

    monkeypatch.delenv("KROUTER_CLAUDE_DESKTOP_RUNNING", raising=False)
    monkeypatch.setattr(bs.platform, "system", lambda: "Darwin")
    ps = ("/Users/u/Library/Application Support/Claude/claude-code/2.1/x/claude.app/Contents/MacOS/claude\n"
          "/Users/u/.local/bin/claude\n")
    monkeypatch.setattr(bs.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, ps, ""))
    assert not bs.claude_desktop_running()  # Claude Code alone is not the desktop app
    ps += "/Applications/Claude.app/Contents/MacOS/Claude\n"
    monkeypatch.setattr(bs.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, ps, ""))
    assert bs.claude_desktop_running()


def test_the_release_extension_passes_its_structure_check_and_answers(tmp_path):
    import build_mcpb

    bundle = build_mcpb.build(tmp_path / "KRouter.mcpb")
    assert build_mcpb.check(bundle) == []
