#!/usr/bin/env python3
"""One model channel for the nightly scripts and the daily writer: API key first, then a logged-in CLI.

This file owns the provider table, the flagship lock, and the list of CLI harnesses with their login
probes; `extras/host-daily-evolution/api_writer.py` and `resolve.py` import them from here, so the
nightly steps and the writer see the same providers and the same CLIs in the same order (PROTOCOL
rule 7). Keys come from the process environment, then `KROUTER_KEYS_ENV` (default
`~/.dsh-krouter-keys.env`), then the vault page `90 系统文件/自动化/自进化钥匙.md`. Values are never
printed and never put in a URL. The model is `KROUTER_LEARN_MODEL`, else `KROUTER_DISTILL_MODEL`, else
the provider's flagship from its live catalog, else the table's default. With no usable key, the first
logged-in CLI the writer would pick (grok, official Codex, claude, cursor-agent, opencode, kimi, pi,
vibe, antigravity; `KROUTER_WRITER` pins one). A host that sets `KROUTER_LEARN_CLI` (or passes
`--cli`) has picked a CLI on purpose; it goes first.

Only grok and claude are used without asking: KRouter keeps what they can read to the vault (a kernel sandbox, a
tool allow-list). Codex writes only the vault but can read the whole account, so it is used when the host names it
(`KROUTER_WRITER`, `KROUTER_LEARN_CLI`) or says `KROUTER_ALLOW_CODEX=1`; otherwise it shows as `codex:reads-account`.
The others run with no confinement KRouter can set, so a logged-in one is skipped unless the host opts in with
`KROUTER_ALLOW_UNCONFINED=1` (environment or keys file); it then shows as `<kind>:unconfined`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

KEY_LINE = re.compile(r"^(?:export\s+)?([A-Z][A-Z0-9_]+)=(.*)$")
PLACEHOLDERS = ("YOUR_", "CHANGE_ME", "REPLACE", "TODO", "sk-your", "PASTE_")
TIMEOUT = 900
GEMINI = "https://generativelanguage.googleapis.com/v1beta/models"

# (env name, chat url, flagship default, style). Order is the order both lanes try keys in.
CHAT_SPECS: list[tuple[str, str, str, str]] = [
    ("DEEPSEEK_API_KEY", "https://api.deepseek.com/chat/completions", "deepseek-reasoner", "openai"),
    ("OPENAI_API_KEY", "https://api.openai.com/v1/chat/completions", "gpt-4.1", "openai"),
    ("ANTHROPIC_API_KEY", "https://api.anthropic.com/v1/messages", "claude-opus-5-5", "anthropic"),
    ("XAI_API_KEY", "https://api.x.ai/v1/chat/completions", "grok-4", "openai"),
    ("GROQ_API_KEY", "https://api.groq.com/openai/v1/chat/completions", "openai/gpt-oss-120b", "openai"),
    ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions", "anthropic/claude-sonnet-4", "openai"),
    ("MOONSHOT_API_KEY", "https://api.moonshot.ai/v1/chat/completions", "kimi-k2-0711-preview", "openai"),
    ("KIMI_API_KEY", "https://api.moonshot.ai/v1/chat/completions", "kimi-k2-0711-preview", "openai"),
    ("DASHSCOPE_API_KEY", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions", "qwen-max", "openai"),
    ("ZHIPUAI_API_KEY", "https://open.bigmodel.cn/api/paas/v4/chat/completions", "glm-4-plus", "openai"),
    ("GLM_API_KEY", "https://open.bigmodel.cn/api/paas/v4/chat/completions", "glm-4-plus", "openai"),
    ("SILICONFLOW_API_KEY", "https://api.siliconflow.cn/v1/chat/completions", "deepseek-ai/DeepSeek-R1", "openai"),
    ("TOGETHER_API_KEY", "https://api.together.xyz/v1/chat/completions", "deepseek-ai/DeepSeek-R1", "openai"),
    ("FIREWORKS_API_KEY", "https://api.fireworks.ai/inference/v1/chat/completions", "accounts/fireworks/models/deepseek-r1", "openai"),
    ("MISTRAL_API_KEY", "https://api.mistral.ai/v1/chat/completions", "mistral-large-latest", "openai"),
    ("CEREBRAS_API_KEY", "https://api.cerebras.ai/v1/chat/completions", "gpt-oss-120b", "openai"),
    ("NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1/chat/completions", "deepseek-ai/deepseek-r1", "openai"),
    ("PERPLEXITY_API_KEY", "https://api.perplexity.ai/chat/completions", "sonar-pro", "openai"),
    ("GEMINI_API_KEY", f"{GEMINI}/gemini-2.5-pro:generateContent", "gemini-2.5-pro", "gemini"),
    ("GOOGLE_API_KEY", f"{GEMINI}/gemini-2.5-pro:generateContent", "gemini-2.5-pro", "gemini"),
    ("GOOGLE_GENERATIVE_AI_API_KEY", f"{GEMINI}/gemini-2.5-pro:generateContent", "gemini-2.5-pro", "gemini"),
]

# First needle that matches scores the id; newer generations sit above older ones.
FLAGSHIP_NEEDLES = (
    ("opus-5", 102),
    ("opus-4", 100),
    ("claude-opus", 98),
    ("grok-4.6", 96),
    ("grok-4", 92),
    ("gpt-5", 90),
    ("o3", 86),
    ("deepseek-reasoner", 85),
    ("deepseek-r1", 84),
    ("claude-sonnet-4", 82),
    ("gpt-4.1", 80),
    ("gemini-2.5-pro", 78),
    ("qwen-max", 76),
    ("kimi-k2", 74),
    ("glm-4.5", 72),
    ("glm-4-plus", 70),
    ("mistral-large", 68),
    ("deepseek-chat", 60),
    ("sonar-pro", 58),
)
FLAGSHIP_PENALTY = ("mini", "nano", "haiku", "lite", "small", "instant", "flash-lite", "tiny")


# ---- CLI harnesses (no key). The writer's detection, shared. -------------------------------------

CLI_KIND_RE = re.compile(r"^[a-z][a-z0-9_-]{0,40}$")
GENERIC_PROBE_TAILS = (("auth", "status"), ("auth", "list"), ("login", "status"), ("models",), ("status",))
CLI_FLAGSHIP = {"grok": "grok-4.6", "claude": "opus"}
PATH_NAMES = ("grok", "codex", "claude", "cursor-agent", "opencode", "kimi", "pi", "vibe", "antigravity")


def detect_candidates() -> list[Path]:
    """Known install paths first, then the same names on PATH (never a PATH-level `agent`)."""
    home = Path.home()
    fixed = [
        home / ".grok/bin/grok",
        home / ".local/bin/grok",
        Path("/Applications/ChatGPT.app/Contents/Resources/codex"),
        Path("/Applications/Codex.app/Contents/Resources/codex"),
        Path("/opt/homebrew/bin/claude"),
        home / ".local/bin/claude",
        Path("/usr/local/bin/claude"),
        home / ".cursor/bin/cursor-agent",
        home / ".cursor/bin/agent",
        Path("/opt/homebrew/bin/opencode"),
        home / ".opencode/bin/opencode",
        Path("/opt/homebrew/bin/kimi"),
        home / ".local/bin/kimi",
        Path("/opt/homebrew/bin/pi"),
        Path("/opt/homebrew/bin/vibe"),
        Path("/opt/homebrew/bin/antigravity"),
    ]
    seen = {str(p) for p in fixed}
    for name in PATH_NAMES:
        found = shutil.which(name)
        if found and found not in seen:
            fixed.append(Path(found))
            seen.add(found)
    return fixed


def writer_probe_argv(writer: str) -> tuple[str, list[str] | None]:
    name = os.path.basename(writer).lower().replace(".exe", "")
    posix = writer.replace("\\", "/")
    if name == "grok":
        return "grok", [writer, "models"]
    if name == "agent":
        if "/.grok/" in posix:
            return "grok", [writer, "models"]
        if "/.cursor/" in posix:
            return "cursor", [writer, "status"]
        return "path-agent", None
    if name == "cursor-agent":
        return "cursor", [writer, "status"]
    if name == "codex":
        return "codex", [writer, "login", "status"]
    if name in {"claude", "claude-max"}:
        return "claude", [writer, "auth", "status"]
    if name == "opencode":
        return "opencode", [writer, "auth", "list"]
    if name == "kimi":
        return "kimi", [writer, "auth", "status"]
    if name == "pi":
        return "pi", [writer, "login", "status"]
    if name == "vibe":
        return "vibe", [writer, "auth", "status"]
    if name == "antigravity":
        return "antigravity", [writer, "auth", "status"]
    if CLI_KIND_RE.match(name):
        return name, None
    return "other", None


def _run_cmd(argv: list[str]) -> tuple[int, str]:
    env = os.environ.copy()
    env.setdefault("HOME", str(Path.home()))
    env.update({k: v for k, v in cli_env().items() if k in CLI_TOKEN_NAMES})
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=25, env=env, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return -1, "network"
    return proc.returncode, f"{proc.stdout}\n{proc.stderr}".lower()


def probe_writer(writer: str) -> str:
    writer = (writer or "").strip()
    if not writer:
        return "unset"
    if not os.path.isabs(writer):
        return "relative"
    if not os.path.isfile(writer) or not os.access(writer, os.X_OK):
        return "not-exec"
    kind, argv = writer_probe_argv(writer)
    if kind == "path-agent":
        return kind
    tails = [tuple(argv[1:])] if argv is not None else list(GENERIC_PROBE_TAILS)
    last = f"{kind}:exit1"
    for tail in tails:
        code, text = _run_cmd([writer, *tail])
        if text == "network" and code == -1:
            return "network"
        if (
            "not authenticated" in text
            or "authentication required" in text
            or "not logged in" in text
            or "loggedin false" in text
            or '"loggedin": false' in text
            or "logged_in: false" in text
        ):
            return f"{kind}:unauth"
        if code == 0:
            return f"{kind}:ok"
        last = f"{kind}:exit{code}"
    return last


def writer_ok(result: str) -> bool:
    return result.endswith(":ok")


def writer_kind(result: str) -> str:
    return result.split(":", 1)[0] if ":" in result else result


CONFINED_KINDS = frozenset({"grok", "codex", "claude"})  # KRouter 能给这三家加约束：沙箱、只写库、工具白名单
UNCONFINED_FLAG = "KROUTER_ALLOW_UNCONFINED"


ACCOUNT_READ_KINDS = frozenset({"codex"})  # 只写库，但读得到整个账号（含 key 文件）：宿主点名才用
CODEX_FLAG = "KROUTER_ALLOW_CODEX"


def _flag(name: str) -> bool:
    if os.environ.get(name, "").strip() == "1":
        return True
    path = keys_file()
    if path.is_file():
        return _parse(path.read_text(encoding="utf-8", errors="replace")).get(name, "").strip() == "1"
    return False


def allow_unconfined() -> bool:
    """The host's explicit yes to a CLI KRouter cannot confine: `KROUTER_ALLOW_UNCONFINED=1`, env or keys file."""
    return _flag(UNCONFINED_FLAG)


