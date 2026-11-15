
from api_writer import apply_files, lock_flagship, parse_files_payload, pick_chat, safe_vault_path


def test_pick_chat_deepseek():
    spec = pick_chat({"DEEPSEEK_API_KEY": "sk-live-looking"})
    assert spec is not None
    assert spec["name"] == "DEEPSEEK_API_KEY"
    assert spec["url"].endswith("/chat/completions")
    assert spec["style"] == "openai"
    assert spec["model"] == "deepseek-reasoner"
    assert "sk-live" not in spec["url"]


def test_lock_flagship_prefers_opus_over_haiku():
    locked = lock_flagship(
        ["claude-3-5-haiku-20241022", "claude-opus-4-20250514", "claude-sonnet-4-20250514"],
        fallback="haiku",
    )
    assert "opus" in locked


def test_lock_flagship_skips_mini():
    locked = lock_flagship(["gpt-4o-mini", "gpt-4.1", "o3"], fallback="gpt-4o-mini")
    assert locked in {"o3", "gpt-4.1"}
    assert "mini" not in locked


def test_pick_chat_unnamed_needs_base():
    keys = {"FOO_API_KEY": "sk-live-looking"}
    assert pick_chat(keys) is None
    spec = pick_chat(keys, {"OPENAI_BASE_URL": "https://api.example/v1"})
    assert spec is not None
    assert spec["url"] == "https://api.example/v1/chat/completions"


def test_pick_chat_openai_custom_base():
    spec = pick_chat(
        {"OPENAI_API_KEY": "sk-live-looking"},
        {"OPENAI_BASE_URL": "https://api.example/v1"},
    )
    assert spec is not None
    assert spec["url"] == "https://api.example/v1/chat/completions"


def test_safe_path_stays_in_vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    ok = safe_vault_path(vault, "05 时间日志/2026-08/21｜day.md")
    assert ok is not None
    assert str(ok).endswith("21｜day.md")
    assert safe_vault_path(vault, "../etc/passwd.md") is None
    assert safe_vault_path(vault, "90 系统文件/自动化/自进化钥匙.md") is None
    assert safe_vault_path(vault, "skill/canonical_sources.psv") is None
    assert safe_vault_path(vault, "Clippings/raw.md") is None
    assert safe_vault_path(vault, "note.txt") is None


def test_parse_and_apply_files(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    text = '```json\n{"files":[{"path":"05 时间日志/2026-08/21｜seal.md","content":"# 21｜seal\\n"}]}\n```'
    files = parse_files_payload(text)
    assert files[0]["path"].endswith("21｜seal.md")
    n = apply_files(vault, files)
    assert n == 1
    written = vault / "05 时间日志" / "2026-08" / "21｜seal.md"
    assert written.is_file()
    assert "seal" in written.read_text(encoding="utf-8")
    assert apply_files(vault, [{"path": "90 系统文件/自动化/自进化钥匙.md", "content": "no"}]) == 0
