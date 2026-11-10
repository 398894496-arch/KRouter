"""A key pasted into the vault never leaves through KRouter: not to a model, not into an agent's context,
not into the query log or the recall cache."""

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
FAKE = "sk-FAKEFAKEFAKE1234567890abcdef"
KEY_PAGE = "90 系统文件/自动化/自进化钥匙.md"
OTHER = "90 系统文件/Agent记忆/DeepSeek 凭据.md"  # secret by its name: never sent, never quoted
PLAIN = "02 经验与方法/模型服务.md"  # an ordinary name with a key written the way people write it
BARE = "Ab3dEf7hIj9kLm2nOp4qRs6t"  # no known prefix (Mistral-style)


@pytest.fixture()
def keyed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    shutil.copytree(REPO / "template", vault)
    page = vault / KEY_PAGE
    # what the page tells a host to do: uncomment one line and paste the key
    page.write_text(re.sub(r"^# (DEEPSEEK_API_KEY=).*$", r"\g<1>" + FAKE, page.read_text(encoding="utf-8"),
                           count=1, flags=re.M), encoding="utf-8")
    (vault / OTHER).write_text("---\ntitle: DeepSeek 凭据\nstatus: active\n---\n\n# DeepSeek 凭据\n\n"
                               f"脚本读环境变量 DEEPSEEK_API_KEY。\nDEEPSEEK_API_KEY={FAKE}\n", encoding="utf-8")
    (vault / PLAIN).write_text("---\ntitle: 模型服务\nstatus: active\n---\n\n# 模型服务\n\n"
                               f"用 Mistral 跑摘要，额度每月 5 美元。\nMistral 密钥：{BARE}\n", encoding="utf-8")
    return vault


def test_redact_keeps_placeholders_and_numbers():
    sys.path.insert(0, str(SCRIPTS))
    from krouter_redact import redact

    assert FAKE not in redact(f"DEEPSEEK_API_KEY={FAKE}")
    assert redact("# DEEPSEEK_API_KEY=YOUR_DEEPSEEK_API_KEY") == "# DEEPSEEK_API_KEY=YOUR_DEEPSEEK_API_KEY"
    assert redact("tokens: 158386") == "tokens: 158386" and redact("max_tokens=8000") == "max_tokens=8000"
    assert "abcdefghijklmnopqrstu" not in redact("Authorization: Bearer abcdefghijklmnopqrstu12345")
    assert "ghp_" not in redact("用 ghp_ABCDEFGHIJKLMNOPQRSTUVWX12 推送")


def test_cards_and_topics_never_send_a_key(keyed_vault, monkeypatch, tmp_path):
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    import answer_cards as ac
    import consolidate_topics as ct
    import llm

    sent: list[str] = []

    def capture(prompt, v=None):
        sent.append(prompt)
        return "{}"

    monkeypatch.setattr(llm, "complete", capture)
    monkeypatch.setattr("sys.argv", ["answer_cards.py", "--vault", str(keyed_vault), "--jobs", "1"])
    assert ac.main() == 0
    assert sent, "answer cards sent nothing at all"
    assert KEY_PAGE not in ac.targets(keyed_vault)  # the key page is never a card target
    assert not any(FAKE in p or BARE in p for p in sent)
    assert not any(OTHER in p for p in sent)  # a 凭据 page is secret by name: not sent at all
    assert any(PLAIN in p and "额度每月" in p for p in sent)  # an ordinary page still goes, its key redacted
    evidence, sources, _ = ct.gather(keyed_vault, {"slug": "k", "title": "密钥", "terms": ["DEEPSEEK_API_KEY"], "auth": []})
    assert FAKE not in evidence and KEY_PAGE not in sources


@pytest.mark.skipif(os.name == "nt", reason="POSIX router")
@pytest.mark.parametrize("sh_only", ["0", "1"])
def test_router_never_prints_or_logs_a_key(keyed_vault, tmp_path, sh_only):
    state, cache = tmp_path / "state", tmp_path / "cache"
    env = {**os.environ, "OBSIDIAN_VAULT": str(keyed_vault), "KROUTER_SH_ONLY": sh_only, "KROUTER_STATE_DIR": str(state),
           "KROUTER_CACHE_DIR": str(cache), "KROUTER_NO_QUERY_LOG": "0"}
    for route, q in (("search", "DEEPSEEK API key 怎么填"), ("search", "DEEPSEEK_API_KEY"), ("memory", "DeepSeek 凭据"),
                     ("search", f"我的 key 是 {FAKE}"), ("search", "Mistral 密钥"), ("search", "模型服务")):
        out = subprocess.run(["/bin/sh", str(SCRIPTS / "route_knowledge.sh"), route, q], env=env,
                             capture_output=True, text=True, timeout=60)
        shown = out.stdout.replace(q, "")
        assert FAKE not in shown and BARE not in shown, (route, q)
    log = state / "queries.jsonl"
    if log.is_file():
        assert FAKE not in log.read_text(encoding="utf-8")
    for db in cache.rglob("*.sqlite*"):
        assert FAKE.encode() not in db.read_bytes() and BARE.encode() not in db.read_bytes()