def allow_codex() -> bool:
    """The host's explicit yes to Codex, which can read the whole account: `KROUTER_ALLOW_CODEX=1`, env or keys file."""
    return _flag(CODEX_FLAG)


def gate(result: str, named: bool = False) -> str:
    """A logged-in CLI outside CONFINED_KINDS counts only with the opt-in (`<kind>:unconfined`); Codex only when the
    host named it or opted in (`codex:reads-account`)."""
    if writer_ok(result) and writer_kind(result) not in CONFINED_KINDS and not allow_unconfined():
        return f"{writer_kind(result)}:unconfined"
    if writer_ok(result) and writer_kind(result) in ACCOUNT_READ_KINDS and not (named or allow_codex()):
        return f"{writer_kind(result)}:reads-account"
    return result


def detect_writer(pinned: str = "") -> tuple[str, str]:
    """Return (path, probe_result). Prefer a pinned absolute binary, else first logged-in CLI KRouter may use."""
    if pinned.strip():
        return pinned.strip(), gate(probe_writer(pinned.strip()), named=True)
    first_existing = ""
    first_existing_result = "unset"
    for path in detect_candidates():
        result = probe_writer(str(path))
        if result == "path-agent":
            continue
        result = gate(result)
        if writer_ok(result):
            return str(path), result
        if result.endswith((":unconfined", ":reads-account")) and not first_existing_result.endswith(
                (":unconfined", ":reads-account")):
            first_existing, first_existing_result = str(path), result  # 记下来，好告诉宿主为什么没用它
            continue
        if path.is_file() and os.access(path, os.X_OK) and not first_existing:
            first_existing = str(path)
            first_existing_result = result
    if first_existing:
        return first_existing, first_existing_result
    return "", "unset"


