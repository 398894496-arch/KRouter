#!/usr/bin/env python3
"""Run one behaviour set on the Codex CLI: every scenario once, in its own throwaway project, memory folder and Codex
home, with KRouter installed the way the README says (`scripts/bootstrap.py --apps codex`, so its MCP server and its
session hooks are what Codex gets). Nothing says "use krouter": the prompt is the scenario's own sentence.

    python3 bench/behavior/run_codex.py SET.json WORKDIR [--only ID,ID] [--jobs 4]

WORKDIR must be outside the user's home tree (Codex reads `.codex/config.toml` and `AGENTS.md` from parent folders).
HOME is a folder of its own, so none of the user's skills (`~/.agents/skills`), instructions or memory folders load
(a first run with the real HOME read the user's real vault through their skill: do not do that). The Codex login is
reached through a symlink to the real auth file (never copied, never printed), `~/Library` through another (Codex's
helper process needs it), and KROUTER_VAULT / XDG_CONFIG_HOME / KROUTER_STATE_DIR point the hooks and the MCP server at
the scenario's folders. Writes WORKDIR/<id>/record.json.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MODEL = os.environ.get("KR_CODEX_MODEL", "gpt-5.6-terra")  # without -m the choice flaked into models the ChatGPT login rejects (gpt-6-astra, gpt-5.5)
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from make_fixture import build  # noqa: E402


def write_project(proj: Path, files: dict) -> None:
    for name, body in files.items():
        if name.startswith("__BYTES__"):
            path, data = proj / name[len("__BYTES__"):], bytes.fromhex(body)
        else:
            path, data = proj / name, body.encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def clean_env(extra: dict) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.endswith(("_API_KEY", "_AUTH_TOKEN"))}
    env.update(extra)
    return env


def run_one(sc: dict, work: Path, base: Path, timeout: int) -> dict:
    d = work / sc["id"]
    if d.exists():
        shutil.rmtree(d)
    home, mem, proj = d / "home", d / "mem", d / "proj"
    (home / ".codex").mkdir(parents=True)
    proj.mkdir(parents=True)
    os.symlink(Path.home() / ".codex/auth.json", home / ".codex/auth.json")
    os.symlink(Path.home() / "Library", home / "Library")  # Codex's helper process needs it; without it the call times out
    shutil.copytree(base, mem, symlinks=True)
    write_project(proj, sc["files"])
    env = clean_env({"HOME": str(home), "CODEX_HOME": str(home / ".codex"), "KROUTER_VAULT": str(mem), "XDG_CONFIG_HOME": str(home / ".config"),
                     "KROUTER_STATE_DIR": str(d / "state"), "KROUTER_NO_QUERY_LOG": "1", "KROUTER_NO_PROMPT": "1"})
    inst = subprocess.run([sys.executable, str(ROOT / "scripts/bootstrap.py"), "--vault", str(mem), "--lang", "en",
                           "--apps", "codex", "--no-open", "--no-timer"],
                          env=env, capture_output=True, text=True, timeout=300)
    (d / "install.txt").write_text(inst.stdout[-3000:] + inst.stderr[-1000:], encoding="utf-8")
    cmd = ["codex", "exec", "-m", MODEL, "--json", "--skip-git-repo-check", "--ephemeral", "-s", "workspace-write",
           "--dangerously-bypass-hook-trust", "--disable", "memories", "--disable", "plugins", "-C", str(proj), sc["prompt"]]
    try:
        res = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        out, rc = res.stdout, res.returncode
    except subprocess.TimeoutExpired as e:
        out, rc = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), "timeout"
    (d / "events.jsonl").write_text(out, encoding="utf-8")
    calls, messages = [], []
    for line in out.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        item = ev.get("item") or {}
        if ev.get("type") == "item.completed" and item.get("type") == "agent_message":
            messages.append(item.get("text", ""))
        if ev.get("type") == "item.completed" and "mcp" in str(item.get("type")):
            res_txt = json.dumps(item.get("result") or item.get("error") or "", ensure_ascii=False)
            calls.append({"tool": item.get("tool"), "server": item.get("server"),
                          "arguments": item.get("arguments"), "status": item.get("status"), "result": res_txt[:600]})
    git = subprocess.run(["git", "-C", str(mem), "log", "--oneline"], capture_output=True, text=True).stdout.split("\n")
    rec = {"id": sc["id"], "group": sc["group"], "rc": rc, "calls": calls, "messages": messages,
           "vault_commits_after_fixture": max(0, len([l for l in git if l.strip()]) - 1)}
    (d / "record.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("set_json")
    ap.add_argument("workdir")
    ap.add_argument("--only", default="")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args()
    work = Path(a.workdir).resolve()
    if str(work).startswith(str(Path.home().resolve()) + os.sep) and "/private/tmp" not in str(work):
        raise SystemExit("WORKDIR must be outside the home tree")
    scenarios = json.loads(Path(a.set_json).read_text(encoding="utf-8"))
    if a.only:
        scenarios = [s for s in scenarios if s["id"] in a.only.split(",")]
    base = work / "_base"
    work.mkdir(parents=True, exist_ok=True)
    if not base.exists():
        build(base)
    with ThreadPoolExecutor(a.jobs) as pool:
        for rec in pool.map(lambda s: run_one(s, work, base, a.timeout), scenarios):
            print(rec["id"], "rc", rec["rc"], "calls", [c["tool"] for c in rec["calls"]], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
