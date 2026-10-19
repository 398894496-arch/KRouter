#!/usr/bin/env python3
"""Resolve the self-evolution key from the vault page and a local CLI login.

The knowledge-base page is the config. No extra env file. No pin required.
Timer auto-detects a logged-in grok / official Codex / claude / opencode / …
CLI, or loads *_API_KEY from the vault page into the writer process.

Never prints secrets. Never writes keys into git.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PLACEHOLDERS = ("YOUR_", "CHANGE_ME", "REPLACE", "TODO", "sk-your", "PASTE_")
TIMEOUT = 12
KEY_LINE = re.compile(r"^(?:export\s+)?([A-Z][A-Z0-9_]+)=(.*)$")
GEMINI_NAMES = frozenset(
    {"GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY"}
)
CONFIG_NAMES = frozenset(
    {"OPENAI_BASE_URL", "OPENAI_API_BASE", "MODEL", "DISTILL_MODEL", "KROUTER_DISTILL_MODEL"}
)
BEARER_URLS = {
    "OPENAI_API_KEY": "https://api.openai.com/v1/models",
    "DEEPSEEK_API_KEY": "https://api.deepseek.com/models",
    "XAI_API_KEY": "https://api.x.ai/v1/models",
    "GROQ_API_KEY": "https://api.groq.com/openai/v1/models",
    "OPENROUTER_API_KEY": "https://openrouter.ai/api/v1/models",
    "TOGETHER_API_KEY": "https://api.together.xyz/v1/models",
    "FIREWORKS_API_KEY": "https://api.fireworks.ai/inference/v1/models",
    "MISTRAL_API_KEY": "https://api.mistral.ai/v1/models",
    "MOONSHOT_API_KEY": "https://api.moonshot.ai/v1/models",
    "KIMI_API_KEY": "https://api.moonshot.ai/v1/models",
    "DASHSCOPE_API_KEY": "https://dashscope.aliyuncs.com/compatible-mode/v1/models",
    "ZHIPUAI_API_KEY": "https://open.bigmodel.cn/api/paas/v4/models",
    "GLM_API_KEY": "https://open.bigmodel.cn/api/paas/v4/models",
    "SILICONFLOW_API_KEY": "https://api.siliconflow.cn/v1/models",
    "CEREBRAS_API_KEY": "https://api.cerebras.ai/v1/models",
    "PERPLEXITY_API_KEY": "https://api.perplexity.ai/models",
    "COHERE_API_KEY": "https://api.cohere.com/v1/models",
    "NVIDIA_API_KEY": "https://integrate.api.nvidia.com/v1/models",
}


def _load_lane():
    """CLI candidates, login probes and harness flagships live in the skill's llm.py, shared with the
    nightly steps. Loaded by file path so an unrelated `llm` package on sys.path cannot stand in for it."""
    import importlib.util

    here = Path(__file__).resolve().parent
    for scripts in (here.parents[1] / "skill/krouter-obsidian/scripts",
                    Path.home() / ".agents/skills/krouter-obsidian/scripts"):
        path = scripts / "llm.py"
        if path.is_file():
            spec = importlib.util.spec_from_file_location("krouter_llm", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if str(scripts) not in sys.path:
                sys.path.append(str(scripts))
            return mod
    raise SystemExit("KRouter: skill/krouter-obsidian/scripts/llm.py not found")


_lane = _load_lane()
import zones  # noqa: E402  (skill scripts dir, appended by _load_lane)
import notify  # noqa: E402
CLI_KIND_RE = _lane.CLI_KIND_RE
GENERIC_PROBE_TAILS = _lane.GENERIC_PROBE_TAILS
CLI_FLAGSHIP = _lane.CLI_FLAGSHIP
detect_candidates = _lane.detect_candidates
writer_probe_argv = _lane.writer_probe_argv
probe_writer = _lane.probe_writer
writer_ok = _lane.writer_ok
writer_kind = _lane.writer_kind
detect_writer = _lane.detect_writer
gate = _lane.gate


def vault_root() -> Path:
    raw = os.environ.get("OBSIDIAN_VAULT", "").strip()
    if not raw:
        raise SystemExit("OBSIDIAN_VAULT is not set")
    return Path(raw)


def key_page(vault: Path) -> Path:
    return zones.path(vault, "90 系统文件/自动化/自进化钥匙.md")


def keys_env_path() -> Path:
    raw = os.environ.get("KROUTER_KEYS_ENV", "").strip()
    return Path(raw) if raw else Path.home() / ".dsh-krouter-keys.env"


def usable(val: str) -> bool:
    val = (val or "").strip().strip('"').strip("'")
    if not val:
        return False
    upper = val.upper()
    return not any(val.startswith(p) or upper.startswith(p.upper()) for p in PLACEHOLDERS)


def is_key_name(name: str) -> bool:
    """Secret names only. Base URLs and model pins are config, not keys."""
    if name in GEMINI_NAMES or name == "HF_TOKEN":
        return True
    return name.endswith("_API_KEY") or name.endswith("_API_TOKEN")


def is_config_name(name: str) -> bool:
    return name in CONFIG_NAMES


def parse_vault_page(text: str) -> dict[str, str]:
    """Pull KEY=value from fenced env blocks and bare lines. No secrets logged."""
    found: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("```"):
            continue
        m = KEY_LINE.match(line)
        if not m:
            continue
        name, val = m.group(1), m.group(2).strip().strip('"').strip("'")
        if (is_key_name(name) or is_config_name(name)) and usable(val):
            found[name] = val
    return found


def collect_keys(vault: Path) -> dict[str, str]:
    """Process env, then the keys file. A key pasted on the vault page is moved into the keys file first
    (so a newly pasted key still wins), and the vault is never read for keys. Values are never printed.
    """
    keys: dict[str, str] = {}
    for name, val in os.environ.items():
        if (is_key_name(name) or is_config_name(name)) and usable(val):
            keys[name] = val.strip().strip('"').strip("'")
    _lane.move_page_keys(vault)  # 钥匙页上贴的 key 先挪进钥匙文件；之后只读文件，永不从库里读
    path = keys_env_path()
    if path.is_file():
        keys.update(parse_vault_page(path.read_text(encoding="utf-8", errors="replace")))
    return keys


def extra_urls(keys: dict[str, str]) -> dict[str, str]:
    extra: dict[str, str] = {}
    for name in sorted(CONFIG_NAMES):
        val = keys.get(name) or os.environ.get(name, "")
        if usable(val):
            extra[name] = val.strip().strip('"').strip("'")
    return extra


def models_url(name: str, extra: dict[str, str]) -> str | None:
    if name in GEMINI_NAMES or name in {"ANTHROPIC_API_KEY", "CURSOR_API_KEY"}:
        return None
    if name == "OPENAI_API_KEY":
        base = extra.get("OPENAI_BASE_URL") or extra.get("OPENAI_API_BASE") or "https://api.openai.com/v1"
        return base.rstrip("/") + "/models"
    if name in BEARER_URLS:
        return BEARER_URLS[name]
    base = extra.get("OPENAI_BASE_URL") or extra.get("OPENAI_API_BASE")
    if base:
        return base.rstrip("/") + "/models"
    return None


def probe_key(name: str, key: str, extra: dict[str, str] | None = None) -> str:
    extra = extra or {}
    if name == "CURSOR_API_KEY":
        return "unprobed"
    if name == "ANTHROPIC_API_KEY":
        url = "https://api.anthropic.com/v1/models"
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Accept": "application/json",
        }
    elif name in GEMINI_NAMES:
        q = urllib.parse.urlencode({"key": key})
        url = f"https://generativelanguage.googleapis.com/v1beta/models?{q}"
        headers = {"Accept": "application/json"}
    else:
        url = models_url(name, extra)
        if not url:
            return "unprobed"
        headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
        if name == "OPENROUTER_API_KEY":
            headers["HTTP-Referer"] = "https://github.com/398894496-arch/KRouter"
            headers["X-Title"] = "KRouter"
    req = urllib.request.Request(url, headers=headers, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            code = getattr(resp, "status", 200) or 200
    except urllib.error.HTTPError as exc:
        code = exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return "network"
    if code in (200, 204, 429):
        return str(code)
    return str(code)


def live_keys(keys: dict[str, str], extra: dict[str, str], probe: bool) -> tuple[dict[str, str], str]:
    """Return (live_key_map, field) where field is present|missing|dead|unknown."""
    secret_names = [n for n in keys if not is_config_name(n)]
    if not secret_names:
        return {}, "missing"
    if not probe:
        return {n: keys[n] for n in secret_names}, "present"
    live: dict[str, str] = {}
    network = False
    dead = False
    for name in secret_names:
        result = probe_key(name, keys[name], extra)
        if result in {"200", "204", "429", "unprobed"}:
            live[name] = keys[name]
        elif result == "network":
            network = True
        elif result.isdigit():
            dead = True
    if live:
        return live, "present"
    if network:
        return {}, "unknown"
    if dead:
        return {}, "dead"
    return {}, "missing"


def writer_field_of(writer: str, wr: str) -> str:
    if wr == "path-agent":
        return "missing"
    if writer and Path(writer).is_file() and os.access(writer, os.X_OK):
        return "present"
    return "missing"


LIVE_FOREIGN_ROUTER = "obsidian-knowledge-router"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def bundled_router() -> Path:
    return repo_root() / "skill/krouter-obsidian/scripts/route_knowledge.sh"


def is_foreign_live_router(path: Path) -> bool:
    return LIVE_FOREIGN_ROUTER in path.as_posix()


def timer_router() -> Path:
    """Clone skill only. Never the host's live obsidian-knowledge-router."""
    pinned = os.environ.get("KROUTER_ROUTER", "").strip()
    candidates: list[Path] = []
    if pinned:
        candidates.append(Path(pinned))
    candidates.append(bundled_router())
    candidates.append(Path.home() / ".agents/skills/krouter-obsidian/scripts/route_knowledge.sh")
    for path in candidates:
        if is_foreign_live_router(path):
            continue
        if path.is_file():
            return path
    return bundled_router()