_CLI: list[str] = []  # the logged-in CLI, detected once per process


def logged_in_cli() -> str:
    """The CLI the writer would pick with no key: `KROUTER_WRITER` if set, else the first logged-in one."""
    if not _CLI:
        path, result = detect_writer(os.environ.get("KROUTER_WRITER", ""))
        _CLI.append(path if writer_ok(result) else "")
    return _CLI[0]


CLI_TOKEN_NAMES = ("CLAUDE_CODE_OAUTH_TOKEN",)  # `claude setup-token`: a year-long token that never needs a refresh


def cli_env() -> dict[str, str]:
    """Environment for a CLI writer: the process environment plus a long-lived CLI token from the keys file.

    A logged-in `claude` keeps a short-lived OAuth token plus a single-use refresh token in the keychain. When
    another program holds the same login (a proxy such as CLIProxyAPI / EasyCLI, a second machine) and refreshes
    first, the CLI's refresh token is spent and the CLI is logged out. `claude setup-token` issues a token that
    needs no refresh; put it in `~/.dsh-krouter-keys.env` as `CLAUDE_CODE_OAUTH_TOKEN=…` and every KRouter call
    uses it instead of the keychain."""
    env = dict(os.environ)
    path = keys_file()
    if path.is_file():
        for name, val in _parse(path.read_text(encoding="utf-8", errors="replace")).items():
            if name in CLI_TOKEN_NAMES and not env.get(name):
                env[name] = val
    return env


