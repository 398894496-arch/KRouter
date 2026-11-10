"""`session_hook.py prompt`: a correction typed in a session is written down at once as a provisional candidate —
local pattern match, redacted, never a model call, never a failed session; rhetorical questions and KRouter's own
model calls are not corrections."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "skill/krouter/scripts/session_hook.py"
KEY = "sk-" + "Abc123XyZ" * 4


@pytest.fixture()
def box(tmp_path):
    vault = tmp_path / "vault"
    (vault / "05 时间日志").mkdir(parents=True)
    state = tmp_path / "state"
    state.mkdir()
    (state / "import.json").write_text(json.dumps({"consent": True}), encoding="utf-8")
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_STATE_DIR": str(state), "KROUTER_NO_QUERY_LOG": "1"}
    env.pop("KROUTER_IN_DISTILL", None)
    page = vault / "05 时间日志/会话摘录" / f"{date.today().isoformat()}｜纠正候选.md"
    return {"vault": vault, "state": state, "env": env, "page": page, "tmp": tmp_path}


def _say(box: dict, text: str, env: dict | None = None, transcript: Path | None = None) -> subprocess.CompletedProcess:
    payload = {"prompt": text, "session_id": "0123abcd-ffff-4444-8888-000000000000", "cwd": str(box["tmp"]),
               "transcript_path": str(transcript or "")}
    res = subprocess.run([sys.executable, str(HOOK), "prompt"], input=json.dumps(payload), env=env or box["env"],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    assert res.stdout == ""  # UserPromptSubmit 的输出会进上下文：记纠正不该往会话里塞东西
    return res


def test_correction_is_written_as_a_provisional_candidate(box):
    _say(box, "不对，封面标题以后一律放左上角，字号改成 96。")
    text = box["page"].read_text(encoding="utf-8")
    assert "status: provisional" in text and "type: correction-candidates" in text
    assert "以后一律放左上角" in text and "`claude:0123abcd`" in text
    assert "待下次蒸馏判定" in text and "命中「" in text


def test_frontmatter_is_valid_yaml(box):
    yaml = pytest.importorskip("yaml")
    _say(box, "记住：发版只从 main 打 tag。")
    head = box["page"].read_text(encoding="utf-8").split("---\n")[1]
    meta = yaml.safe_load(head)
    assert meta["status"] == "provisional" and str(meta["date"]) == date.today().isoformat()


def test_two_corrections_append_to_one_page(box):
    _say(box, "改成每 6 小时一次。")
    _say(box, "from now on, always use the API lane.")
    text = box["page"].read_text(encoding="utf-8")
    assert text.count("待下次蒸馏判定") == 2 and text.count("type: correction-candidates") == 1


@pytest.mark.parametrize("text", [
    "所以还是定时蒸馏更可靠 不是吗！",
    "这个改成 B 对不对？",
    "检查一下我本机的第二大脑 是否正常运作",
    "给我们的KRouter跟目前市场上热门的记忆系统作一个横向对比",
])
def test_questions_and_plain_requests_are_not_corrections(box, text):
    _say(box, text)
    assert not box["page"].exists()


def test_keys_are_redacted_and_long_text_is_cut(box):
    _say(box, "以后都用这个 key：" + KEY + " " + "很长的说明" * 80)
    text = box["page"].read_text(encoding="utf-8")
    assert KEY not in text
    line = [ln for ln in text.splitlines() if ln.startswith("- （")][0]
    assert "…" in line and len(line) < 420


def test_nothing_without_consent(box):
    (box["state"] / "import.json").write_text(json.dumps({"consent": False}), encoding="utf-8")
    _say(box, "改成每天两次。")
    assert not box["page"].exists()


def test_krouter_model_calls_are_not_captured(box):
    _say(box, "下面是会话摘录：原来 A，改成 B。", env={**box["env"], "KROUTER_IN_DISTILL": "1"})
    assert not box["page"].exists()


def test_long_prompts_are_not_captured(box):
    _say(box, "改成 B。" + "背景材料" * 500)
    assert not box["page"].exists()


def test_session_marked_not_to_record(box):
    _say(box, "#不记 以后一律用测试账号。")
    assert not box["page"].exists()
    transcript = box["tmp"] / "t.jsonl"
    rows = [{"type": "user", "message": {"role": "user", "content": "这段别记 #不记"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "好"}]}}]
    transcript.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    _say(box, "改成 B。", transcript=transcript)
    assert not box["page"].exists()


def test_an_answer_that_mentions_the_marker_does_not_mark_the_session(box):
    transcript = box["tmp"] / "t.jsonl"
    rows = [{"type": "user", "message": {"role": "user", "content": "怎么让一个会话不被记录？"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "在提问里写 #不记 就行。"}]}}]
    transcript.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    _say(box, "那以后一律这么做。", transcript=transcript)
    assert box["page"].exists()


def test_bad_input_never_fails_the_session(box):
    res = subprocess.run([sys.executable, str(HOOK), "prompt"], input="not json", env=box["env"],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0


def test_questions_attached_blocks_and_suggestions_are_not_corrections():
    sys.path.insert(0, str(HOOK.parent))
    import session_hook as h
    for text in ("另外我们有 ECC 纠错吗", "这两套机器性能上应该是一样的吗？", "你要不要再去社交媒体上查一下！",
                 '<pasted_content id="p1">验收改成只记录速度</pasted_content>',
                 '<artifact-view-context artifact="a">{"mode":"edit"}</artifact-view-context>'):
        assert h.correction_cue(h.own_words(text)) == "", text
    for text in ("缓存改成 512K", "不是 750B 的模型，你别再搞错！！！", "那就换成 NekoBox"):
        assert h.correction_cue(h.own_words(text)), text
    assert h.own_words('前面 <pasted_content id="p">粘贴的</pasted_content> 后面') == "前面   后面"
    assert h.own_words('改成这样 <pasted_content id="p">粘贴了一半，没有结尾') == "改成这样"


def test_settle_needs_shared_content_not_shared_correction_words():
    sys.path.insert(0, str(HOOK.parent))
    import corrections as c
    digest = ["- 4 卡版也保留两颗 CPU，不改成单 CPU（00:01）", "- 原来报价只有一套 → 改成 8 卡和 4 卡两套报价（00:01）",
              "- 原来缓存 256K → 改成 512K（03:17）"]
    got = {r["said"]: r for r in c.settle([{"said": "硬盘可以的话改成单块 1.92TB"}, {"said": "改成 512K"},
                                           {"said": "以后报价一律写两套"}], digest)}
    assert not got["硬盘可以的话改成单块 1.92TB"]["ok"]  # 只共有"改成"，不是同一件事
    assert got["改成 512K"]["ok"] and "512K" in got["改成 512K"]["line"]
    assert not got["以后报价一律写两套"]["ok"]  # 只共有"报价"一个中文词组，不够

