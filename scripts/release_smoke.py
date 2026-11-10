#!/usr/bin/env python3
"""After a release is published: take every install command README.md and README.zh.md give, and run it against the
real addresses. Any one that cannot be fetched or does not start fails the check.

    python3 scripts/release_smoke.py [--tag v1.4.0]

What it checks, each in a throwaway HOME (nothing on this machine is installed or changed):

1. Every `releases/latest/download/<file>` the READMEs link downloads.
2. The one-line install, run the way the README says (saved to a file, then `sh` on it) with `--dry-run --no-open`:
   it looks up the latest release, downloads the package and verifies its SHA-256 (exit 0 and "sha256 verified").
3. `bootstrap.sh` and `bootstrap.ps1` as published match the release's `SHA256SUMS`.
4. Every `git+https://…` the READMEs give, through `uvx --from … krouter --version` and `krouter demo`, and through
   `pipx install …` then `krouter --version`. With `--tag`, the version must be the tag's.
5. The Claude Code marketplace the README names has its `.claude-plugin/marketplace.json` on the default branch.

`--rewrite FROM=TO` (repeatable) points the addresses elsewhere, so the check itself can be proven on local files
before a release: `--rewrite https://github.com/398894496-arch/KRouter/releases/latest/download/=file:///tmp/rel/`.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "398894496-arch/KRouter"
READMES = ("README.md", "README.zh.md")
results: list[tuple[bool, str]] = []


def check(ok: bool, what: str, detail: str = "") -> bool:
    results.append((ok, what))
    print(("ok    " if ok else "FAIL  ") + what + (f"\n      {detail.strip()[-800:]}" if detail and not ok else ""))
    return ok


def rewrite(url: str, rules: list[tuple[str, str]]) -> str:
    for a, b in rules:
        if url.startswith(a):
            return b + url[len(a):]
    return url


def fetch(url: str, dest: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["curl", "-fsSL", url, "-o", str(dest)], capture_output=True, text=True, timeout=300)


def clean_env(home: Path, **extra: str) -> dict:
    """A throwaway HOME, no keys, no query log, no terminal questions."""
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "en_US.UTF-8",
           "TMPDIR": str(home / "tmp"), "KROUTER_NO_QUERY_LOG": "1", "KROUTER_NO_PROMPT": "1",
           "XDG_CONFIG_HOME": str(home / ".config"), "UV_CACHE_DIR": str(home / "uv-cache"),
           "PIPX_HOME": str(home / "pipx"), "PIPX_BIN_DIR": str(home / "bin"), "UV_TOOL_DIR": str(home / "uv-tools")}
    (home / "tmp").mkdir(parents=True, exist_ok=True)
    env.update(extra)
    return env


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tag", default="", help="the release just published (its version must be what installs)")
    ap.add_argument("--rewrite", action="append", default=[], metavar="FROM=TO")
    ap.add_argument("--release-base", default="", help="KROUTER_RELEASE_BASE for the one-line install (local proof)")
    args = ap.parse_args()
    rules = [tuple(r.split("=", 1)) for r in args.rewrite]
    want = args.tag.lstrip("v")
    text = "\n".join((ROOT / r).read_text(encoding="utf-8") for r in READMES)
    work = Path(tempfile.mkdtemp(prefix="krouter-smoke-"))
    try:
        # 1. 发布附件
        assets = sorted(set(re.findall(rf"https://github\.com/{re.escape(REPO)}/releases/latest/download/[A-Za-z0-9._-]+", text)))
        check(bool(assets), f"the READMEs link {len(assets)} release assets")
        got: dict[str, Path] = {}
        for url in assets:
            dest = work / "assets" / url.rsplit("/", 1)[1]
            dest.parent.mkdir(parents=True, exist_ok=True)
            res = fetch(rewrite(url, rules), dest)
            if check(res.returncode == 0 and dest.stat().st_size > 0 if dest.exists() else False, f"download {url}", res.stderr):
                got[dest.name] = dest
        # 3. 附件和校验和对得上
        sums_url = f"https://github.com/{REPO}/releases/latest/download/SHA256SUMS"
        sums = work / "assets" / "SHA256SUMS"
        res = fetch(rewrite(sums_url, rules), sums)
        if check(res.returncode == 0, f"download {sums_url}", res.stderr):
            table = dict(reversed(ln.split()) for ln in sums.read_text().splitlines() if len(ln.split()) == 2)
            for name, path in got.items():
                if name in table:
                    check(hashlib.sha256(path.read_bytes()).hexdigest() == table[name], f"{name} matches SHA256SUMS")
            pkgs = [n for n in table if n.startswith("dsh-krouter-") and n.endswith(".tgz")]
            check(len(pkgs) == 1 and (not want or pkgs[0] == f"dsh-krouter-{want}.tgz"),
                  f"SHA256SUMS names the package for {want or 'this release'}: {pkgs}")
        # 2. 一行安装，按 README 的写法（先存成文件再 sh），只预演
        if "bootstrap.sh" in got:
            home = work / "home-oneline"
            extra = {"KROUTER_RELEASE_BASE": args.release_base} if args.release_base else {}
            if args.tag and args.release_base:
                extra["KROUTER_TAG"] = args.tag
            res = subprocess.run(["sh", str(got["bootstrap.sh"]), "--dry-run", "--no-open"], env=clean_env(home, **extra),
                                 stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=600)
            check(res.returncode == 0 and "sha256 verified" in res.stdout and "Plan:" in res.stdout,
                  "the one-line install fetches, verifies and plans (--dry-run)", res.stdout + res.stderr)
            if want:
                check(f"KRouter v{want} " in res.stdout, f"the one-line install picks v{want}", res.stdout)
        # 4. uvx / pipx 从 git 地址装
        gits = sorted(set(re.findall(rf"git\+https://github\.com/{re.escape(REPO)}(?:\.git)?(?:@[\w.-]+)?", text)))
        check(bool(gits), f"the READMEs give {len(gits)} git install address(es)")
        for git in gits:
            src = rewrite(git, rules)
            if shutil.which("uvx"):
                home = work / "home-uvx"
                env = clean_env(home)
                res = subprocess.run(["uvx", "--from", src, "krouter", "--version"], env=env, capture_output=True,
                                     text=True, timeout=900)
                check(res.returncode == 0 and (not want or want in res.stdout), f"uvx --from {git} krouter --version",
                      res.stdout + res.stderr)
                res = subprocess.run(["uvx", "--from", src, "krouter", "demo"], env=env, capture_output=True, text=True,
                                     timeout=900)
                check(res.returncode == 0 and "recall: none" in res.stdout, f"uvx --from {git} krouter demo",
                      res.stdout + res.stderr)
            else:
                check(False, "uvx is not installed here (install uv to run this check)")
            if shutil.which("pipx"):
                home = work / "home-pipx"
                env = clean_env(home)
                res = subprocess.run(["pipx", "install", src], env=env, capture_output=True, text=True, timeout=900)
                if check(res.returncode == 0, f"pipx install \"{git}\"", res.stdout + res.stderr):
                    res = subprocess.run([str(home / "bin/krouter"), "--version"], env=env, capture_output=True, text=True,
                                         timeout=120)
                    check(res.returncode == 0 and (not want or want in res.stdout), "krouter --version after pipx",
                          res.stdout + res.stderr)
            else:
                check(False, "pipx is not installed here (install pipx to run this check)")
        # 5. Claude Code 插件市场
        if f"--marketplace {REPO}" in text:
            url = f"https://raw.githubusercontent.com/{REPO}/main/.claude-plugin/marketplace.json"
            res = fetch(rewrite(url, rules), work / "marketplace.json")
            check(res.returncode == 0 and '"krouter"' in (work / "marketplace.json").read_text(errors="replace")
                  if res.returncode == 0 else False, f"Claude Code marketplace {REPO} ({url})", res.stderr)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    bad = [w for ok, w in results if not ok]
    print(f"\nrelease smoke: {len(results) - len(bad)} ok, {len(bad)} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
