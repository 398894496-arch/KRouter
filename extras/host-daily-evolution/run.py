#!/usr/bin/env python3
"""Cross-platform twin of run.sh (Windows has no /bin/sh): seal yesterday, then the nightly upkeep.

Same contract: OBSIDIAN_VAULT unset → exit 0; the seal's exit code is the process's exit code;
KROUTER_NIGHTLY=0 turns the nightly steps off; `--dry-run` calls no model and writes nothing.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
ROOT = DIR.parents[1]
BUNDLED_ROUTER = ROOT / "skill/krouter-obsidian/scripts/route_knowledge.sh"


def main() -> int:
    vault = (os.environ.get("KROUTER_VAULT") or os.environ.get("OBSIDIAN_VAULT", "")).strip()
    if not vault:
        print("KRouter: KROUTER_VAULT (or OBSIDIAN_VAULT) is not set. Timer on; distill skipped.", file=sys.stderr)
        return 0
    router = os.environ.get("KROUTER_ROUTER", "")
    if "obsidian-knowledge-router" in router or not router:
        router = str(BUNDLED_ROUTER)
    os.environ["KROUTER_ROUTER"] = router
    scripts = Path(router).parent if (Path(router).parent / "nightly.py").is_file() else BUNDLED_ROUTER.parent
    if "--dry-run" in sys.argv[1:]:
        subprocess.run([sys.executable, str(DIR / "resolve.py"), "--status", "--offline"], check=False)
        subprocess.run([sys.executable, str(scripts / "nightly.py"), "--vault", vault, "--dry-run"], check=False)
        return 0
    rc = subprocess.run([sys.executable, str(DIR / "resolve.py"), "--exec"], check=False).returncode
    if os.environ.get("KROUTER_NIGHTLY", "1") != "0":
        night = subprocess.run([sys.executable, str(scripts / "nightly.py"), "--vault", vault],
                               stdout=sys.stderr, check=False)
        if night.returncode != 0:
            print(f"KRouter: nightly runner failed (rc={night.returncode})", file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