class _CliLock:
    """One `claude` at a time across KRouter processes: concurrent CLIs refreshing the same keychain login race,
    and the loser's refresh token is spent (it logs the CLI out). A file lock, released on exit or crash."""

    def __init__(self) -> None:
        self.fh = None

    def __enter__(self):
        try:
            import fcntl
        except ImportError:  # Windows: no flock; the long-lived token is the fix there
            return self
        path = Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local/state/krouter") / "cli.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(path, "w")
        fcntl.flock(self.fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc) -> None:
        if self.fh is not None:
            self.fh.close()


def text_argv(cli: str, prompt_file: str) -> tuple[list[str], bool]:
    """(argv, prompt on stdin) for a plain text completion: no tools, no file writes."""
    kind, _ = writer_probe_argv(cli)
    model = os.environ.get("KROUTER_LEARN_MODEL", "") or os.environ.get("KROUTER_DISTILL_MODEL", "") \
        or CLI_FLAGSHIP.get(kind, "")
    prompt = Path(prompt_file).read_text(encoding="utf-8")
    if kind == "codex":
        return [cli, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "-"], True
    if kind == "claude":
        argv = [cli, "--print", "--tools", "", "--output-format", "text", "--no-session-persistence"]
        return argv + (["--model", model] if model else []) + [prompt], False
    if kind == "grok":
        argv = [cli] + (["--model", model] if model else [])
        return argv + ["--prompt-file", prompt_file, "--max-turns", "1", "--cwd", str(Path(prompt_file).parent)], False
    if kind == "opencode":
        return [cli, "run", prompt], False
    return [cli, "--print", prompt], False


class NoModel(RuntimeError):
    """No key and no logged-in CLI: the caller skips its step."""


def _usable(val: str) -> bool:
    val = (val or "").strip().strip('"').strip("'")
    return bool(val) and not any(val.upper().startswith(p.upper()) for p in PLACEHOLDERS)