def enrich_path(raw: str) -> str:
    home = Path.home()
    extra = [str(home / ".grok/bin"), str(home / ".local/bin")]
    parts = [p for p in raw.split(":") if p] if raw else []
    for item in reversed(extra):
        if item not in parts:
            parts.insert(0, item)
    return ":".join(parts)


def distill_wrote(vault: Path, day) -> bool:
    month = zones.path(vault, "05 时间日志") / day.strftime("%Y-%m")
    if not month.is_dir():
        return False
    prefix = day.strftime("%d")
    for path in month.iterdir():
        if path.is_file() and path.name.startswith(prefix + "｜"):
            return True
    return False


def zone_note(vault: Path) -> str:
    """This vault renamed the default folders: say so, so the writer writes where the vault keeps them."""
    pairs = zones.pairs(vault)
    if not pairs:
        return ""
    lines = "\n".join(f"- `{a}` → `{b}`" for a, b in pairs)
    return ("This vault renames the default layout. Wherever the instructions below say the left name, "
            f"use the right one:\n{lines}\n\n")


def write_runtime_prompt(base: Path, vault: Path, router: Path) -> Path:
    header = (
        "# Runtime lock (injected by the timer)\n\n"
        f"OBSIDIAN_VAULT={vault}\n"
        f"KROUTER_ROUTER={router}\n\n"
        f"Run `{router} status` (then search / correction as needed), exactly as written: no `env` or `VAR=` prefix, "
        "no other command — the writer's permissions allow the router and nothing else. "
        "Write only inside that vault. "
        "Do not read or run ~/.agents/skills/obsidian-knowledge-router "
        "or any other knowledge router.\n\n"
        + zone_note(vault)
        + "---\n\n"
    )
    # 放在库里：grok 的内核沙箱只许读库目录，库外的提示文件它读不到。`.krouter/` 是点目录，不进索引，跑完就删
    dest = vault / ".krouter" / "runtime-prompt.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(header + base.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


