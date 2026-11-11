"""Every entry file an agent may read on its own carries the same, current status block (scripts/sync_status.py)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_status_block_is_in_sync_everywhere():
    res = subprocess.run([sys.executable, str(ROOT / "scripts/sync_status.py"), "--check"], capture_output=True,
                         text=True, timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr + " — edit docs/STATUS*.md, then run scripts/sync_status.py"


def _status_texts() -> dict[str, str]:
    return {lang: (ROOT / f"docs/STATUS{lang}.md").read_text(encoding="utf-8") for lang in ("", ".zh")}


def test_status_version_is_the_shipped_version():
    import json
    import re

    version = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    # 顶部是「未发布」的一节时，STATUS 写的是上一个已发布的版本（最新发布版），不是还没发的这一个
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if re.search(r"^## " + re.escape(version) + r" — unreleased", changelog, re.M):
        version = re.search(r"^## (\d+\.\d+\.\d+) — \d{4}-", changelog, re.M).group(1)
    for lang, text in _status_texts().items():
        assert re.search(r"v(\d+\.\d+\.\d+)", text).group(1) == version, f"docs/STATUS{lang}.md names another version"


def test_status_numbers_are_what_the_bench_gives_now(monkeypatch):
    """The numbers in the block are recomputed: a ranking change or a new stored result must update the block."""
    import importlib.util
    import json

    spec = importlib.util.spec_from_file_location("mh_bench_status", ROOT / "bench/memory_honesty/run.py")
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    monkeypatch.setenv("KROUTER_DENSE", "0")  # 测试结束自动恢复，不影响同一进程里后面的测试
    rows = bench.questions("heldout3")

    def nums(answers: list[dict]) -> tuple[int, int, int]:
        r = bench.score(rows, answers)
        right = int(r["correction_hit"].split("/")[0]) + int(r["current_hit"].split("/")[0])
        return round(100 * r["wrong_citation_rate"]), int(r["refused"].split("/")[0]), right

    kr = nums(bench.krouter_answers(rows, bench.vault_of("heldout3")))
    stored = ROOT / "bench/memory_honesty/results/2026-10-14"
    cm, bm = (nums([json.loads(x) for x in (stored / f"{n}.heldout3.jsonl").read_text(encoding="utf-8").splitlines()
                    if x.strip()]) for n in ("claude-mem-13.39.0", "basic-memory-0.23.2"))
    want = {"": [f"KRouter {kr[0]}%", f"{kr[1]} of 80", f"{kr[2]} of 120", f"claude-mem\n>   {cm[0]}%",
                 f"basic-memory {bm[0]}%", f"{cm[2]} and {bm[2]} right"],
            ".zh": [f"KRouter 引错 {kr[0]}%", f"拒答 {kr[1]} 道", f"答对 {kr[2]} 道", f"claude-mem 引错 {cm[0]}%",
                    f"basic-memory {bm[0]}%", f"分别答对 {cm[2]} 和 {bm[2]} 道"]}
    for lang, text in _status_texts().items():
        flat = " ".join(text.replace(">", " ").split())
        for phrase in want[lang]:
            assert " ".join(phrase.replace(">", " ").split()) in flat, f"docs/STATUS{lang}.md: expected {phrase!r}"


def test_status_plugin_and_changelog_name_the_same_release():
    """The block names the latest release; so do plugin.json and the newest released heading in CHANGELOG.md.
    What main has beyond it lives under "Unreleased", which the block's first line points to."""
    import json
    import re

    version = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    released = re.findall(r"(?m)^## (\d+\.\d+\.\d+) — ", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    assert released and released[0] == version, "plugin.json and the newest CHANGELOG release disagree"
    for lang, text in _status_texts().items():
        assert "Unreleased" in text, f"docs/STATUS{lang}.md must say that main may be ahead of the release"