def _parse(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        m = KEY_LINE.match(raw.strip())
        if m and _usable(m.group(2)):
            out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out


def keys_file() -> Path:
    return Path(os.environ.get("KROUTER_KEYS_ENV") or Path.home() / ".dsh-krouter-keys.env")


PROVIDER_WORDS = (  # 标签里的厂商名 → 变量名（先长后短，`openrouter` 在 `openai` 前）
    ("openrouter", "OPENROUTER_API_KEY"), ("deepseek", "DEEPSEEK_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY"),
    ("claude", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY"), ("chatgpt", "OPENAI_API_KEY"), ("gpt", "OPENAI_API_KEY"),
    ("gemini", "GEMINI_API_KEY"), ("google", "GEMINI_API_KEY"), ("grok", "XAI_API_KEY"), ("xai", "XAI_API_KEY"),
    ("groq", "GROQ_API_KEY"), ("moonshot", "MOONSHOT_API_KEY"), ("kimi", "MOONSHOT_API_KEY"), ("月之暗面", "MOONSHOT_API_KEY"),
    ("dashscope", "DASHSCOPE_API_KEY"), ("qwen", "DASHSCOPE_API_KEY"), ("通义", "DASHSCOPE_API_KEY"), ("百炼", "DASHSCOPE_API_KEY"),
    ("zhipu", "ZHIPUAI_API_KEY"), ("glm", "ZHIPUAI_API_KEY"), ("智谱", "ZHIPUAI_API_KEY"), ("siliconflow", "SILICONFLOW_API_KEY"),
    ("硅基", "SILICONFLOW_API_KEY"), ("together", "TOGETHER_API_KEY"), ("fireworks", "FIREWORKS_API_KEY"),
    ("mistral", "MISTRAL_API_KEY"), ("cerebras", "CEREBRAS_API_KEY"), ("nvidia", "NVIDIA_API_KEY"), ("perplexity", "PERPLEXITY_API_KEY"),
)
KEY_PREFIXES = (("sk-ant-", "ANTHROPIC_API_KEY"), ("sk-or-", "OPENROUTER_API_KEY"), ("AIza", "GEMINI_API_KEY"),
                ("xai-", "XAI_API_KEY"), ("gsk_", "GROQ_API_KEY"), ("pplx-", "PERPLEXITY_API_KEY"),
                ("nvapi-", "NVIDIA_API_KEY"), ("csk-", "CEREBRAS_API_KEY"), ("fw_", "FIREWORKS_API_KEY"))
NAMED_LINE = re.compile(r"^(?:export\s+)?([A-Z][A-Z0-9_]+)\s*[=:：]\s*[\"'`]?([^\s\"'`]+)[\"'`]?\s*$")
PENDING = "KROUTER_PENDING_KEY_"


def _name_for(value: str, before: str) -> str:
    """The provider of a pasted key: its prefix, else the nearest provider word written before it."""
    name = next((n for p, n in KEY_PREFIXES if value.startswith(p)), "")
    if name:
        return name
    low = before.lower()
    best, at = "", -1
    for word, n in PROVIDER_WORDS:
        i = low.rfind(word)
        if i > at:
            best, at = n, i
    return best


def _keys_in_line(line: str) -> tuple[list[tuple[str, str]], bool]:
    """([(name or "", value), …] for every key pasted on this line, leftover). `leftover` is True when the line
    still holds something key-shaped that could not be taken out — then the whole line is kept, not dropped."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import krouter_redact as kr

    body = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line.strip())  # 列表项
    if not body or body.startswith(("#", "```", ">")):
        return [], False
    m = NAMED_LINE.match(body)
    if m and _usable(m.group(2)) and not kr.PLACEHOLDER.match(m.group(2)):
        return [(m.group(1), m.group(2))], False
    found: list[tuple[int, int, str]] = []
    for hit in kr.KNOWN.finditer(body):
        found.append((hit.start(), hit.end(), hit.group(0)))
    for hit in kr.RUN.finditer(body):
        v = hit.group(0)
        if kr._high_entropy(v) and not any(a <= hit.start() < b for a, b, _ in found):
            found.append((hit.start(), hit.end(), v))
    for hit in kr.ASSIGN.finditer(body):
        v = hit.group("v")
        if kr._value_is_secret(v) and not any(a <= hit.start("v") < b for a, b, _ in found):
            found.append((hit.start("v"), hit.end("v"), v))
    found.sort()
    keys = []
    rest = body
    for i, (a, b, v) in enumerate(found):
        prev_end = found[i - 1][1] if i else 0
        keys.append((_name_for(v, body[prev_end:a]), v))  # 同一行的多把 key：各自看前面紧挨着的那段文字
        rest = rest.replace(v, " ")
    leftover = bool(keys) and kr.redact(rest) != rest
    return keys, leftover


def _write_private(path: Path, text: str) -> None:
    """Write `text` to `path` atomically, readable only by the user (tmp file in the same dir, then rename)."""
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def move_page_keys(vault: Path | None) -> list[str]:
    """Keys pasted on the vault's key page move to the keys file (chmod 600) and leave the vault.

    The page is the easiest place for anyone to paste a key, but anything in the vault is readable by the CLI
    writer, synced by Obsidian Sync / iCloud / git, and one mistake away from a model. So KRouter never reads
    keys from the vault: on every run, a key pasted on the key page in any common shape — `NAME=value`,
    `export NAME="…"`, `NAME: value`, a list item, `DeepSeek 密钥：sk-…`, a bare key — is written to the keys
    file and the page line becomes a note saying where it went. The provider comes from `NAME`, the key's
    prefix, or a provider word on the line; when none tells, the key is kept as `KROUTER_PENDING_KEY_n` and the
    note says how to name it. Returns the names moved; values are never printed.
    """
    if vault is None:
        return []
    import sys
    from datetime import date

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import zones

    page = zones.path(vault, "90 系统文件/自动化/自进化钥匙.md")
    if not page.is_file():
        return []
    target = keys_file()
    existing = target.read_text(encoding="utf-8", errors="replace").splitlines() if target.is_file() else []
    pending_n = 1 + sum(1 for ln in existing if ln.startswith(PENDING))
    lines = page.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    moved: dict[str, str] = {}
    today = date.today().isoformat()
    for i, raw in enumerate(lines):
        keys, leftover = _keys_in_line(raw)
        if not keys:
            continue
        notes = []
        for name, value in keys:
            if not name or leftover:
                name = f"{PENDING}{pending_n}"
                pending_n += 1
            moved[name] = value.strip().strip('"').strip("'")
            notes.append(name)
        if leftover:  # 这一行还有认不全的东西：整行原样存进钥匙文件，页面上不留，也不丢
            moved[f"{PENDING}{pending_n}_LINE"] = raw.strip().replace("\n", " ")
            pending_n += 1
        pending = [n for n in notes if n.startswith(PENDING)]
        lines[i] = (f"# 已移到 {target}（{today}）：{'、'.join(notes)}"
                    + (f"。其中 {'、'.join(pending)} 认不出是哪家服务：请在那个文件里改成对应的名字，如 DEEPSEEK_API_KEY，"
                       f"或者在这里按 `DEEPSEEK_API_KEY=…` 的格式一行一个重贴" if pending else "") + "\n")
    if not moved:
        return []
    kept = [ln for ln in existing if not ((m := KEY_LINE.match(ln.strip())) and m.group(1) in moved)]
    _write_private(target, "\n".join(kept + [f"{k}={v}" for k, v in moved.items()]) + "\n")
    page.write_text("".join(lines), encoding="utf-8")  # 先写好钥匙文件，再从页面上抹掉
    return sorted(moved)


def pending_keys() -> list[str]:
    """Names of keys the host pasted whose provider could not be told (they are not used until renamed)."""
    path = keys_file()
    if not path.is_file():
        return []
    return [ln.split("=", 1)[0] for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if ln.startswith(PENDING) and "=" in ln]


def collect_keys(vault: Path | None) -> dict[str, str]:
    """Process environment, then the keys file. Never the vault (keys pasted there are moved out first)."""
    move_page_keys(vault)
    keys = {k: v for k, v in os.environ.items() if k.endswith(("_API_KEY", "_BASE_URL", "_MODEL")) and _usable(v)}
    env_file = keys_file()
    if env_file.is_file():
        keys.update(_parse(env_file.read_text(encoding="utf-8", errors="replace")))
    return keys


def lock_flagship(model_ids: list[str], fallback: str = "") -> str:
    """Pick the flagship id from a provider catalog. Never prefers mini/haiku/flash-lite."""
    best_id = fallback
    best_score = -10_000
    for raw in model_ids:
        mid = (raw or "").strip()
        if not mid:
            continue
        lower = mid.lower()
        score = 1
        for needle, pts in FLAGSHIP_NEEDLES:
            if needle in lower:
                score = max(score, pts)
                break
        if any(p in lower for p in FLAGSHIP_PENALTY):
            score -= 40
        if "flash" in lower and "pro" not in lower:
            score -= 20
        if score > best_score:
            best_score = score
            best_id = mid
    return best_id or fallback


def openai_headers(key: str, name: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}
    if name == "OPENROUTER_API_KEY":
        headers["HTTP-Referer"] = "https://github.com/398894496-arch/KRouter"
        headers["X-Title"] = "KRouter"
    return headers


def _opener(url: str):
    return urllib.request.build_opener(urllib.request.ProxyHandler({})) if "127.0.0.1" in url else urllib.request.build_opener()


def _get_json(url: str, headers: dict[str, str]) -> dict:
    try:
        with _opener(url).open(urllib.request.Request(url, headers=headers, method="GET"), timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return {}


def catalog_ids(spec: dict[str, str], key: str) -> list[str]:
    """Model ids the provider lists for this key; [] when the catalog is unreachable."""
    style = spec.get("style")
    if style == "anthropic":
        data = _get_json("https://api.anthropic.com/v1/models",
                         {"x-api-key": key, "anthropic-version": "2023-06-01", "Accept": "application/json"})
        return [str(r.get("id") or "") for r in data.get("data") or [] if isinstance(r, dict)]
    if style == "gemini":
        data = _get_json(GEMINI, {"x-goog-api-key": key, "Accept": "application/json"})
        return [str(r.get("name") or "").split("/")[-1] for r in data.get("models") or [] if isinstance(r, dict)]
    data = _get_json(spec["url"].replace("/chat/completions", "/models"), openai_headers(key, spec["name"]))
    return [str(r.get("id") or "") for r in data.get("data") or [] if isinstance(r, dict)]


def _override(keys: dict[str, str]) -> str:
    return keys.get("KROUTER_LEARN_MODEL") or os.environ.get("KROUTER_LEARN_MODEL") \
        or keys.get("KROUTER_DISTILL_MODEL") or os.environ.get("KROUTER_DISTILL_MODEL") or ""


def _post(url: str, headers: dict[str, str], body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={**headers, "Content-Type": "application/json"}, method="POST")
    with _opener(url).open(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_specs(keys: dict[str, str]) -> list[dict[str, str]]:
    """The providers this key set can reach, in table order. Metadata only — never the secret."""
    out = []
    for name, url, default, style in CHAT_SPECS:
        if name not in keys:
            continue
        base = keys.get(name.replace("_API_KEY", "_BASE_URL"), "").rstrip("/")
        if name == "OPENAI_API_KEY":
            base = base or keys.get("OPENAI_API_BASE", "").rstrip("/")
        out.append({"name": name, "url": base + "/chat/completions" if base and style == "openai" else url,
                    "model": default, "style": style})
    return out


def plan(vault: Path | None = None) -> list[tuple[str, str]]:
    """Ordered (kind, detail) the channel would try. No secrets in the output."""
    keys = collect_keys(vault)
    steps: list[tuple[str, str]] = []
    explicit = os.environ.get("KROUTER_LEARN_CLI", "")
    if explicit and writer_probe_argv(explicit)[0] not in CONFINED_KINDS and not allow_unconfined():
        explicit = ""  # 点名的 CLI 也一样：KRouter 管不住的，没有宿主的明确同意就不用
    if explicit and Path(explicit).is_file() and os.access(explicit, os.X_OK):
        # the host named a CLI on purpose (e.g. a subscription model): honor it before any key
        steps.append(("cli", explicit))
    override = _override(keys)
    for spec in api_specs(keys):
        # without an override the model is the catalog's flagship, decided at call time
        steps.append((f"api:{spec['name']}", override or f"flagship (default {spec['model']})"))
    if not explicit:
        cli = logged_in_cli()
        if cli:
            steps.append(("cli", cli))
    return steps


def _call_api(spec: dict[str, str], key: str, model: str, prompt: str) -> str:
    if spec["style"] == "anthropic":
        data = _post(spec["url"], {"x-api-key": key, "anthropic-version": "2023-06-01"},
                     {"model": model, "max_tokens": 8000, "messages": [{"role": "user", "content": prompt}]})
        u = data.get("usage") or {}
        return ("".join(b.get("text", "") for b in data.get("content", []) if isinstance(b, dict)),
                {"tokens_in": u.get("input_tokens"), "tokens_out": u.get("output_tokens")})
    if spec["style"] == "gemini":
        data = _post(f"{GEMINI}/{model}:generateContent", {"x-goog-api-key": key},
                     {"contents": [{"parts": [{"text": prompt}]}]})
        cands = data.get("candidates") or []
        parts = ((cands[0] if cands else {}).get("content") or {}).get("parts") or []
        u = data.get("usageMetadata") or {}
        return ("".join(p.get("text", "") for p in parts if isinstance(p, dict)),
                {"tokens_in": u.get("promptTokenCount"), "tokens_out": u.get("candidatesTokenCount")})
    data = _post(spec["url"], openai_headers(key, spec["name"]),
                 {"model": model, "messages": [{"role": "user", "content": prompt}]})
    u = data.get("usage") or {}
    return data["choices"][0]["message"]["content"], {"tokens_in": u.get("prompt_tokens"), "tokens_out": u.get("completion_tokens")}


def _record(kind: str, model: str, prompt: str, text: str, usage: dict | None = None) -> None:
    """Append one call's metadata (never its content) to `KROUTER_USAGE_LOG` when the host asks for it."""
    log = os.environ.get("KROUTER_USAGE_LOG", "")
    if not log:
        return
    row = {"kind": kind.split(":", 1)[0], "provider": kind.split(":", 1)[-1] if kind.startswith("api:") else Path(model).name,
           "model": model if kind.startswith("api:") else os.environ.get("KROUTER_LEARN_MODEL", ""),
           "chars_in": len(prompt), "chars_out": len(text or "")}
    row.update({k: v for k, v in (usage or {}).items() if v is not None})
    try:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


_LOCKED: dict[str, str] = {}  # provider → flagship id, once per process


def complete(prompt: str, vault: Path | None = None) -> str:
    """Return the model's text, trying each available channel once in order."""
    keys = collect_keys(vault)
    specs = {f"api:{s['name']}": s for s in api_specs(keys)}
    override = _override(keys)
    errors: list[str] = []
    for kind, detail in plan(vault):
        try:
            if kind in specs:
                spec = specs[kind]
                key = keys[spec["name"]]
                model = override
                if not model:
                    if spec["name"] not in _LOCKED:
                        _LOCKED[spec["name"]] = lock_flagship(catalog_ids(spec, key), spec["model"])
                    model = _LOCKED[spec["name"]]
                text, usage = _call_api(spec, key, model, prompt)
                _record(kind, model, prompt, text, usage)
                return text
            if kind == "cli":
                with tempfile.TemporaryDirectory(prefix="krouter-llm-") as tmp:
                    prompt_file = str(Path(tmp) / "prompt.md")
                    Path(prompt_file).write_text(prompt, encoding="utf-8")
                    argv, on_stdin = text_argv(detail, prompt_file)
                    with _CliLock():
                        proc = subprocess.run(argv, input=prompt if on_stdin else None, capture_output=True, text=True,
                                              timeout=TIMEOUT, cwd=tmp, stdin=None if on_stdin else subprocess.DEVNULL,
                                              env=cli_env())
                if proc.returncode != 0:
                    raise RuntimeError((proc.stderr or proc.stdout)[-200:])
                _record("cli", detail, prompt, proc.stdout)
                return proc.stdout
        except (urllib.error.URLError, OSError, KeyError, IndexError, ValueError, RuntimeError,
                subprocess.TimeoutExpired) as exc:
            errors.append(f"{kind}: {str(exc)[:160]}")
    if errors:
        raise RuntimeError("all model channels failed: " + " | ".join(errors))
    raise NoModel("no API key and no logged-in CLI; set a *_API_KEY or log in one of: " + ", ".join(PATH_NAMES))
