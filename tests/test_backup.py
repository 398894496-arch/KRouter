"""Off-machine backups: encrypted, checked by restoring, kept on a schedule, and loud when they stop working."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill/krouter-obsidian/scripts/backup.py"
pytestmark = pytest.mark.skipif(shutil.which("openssl") is None or shutil.which("git") is None,
                                reason="needs openssl and git")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("KROUTER_KEYS_ENV", str(tmp_path / "keys.env"))
    monkeypatch.setenv("KROUTER_STATE_DIR", str(tmp_path / "state"))
    for k in ("KROUTER_BACKUP_PASSPHRASE", "KROUTER_BACKUP_DIR"):
        monkeypatch.delenv(k, raising=False)
    import backup

    return backup


def _vault(root: Path) -> Path:
    v = root / "Vault"
    (v / "02 经验与方法").mkdir(parents=True)
    (v / "02 经验与方法/发版.md").write_text("# 发版\n只从 main 的 tag 发。\n", encoding="utf-8")
    (v / "notes.md").write_text("plain note\n", encoding="utf-8")
    (v / ".trash").mkdir()
    (v / ".trash/old.md").write_text("deleted\n", encoding="utf-8")
    (v / ".obsidian").mkdir()
    (v / ".obsidian/workspace.json").write_text("{}", encoding="utf-8")
    (v / ".obsidian/app.json").write_text("{}", encoding="utf-8")
    for argv in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"]):
        subprocess.run(["git", "-C", str(v), *argv], check=True)
    return v


def test_backup_restores_the_vault_and_its_history(env, tmp_path):
    v = _vault(tmp_path)
    made = env.make(v, tmp_path / "out", "correct horse battery staple")
    archive = Path(made["archive"])
    assert archive.name.endswith(".tar.gz.enc") and made["pages"] == 3 - 1  # .trash 里的不算
    assert b"main" not in archive.read_bytes()  # 加密了，原文不在文件里
    res = env.open_archive(archive, "correct horse battery staple", tmp_path / "restored")
    root = Path(res["restored"])
    assert (root / "02 经验与方法/发版.md").read_text(encoding="utf-8") == "# 发版\n只从 main 的 tag 发。\n"
    assert not (root / ".trash").exists() and not (root / ".obsidian/workspace.json").exists()
    assert (root / ".obsidian/app.json").is_file() and res["git_ok"] is True
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout
    assert head.strip() == made["git_head"]


def test_wrong_passphrase_damage_and_overwrite_are_refused(env, tmp_path):
    v = _vault(tmp_path)
    archive = Path(env.make(v, tmp_path / "out", "right")["archive"])
    with pytest.raises(ValueError, match="HMAC"):
        env.open_archive(archive, "wrong", tmp_path / "a")
    (tmp_path / "taken").mkdir()
    with pytest.raises(ValueError, match="already exists"):
        env.open_archive(archive, "right", tmp_path / "taken")
    data = bytearray(archive.read_bytes())
    data[len(data) // 2] ^= 0x01
    archive.write_bytes(bytes(data))
    with pytest.raises(ValueError, match="HMAC"):
        env.open_archive(archive, "right", tmp_path / "b")


def test_prune_keeps_newest_weeks_and_months(env, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    now = datetime(2026, 10, 20, 3, 0)
    for d in range(0, 200, 1):
        t = now - timedelta(days=d)
        name = f"krouter-backup-Vault-{t:%Y%m%d-%H%M%S}.tar.gz.enc"
        (out / name).write_bytes(b"x")
        (out / name.replace(".tar.gz.enc", ".json")).write_text("{}", encoding="utf-8")
    (out / "my-own-file.txt").write_text("keep me", encoding="utf-8")
    env.prune(out, now)
    left = sorted(env._stamp(p) for p in env.archives(out))
    assert len(left) <= 7 + 4 + 6 and left[-1] == now and (out / "my-own-file.txt").is_file()
    assert all((out / (p.name[: -len(".tar.gz.enc")] + ".json")).is_file() for p in env.archives(out))
    assert min(left) >= now - timedelta(days=6 * 31)


def test_cli_off_without_a_folder_then_init_run_and_status(env, tmp_path, monkeypatch):
    v = _vault(tmp_path)
    run = lambda *a: subprocess.run([sys.executable, str(SCRIPT), *a], capture_output=True, text=True,  # noqa: E731
                                    env={**__import__("os").environ})
    off = run("--vault", str(v))
    assert off.returncode == 0 and json.loads(off.stdout)["backup"] == "off"
    sys.path.insert(0, str(SCRIPT.parent))
    import nightly

    assert nightly.classify(0, off.stdout)[0] == "off"
    init = run("init", "--dir", str(tmp_path / "cloud"))
    shown = json.loads(init.stdout)
    assert shown["passphrase"] == "created" and "KROUTER_BACKUP_PASSPHRASE" not in init.stdout.split("next")[0]
    secret = (tmp_path / "keys.env").read_text(encoding="utf-8")
    assert secret.split("KROUTER_BACKUP_PASSPHRASE=", 1)[1].split("\n")[0] not in init.stdout  # 不打印密码
    st = json.loads(run("status").stdout)
    assert st["backup"] == "on" and "password manager" in st["host_action"] and "no backup" in st["host_action"]
    ok = json.loads(run("--vault", str(v)).stdout)
    assert ok["backup"] == "ok" and ok["restore_checked"] and ok["git_ok"]
    assert json.loads(run("verify", "--latest").stdout)["verify"] == "ok"
    run("saved")
    st = json.loads(run("status").stdout)
    assert "host_action" not in st and st["archives"] == 1


def test_two_places_each_get_a_checked_archive_and_one_failing_is_partial(env, tmp_path, monkeypatch):
    v = _vault(tmp_path)
    blocked = tmp_path / "blocked"
    blocked.write_text("a file, not a folder", encoding="utf-8")
    monkeypatch.setenv("KROUTER_BACKUP_PASSPHRASE", "pw")
    monkeypatch.setenv("KROUTER_BACKUP_DIR", f"{tmp_path / 'cloud'}|{tmp_path / 'usb'}")
    run = lambda *a: subprocess.run([sys.executable, str(SCRIPT), *a], capture_output=True, text=True,  # noqa: E731
                                    env={**__import__("os").environ})
    both = json.loads(run("--vault", str(v)).stdout)
    assert both["backup"] == "ok" and len(both["places"]) == 2
    monkeypatch.setenv("KROUTER_BACKUP_DIR", f"{tmp_path / 'cloud'}|{blocked}")
    res = run("--vault", str(v))
    out = json.loads(res.stdout)
    assert res.returncode == 0 and out["backup"] == "partial" and len(out["places"]) == 1
    sys.path.insert(0, str(SCRIPT.parent))
    import nightly

    assert nightly.classify(res.returncode, res.stdout)[0] == "partial"
