#!/usr/bin/env python3
"""Recompute, on your machine, every registered number that needs no model, no key and no download, and print it next to
the value written down when it was registered.

    python3 bench/reproduce.py              # about 20 seconds; Python 3.9+, standard library plus what `pip install -e .` gives
    python3 bench/reproduce.py --zh         # the same table with 一致 / 不一致
    python3 bench/reproduce.py --timing     # also this machine's hook latency, kept apart from the table (about 30 s more)

Nothing is sent anywhere, no model is called, no file outside a temporary folder is written, and the real query log is
off (`KROUTER_NO_QUERY_LOG=1`). The exit code is 0 only if every row matches. If a row does not, do not trust either side
yet: open the source named in its last column and the run's command, and file an issue with both numbers.

What is NOT in the table (needs a model, or someone else's data, or is a timing) is listed under the table and in
bench/REPRODUCE.md.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
ENV = {**os.environ, "KROUTER_NO_QUERY_LOG": "1", "PYTHONDONTWRITEBYTECODE": "1"}
for k in [k for k in ENV if k.endswith("_API_KEY")]:
    ENV.pop(k)  # nothing here calls a model; make sure nothing could

HONESTY = "bench/memory_honesty/run.py"
HELD = "bench/memory_honesty/HELDOUT.md"
BENCH = "docs/BENCHMARK.md"
NUMBERS = "docs/NUMBERS.md"
_cache: dict[tuple, str] = {}


def sh(*cmd: str) -> str:
    key = cmd
    if key not in _cache:
        # -X utf8: the scripts print Chinese; a Windows console or pipe would otherwise use cp1252 (and -I ignores PYTHONUTF8)
        r = subprocess.run([PY, "-X", "utf8", "-I", *cmd], cwd=REPO, env=ENV, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise SystemExit(f"command failed: {' '.join(cmd)}\n{r.stderr[-800:]}")
        _cache[key] = r.stdout
    return _cache[key]


def js(*cmd: str) -> dict:
    out = sh(*cmd)
    return json.loads(out[out.index("{"):])


def pct(x: float) -> int:
    return int(math.floor(x * 100 + 0.5 + 1e-9))  # round half up; the intervals are stored to three decimals (0.575 -> 58)


def honesty(qset: str, *extra: str) -> dict:
    return js(HONESTY, "--set", qset, *extra)


def right(d: dict) -> int:
    return int(d["correction_hit"].split("/")[0]) + int(d["current_hit"].split("/")[0])


def row_hon(d: dict, n_ans: bool = True) -> str:
    return (f"wrong {d['wrong_citations']}/{d['answered']}, refused {d['refused']}, right {right(d)}"
            f" (corrections {d['correction_hit']}, current {d['current_hit']})")


def kb_auto() -> dict[str, str]:
    d = tempfile.mkdtemp(prefix="krouter-repro-kb-")
    try:
        sh("bench/kb_auto/make.py", d)
        out = {}
        for split in ("heldout", "dev"):
            r = js("bench/kb_auto/run.py", d, split)
            out[split] = f"outside pages recognised {r['outside_recognised']}, own pages taken for reference {r['own_misjudged']}"
        return out
    finally:
        shutil.rmtree(d, ignore_errors=True)


def hook(cases: str) -> str:
    out = sh("bench/subconscious/set45.py", "run", cases)
    m = re.search(r"all: recall (\d+/\d+)  changed (\d+/\d+)  quiet-loud (\d+/\d+)  wrong (\d+)  old (\d+)", out)
    s = f"recall {m[1]}, changed {m[2]}, quiet messages that got a page {m[3]}, wrong pages {m[4]}, old pages {m[5]}"
    lang = re.findall(r"  (zh|en): recall (\d+/\d+)", out)
    s += " (" + ", ".join(f"{l} {r}" for l, r in lang) + ")"
    nn = re.search(r"recall not named \(mechanical\): (\d+/\d+)", out)
    if nn:
        s += f"; of the recall cases that use none of the page's names {nn[1]}"
    return s


def rows() -> list[tuple[str, str, str, str]]:
    """(what, registered, recomputed, where it is registered)"""
    R: list[tuple[str, str, str, str]] = []
    add = lambda what, reg, got, src: R.append((what, reg, got, src))

    # --- the honesty bench: right page, or refuse -------------------------------------------------------------
    h3 = honesty("heldout3", "--ci")
    add("Honesty bench, set 3 (200 questions, a vault nobody tuned on): KRouter",
        "wrong 36/138, refused 47/80, right 102 (corrections 50/60, current 52/60)", row_hon(h3), f"{NUMBERS}, 'Wrong citations on a vault nobody tuned on'")
    ci = h3["ci95"]
    add("  95% intervals of that row",
        "wrong rate 19.0-33.1%, right 88-116, refused 36-59",
        f"wrong rate {ci['wrong_citation_rate'][0] * 100:.1f}-{ci['wrong_citation_rate'][1] * 100:.1f}%, right {ci['right'][0]}-{ci['right'][1]}, refused {ci['refused'][0]}-{ci['refused'][1]}",
        f"{HELD}, set 3 log")
    b3 = honesty("heldout3", "--ci", "--adapter", "bm25")
    add("  plain keyword search (BM25, always answers) on the same questions",
        "wrong 116/199, refused 1/80, right 83; wrong rate 52-65%",
        f"wrong {b3['wrong_citations']}/{b3['answered']}, refused {b3['refused']}, right {right(b3)}; wrong rate "
        f"{pct(b3['ci95']['wrong_citation_rate'][0])}-{pct(b3['ci95']['wrong_citation_rate'][1])}%", f"{HELD}, set 3 baseline table")
    m3 = honesty("heldout3", "--vs-matched", "bm25-floor")
    vm = m3["vs_matched"]
    add("  BM25 plus the same two rules, at KRouter's coverage",
        "wrong 42/138, right 96, refused 45/80",
        f"wrong {vm['wrong_citations']}/{vm['answered']}, right {right(vm)}, refused {vm['refused']}", f"{NUMBERS}, same row")
    c = vm["ci95"]
    add("  paired intervals KRouter minus that baseline",
        "wrong rate -10.2 to +1.3 points, right -2 to +14",
        f"wrong rate {c['delta_wrong_citation_rate'][0] * 100:+.1f} to {c['delta_wrong_citation_rate'][1] * 100:+.1f} points, right {c['delta_right'][0]:+d} to {c['delta_right'][1]:+d}",
        f"{NUMBERS}, same row")
    for name, reg_w, reg_ref, reg_r, label in (("claude-mem-13.39.0", "128/200 (64%, 58-71%)", "0/80", "72", "claude-mem 13.39.0"),
                                                ("basic-memory-0.23.2", "155/200 (78%, 72-84%)", "0/80", "45", "basic-memory 0.23.2")):
        d = js(HONESTY, "--set", "heldout3", "--ci", "--answers", f"bench/memory_honesty/results/2026-10-14/{name}.heldout3.jsonl")
        lo, hi = d["ci95"]["wrong_citation_rate"]
        add(f"  {label}: its stored raw answers, graded again here (the tool itself is not run)",
            f"wrong {reg_w}, refused {reg_ref}, right {reg_r}",
            f"wrong {d['wrong_citations']}/{d['answered']} ({pct(d['wrong_citation_rate'])}%, {pct(lo)}-{pct(hi)}%), refused {d['refused']}, right {right(d)}",
            f"{BENCH}, 'Other memory systems on the same 200 questions'")
    h1 = honesty("heldout")
    add("Honesty bench, set 1 (25 questions): KRouter, as frozen at 1.0.1",
        "wrong 3/12, refused 8/10, right 9 (corrections 5/9, current 4/6)", row_hon(h1), f"{HELD}, 'Baseline at freeze'")
    add("  plain BM25 on the same questions", "wrong 14/23, refused 1/10, right 9 (corrections 4/9, current 5/6)", row_hon(honesty("heldout", "--adapter", "bm25")), f"{HELD}, 'Baseline at freeze'")
    add("  BM25 plus the two rules (floor picked on dev)", "wrong 3/16, refused 7/10, right 13 (corrections 8/9, current 5/6)", row_hon(honesty("heldout", "--adapter", "bm25-floor")), f"{BENCH}, 'Matched baselines'")
    h2 = honesty("heldout2")
    add("Honesty bench, set 2 (50 questions, second vault): KRouter", "wrong 12/36, refused 9/20, right 24 (corrections 12/15, current 12/15)", row_hon(h2), f"{BENCH}, 'Second bench'")
    add("  plain BM25 on the same questions", "wrong 30/49, refused 1/20, right 19 (corrections 5/15, current 14/15)", row_hon(honesty("heldout2", "--adapter", "bm25")), f"{BENCH}, 'Second bench'")
    add("  BM25 plus the two rules (floor picked on dev3)", "wrong 4/21, refused 16/20, right 17 (corrections 9/15, current 8/15)", row_hon(honesty("heldout2", "--adapter", "bm25-floor")), f"{BENCH}, second-bench table")

    # --- reference material told from your own pages ----------------------------------------------------------
    kb = kb_auto()
    add("Reference recognition (set 40), held-out half of labelled synthetic vaults",
        "outside pages recognised 30/32, own pages taken for reference 0/43", kb["heldout"], f"{NUMBERS}, set 40 row")
    add("  development half", "outside pages recognised 35/35, own pages taken for reference 0/41", kb["dev"], f"{NUMBERS}, set 40 row")

    # --- the subconscious: the prompt hook by itself ----------------------------------------------------------
    add("Mention it, spoken style (set 45), the hook alone, development half (120 invented messages)",
        "recall 7/48, changed 7/24, quiet messages that got a page 2/48, wrong pages 0, old pages 0 (zh 5/24, en 2/24); of the recall cases that use none of the page's names 1/42",
        hook("set45dev"), f"{HELD}, 'Log, set 45'")
    add("Mention it (set 32), the hook alone, held-out half (run once when registered)",
        "recall 7/24, changed 4/12, quiet messages that got a page 1/24, wrong pages 0, old pages 0 (zh 6/12, en 1/12)",
        hook("set32held"), f"{HELD}, set 32 log; {NUMBERS}")
    add("Mention it (set 35), the hook's share of the whole chain, held-out half",
        "recall 7/24, changed 5/12, quiet messages that got a page 1/24, wrong pages 0, old pages 0 (zh 4/12, en 3/12)",
        hook("set35held"), f"{HELD}, 'Log, set 45' (N2) and set 35 log")
    return R


NOT_IN_TABLE = """\
Not in the table above (and why):
  needs a model, and a key of your own: LongMemEval answer accuracy (sets 11, 12, 22), the refusal chain (set 41), the host
    layer of the subconscious (sets 33, 35 host half, 45 addendum: Sonnet 44/48 and the like), lessons and skills (sets 15-26),
    real sessions (30, 31). Commands, what each reads and what each costs: bench/REPRODUCE.md.
  needs someone else's data, downloaded by you (the scripts download nothing): LongMemEval (sets 7, 11, 14, 22, 37-39 counts
    over its 500 questions) and LoCoMo (set 10, 18). Commands: README.md, 'Check it yourself'.
  needs a real machine of yours: set 42 (a real vault, read-only), sets 27-28 (ten people at once, 30 minutes), scale and speed.
  a timing, so it depends on your machine: use --timing; it is printed apart and never compared.
  sealed: the held-out half of set 45 (120 messages). It is not run or read here; the maintainer opens it once, to confirm.