GROK_PROFILE = "krouter"
GROK_MARK = "# krouter: written by KRouter for the nightly writer; regenerated every run"


def write_grok_sandbox(vault: Path, router: Path) -> None:
    """A kernel-enforced grok sandbox for the writer: read and write the vault, read the router, write its cache
    and state; nothing else in the account — no keys file, no ~/.ssh, no browser profiles. Extends grok's
    built-in `strict` profile (read CWD + system paths, write CWD + temp). Other profiles in the file are kept."""
    home = Path.home()
    cache = Path(os.environ.get("KROUTER_CACHE_DIR") or home / ".cache" / "krouter")
    state = Path(os.environ.get("KROUTER_STATE_DIR") or home / ".local" / "state" / "krouter")
    for d in (cache, state):
        d.mkdir(parents=True, exist_ok=True)
    skill = router.resolve().parent
    block = "\n".join([
        GROK_MARK, f"[profiles.{GROK_PROFILE}]", 'extends = "strict"',
        "read_only = " + json.dumps(sorted({skill.as_posix(), skill.parent.as_posix()})),
        "read_write = " + json.dumps([cache.as_posix(), state.as_posix()]), "",
    ])
    path = vault / ".grok" / "sandbox.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    kept, skipping = [], False
    for line in lines:  # drop our previous block (marker line through the next blank line), keep everything else
        if line == GROK_MARK:
            skipping = True
            continue
        if skipping:
            skipping = bool(line.strip())
            continue
        kept.append(line)
    old = "\n".join(kept).rstrip()
    path.write_text((old + "\n\n" if old else "") + block, encoding="utf-8")


