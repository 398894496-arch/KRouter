"""KRouter from Python: ask your memory a question, check its health, write a note.

    import krouter
    a = krouter.ask("how do we ship a release?")
    a.page, a.how, a.refused        # the page it came from, the one-line answer, True when the memory does not know
    a.references                    # knowledge-base pages (reference material), listed apart from the answer
    krouter.note("Releases are tagged from main only.", kind="decision")

The memory is `vault=`, else `KROUTER_VAULT` (`OBSIDIAN_VAULT`, the older name, also works), else the folder the
one-line install recorded (`~/.config/krouter/vault`).
Lookups run on this machine; nothing is sent anywhere.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

__version__ = "2.1.0"
ROUTES = ("search", "preference", "correction", "memory", "project", "suggest")


def router_dir() -> Path:
    """The router's scripts: the copy installed with this package, else the repository this file sits in."""
    try:
        import krouter_router  # 打包时随包装进来的那份路由器

        return Path(list(krouter_router.__path__)[0]).resolve()  # 没有 __init__.py 的命名空间包，只有 __path__
    except ImportError:
        here = Path(__file__).resolve().parents[2] / "skill" / "krouter" / "scripts"
        if (here / "route_knowledge.py").exists():
            return here
        raise RuntimeError("KRouter's router scripts were not found; reinstall the package") from None


@dataclass
class Answer:
    """One receipt. `fields` holds every `key: value` line; the properties name the ones most callers need."""

    text: str
    fields: dict = field(default_factory=dict)

    @property
    def hits(self) -> list[dict]:
        """The pages recall listed, best first: `{"page", "tier", "status", "how"}`. A replaced page can be listed
        (tier `dead`, status `superseded`) so you see it was replaced; it is never the answer."""
        out: list[dict] = []
        inside = False
        for line in self.text.splitlines():
            if line.startswith("recall:"):
                inside = line.strip() == "recall:"
                continue
            if not inside:
                continue
            if line.startswith("- "):
                head, _, rest = line[2:].partition(" tier=")
                meta = dict(kv.split("=", 1) for kv in ("tier=" + rest).split() if "=" in kv) if rest else {}
                out.append({"page": head.strip(), "tier": meta.get("tier", ""), "status": meta.get("status", ""), "how": ""})
            elif line.startswith("  how: ") and out:
                out[-1]["how"] = line[len("  how: "):].strip()
            elif not line.startswith(" "):
                inside = False
        return out

    @property
    def references(self) -> list[dict]:
        """Pages of the knowledge base the receipt listed apart (`knowledge_base:`): reference material someone else
        wrote, never the answer to what you decided. `{"page", "kb", "title", "source"}`, best first."""
        out: list[dict] = []
        inside = False
        for line in self.text.splitlines():
            if line.startswith("knowledge_base:"):
                inside = True
                continue
            if not inside:
                continue
            if line.startswith("- "):
                head, _, rest = line[2:].partition(" kb=")
                out.append({"page": head.strip(), "kb": rest.split()[0] if rest else "", "title": "", "source": ""})
            elif line.startswith("  title: ") and out:
                out[-1]["title"] = line[len("  title: "):].strip()
            elif line.startswith("  source: ") and out:
                out[-1]["source"] = line[len("  source: "):].strip()
            elif not line.startswith(" "):
                inside = False
        return out

    @property
    def memory_none(self) -> bool:
        """True when your memory has nothing on the question and only the knowledge base matched."""
        return self.fields.get("memory", "").startswith("none")

    def _top(self) -> dict:
        return next((h for h in self.hits if h["tier"] != "dead" and h["status"] != "superseded"), {})

    @property
    def page(self) -> str:
        """The page the answer comes from: the locked page on an exact match, else recall's best live page."""
        if self.fields.get("canonical_match") == "true":
            return self.fields.get("source", "")
        return "" if self.refused else self._top().get("page", "")

    @property
    def how(self) -> str:
        """The one line that answers it (recall's `how:`), empty when the memory does not know."""
        return "" if self.refused else (self._top().get("how") or self.fields.get("how", ""))

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
    if vault:  # 点名的文件夹优先：子进程里 KROUTER_VAULT 会盖过 OBSIDIAN_VAULT，所以两个都设成它
        env["KROUTER_VAULT"] = env["OBSIDIAN_VAULT"] = str(Path(vault).expanduser())
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
