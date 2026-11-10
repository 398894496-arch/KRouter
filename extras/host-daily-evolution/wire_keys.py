#!/usr/bin/env python3
"""Install-time graft for the self-evolution writer.

One probe engine lives in resolve.py; this is the installer front end.

API lane: any mainstream *_API_KEY (named /models, or OPENAI_BASE_URL for the rest).
Subscription lane: any Claudian-class local CLI already logged in.
Never writes the Obsidian vault. Never copies auth.json. Never prints a secret.

  python3 wire_keys.py           # install: detect CLI, probe keys, keep the live ones
  python3 wire_keys.py --check   # probe only, do not rewrite the keys file
  python3 wire_keys.py --detect  # print the first logged-in CLI path
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from resolve import (  # noqa: E402
    CONFIG_NAMES,
    detect_writer,
    extra_urls,
    is_config_name,
    is_key_name,
    keys_env_path,
    models_url,
    parse_vault_page,
    probe_key,
    usable,
    writer_kind,
    writer_ok,
    writer_probe_argv,
)

__all__ = [
    "CONFIG_NAMES",
    "is_config_name",
    "is_key_name",
    "models_url",
    "writer_kind",
    "writer_ok",
    "writer_probe_argv",
]

HEADER = (
    "# KRouter self-evolution keys. chmod 600. Never commit. Never in the vault.\n"
    "# Written by scripts/install.sh. KROUTER_CLI_LOGIN marks a logged-in CLI, not a secret.\n"
)


def candidate_keys() -> dict[str, str]:
    """Process env plus the keys file (a key pasted on the vault page is moved there first)."""
    found: dict[str, str] = {}
    for name, val in os.environ.items():
        if (is_key_name(name) or is_config_name(name)) and usable(val):
            found[name] = val.strip().strip('"').strip("'")
    vault = (os.environ.get("KROUTER_VAULT") or os.environ.get("OBSIDIAN_VAULT", "")).strip()
    if vault:
        from resolve import _lane

        _lane.move_page_keys(Path(vault))  # 钥匙页上的 key 挪进钥匙文件，库里不留
    path = keys_env_path()
    if path.is_file():
        found.update(parse_vault_page(path.read_text(encoding="utf-8", errors="replace")))
    return found


def write_keys(path: Path, live: dict[str, str], cli: str) -> None:
    """Update the names this probe manages and keep every other line as it was: the long-lived
    `CLAUDE_CODE_OAUTH_TOKEN`, `KROUTER_PENDING_KEY_n`, a key that failed today's probe, the host's comments.
    Rewriting the file from the probe alone deleted those (a re-install wiped the claude token)."""
    managed = dict(live)
    if cli:
        managed["KROUTER_CLI_LOGIN"] = cli
    old = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.is_file() else []
    out: list[str] = [] if old else HEADER.splitlines()
    done: set[str] = set()
    for line in old:
        name = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if name == "KROUTER_CLI_LOGIN" and not cli:
            continue  # 这次没探到登录的 CLI：标记作废
        if name in managed:
            if name not in done:
                out.append(f"{name}={managed[name]}")
                done.add(name)
            continue
        out.append(line)
    out += [f"{n}={managed[n]}" for n in sorted(managed) if n not in done]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    os.replace(tmp, path)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def main() -> int:
    parser = argparse.ArgumentParser(description="Graft the KRouter self-evolution key")
    parser.add_argument("--check", action="store_true", help="probe only, never rewrite")
    parser.add_argument("--detect", action="store_true", help="print the first logged-in CLI")
    args = parser.parse_args()

    if args.detect:
        path, result = detect_writer()
        print(path if writer_ok(result) else "")
        return 0

    dest = keys_env_path()
    keys = candidate_keys()
    extra = extra_urls(keys)
    secrets = {n: v for n, v in keys.items() if not is_config_name(n)}

    cli_path, cli_result = detect_writer()
    cli = cli_path if writer_ok(cli_result) else ""

    live: dict[str, str] = {}
    rejected: list[str] = []
    network = False
    for name, val in secrets.items():
        result = probe_key(name, val, extra)
        if result in {"200", "204", "429", "unprobed"}:
            live[name] = val
        elif result == "network":
            network = True
        else:
            rejected.append(f"{name}:{result}")

    keep = dict(live)
    for name in CONFIG_NAMES:
        if name in keys:
            keep[name] = keys[name]

    if live or cli:
        if not args.check:
            write_keys(dest, keep, cli)
        names = ",".join(sorted(live)) or "none"
        print(
            f"present path={dest} cli={writer_kind(cli_result) if cli else 'none'} "
            f"names={names} dropped={','.join(rejected) or 'none'}"
        )
        return 0
    if rejected:
        print(f"dead path={dest} rejected={','.join(rejected)}")
        return 0
    if network:
        print(f"unknown path={dest} (probe network failed; file left unchanged)")
        return 0
    print(f"missing path={dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