def claude_allow(vault: Path, router: Path) -> list[str]:
    """Claude Code has no kernel sandbox here, so its tools are allow-listed instead: read and edit only inside
    the vault, run only the router, no other shell command, no web fetch; anything else is refused (`dontAsk`)."""
    v = str(vault).rstrip("/")
    r = str(router)
    return [f"Read(/{v}/**)", f"Edit(/{v}/**)", "Glob", "Grep", f"Bash(sh {r}:*)", f"Bash({r}:*)", f"Bash(bash {r}:*)",
            f"Bash(/bin/sh {r}:*)"]


def writer_invoke(writer: str, prompt: Path, vault: Path, router: Path | None = None) -> list[str]:
    """argv for the CLI writer. grok runs in a kernel sandbox; claude with an allow-list and no other shell;
    codex in its workspace-write sandbox (writes the vault only, can still read the account); other harnesses
    have no confinement KRouter can set, and the install prompt says so."""
    router = router or Path(os.environ.get("KROUTER_ROUTER") or timer_router())
    kind, _ = writer_probe_argv(writer)
    vault_s = str(vault)
    prompt_s = str(prompt)
    flagship = os.environ.get("KROUTER_DISTILL_MODEL", "").strip() or CLI_FLAGSHIP.get(kind, "")
    if kind == "grok":
        argv = [writer]
        if flagship:
            argv.extend(["--model", flagship])
        argv.extend(
            [
                "--prompt-file",
                prompt_s,
                "--always-approve",
                "--permission-mode",
                "bypassPermissions",
                "--sandbox",
                GROK_PROFILE,
                "--max-turns",
                "32",
                "--no-alt-screen",
                "--cwd",
                vault_s,
            ]
        )
        return argv
    if kind == "codex":
        return [
            writer,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "-C",
            vault_s,
            "--add-dir",
            vault_s,
            "-",
        ]
    if kind == "claude":
        argv = [writer, "--print", "--no-session-persistence", "--permission-mode", "dontAsk",
                "--tools", "Read,Edit,Write,Glob,Grep,Bash", "--add-dir", vault_s]
        if flagship:
            argv.extend(["--model", flagship])
        return argv + ["--allowedTools", *claude_allow(vault, router)]  # prompt on stdin
    if kind == "opencode":
        return [writer, "run", "--auto", "--dir", vault_s, prompt.read_text(encoding="utf-8")]
    if kind in {"kimi", "pi", "vibe", "antigravity", "cursor"}:
        return [writer, "--print", prompt.read_text(encoding="utf-8")]
    return [writer, "--print", prompt_s]