def test_upgrade_rebuilds_a_cache_built_before_redaction(keyed_vault, tmp_path, monkeypatch):
    """A cache written by an older version holds raw page text; the schema bump must force a full rebuild."""
    monkeypatch.setenv("KROUTER_CACHE_DIR", str(tmp_path / "cache"))
    import recall_index as ri

    con = ri.connect(ri.cache_path(keyed_vault))
    ri.refresh(keyed_vault, con)
    # simulate the old cache: same files, raw (unredacted) body, older schema tag
    con.execute("UPDATE docs SET body = body || ' ' || ?", (FAKE,))
    con.execute("UPDATE meta SET v='recall-v11' WHERE k='schema'")
    con.commit()
    con.close()
    con = ri.connect(ri.cache_path(keyed_vault))
    ri.refresh(keyed_vault, con)
    assert not any(FAKE in (b or "") for (b,) in con.execute("SELECT body FROM docs"))
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    for db in (tmp_path / "cache").rglob("*.sqlite*"):
        assert FAKE.encode() not in db.read_bytes(), db  # not left behind in free pages either


REDACT_CASES = [  # the shapes an outside review found leaking, plus the ones 0.10.2 already caught
    "密钥：{v}", "凭据 {v}", "Key: {v}", "| DeepSeek | {v} |", "https://api.example.com/v1?key={v}&a=1",
    "postgres://admin:{v}@db.local:5432/app",
    # an unlabeled bare-hex key is left to the secret-page layer: pure hex is how notes record commits and digests
    "Together key: a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4", "智谱 0f3e2d1c0f3e2d1c.{v}",
    "fw_{v}", "pplx-{v}{v}", "nvapi-{v}{v}", "csk-{v}", "Mistral 密钥：{v}", "DEEPSEEK_API_KEY=sk-{v}",
    "Authorization: Bearer {v}", 'secret = "{v}"',
]
KEEP_CASES = [
    "tokens: 158386", "max_tokens=8000", "# DEEPSEEK_API_KEY=YOUR_DEEPSEEK_API_KEY", "凭据 页面在 90 系统文件",
    "会话 20260811-090406-v4-flash-abcdefgh", "路径 short-video-governance-contract.md",
    "UUID 123e4567-e89b-12d3-a456-426614174000", "OPENAI_BASE_URL=https://api.example/v1", "版本 v0.10.2，端口 8080",
    "key 读 DEEPSEEK_API_KEY 变量", "api_key: <your key>",
]


@pytest.mark.parametrize("case", REDACT_CASES)
def test_redact_catches_the_common_shapes(case):
    sys.path.insert(0, str(SCRIPTS))
    from krouter_redact import redact

    out = redact(case.format(v=BARE))
    assert BARE[:12] not in out and "a1b2c3d4a1b2c3d4" not in out and "0f3e2d1c0f3e" not in out, out


@pytest.mark.parametrize("case", KEEP_CASES)
def test_redact_leaves_ordinary_text_alone(case):
    sys.path.insert(0, str(SCRIPTS))
    from krouter_redact import redact

    assert redact(case) == case


PASTES = [  # how people paste a key on the key page (outside review, round six)
    ("DEEPSEEK_API_KEY=sk-{v}", "DEEPSEEK_API_KEY"),
    ('export DEEPSEEK_API_KEY="sk-{v}"', "DEEPSEEK_API_KEY"),
    ("DEEPSEEK_API_KEY: sk-{v}", "DEEPSEEK_API_KEY"),
    ("DeepSeek 密钥：sk-{v}", "DEEPSEEK_API_KEY"),
    ("- DEEPSEEK_API_KEY=sk-{v}", "DEEPSEEK_API_KEY"),
    ("Gemini 的 key 是 AIza{v}{v}", "GEMINI_API_KEY"),
    ("sk-{v}", "KROUTER_PENDING_KEY_1"),  # no provider word, ambiguous prefix: held, not guessed
]


