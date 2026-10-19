"""A new session must not start from an answer the user already changed.

The SessionStart hook brings this repository's recorded decisions. When a later correction says "原来 A → 改成 B",
the older line "A" is left out (it used to be injected next to the correction, so the agent saw both). A line that
restates the new decision, and unrelated decisions, stay. Chains (A → B, then B → C) keep only the newest.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "skill/krouter-obsidian/scripts/session_hook.py"


@pytest.fixture()
def world(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    sys.path.insert(0, str(REPO / "skill/krouter-obsidian/scripts"))
    from krouter_home import project_root

    root = project_root(str(repo))  # 和 hook 用同一个函数：Windows 上 git 输出的路径写法和它解析出的不一样
    vault = tmp_path / "vault"
    (vault / "05 时间日志/会话摘录").mkdir(parents=True)
    state = tmp_path / "state"
    state.mkdir()
    (state / "import.json").write_text('{"consent": true}', encoding="utf-8")

    def page(name: str, days_ago: int, lines: list[str], status: str = "active") -> None:
        day = (date.today() - timedelta(days=days_ago)).isoformat()
        body = "\n".join(f"- {ln}" for ln in lines)
        (vault / "05 时间日志/会话摘录" / f"{name}.md").write_text(
            f"---\ntype: session-excerpt\nsource: krouter-import\nstatus: {status}\ndate: {day}\nproject_root: {root}\n---\n\n"
            f"# {name}\n\n## 定了什么、改了什么（模型提炼，待你确认）\n\n{body}\n", encoding="utf-8")

    def inject() -> str:
        env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_STATE_DIR": str(state)}
        res = subprocess.run([sys.executable, str(HOOK), "start"], input=json.dumps({"cwd": str(repo)}), env=env,
                             capture_output=True, text=True, timeout=60)
        out = res.stdout.strip()
        return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""

    return page, inject


def test_a_replaced_decision_is_not_injected(world):
    page, inject = world
    page("s1", 10, ["本地 API 端口用 8080（10:05）", "日志级别用 info（10:20）"])
    page("s2", 3, ["原来本地 API 端口 8080 → 改成 9090（14:00）"])
    ctx = inject()
    assert "→ 改成 9090" in ctx and "日志级别用 info" in ctx
    assert "本地 API 端口用 8080" not in ctx


def test_a_line_that_restates_the_new_decision_stays(world):
    page, inject = world
    page("s1", 10, ["原来本地 API 端口 8080 → 改成 9090（14:00）"])
    page("s2", 2, ["本地 API 端口用 9090，已经写进 README（09:00）"])
    assert "本地 API 端口用 9090" in inject()


def test_same_page_decide_then_change(world):
    page, inject = world
    page("s1", 1, ["发版从任意分支打 tag（10:00）", "原来发版从任意分支打 tag → 改成只从 main 打 tag（11:30）"])
    ctx = inject()
    assert "只从 main 打 tag" in ctx and "- 发版从任意分支打 tag（10:00）" not in ctx


def test_a_chain_keeps_only_the_newest(world):
    page, inject = world
    page("s1", 9, ["原来缓存过期 30 分钟 → 改成 10 分钟（10:00）"])
    page("s2", 2, ["原来缓存过期 10 分钟 → 改成 5 分钟（15:00）"])
    ctx = inject()
    assert "改成 5 分钟" in ctx and "改成 10 分钟" not in ctx


def test_english_lines(world):
    page, inject = world
    page("s1", 8, ["Releases ship from any branch, tagged by hand (10:05)"])
    page("s2", 1, ["was releases ship from any branch → now releases ship from main only, tagged by CI (16:40)"])
    ctx = inject()
    assert "main only" in ctx and "- Releases ship from any branch, tagged by hand" not in ctx


def test_same_day_revert_keeps_the_reverted_decision(world):
    """10:00 decide A, 11:00 change A → B, 15:00 change back B → A: the session starts from A, not from B."""
    page, inject = world
    page("s1", 1, ["本地 API 端口用 8080（10:00）", "原来本地 API 端口 8080 → 改成 9090（11:00）",
                   "原来本地 API 端口 9090 → 改回 8080（15:00）"])
    ctx = inject()
    assert "改回 8080" in ctx
    assert "改成 9090（11:00）" not in ctx  # 被当天更晚的回退推翻了


def test_a_shared_subject_word_does_not_drop_another_decision(world):
    """A correction about the API port must not drop other API decisions that only share words like 本地 API."""
    page, inject = world
    page("s1", 9, ["本地 API 端口文档放在 README（10:00）", "本地 API 用 JWT 鉴权（10:10）",
                   "Local API docs live in README (10:20)"])
    page("s2", 2, ["原来本地 API 端口 8080 → 改成 9090（14:00）", "was local API port 8080 → now 9090 (14:05)"])
    ctx = inject()
    for keep in ("本地 API 端口文档放在 README", "本地 API 用 JWT 鉴权", "Local API docs live in README"):
        assert keep in ctx, keep


def test_the_same_value_on_another_subject_stays(world):
    """"会议时长 10 分钟 → 15 分钟" must not drop "缓存过期 10 分钟": same value, different subject."""
    page, inject = world
    page("s1", 9, ["缓存过期 10 分钟（10:00）", "会议时长 10 分钟（10:05）"])
    page("s2", 2, ["原来会议时长 10 分钟 → 改成 15 分钟（14:00）"])
    ctx = inject()
    assert "缓存过期 10 分钟" in ctx and "改成 15 分钟" in ctx
    assert "- 会议时长 10 分钟（10:05）" not in ctx


def test_another_subject_with_shared_words_is_kept_and_flagged(world):
    """An outside review's probe: "测试环境 API 端口用 8080" shares "API 端口 8080" with a correction about the *local*
    port. Different subject (测试环境 vs 本地): kept, with a note to check, never silently dropped."""
    page, inject = world
    page("s1", 9, ["测试环境 API 端口用 8080（10:00）", "本地 API 端口用 8080（10:05）"])
    page("s2", 2, ["原来本地 API 端口 8080 → 改成 9090（14:00）"])
    ctx = inject()
    assert "测试环境 API 端口用 8080" in ctx and "可能已被" in ctx.split("测试环境 API 端口用 8080", 1)[1].split("\n", 1)[0]
    assert "- 本地 API 端口用 8080" not in ctx


def test_a_one_word_old_side(world):
    page, inject = world
    page("s1", 5, ["包管理用 npm（09:00）"])
    page("s2", 1, ["原来包管理用 npm → 改成 pnpm（16:00）"])
    ctx = inject()
    assert "改成 pnpm" in ctx and "- 包管理用 npm（09:00）" not in ctx
