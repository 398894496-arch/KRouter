#!/usr/bin/env python3
"""The KRouter command line from this copy, no pip needed: `python scripts/krouter_run.py doctor | ask "question" | why | ...`.

`scripts/krouter` does the same on macOS and Linux (a shell script). This file is for Windows, where the install prints
`python "<this file>" doctor`: one command that runs unchanged in cmd, PowerShell 5.1 and PowerShell 7, with no `&&`
and no environment variable to set. It puts `sdk/` on the import path itself and hands over to `krouter.cli`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sdk"))

from krouter.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
