"""KRouter from Python: ask your memory a question, check its health, write a note.

    import krouter
    a = krouter.ask("how do we ship a release?")
    a.page, a.how, a.refused        # the page it came from, the one-line answer, True when the memory does not know
    krouter.note("Releases are tagged from main only.", kind="decision")

The memory is the vault the one-line install recorded (`~/.config/krouter/vault`), `OBSIDIAN_VAULT`, or `vault=`.
Lookups run on this machine; nothing is sent anywhere.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

__version__ = "1.3.0"
ROUTES = ("search", "preference", "correction", "memory", "project", "suggest")


def router_dir() -> Path:
    """The router's scripts: the copy installed with this package, else the repository this file sits in."""
    try:
        import krouter_router  # 打包时随包装进来的那份路由器

        return Path(list(krouter_router.__path__)[0]).resolve()  # 没有 __init__.py 的命名空间包，只有 __path__
    except ImportError:
        here = Path(__file__).resolve().parents[2] / "skill" / "krouter-obsidian" / "scripts"
        if (here / "route_knowledge.py").exists():
            return here
        raise RuntimeError("KRouter's router scripts were not found; reinstall the package") from None


@dataclass
class Answer:
    """One receipt. `fields` holds every `key: value` line; the properties name the ones most callers need."""

    text: str
    fields: dict = field(default_factory=dict)

    @property
    def page(self) -> str:
        return self.fields.get("source", "")

    @property
    def how(self) -> str:
        return self.fields.get("how", "")

    @property
    def refused(self) -> bool:
        return self.fields.get("recall", "").startswith("none")

    @property
    def confidence(self) -> str:
        return self.fields.get("recall_confidence", "")

    def __str__(self) -> str:
        return self.text


def _parse(text: str) -> dict:
    out: dict = {}
    for line in text.splitlines():
        if ": " in line and not line.startswith((" ", "-", "|")):
            k, v = line.split(": ", 1)
            out.setdefault(k.strip(), v.strip())
    return out


def _env(vault: str | os.PathLike | None) -> dict:
    env = dict(os.environ)
    if vault:
        env["OBSIDIAN_VAULT"] = str(Path(vault).expanduser())
    return env


def ask(question: str, route: str = "search", vault: str | os.PathLike | None = None, timeout: float = 120) -> Answer:
    """Look the question up in the memory. `route` narrows where it looks (see ROUTES)."""
    if route not in ROUTES:
        raise ValueError(f"route must be one of {', '.join(ROUTES)}")
    proc = subprocess.run([sys.executable, str(router_dir() / "route_knowledge.py"), route, question],
                          env=_env(vault), capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or f"router exited {proc.returncode}").strip()[-2000:])
    return Answer(proc.stdout.strip(), _parse(proc.stdout))


def status(vault: str | os.PathLike | None = None) -> Answer:
    """Health of the memory and of the nightly job, with what to do when something is off."""
    proc = subprocess.run([sys.executable, str(router_dir() / "route_knowledge.py"), "status", ""], env=_env(vault),
                          capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    return Answer(proc.stdout.strip(), _parse(proc.stdout))


def note(text: str, kind: str = "note", vault: str | os.PathLike | None = None) -> str:
    """Write one line to today's notes page (a clue, not a rule), listed in the change ledger and one git commit."""
    sys.path.insert(0, str(router_dir()))
    import mcp_server

    saved = os.environ.get("OBSIDIAN_VAULT")
    if vault:
        os.environ["OBSIDIAN_VAULT"] = str(Path(vault).expanduser())
    try:
        msg, err = mcp_server.note({"text": text, "kind": kind})
    finally:  # 不改调用方进程的环境
        if saved is None:
            os.environ.pop("OBSIDIAN_VAULT", None)
        else:
            os.environ["OBSIDIAN_VAULT"] = saved
    if err:
        raise ValueError(msg)
    return msg