@pytest.mark.parametrize("paste,name", PASTES)
def test_any_pasted_key_leaves_the_vault(keyed_vault, tmp_path, monkeypatch, paste, name):
    sys.path.insert(0, str(SCRIPTS))
    import llm

    keys = tmp_path / "keys.env"
    monkeypatch.setenv("KROUTER_KEYS_ENV", str(keys))
    page = keyed_vault / KEY_PAGE
    page.write_text("# 自进化钥匙\n\n" + paste.format(v=BARE) + "\n", encoding="utf-8")
    assert llm.move_page_keys(keyed_vault) == [name]
    assert BARE not in page.read_text(encoding="utf-8")  # gone from the vault
    assert f"{name}=" in keys.read_text(encoding="utf-8") and BARE in keys.read_text(encoding="utf-8")
    if name.startswith("KROUTER_PENDING"):
        assert "DEEPSEEK_API_KEY" in page.read_text(encoding="utf-8")  # the note says how to name it
        assert llm.pending_keys() == [name]


def test_hashes_in_notes_survive_redaction():
    sys.path.insert(0, str(SCRIPTS))
    from krouter_redact import redact

    for text in ("根因在 commit 3f6c4a7da8b6ff65c51203b9d4813653bb84ef90，回滚时 revert 它",
                 "sha256 d8c1d5af1234567890abcdef1234567890abcdef1234567890abcdef12345678",
                 "integrity sha512-y77VWOwb/Th4MabcdEFGH1234567yxZfYWe5+K+Pg=="):
        assert redact(text) == text
    assert "a1b2c3d4a1b2" not in redact("Together 密钥：" + "a1b2c3d4" * 8)  # labelled hex is still a key


def test_two_keys_on_one_line_are_both_kept(keyed_vault, tmp_path, monkeypatch):
    sys.path.insert(0, str(SCRIPTS))
    import llm

    keys = tmp_path / "keys.env"
    monkeypatch.setenv("KROUTER_KEYS_ENV", str(keys))
    page = keyed_vault / KEY_PAGE
    other = "Zy9xWv8uTs7rQp6oNm5lKj4i"
    page.write_text(f"DeepSeek: sk-{BARE} OpenAI: sk-proj-{other}\n", encoding="utf-8")
    assert set(llm.move_page_keys(keyed_vault)) == {"DEEPSEEK_API_KEY", "OPENAI_API_KEY"}
    text = keys.read_text(encoding="utf-8")
    assert f"DEEPSEEK_API_KEY=sk-{BARE}" in text and f"OPENAI_API_KEY=sk-proj-{other}" in text
    assert BARE not in page.read_text(encoding="utf-8") and other not in page.read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY" in page.read_text(encoding="utf-8") and "OPENAI_API_KEY" in page.read_text(encoding="utf-8")


PATHS = [
    "报告在 /Users/me/Documents/2026Q3Report2026Final.csv",
    "见 https://docs.example.com/guide/v2/Install2026Guide",
    "备份 s3://bucket-a/2026Backup2026Daily/x",
    "gs://b/Model2026Weights2026v3",
    "~/proj/Release2026Notes2026v2",
]


@pytest.mark.parametrize("text", PATHS)
def test_paths_and_urls_survive_redaction(text):
    sys.path.insert(0, str(SCRIPTS))
    from krouter_redact import redact

    assert redact(text) == text


def test_keys_inside_urls_are_still_masked():
    sys.path.insert(0, str(SCRIPTS))
    from krouter_redact import redact

    assert BARE not in redact(f"https://api.x.com/v1?key={BARE}")
    assert "sk-abcdefghijklmnop1234" not in redact("https://hooks.example.com/sk-abcdefghijklmnop1234")


def test_rewiring_keys_keeps_lines_it_does_not_manage(tmp_path):
    """A re-install probes the API keys again; it must not delete the claude long-lived token, pending keys,
    a key that failed today's probe, or the host's comments."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "extras/host-daily-evolution"))
    import wire_keys

    path = tmp_path / "keys.env"
    path.write_text("# mine\nKROUTER_CLI_LOGIN=/old/claude\nDEEPSEEK_API_KEY=old\nCLAUDE_CODE_OAUTH_TOKEN=tok\n"
                    "KROUTER_PENDING_KEY_1=p\nGROQ_API_KEY=dead\n", encoding="utf-8")
    wire_keys.write_keys(path, {"DEEPSEEK_API_KEY": "new", "OPENAI_API_KEY": "o"}, "/opt/claude")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines == ["# mine", "KROUTER_CLI_LOGIN=/opt/claude", "DEEPSEEK_API_KEY=new", "CLAUDE_CODE_OAUTH_TOKEN=tok",
                     "KROUTER_PENDING_KEY_1=p", "GROQ_API_KEY=dead", "OPENAI_API_KEY=o"]
    assert oct(path.stat().st_mode & 0o777) == "0o600" or os.name == "nt"
    wire_keys.write_keys(path, {}, "")
    assert "KROUTER_CLI_LOGIN" not in path.read_text(encoding="utf-8")
    assert "CLAUDE_CODE_OAUTH_TOKEN=tok" in path.read_text(encoding="utf-8")
