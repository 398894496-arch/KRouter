#!/usr/bin/env python3
"""The Claude Desktop extension (`KRouter.mcpb`): one file the user double-clicks to install KRouter in Claude Desktop,
with no settings file to edit and no restart.

Claude Desktop keeps its settings in memory while it runs and writes the whole `claude_desktop_config.json` back when
it quits, so an `mcpServers` entry written while it is open is gone after the next restart. An extension is
installed by the app itself, so it does not have that problem.

    python3 scripts/build_mcpb.py [--out dist/KRouter.mcpb] [--vault FOLDER] [--python /path/to/python3]
    python3 scripts/build_mcpb.py --check KRouter.mcpb          # the structure checks, and a real MCP round trip

A bundle follows the MCPB manifest spec (https://github.com/modelcontextprotocol/mcpb, `manifest_version` 0.3): a zip
holding `manifest.json` and `server/` (the router's scripts and `krouter_desktop.py`, its entry point). The memory
folder is a `directory` setting the user can pick at install; `--vault` makes it the default (the installer passes
the folder it recorded), and left empty the server uses the folder the install recorded. `--python` names the
interpreter (the installer passes the one it found; Claude Desktop does not ship Python).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "extras/claude-desktop/manifest.json"
LAUNCHER = ROOT / "extras/claude-desktop/krouter_desktop.py"
SCRIPTS = ROOT / "skill/krouter/scripts"
REQUIRED = ("manifest_version", "name", "version", "description", "author", "server")
USER_TYPES = {"string", "number", "boolean", "directory", "file"}
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def version() -> str:
    return json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]


def manifest(vault: str = "", python: str = "") -> dict:
    m = json.loads(TEMPLATE.read_text(encoding="utf-8").replace("__VERSION__", version()))
    if vault:
        m["user_config"]["memory_folder"]["default"] = vault
    if python:
        m["server"]["mcp_config"]["command"] = python
        m["server"]["mcp_config"].pop("platform_overrides", None)  # 这台机器上找到的那个解释器，就只给这台机器用
    return m


def build(out: Path, vault: str = "", python: str = "") -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest(vault, python), ensure_ascii=False, indent=2) + "\n")
        for src in sorted(SCRIPTS.iterdir()):
            if src.is_file() and not src.name.endswith(".pyc") and src.name != ".DS_Store":
                info = zipfile.ZipInfo.from_file(src, f"server/{src.name}")
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, src.read_bytes())
        z.write(LAUNCHER, "server/krouter_desktop.py")
    os.replace(tmp, out)
    return out


def _rpc(proc: subprocess.Popen, msg: dict) -> dict | None:
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    if "id" not in msg:
        return None
    line = proc.stdout.readline()
    return json.loads(line) if line.strip() else None


def round_trip(server: Path, vault_arg: str, env: dict, declared: set[str] | None = None) -> list[str]:
    """Start the bundled server the way the manifest says and ask it something over stdio; problems found."""
    proc = subprocess.Popen([sys.executable, str(server), "--vault", vault_arg], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    problems = []
    try:
        init = _rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "mcpb-check", "version": "0"}}})
        if not init or "result" not in init:
            return [f"initialize failed: {init}"]
        _rpc(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = _rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) or {}
        names = {t["name"] for t in tools.get("result", {}).get("tools", [])}
        if not {"krouter_ask", "krouter_status"} <= names:
            problems.append(f"tools/list lacks krouter_ask / krouter_status: {sorted(names)}")
        if declared is not None and names - declared:  # 清单里列的工具要跟服务真给的对得上
            problems.append(f"the server offers tools the manifest does not list: {sorted(names - declared)}")
        ans = _rpc(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                          "params": {"name": "krouter_ask", "arguments": {"query": "home"}}}) or {}
        text = json.dumps(ans.get("result", {}), ensure_ascii=False)
        if "canonical" not in text and "source" not in text:
            problems.append(f"krouter_ask gave no receipt: {text[:300]}")
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
    return problems


def check(bundle: Path) -> list[str]:
    """Structure checks against the MCPB manifest spec, then the server started from the unpacked bundle."""
    problems: list[str] = []
    try:
        z = zipfile.ZipFile(bundle)
    except (OSError, zipfile.BadZipFile) as exc:
        return [f"not a zip: {exc}"]
    names = set(z.namelist())
    if "manifest.json" not in names:
        return ["no manifest.json at the root"]
    try:
        m = json.loads(z.read("manifest.json"))
    except ValueError as exc:
        return [f"manifest.json is not JSON: {exc}"]
    problems += [f"manifest lacks {k}" for k in REQUIRED if k not in m]
    if m.get("manifest_version") not in ("0.2", "0.3"):
        problems.append(f"manifest_version {m.get('manifest_version')!r} (expected 0.3)")
    if not SEMVER.match(str(m.get("version", ""))):
        problems.append(f"version {m.get('version')!r} is not semver")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", str(m.get("name", ""))):
        problems.append(f"name {m.get('name')!r} should be lowercase, digits and dashes")
    if not isinstance(m.get("author"), dict) or not m["author"].get("name"):
        problems.append("author.name missing")
    server = m.get("server") or {}
    entry = server.get("entry_point", "")
    if server.get("type") != "python":
        problems.append(f"server.type {server.get('type')!r} (this bundle is a python server)")
    if entry not in names:
        problems.append(f"entry_point {entry!r} is not in the bundle")
    cfg = server.get("mcp_config") or {}
    if not cfg.get("command") or not isinstance(cfg.get("args"), list):
        problems.append("mcp_config needs command and args")
    if f"${{__dirname}}/{entry}" not in cfg.get("args", []):
        problems.append("mcp_config.args does not start the entry_point through ${__dirname}")
    user = m.get("user_config") or {}
    for key, spec in user.items():
        if spec.get("type") not in USER_TYPES:
            problems.append(f"user_config.{key}.type {spec.get('type')!r}")
        if not spec.get("title") or not spec.get("description"):
            problems.append(f"user_config.{key} needs title and description")
    used = set(re.findall(r"\$\{user_config\.([A-Za-z0-9_]+)\}", json.dumps(cfg)))
    problems += [f"mcp_config uses ${{user_config.{k}}}, which user_config does not define" for k in sorted(used - set(user))]
    plats = set((m.get("compatibility") or {}).get("platforms") or [])
    if plats - {"darwin", "win32", "linux"}:
        problems.append(f"unknown platforms {sorted(plats)}")
    for n in sorted(x for x in names if x.endswith(".py")):
        try:
            compile(z.read(n), n, "exec")
        except SyntaxError as exc:
            problems.append(f"{n} does not compile: {exc}")
    for need in ("server/mcp_server.py", "server/route_knowledge.py", "server/zones.py", "server/zones_en.psv",
                 "server/associate.py", "server/experience.py", "server/corrections.py", "server/llm.py",
                 "server/skills.py"):
        if need not in names:
            problems.append(f"bundle lacks {need}")
    if problems:
        return problems
    # 真跑一遍：解开、按清单的方式启动、走一次 MCP 握手和查询（选了文件夹 / 没选、占位符没替换 两种）
    work = Path(tempfile.mkdtemp(prefix="krouter-mcpb-"))
    try:
        z.extractall(work / "ext")
        sys.path.insert(0, str(SCRIPTS))
        import zones

        vault = work / "vault"
        zones.lay_out(ROOT / "template", vault, alias_sample=SCRIPTS / "canonical_sources.psv")
        import skills  # 一份技能：krouter_skill 只在库里有技能时出现，这样它也要对得上清单

        sk = vault / zones.real(vault, skills.FOLDER)
        sk.mkdir(parents=True, exist_ok=True)
        (sk / "Skill - check the copy that is read.md").write_text(
            f"---\ntitle: \"Skill - check the copy that is read\"\ntype: {skills.TYPE}\nstatus: active\nskill_id: S01\n"
            "use_when: \"a change has no effect\"\ncards: C01\ndrafted: 2026-10-01\n---\n\n# Skill - check the copy that is read\n\n"
            "## Steps\n\n1. Find which copy is read.\n\n## Sources\n\n- the bundle check\n", encoding="utf-8")
        env = {**os.environ, "HOME": str(work), "XDG_CONFIG_HOME": str(work / "cfg"), "KROUTER_NO_QUERY_LOG": "1",
               "KROUTER_CACHE_DIR": str(work / "cache"), "KROUTER_STATE_DIR": str(work / "state"),
               "KROUTER_VAULT_FILE": str(work / "recorded")}
        for k in ("KROUTER_VAULT", "OBSIDIAN_VAULT"):
            env.pop(k, None)
        server_py = work / "ext" / entry
        problems += [f"with a folder picked: {p}" for p in round_trip(server_py, str(vault), env,
                                                                         {t.get("name") for t in m.get("tools") or []})]
        (work / "recorded").write_text(str(vault) + "\n", encoding="utf-8")
        problems += [f"with nothing picked: {p}" for p in round_trip(server_py, "${user_config.memory_folder}", env)]
        problems += [f"with an empty choice: {p}" for p in round_trip(server_py, "", env)]
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(ROOT / "dist-release/KRouter.mcpb"))
    ap.add_argument("--vault", default="", help="default memory folder shown at install (the installer's recorded one)")
    ap.add_argument("--python", default="", help="interpreter to start the server with (default: python3 / python)")
    ap.add_argument("--check", default="", metavar="BUNDLE", help="check an existing bundle instead of building one")
    args = ap.parse_args()
    if args.check:
        problems = check(Path(args.check))
        for p in problems:
            print(f"FAIL {p}")
        print("mcpb OK: " + args.check if not problems else f"mcpb: {len(problems)} problem(s)")
        return 1 if problems else 0
    out = build(Path(args.out).expanduser(), args.vault, args.python)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
