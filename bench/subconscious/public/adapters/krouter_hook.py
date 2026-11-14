"""KRouter's prompt hook, by itself: the lookup `session_hook.py prompt` runs on every message (no model, no network).

It is called as the hook calls it, on a temporary copy of the benchmark's knowledge base (bench/memory_honesty/vault3)
with the alias table and trigger words that were written for it before any case existed (bench/subconscious/overlay/,
the KRouter side of the setup; the other adapters are not given them). `pages` is not read: the hook reads its own copy.

The host layer (the standing index at session start and the host model fetching for itself) is not part of this adapter
and needs a model; see README.md in this folder. `SET45_SCRIPTS` points at another copy of skill/krouter/scripts.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
_tmp = None
_vault = None
_recollect = None


def setup(pages, **options):
    global _tmp, _vault, _recollect
    scripts = Path(os.environ.get("SET45_SCRIPTS") or REPO / "skill/krouter/scripts")
    sys.path.insert(0, str(scripts))
    sys.path.insert(0, str(REPO / "bench/subconscious"))
    _tmp = tempfile.mkdtemp(prefix="krouter-public-")
    os.environ.update(KROUTER_CACHE_DIR=str(Path(_tmp) / "cache"), KROUTER_STATE_DIR=str(Path(_tmp) / "state"),
                      KROUTER_NO_QUERY_LOG="1")
    import recollect
    import recall_index
    import importlib.util

    # make_vault: vault3 + overlay, exactly what the registered runs use (loaded by path: other benches also have a run.py)
    spec = importlib.util.spec_from_file_location("krouter_subconscious_run", REPO / "bench/subconscious/run.py")
    set32 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(set32)

    _recollect = recollect
    _vault = set32.make_vault(Path(_tmp))
    recall_index.recall(_vault, "warm up the index")  # the router, the MCP server or the nightly job builds it in real use


def handle(message):
    return [h["real"] for h in _recollect.recollect(_vault, message, _recollect.DEFAULT_ROUTES)]


def close():
    if _tmp:
        shutil.rmtree(_tmp, ignore_errors=True)
