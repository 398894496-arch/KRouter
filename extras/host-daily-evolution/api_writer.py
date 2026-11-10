#!/usr/bin/env python3
"""Bundled distill writer: an API key is enough. No grok / Codex / claude required.

Reads OBSIDIAN_VAULT, calls a mainstream chat API with PROMPT.md, writes markdown
only inside the vault. Never prints secrets. Never edits canonical_sources.psv
or the key page.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

TIMEOUT = 180
MAX_ROUNDS = 12
MAX_FILE_BYTES = 120_000
DENIED_NAMES = frozenset({"canonical_sources.psv", "自进化钥匙.md"})

HERE = Path(__file__).resolve().parent
PROMPT = HERE / "PROMPT.md"


def _load_lane():
    """The provider table and flagship lock live in the skill's llm.py: one table for the writer and the
    nightly steps. Loaded by file path so an unrelated `llm` package on sys.path cannot stand in for it."""
    for scripts in (HERE.parents[1] / "skill/krouter/scripts",
                    Path.home() / ".agents/skills/krouter/scripts"):
        path = scripts / "llm.py"
        if path.is_file():
            spec = importlib.util.spec_from_file_location("krouter_llm", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if str(scripts) not in sys.path:
                sys.path.append(str(scripts))
            return mod
    raise SystemExit("KRouter: skill/krouter/scripts/llm.py not found")


_lane = _load_lane()
import zones  # noqa: E402  (skill scripts dir, appended by _load_lane)
from krouter_redact import is_secret_page, redact  # noqa: E402
CHAT_SPECS = _lane.CHAT_SPECS
lock_flagship = _lane.lock_flagship
openai_headers = _lane.openai_headers
catalog_ids = _lane.catalog_ids
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a markdown file relative to the vault root.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write a markdown file relative to the vault root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_md",
            "description": "List markdown files under a vault-relative directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "route",
            "description": "Run route_knowledge.sh. route is status|search|correction|preference|memory|project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "route": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": ["route"],
            },
        },
    },
]


def vault_root() -> Path:
    raw = (os.environ.get("KROUTER_VAULT") or os.environ.get("OBSIDIAN_VAULT", "")).strip()
    if not raw:
        raise SystemExit("KROUTER_VAULT (or OBSIDIAN_VAULT) is not set")
    return Path(raw).resolve()


def model_override(keys: dict[str, str], extra: dict[str, str]) -> str:
    for name in ("MODEL", "DISTILL_MODEL", "KROUTER_DISTILL_MODEL"):
        val = (keys.get(name) or extra.get(name) or os.environ.get(name, "")).strip()
        if val:
            return val
    return ""


def pick_chat(keys: dict[str, str], extra: dict[str, str] | None = None) -> dict[str, str] | None:
    """Choose a chat endpoint. Return metadata only — never the secret."""
    extra = extra or {}
    override = model_override(keys, extra)
    base = (extra.get("OPENAI_BASE_URL") or extra.get("OPENAI_API_BASE") or "").rstrip("/")
    for name, url, model, style in CHAT_SPECS:
        if name not in keys:
            continue
        chosen = dict(name=name, url=url, model=override or model, style=style, locked="override" if override else "default")
        if name == "OPENAI_API_KEY" and base:
            chosen["url"] = base + "/chat/completions"
        return chosen
    for name, val in keys.items():
        if name in {"OPENAI_BASE_URL", "OPENAI_API_BASE", "MODEL", "DISTILL_MODEL", "KROUTER_DISTILL_MODEL"} or not val:
            continue
        if not (name.endswith("_API_KEY") or name.endswith("_API_TOKEN")):
            continue
        if not base:
            return None
        return {
            "name": name,
            "url": base + "/chat/completions",
            "model": override or "gpt-4.1",
            "style": "openai",
            "locked": "override" if override else "default",
        }
    return None


def safe_vault_path(vault: Path, rel: str) -> Path | None:
    rel = (rel or "").strip().lstrip("/")
    if not rel or ".." in Path(rel).parts:
        return None
    name = Path(rel).name
    if name in DENIED_NAMES:
        return None
    if rel.endswith("canonical_sources.psv"):
        return None
    if "Clippings/" in rel.replace("\\", "/"):
        return None
    path = (vault / rel).resolve()
    try:
        path.relative_to(vault)
    except ValueError:
        return None
    if path.suffix.lower() != ".md":
        return None
    return path


def parse_files_payload(text: str) -> list[dict[str, str]]:
    raw = (text or "").strip()
    if not raw:
        return []
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json|markdown|md)?\n", "", raw)
        raw = re.sub(r"\n```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    files = data.get("files") if isinstance(data, dict) else data
    if not isinstance(files, list):
        return []
    out: list[dict[str, str]] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        content = item.get("content")
        if path and isinstance(content, str):
            out.append({"path": path, "content": content})
    return out


def apply_files(vault: Path, files: list[dict[str, str]]) -> int:
    written = 0
    for item in files[:8]:
        # 模型按默认区名给路径；库里改过区名就换成真实路径
        path = safe_vault_path(vault, zones.real(vault, str(item.get("path") or "")))
        if path is None:
            continue
        body = item["content"]
        if len(body.encode("utf-8")) > MAX_FILE_BYTES:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if not body.endswith("\n"):
            body += "\n"
        path.write_text(body, encoding="utf-8")
        written += 1
    return written


def target_day() -> date:
    raw = os.environ.get("TARGET_DATE", "").strip()
    if raw:
        return date.fromisoformat(raw)
    return date.today() - timedelta(days=1)


def collect_snapshot(vault: Path, day: date) -> str:
    logs = zones.path(vault, "05 时间日志")
    names: list[str] = []
    if logs.is_dir():
        for p in sorted(logs.rglob("*.md")):
            try:
                rel = p.relative_to(vault).as_posix()
            except ValueError:
                continue
            names.append(rel)
            if len(names) >= 40:
                break
    health = zones.path(vault, "90 系统文件/自动化/日更健康.md")
    health_text = ""
    if health.is_file():
        health_text = redact(health.read_text(encoding="utf-8", errors="replace")[:2000])
    return json.dumps(
        {
            "target_date": day.isoformat(),
            "logs": names,
            "health": health_text,
        },
        ensure_ascii=False,
    )


def router_script() -> Path | None:
    from resolve import timer_router

    path = timer_router()
    return path if path.is_file() else None


def run_route(route: str, query: str = "") -> str:
    script = router_script()
    if script is None:
        return "router missing"
    argv = [str(script), route]
    if query:
        argv.append(query)
    env = os.environ.copy()
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return "router failed"
    text = (proc.stdout or "") + (proc.stderr or "")
    return text[:8000]


def tool_impl(vault: Path, name: str, args: dict) -> str:
    if name == "read_file":
        path = safe_vault_path(vault, zones.real(vault, str(args.get("path") or "")))
        if path is None or not path.is_file():
            return "denied or missing"
        if is_secret_page(zones.canon(vault, path.relative_to(vault).as_posix())):
            return "denied: secret page"
        return redact(path.read_text(encoding="utf-8", errors="replace")[:MAX_FILE_BYTES])
    if name == "write_file":
        files = [{"path": str(args.get("path") or ""), "content": str(args.get("content") or "")}]
        n = apply_files(vault, files)
        return "wrote" if n else "denied"
    if name == "list_md":
        rel = zones.real(vault, str(args.get("path") or ".").strip() or ".")
        root = (vault / rel).resolve()
        try:
            root.relative_to(vault)
        except ValueError:
            return "denied"
        if not root.is_dir():
            return "missing"
        names = []
        for p in sorted(root.rglob("*.md")):
            try:
                names.append(p.relative_to(vault).as_posix())
            except ValueError:
                continue
            if len(names) >= 60:
                break
        return "\n".join(names) or "(empty)"
    if name == "route":
        return run_route(str(args.get("route") or "status"), str(args.get("query") or ""))
    return "unknown tool"


def _http_json(url: str, payload: dict, headers: dict[str, str]) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"KRouter: chat API HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SystemExit("KRouter: chat API network failed") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit("KRouter: chat API returned non-JSON") from exc


def write_pending(vault: Path, day: date, reason: str) -> None:
    month = zones.path(vault, "05 时间日志") / day.strftime("%Y-%m")
    path = month / f"{day.strftime('%d')}｜待总结.md"
    if path.exists():
        return
    month.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ntitle: {day.strftime('%d')}｜待总结\ntype: daily-log\nstatus: to-summarize\ndate: {day.isoformat()}\n---\n\n"
        f"# {day.strftime('%d')}｜待总结\n\n{reason}\n",
        encoding="utf-8",
    )


def run_openai_tools(vault: Path, spec: dict[str, str], key: str, user: str) -> int:
    messages = [
        {"role": "system", "content": PROMPT.read_text(encoding="utf-8") if PROMPT.is_file() else ""},
        {"role": "user", "content": user},
    ]
    wrote = 0
    for _ in range(MAX_ROUNDS):
        data = _http_json(
            spec["url"],
            {
                "model": spec["model"],
                "messages": messages,
                "tools": TOOLS,
                "tool_choice": "auto",
            },
            openai_headers(key, spec["name"]),
        )
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        tool_calls = msg.get("tool_calls") or []
        content = msg.get("content") or ""
        if tool_calls:
            messages.append(msg)
            for call in tool_calls:
                fn = (call.get("function") or {})
                name = fn.get("name") or ""
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = tool_impl(vault, name, args if isinstance(args, dict) else {})
                if name == "write_file" and result == "wrote":
                    wrote += 1
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id") or name,
                        "content": result,
                    }
                )
            continue
        files = parse_files_payload(content)
        wrote += apply_files(vault, files)
        break
    return wrote


def run_single_shot(vault: Path, spec: dict[str, str], key: str, user: str) -> int:
    prompt_text = (PROMPT.read_text(encoding="utf-8") if PROMPT.is_file() else "") + "\n\n" + user
    prompt_text += (
        "\n\nWhen finished, output JSON only: "
        '{"files":[{"path":"05 时间日志/YYYY-MM/DD｜summary.md","content":"..."}]}'
    )
    if spec["style"] == "anthropic":
        data = _http_json(
            spec["url"],
            {
                "model": spec["model"],
                "max_tokens": 8192,
                "messages": [{"role": "user", "content": prompt_text}],
            },
            {
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        blocks = data.get("content") or []
        text = "".join(b.get("text") or "" for b in blocks if isinstance(b, dict))
    elif spec["style"] == "gemini":
        data = _http_json(
            spec["url"],
            {"contents": [{"parts": [{"text": prompt_text}]}]},
            {"Content-Type": "application/json", "x-goog-api-key": key},
        )
        cands = data.get("candidates") or []
        parts = (((cands[0] if cands else {}).get("content") or {}).get("parts") or [])
        text = "".join(p.get("text") or "" for p in parts if isinstance(p, dict))
    else:
        data = _http_json(
            spec["url"],
            {"model": spec["model"], "messages": [{"role": "user", "content": prompt_text}]},
            openai_headers(key, spec["name"]),
        )
        text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
    return apply_files(vault, parse_files_payload(text))


def apply_flagship_lock(spec: dict[str, str], key: str) -> dict[str, str]:
    if spec.get("locked") == "override":
        return spec
    ids = catalog_ids(spec, key)
    if ids:
        spec["model"] = lock_flagship(ids, spec.get("model") or "")
        spec["locked"] = "catalog"
    if spec.get("style") == "gemini":
        spec["url"] = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            + spec["model"]
            + ":generateContent"
        )
    return spec


def run(keys: dict[str, str], extra: dict[str, str] | None = None) -> int:
    vault = vault_root()
    extra = extra or {}
    spec = pick_chat(keys, extra)
    if spec is None:
        print("KRouter: no chat endpoint for the vault-page key.", file=sys.stderr)
        return 1
    secret = keys.get(spec["name"], "")
    spec = apply_flagship_lock(spec, secret)
    day = target_day()
    user = (
        f"Vault root: {vault}\n"
        f"Target day: {day.isoformat()} (yesterday unless TARGET_DATE is set).\n"
        f"Observed at: {datetime.now().isoformat(timespec='seconds')}\n"
        f"Locked model: {spec['model']}\n"
        f"Snapshot:\n{collect_snapshot(vault, day)}\n"
        "Use tools if available. Seal yesterday, distill, and when the five gates pass "
        "write provisional the same day. Do not write active. Do not edit the key page."
    )
    os.chdir(str(vault))
    try:
        if spec["style"] == "openai":
            try:
                wrote = run_openai_tools(vault, spec, secret, user)
            except SystemExit as exc:
                if "HTTP 4" in str(exc):
                    wrote = run_single_shot(vault, spec, secret, user)
                else:
                    raise
        else:
            wrote = run_single_shot(vault, spec, secret, user)
    except SystemExit:
        write_pending(vault, day, "chat API failed; left to-summarize.")
        raise
    if wrote == 0:
        write_pending(vault, day, "API writer produced no files; left to-summarize.")
        print("KRouter: API writer left a to-summarize note.", file=sys.stderr)
        return 0
    print(f"KRouter: API writer wrote {wrote} file(s) via {spec['name']}/{spec['model']}.")
    return 0