def status_payload(detect: bool, probe: bool) -> dict[str, str]:
    vault = vault_root()
    page = key_page(vault)
    keys = collect_keys(vault)
    extra = extra_urls(keys)
    live, key_field = live_keys(keys, extra, probe=probe)
    pinned = os.environ.get("KROUTER_WRITER", "").strip()
    writer, wr = ("", "unset")
    if detect:
        writer, wr = detect_writer(pinned)
    elif pinned:
        writer, wr = pinned, gate(probe_writer(pinned)) if probe else "skipped"
    cli_ok = writer_ok(wr) and not wr.startswith("api-writer")
    writer_field = writer_field_of(writer, wr)
    if cli_ok:
        key_field = "present"
    elif live:
        bundled = Path(__file__).resolve().parent / "api_writer.py"
        if bundled.is_file():
            writer_field = "present"
            writer = str(bundled)
            wr = "api-writer:ok"
    return {
        "key_page": str(page),
        "key": key_field,
        "writer": writer_field,
        "writer_path": writer,
        "writer_probe": wr,
        "lane": "cli-login" if cli_ok else ("api-key" if live else "none"),
        "kind": "api-writer" if wr.startswith("api-writer") else (writer_kind(wr) if wr not in {"unset", "skipped"} else ""),
    }


def patch_health(vault: Path, key_field: str, writer_field: str) -> None:
    health = zones.path(vault, "90 系统文件/自动化/日更健康.md")
    patch = Path(__file__).resolve().parent / "patch_health.py"
    if not health.is_file() or not patch.is_file():
        return
    if key_field:
        subprocess.run(
            [sys.executable, str(patch), str(health), "self_evolution_key", key_field],
            check=False,
        )
    subprocess.run(
        [sys.executable, str(patch), str(health), "krouter_writer", writer_field],
        check=False,
    )


def distill_gate(payload: dict[str, str]) -> tuple[bool, int, str]:
    """Whether to run distill. Exit 0 = timer on, skip. API key alone is enough."""
    page = payload.get("key_page", "90 系统文件/自动化/自进化钥匙.md")
    probe = payload.get("writer_probe", "")
    cli_ok = writer_ok(probe) and not probe.startswith("api-writer")
    key = payload.get("key", "missing")
    if cli_ok or key == "present":
        return True, 0, ""
    if key == "unknown" and not cli_ok:
        return (
            False,
            0,
            "KRouter: timer on; key probe network failed. Distill skipped.",
        )
    return (
        False,
        0,
        f"KRouter: timer on; distill skipped. "
        f"Log in grok/codex/claude once, or put your *_API_KEY on {page} "
        f"or in {keys_env_path()}.",
    )


def apply_live_env(vault: Path, probe: bool) -> tuple[dict[str, str], dict[str, str]]:
    keys = collect_keys(vault)
    extra = extra_urls(keys)
    live, _ = live_keys(keys, extra, probe=probe)
    for name, val in live.items():
        os.environ[name] = val
    for name, val in extra.items():
        os.environ[name] = val
    return live, extra