"""


def timing() -> None:
    print("\nThis machine's numbers (hook process latency, vault3, warm 50 / cold 5 runs per message; NOT compared with anything):")
    tmp = tempfile.mkdtemp(prefix="krouter-repro-speed-")
    try:
        os.environ["KROUTER_NO_QUERY_LOG"] = "1"
        os.environ["KROUTER_CACHE_DIR"] = str(Path(tmp) / "cache0")
        os.environ["KROUTER_STATE_DIR"] = str(Path(tmp) / "state0")
        sys.path.insert(0, str(REPO / "skill/krouter/scripts"))
        import importlib.util

        spec = importlib.util.spec_from_file_location("krouter_subconscious_run", REPO / "bench/subconscious/run.py")
        set32 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(set32)

        v = set32.make_vault(Path(tmp))
        out = subprocess.run([PY, "-X", "utf8", "-I", "bench/subconscious/speed.py", "--vault", str(v), "--warm", "50", "--cold", "5",
                              "--hit", "do we add the Sunset header?", "--miss", "what should we have for lunch today"],
                             cwd=REPO, env=ENV, capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(out.stdout.strip() or out.stderr[-500:])
        try:
            la = os.getloadavg()[0]
            print(f"  load average at the start of this run: about {la:.1f} (a busy machine reads slower)")
        except OSError:
            pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zh", action="store_true", help="一致 / 不一致 instead of match / MISMATCH")
    ap.add_argument("--timing", action="store_true")
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):  # --zh prints 一致; a cp1252 console would raise UnicodeEncodeError
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    t0 = time.time()
    ok_w, bad_w = ("一致", "不一致") if a.zh else ("match", "MISMATCH")
    table = rows()
    bad = 0
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    except OSError:
        rev = ""
    import platform
    import sqlite3

    print(f"KRouter {rev or '(not a git checkout)'}: registered numbers that need no model, recomputed now")
    print(f"(Python {platform.python_version()}, SQLite {sqlite3.sqlite_version}, {platform.system()} {platform.machine()})\n")
    for what, reg, got, src in table:
        same = reg == got
        bad += not same
        print(f"[{ok_w if same else bad_w}] {what}")
        print(f"      registered: {reg}")
        if not same:
            print(f"      recomputed: {got}")
        print(f"      source: {src}")
    print(f"\n{len(table) - bad} of {len(table)} rows {ok_w}; {bad} {bad_w}.  ({time.time() - t0:.0f} s)\n")
    print(NOT_IN_TABLE)
    if a.timing:
        timing()
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
