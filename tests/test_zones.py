"""A vault with its own folder names: krouter-zones.psv maps the default layout onto it."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill/krouter/scripts"
sys.path.insert(0, str(SCRIPTS))
import zones  # noqa: E402

RENAMES = {
    "90 系统文件": "System",
    "02 经验与方法": "Methods",
    "05 时间日志": "Journal",
    "01 项目": "Projects",
    "Agent第二大脑.md": "Home.md",
}


@pytest.fixture()
def english_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template", vault)
    for src, dst in RENAMES.items():
        (vault / src).rename(vault / dst)
    (vault / zones.ZONES_FILE).write_text(
        "# default|mine\n" + "".join(f"{a}|{b}\n" for a, b in RENAMES.items()), encoding="utf-8")
    # the host's own table names the host's own paths
    rows = []
    for line in (SCRIPTS / "canonical_sources.psv").read_text(encoding="utf-8").splitlines():
        parts = line.split("|")
        if len(parts) == 4 and not line.startswith("#"):
            parts[2] = zones.real(vault, parts[2])
        rows.append("|".join(parts))
    (vault / "System/canonical_sources.psv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return vault


def test_real_and_canon_round_trip(english_vault):
    v = english_vault
    assert zones.real(v, "90 系统文件/自动化/日更健康.md") == "System/自动化/日更健康.md"
    assert zones.real(v, "Agent第二大脑.md") == "Home.md"
    assert zones.real(v, "03 资料与证据/x.md") == "03 资料与证据/x.md"  # not mapped: unchanged
    assert zones.real(v, "90 系统文件x/a.md") == "90 系统文件x/a.md"  # segment boundary
    assert zones.canon(v, "Journal/2026-01/01｜x.md") == "05 时间日志/2026-01/01｜x.md"


def _route(vault: Path, sh_only: str, *args: str) -> str:
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_SH_ONLY": sh_only,
           "KROUTER_CACHE_DIR": str(vault.parent / "cache"), "KROUTER_NO_QUERY_LOG": "1"}
    env.pop("KROUTER_MAP", None)
    return subprocess.run(["/bin/sh", str(SCRIPTS / "route_knowledge.sh"), *args], env=env,
                          capture_output=True, text=True, timeout=60).stdout


@pytest.mark.skipif(os.name == "nt", reason="POSIX router")
@pytest.mark.parametrize("sh_only", ["0", "1"])
def test_router_follows_the_mapping(english_vault, sh_only):
    v = english_vault
    status = _route(v, sh_only, "status")
    assert f"source: {v}/Home.md" in status, status
    assert f"health: {v}/System/自动化/日更健康.md" in status
    assert f"canonical_map: {v}/System/canonical_sources.psv" in status
    pref = _route(v, sh_only, "search", "剪藏")
    assert "retrieval_status: canonical-match" in pref and f"{v}/Methods/Agent/用户偏好与工作约束.md" in pref


def test_recall_tiers_and_nightly_outputs_use_the_mapping(english_vault, monkeypatch, tmp_path):
    v = english_vault
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache2"))
    import recall_index as ri

    con = ri.connect(ri.cache_path(v))
    ri.refresh(v, con)
    tier = dict(con.execute("SELECT rel, tier FROM docs").fetchall())
    assert tier["Methods/Agent/用户偏好与工作约束.md"] == "rule"  # tiered by its default name
    assert tier["Home.md"] == "rule"
    assert any(t == "log" for r, t in tier.items() if r.startswith("Journal/"))
    env = {k: val for k, val in os.environ.items() if not k.endswith(("_API_KEY", "_BASE_URL", "_MODEL"))}
    env.update({"OBSIDIAN_VAULT": str(v), "HOME": str(tmp_path), "KROUTER_KEYS_ENV": str(tmp_path / "none"),
                "KROUTER_WRITER": "/nonexistent/grok", "KROUTER_CACHE_DIR": str(tmp_path / "cache3"),
                "KROUTER_NO_QUERY_LOG": "1"})
    env.pop("KROUTER_LEARN_CLI", None)
    res = subprocess.run([sys.executable, str(SCRIPTS / "nightly.py"), "--vault", str(v)], env=env,
                         capture_output=True, text=True, timeout=600)
    assert res.returncode == 0, res.stderr
    assert (v / "System/自动化/夜间维护.md").is_file() and (v / "System/自动化/下意识.md").is_file()
    assert (v / "System/自动化/下意识体检.md").is_file()
    assert "nightly: skipped" in (v / "System/自动化/日更健康.md").read_text(encoding="utf-8")
    assert not (v / "90 系统文件").exists()  # nothing recreated the default folder
