"""Install / upgrade / uninstall keep the host's alias table; nightly outcomes reach the health page and status."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter-obsidian/scripts"
SAMPLE = SCRIPTS / "canonical_sources.psv"
MY_ROW = "Q99|我的名词;my noun|02 经验与方法/经验与方法.md|Methods\n"

pytestmark = pytest.mark.skipif(os.name == "nt", reason="install.sh is POSIX")


def _env(tmp: Path, vault: Path | None) -> dict:
    env = {
        "HOME": str(tmp / "home"),
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "en_US.UTF-8",
        "KROUTER_SKILL_HOME": str(tmp / "home/.agents/skills/krouter-obsidian"),
        "KROUTER_CURSOR_RULE": str(tmp / "home/.cursor/rules/krouter-obsidian.mdc"),
        "KROUTER_ASK_RULE": str(tmp / "home/.cursor/rules/ask-product.mdc"),
        "KROUTER_KEYS_ENV": str(tmp / "home/keys.env"),
        "KROUTER_SKIP_LAUNCHD": "1",
        "KROUTER_SKIP_TIMER": "1",
        "KROUTER_WRITER": "/nonexistent/grok",
    }
    (tmp / "home").mkdir(exist_ok=True)
    if vault is not None:
        env["OBSIDIAN_VAULT"] = str(vault)
    return env


def _sh(script: str, env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/bin/sh", str(REPO / "scripts" / script), *args], env=env,
                          capture_output=True, text=True, timeout=300)


def test_upgrade_keeps_the_table_and_moves_it_into_the_vault(tmp_path):
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template", vault)
    skill = tmp_path / "home/.agents/skills/krouter-obsidian"
    # an old install whose table the host edited, before tables lived in the vault
    first = _sh("install.sh", _env(tmp_path, None))
    assert first.returncode == 0, first.stderr
    old = skill / "scripts/canonical_sources.psv"
    old.write_text(SAMPLE.read_text(encoding="utf-8") + MY_ROW, encoding="utf-8")
    assert _sh("install.sh", _env(tmp_path, vault)).returncode == 1  # refuses without --upgrade
    up = _sh("install.sh", _env(tmp_path, vault), "--upgrade")
    assert up.returncode == 0, up.stderr
    in_vault = vault / "90 系统文件/canonical_sources.psv"
    assert MY_ROW in in_vault.read_text(encoding="utf-8"), up.stdout
    assert old.is_symlink() and old.resolve() == in_vault.resolve()
    # a second upgrade keeps the link and touches nothing in the vault table
    before = in_vault.read_bytes()
    again = _sh("install.sh", _env(tmp_path, vault), "--upgrade")
    assert again.returncode == 0, again.stderr
    assert in_vault.read_bytes() == before and old.is_symlink()
    # the router now reads the vault's table
    out = subprocess.run([sys.executable, str(skill / "scripts/route_knowledge.py"), "search", "我的名词"],
                         env={**os.environ, "OBSIDIAN_VAULT": str(vault)}, capture_output=True, text=True).stdout
    assert f"canonical_map: {in_vault}" in out and "02 经验与方法/经验与方法.md" in out


def test_fresh_install_seeds_the_sample_into_the_vault(tmp_path):
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template", vault)
    res = _sh("install.sh", _env(tmp_path, vault))
    assert res.returncode == 0, res.stderr
    assert (vault / "90 系统文件/canonical_sources.psv").read_bytes() == SAMPLE.read_bytes()


def test_uninstall_saves_an_unsaved_table_and_leaves_the_vault(tmp_path):
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template", vault)
    env = _env(tmp_path, None)
    assert _sh("install.sh", env).returncode == 0
    skill = Path(env["KROUTER_SKILL_HOME"])
    (skill / "scripts/canonical_sources.psv").write_text(SAMPLE.read_text(encoding="utf-8") + MY_ROW, encoding="utf-8")
    before = sorted(p.relative_to(vault).as_posix() for p in vault.rglob("*"))
    dry = _sh("uninstall.sh", {**env, "OBSIDIAN_VAULT": str(vault)}, "--dry-run")
    assert dry.returncode == 0 and skill.exists() and "would: rm -rf" in dry.stdout
    res = _sh("uninstall.sh", {**env, "OBSIDIAN_VAULT": str(vault)})
    assert res.returncode == 0, res.stderr
    assert not skill.exists() and not Path(env["KROUTER_CURSOR_RULE"]).exists()
    saved = vault / "90 系统文件/canonical_sources.psv"
    assert MY_ROW in saved.read_text(encoding="utf-8")
    after = sorted(p.relative_to(vault).as_posix() for p in vault.rglob("*"))
    assert set(after) - set(before) == {"90 系统文件/canonical_sources.psv"}  # nothing else changed


def _nightly_env(tmp: Path, vault: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.endswith(("_API_KEY", "_BASE_URL", "_MODEL"))}
    env.update({"OBSIDIAN_VAULT": str(vault), "HOME": str(tmp), "KROUTER_KEYS_ENV": str(tmp / "none.env"),
                "KROUTER_WRITER": "/nonexistent/grok", "KROUTER_CACHE_DIR": str(tmp / "cache"),
                "KROUTER_NO_QUERY_LOG": "1"})
    env.pop("KROUTER_LEARN_CLI", None)
    return env


def test_nightly_outcome_reaches_health_page_and_status(tmp_path):
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template", vault)
    env = _nightly_env(tmp_path, vault)
    res = subprocess.run([sys.executable, str(SCRIPTS / "nightly.py"), "--vault", str(vault)],
                         env=env, capture_output=True, text=True, timeout=600)
    assert res.returncode == 0, res.stderr
    summary = json.loads(res.stdout.strip().splitlines()[-1])
    assert summary["nightly"] == "skipped" and summary["lane"] == "none"  # no key, no logged-in CLI
    report = (vault / "90 系统文件/自动化/夜间维护.md").read_text(encoding="utf-8")
    assert "nightly: skipped" in report and "| answer_cards | skipped |" in report
    health = (vault / "90 系统文件/自动化/日更健康.md").read_text(encoding="utf-8")
    assert "nightly: skipped" in health and "nightly_at:" in health
    for sh_only in ("0", "1"):
        status = subprocess.run(["/bin/sh", str(SCRIPTS / "route_knowledge.sh"), "status"],
                                env={**env, "KROUTER_SH_ONLY": sh_only}, capture_output=True, text=True).stdout
        assert "nightly: skipped" in status and "host_action: Nightly upkeep skipped" in status, sh_only


def test_nightly_dry_run_calls_nothing_and_writes_nothing(tmp_path):
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template", vault)
    before = {p.relative_to(vault).as_posix(): p.stat().st_mtime_ns for p in vault.rglob("*") if p.is_file()}
    usage = tmp_path / "usage.jsonl"
    res = subprocess.run([sys.executable, str(SCRIPTS / "nightly.py"), "--vault", str(vault), "--dry-run"],
                         env={**_nightly_env(tmp_path, vault), "KROUTER_USAGE_LOG": str(usage)},
                         capture_output=True, text=True, timeout=600)
    assert res.returncode == 0, res.stderr
    plan = json.loads(res.stdout)
    steps = {s["step"]: s for s in plan["steps"]}
    assert set(steps) == {"import_sessions", "import_claude_mem", "compile_subconscious", "reconsolidate", "consolidate_topics", "answer_cards",
                          "checkup", "backup"}
    assert steps["backup"]["sends"] == "nothing (no model)"
    assert steps["import_sessions"]["chars"] == 0  # 没同意过：不导入、不发
    assert steps["answer_cards"]["chars"] > 0 and "90 系统文件/自动化/下意识问答.jsonl" in steps["answer_cards"]["writes"]
    assert plan["est_tokens_total"] > 0
    after = {p.relative_to(vault).as_posix(): p.stat().st_mtime_ns for p in vault.rglob("*") if p.is_file()}
    assert after == before and not usage.exists()


def test_run_py_matches_run_sh_contract(tmp_path):
    """Windows twin: unset vault is a no-op; --dry-run writes nothing."""
    run_py = REPO / "extras/host-daily-evolution/run.py"
    env = _nightly_env(tmp_path, tmp_path / "unused")
    env.pop("OBSIDIAN_VAULT")
    res = subprocess.run([sys.executable, str(run_py)], env=env, capture_output=True, text=True, timeout=60)
    assert res.returncode == 0 and "OBSIDIAN_VAULT is not set" in res.stderr
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template", vault)
    before = {p.relative_to(vault).as_posix(): p.stat().st_mtime_ns for p in vault.rglob("*") if p.is_file()}
    res = subprocess.run([sys.executable, str(run_py), "--dry-run"], env=_nightly_env(tmp_path, vault),
                         capture_output=True, text=True, timeout=600)
    assert res.returncode == 0, res.stderr
    assert '"est_tokens_total"' in res.stdout
    after = {p.relative_to(vault).as_posix(): p.stat().st_mtime_ns for p in vault.rglob("*") if p.is_file()}
    assert after == before


def test_propose_aliases_drafts_and_apply_adds_only_ticked_rows(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template", vault)
    table = vault / "90 系统文件/canonical_sources.psv"
    shutil.copy(SAMPLE, table)
    monkeypatch.delenv("KROUTER_MAP", raising=False)
    sys.path.insert(0, str(SCRIPTS))
    import propose_aliases as pa

    out, n = pa.propose(vault, 40, use_model=False)
    text = out.read_text(encoding="utf-8")
    assert n > 0 and not any(ln.startswith("- [x]") for ln in text.splitlines())
    assert table.read_bytes() == SAMPLE.read_bytes()  # nothing applied by itself
    rows = [ln for ln in text.splitlines() if ln.startswith("- [ ] ")]
    first = rows[0].replace("- [ ] ", "- [x] ", 1)
    cid, aliases, rel, _anchor = first[6:].split("|", 3)
    # a ticked row whose alias already locks another page is refused, not written
    bad = f"- [x] Q98|唯一总入口|{rel}|x"
    out.write_text(text.replace(rows[0], first) + bad + "\n", encoding="utf-8")
    res = pa.apply(vault)
    assert res["applied"] == 1 and res["refused"] and "唯一总入口" in res["refused"][0]["why"]
    new = table.read_text(encoding="utf-8")
    assert f"{cid}|{aliases}|{rel}|" in new and "Q98" not in new
    left = out.read_text(encoding="utf-8")
    assert first not in left and bad in left  # applied row leaves the checklist; refused one stays for review


def test_first_run_does_not_write_the_query_log(tmp_path):
    """The demo on the template is not the host's traffic; the nightly learning must never see it."""
    state = tmp_path / "state"
    env = {**os.environ, "KROUTER_STATE_DIR": str(state), "KROUTER_CACHE_DIR": str(tmp_path / "cache")}
    env.pop("KROUTER_NO_QUERY_LOG", None)
    res = subprocess.run(["/bin/sh", str(REPO / "scripts/first_run.sh")], env=env, capture_output=True,
                         text=True, timeout=600, cwd=REPO)
    assert res.returncode == 0, res.stdout[-800:] + res.stderr[-800:]
    assert not (state / "queries.jsonl").exists()


def test_notify_once_a_day_and_off_switch(tmp_path, monkeypatch):
    sys.path.insert(0, str(SCRIPTS))
    import notify

    sent = []
    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(notify.subprocess, "run", lambda *a, **k: sent.append(a) or subprocess.CompletedProcess(a, 0))
    monkeypatch.setattr(notify.subprocess, "Popen", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(notify.shutil, "which", lambda name: "/usr/bin/notify-send")
    monkeypatch.setenv("KROUTER_NOTIFY", "0")
    assert notify.send("x", kind="t") is False and not sent
    monkeypatch.setenv("KROUTER_NOTIFY", "1")
    assert notify.send("x", kind="t") is True and len(sent) == 1
    assert notify.send("x", kind="t") is False and len(sent) == 1  # once per kind per day
    assert notify.send("y", kind="other") is True
