"""End-to-end API lane on a loopback OpenAI-compatible stub.

No provider, no credential: the token is a literal for 127.0.0.1. Covers the whole
path a paying stranger takes -- catalog, flagship lock, chat, seal on disk -- plus
the failure branch that must leave a to-summarize note.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RUN_SH = REPO / "extras/host-daily-evolution/run.sh"
TOKEN = "loopback-stub-token"
DAY = "2026-08-21"
SEAL_REL = "05 时间日志/2026-08/21｜stub sealed day.md"
PENDING_REL = "05 时间日志/2026-08/21｜待总结.md"


class _Stub(BaseHTTPRequestHandler):
    seen: dict = {}
    fail_chat = False

    def log_message(self, *_args):  # keep pytest output clean
        pass

    def _json(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.path.endswith("/models"):
            self.send_error(404)
            return
        self.seen["models"] = self.seen.get("models", 0) + 1
        self._json({"data": [{"id": "gpt-4o-mini"}, {"id": "gpt-4.1"}]})

    def do_POST(self):
        if not self.path.endswith("/chat/completions"):
            self.send_error(404)
            return
        self.seen["chat"] = self.seen.get("chat", 0) + 1
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        self.seen["model"] = body.get("model", "")
        self.seen.setdefault("models_used", []).append(body.get("model", ""))
        self.seen["auth_bearer"] = self.headers.get("Authorization") == f"Bearer {TOKEN}"
        if self.fail_chat:
            self.send_error(500)
            return
        seal = {
            "files": [
                {
                    "path": SEAL_REL,
                    "content": "---\ntitle: 21｜stub sealed day\ntype: daily-log\n---\n\nSealed.\n",
                }
            ]
        }
        content = "```json\n" + json.dumps(seal, ensure_ascii=False) + "\n```"
        self._json({"choices": [{"message": {"role": "assistant", "content": content}}]})


def _run(tmp_path: Path, fail_chat: bool, extra_env: dict | None = None) -> tuple[subprocess.CompletedProcess, Path, dict]:
    vault = tmp_path / "MySecondBrain"
    shutil.copytree(REPO / "template", vault)

    handler = type("Handler", (_Stub,), {"seen": {}, "fail_chat": fail_chat})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/v1"
    try:
        proc = subprocess.run(
            ["/bin/sh", str(RUN_SH)],
            env={
                "HOME": str(tmp_path),
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "LANG": "en_US.UTF-8",
                "OBSIDIAN_VAULT": str(vault),
                "TARGET_DATE": DAY,
                "OPENAI_API_KEY": TOKEN,
                "OPENAI_BASE_URL": base,
                "KROUTER_KEYS_ENV": str(tmp_path / "keys.env"),
                "NO_PROXY": "127.0.0.1,localhost",
                **(extra_env or {}),
            },
            capture_output=True,
            text=True,
            timeout=120,
        )
    finally:
        server.shutdown()
        server.server_close()
    return proc, vault, dict(handler.seen)


@pytest.mark.skipif(os.name == "nt", reason="run.sh is POSIX")
def test_api_lane_seals_the_day(tmp_path: Path):
    proc, vault, seen = _run(tmp_path, fail_chat=False)
    assert proc.returncode == 0, proc.stderr
    assert seen.get("models", 0) > 0, "flagship lock never read the catalog"
    assert seen.get("model") == "gpt-4.1", "flagship lock did not pick the top model"
    assert seen.get("auth_bearer") is True, "key was not sent as a bearer token"
    assert (vault / SEAL_REL).is_file(), "no seal written"
    assert not (vault / PENDING_REL).exists(), "left a to-summarize note on success"
    key_page = vault / "90 系统文件/自动化/自进化钥匙.md"
    assert TOKEN not in key_page.read_text(encoding="utf-8"), "writer edited the key page"


@pytest.mark.skipif(os.name == "nt", reason="run.sh is POSIX")
def test_api_lane_failure_leaves_pending(tmp_path: Path):
    proc, vault, seen = _run(tmp_path, fail_chat=True)
    assert seen.get("chat", 0) > 0
    assert not (vault / SEAL_REL).exists()
    assert (vault / PENDING_REL).is_file(), "failed API run left no to-summarize note"
    assert proc.returncode != 0


@pytest.mark.skipif(os.name == "nt", reason="run.sh is POSIX")
def test_timer_runs_nightly_upkeep_without_touching_the_seal(tmp_path: Path):
    proc, vault, seen = _run(tmp_path, fail_chat=False)
    assert proc.returncode == 0, proc.stderr
    assert (vault / SEAL_REL).is_file(), "nightly upkeep disturbed the seal"
    assert (vault / "90 系统文件/自动化/下意识体检.md").is_file(), "checkup did not run"
    # one lane: the nightly steps reach the same provider with the same flagship lock as the writer
    assert len(seen.get("models_used", [])) > 1, "nightly steps did not use the writer's key"
    assert set(seen["models_used"]) == {"gpt-4.1"}, seen["models_used"]


@pytest.mark.skipif(os.name == "nt", reason="run.sh is POSIX")
def test_timer_nightly_can_be_turned_off_and_keeps_failure_exit(tmp_path: Path):
    proc, vault, _seen = _run(tmp_path, fail_chat=True, extra_env={"KROUTER_NIGHTLY": "0"})
    assert proc.returncode != 0
    assert not (vault / "90 系统文件/自动化/下意识体检.md").exists()