def run_cli_writer(writer: str, vault: Path, router: Path) -> int:
    base = Path(__file__).resolve().parent / "PROMPT.md"
    prompt = write_runtime_prompt(base, vault, router)
    kind = writer_probe_argv(writer)[0]
    if kind == "grok":
        write_grok_sandbox(vault, router)
    argv = writer_invoke(writer, prompt, vault, router)
    stdin = subprocess.DEVNULL
    handle = None
    if kind in ("codex", "claude"):
        handle = open(prompt, "rb")
        stdin = handle
    try:
        proc = subprocess.run(argv, cwd=str(vault), stdin=stdin, env=_lane.cli_env())  # long-lived CLI token, if any
        code = int(proc.returncode or 0)
    except OSError:
        code = 1
    finally:
        if handle is not None:
            handle.close()
        prompt.unlink(missing_ok=True)
    from api_writer import target_day, write_pending

    day = target_day()
    if not distill_wrote(vault, day):
        write_pending(
            vault,
            day,
            f"CLI writer {kind} left no seal (exit {code}). Timer on; left to-summarize.",
        )
        print(
            "KRouter: CLI writer left a to-summarize note.",
            file=sys.stderr,
        )
    return 0


def exec_distill(probe: bool) -> int:
    vault = vault_root()
    payload = status_payload(detect=True, probe=probe)
    patch_health(vault, payload["key"], payload["writer"])
    ok, code, msg = distill_gate(payload)
    if not ok and "network" not in msg:
        # 没有模型：宿主不看终端也要知道；贴了 key 却认不出服务商时，说的是这个，不是"没有模型"
        notify.send(notify.PENDING_KEY if _lane.pending_keys() else notify.NO_WRITER, kind="no-writer")
    if not ok:
        print(msg, file=sys.stderr)
        return code
    live, extra = apply_live_env(vault, probe=probe)
    model = extra.get("MODEL") or extra.get("DISTILL_MODEL") or extra.get("KROUTER_DISTILL_MODEL")
    if model:
        os.environ["KROUTER_DISTILL_MODEL"] = model
    probe_result = payload.get("writer_probe", "")
    writer = payload.get("writer_path", "")
    router = timer_router()
    os.environ["KROUTER_ROUTER"] = str(router)
    os.environ["OBSIDIAN_VAULT"] = str(vault)
    os.environ["PATH"] = enrich_path(os.environ.get("PATH", ""))
    os.environ.setdefault("HOME", str(Path.home()))
    if live:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from api_writer import run as run_api

        return run_api(live, extra)
    if writer_ok(probe_result) and not probe_result.startswith("api-writer") and writer:
        return run_cli_writer(writer, vault, router)
    notify.send(notify.NO_WRITER, kind="no-writer")
    if probe_result.endswith(":unconfined"):
        print(f"KRouter: {writer_kind(probe_result)} is logged in but not used: it runs with no confinement KRouter "
              f"can set. Set KROUTER_ALLOW_UNCONFINED=1 in the keys file to use it anyway.", file=sys.stderr)
    if probe_result.endswith(":reads-account"):
        print("KRouter: Codex is logged in but not used: it can read your whole account. Set KROUTER_ALLOW_CODEX=1 "
              "in the keys file to use it anyway, or log in grok / claude (they are limited to the vault).",
              file=sys.stderr)
    print(
        f"KRouter: timer on; distill skipped. "
        f"Put *_API_KEY on {payload.get('key_page', 'the vault key page')} "
        f"or log in grok/codex/claude (Claudian-class subscription).",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve KRouter self-evolution key and writer")
    parser.add_argument("--exec", action="store_true", help="timer entry: detect, then run the writer")
    parser.add_argument("--status", action="store_true", help="print JSON status, no secrets")
    parser.add_argument("--sync-health", action="store_true", help="patch the health page from local detect")
    parser.add_argument("--offline", action="store_true", help="do not HTTP-probe API keys")
    parser.add_argument("--no-detect", action="store_true", help="do not spawn CLI login probes")
    args = parser.parse_args()
    probe = not args.offline
    if args.exec:
        return exec_distill(probe=probe)
    payload = status_payload(detect=not args.no_detect, probe=probe)
    if args.sync_health:
        patch_health(vault_root(), payload["key"], payload["writer"])
    if args.status or args.sync_health:
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
