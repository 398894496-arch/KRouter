#!/usr/bin/env python3
"""Why the full-text lookup refuses or holds back a message: the refusal gate's criteria, one by one, as the prompt hook
calls the lookup (`recollect._ranked`). Read-only diagnostics; no model, no network; the engine is not changed on disk (a
copy of `recall_index.py` is loaded in memory with a few lines that record the gate's inputs).

    python3 bench/subconscious/gate_reasons.py set45dev          # recall and quiet cases of set 45's development half
    python3 bench/subconscious/gate_reasons.py real --vault DIR  # counts only, on this machine's messages (fixed window)

`real` needs the vault to replay against (`--vault` or `KROUTER_REPLAY_VAULT`; there is no default, and without one it
says so and does nothing). It reads the vault and the Claude Code transcripts read-only; the index and state are copied to a temporary folder;
`KROUTER_NO_QUERY_LOG=1`. It prints counts and distributions only: no message, phrase or page name.
"""

from __future__ import annotations

import collections
import glob
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SCRIPTS = REPO / "skill/krouter/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))
os.environ["KROUTER_NO_QUERY_LOG"] = "1"

MARK1 = "    partial = not single and strong < need\n"
REC1 = MARK1 + (
    "    if not library:\n"
    "        _DIAG.update(top=top, floor=SCORE_MIN * scale * (0.5 if single else 1.0), single_floor=SINGLE_TERM_SCORE * scale,\n"
    "                     strong=strong, need=need, unknown=unknown, alien=alien, off_vault=off_vault, absent=absent_words,\n"
    "                     top_words=top_words, unnamed=len(unnamed), single=single, margin=margin, refuse=refuse,\n"
    "                     tier=hits[0]['tier'], top_rel=hits[0]['rel'])\n")
MARK2 = "        conf = \"none\"  # 排在前面的只是你以前的提问，剩下的又只是弱匹配：库里没有\n"
REC2 = MARK2 + "    if not library:\n        _DIAG.update(clipped=clipped, crowded=crowded, asked=bool(asked), conf_gate=conf)\n"


def diag_module():
    src = (SCRIPTS / "recall_index.py").read_text(encoding="utf-8")
    assert src.count(MARK1) == 1 and src.count(MARK2) == 1
    src = src.replace(MARK1, REC1).replace(MARK2, REC2).replace("\nimport argparse\n", "\nimport argparse\n_DIAG = {}\n", 1)
    spec = importlib.util.spec_from_loader("ri_diag", loader=None)
    mod = importlib.util.module_from_spec(spec)
    mod.__file__ = str(SCRIPTS / "recall_index.py")
    sys.modules["ri_diag"] = mod
    exec(compile(src, str(SCRIPTS / "recall_index.py"), "exec"), mod.__dict__)
    return mod


def reasons(d: dict) -> list[str]:
    """The criteria that fire for one lookup (empty: the gate let it through)."""
    if "top" not in d:
        return ["no_candidate"]
    out = []
    if d["single"]:
        if d["top"] < d["floor"]:
            out.append("score_floor")
        if d["unknown"] and d["strong"] == 0:
            out.append("unknown_terms")
        if d["unnamed"]:
            out.append("unnamed")
    else:
        if d["top"] < d["floor"]:
            out.append("score_floor")
        if d["strong"] < d["need"] and d["top"] < d["single_floor"]:
            out.append("one_word_weak")
        if d["strong"] == 0:
            out.append("no_strong_word")
        if d["unknown"] and d["strong"] <= 2:
            out.append("unknown_terms")
        if d["strong"] < d["need"] and d["alien"] >= 2:
            out.append("alien_chars")
        if d["off_vault"]:
            out.append("off_vault")
        if d["unnamed"]:
            out.append("unnamed")
    for k in ("clipped", "crowded", "asked"):
        if d.get(k) and d.get("conf_gate") == "none":
            out.append(k)
    return out


def lookup(ri, R, vault: Path, text: str) -> tuple[dict | None, dict]:
    said = R.prose(text)
    ri._DIAG.clear()
    try:
        res = ri.recall(vault, said, refresh_first=False, assoc=False, conflict=True)
    except Exception:  # noqa: BLE001
        res = None
    return res, dict(ri._DIAG)


def band(m: float) -> str:
    return "<1.15" if m < 1.15 else "1.15-1.5" if m < 1.5 else "1.5-2.5" if m < 2.5 else ">=2.5"


def set45dev(_a) -> int:
    import run
    import recollect as R

    ri = diag_module()
    rows = [json.loads(x) for x in (HERE / "set45_dev.jsonl").read_text(encoding="utf-8").split("\n") if x.strip()]
    tmp = Path(tempfile.mkdtemp())
    os.environ.update(KROUTER_CACHE_DIR=str(tmp / "c"), KROUTER_STATE_DIR=str(tmp / "s"))
    v = run.make_vault(tmp)
    ri.recall(v, "warm up the index")
    today = date.today()
    groups = collections.defaultdict(list)
    for r in rows:
        if r["kind"] not in ("recall", "quiet"):
            continue
        res, d = lookup(ri, R, v, r["text"])
        conf = (res or {}).get("confidence")
        top_real = ""
        if d.get("top_rel"):
            cur = R.current(v, ri.zones.real(v, d["top_rel"]), today)
            top_real = cur[0] if cur else ""
        rank = None
        if r["kind"] == "recall":
            full = ri.recall(v, R.prose(r["text"]), refresh_first=False, assoc=False, gate=False, limit=80) or {}
            reals = []
            for h in full.get("hits") or []:
                cur = R.current(v, ri.zones.real(v, h["rel"]), today)
                reals.append(cur[0] if cur else ri.zones.real(v, h["rel"]))
            rank = reals.index(r["expect"]) + 1 if r["expect"] in reals else None
        row = {"id": r["id"], "kind": r["kind"], "sub": r.get("subkind"), "lang": r["lang"], "conf": conf,
               "why": reasons(d), "top_right": r["kind"] == "recall" and top_real == r.get("expect"), "rank": rank,
               **{k: d.get(k) for k in ("top", "floor", "single_floor", "strong", "need", "unknown", "alien", "absent",
                                         "top_words", "unnamed", "single", "margin", "tier")}}
        if conf == "none" and r["kind"] == "recall":
            groups["refused_right" if row["top_right"] else "refused_other"].append(row)
        elif r["kind"] == "recall":
            groups["recall_not_refused"].append(row)
        else:
            groups["quiet_" + ("refused" if conf == "none" else str(conf))].append(row)
    out = {}
    for g, rs in sorted(groups.items()):
        out[g] = {"n": len(rs),
                  "why": dict(collections.Counter("+".join(x["why"]) or "-" for x in rs).most_common()),
                  "only_one": dict(collections.Counter(x["why"][0] for x in rs if len(x["why"]) == 1).most_common()),
                  "strong_need": dict(collections.Counter(f"{x['strong']}/{x['need']}" for x in rs if x["strong"] is not None)),
                  "top_over_floor": sorted(round(x["top"] / x["floor"], 2) for x in rs if x["top"] is not None),
                  "margin": dict(collections.Counter(band(x["margin"]) for x in rs if x["margin"] is not None)),
                  "tier": dict(collections.Counter(x["tier"] for x in rs if x["tier"])),
                  "rank_of_expected": dict(collections.Counter(str(x["rank"]) for x in rs if x["kind"] == "recall"))}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    (tmp / "rows.json").write_text(json.dumps(groups, ensure_ascii=False), encoding="utf-8")
    print("rows:", tmp / "rows.json")
    return 0


START, END = "2026-11-11T00:00:00", "2026-11-13T22:00:00"


def turns():
    for fp in glob.glob(str(Path.home() / ".claude/projects/*/*.jsonl")):
        try:
            if os.stat(fp).st_mtime < datetime(2026, 11, 11, tzinfo=timezone.utc).timestamp():
                continue
        except OSError:
            continue
        try:
            for line in open(fp, encoding="utf-8", errors="replace"):
                if '"user"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                ts = str(r.get("timestamp", ""))
                if r.get("type") != "user" or r.get("isSidechain") or r.get("isMeta") or not (START <= ts[:19] < END):
                    continue
                c = (r.get("message") or {}).get("content")
                if isinstance(c, list):
                    if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                        continue
                    c = "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
                if isinstance(c, str) and c.strip():
                    yield c
        except OSError:
            pass


def real(a) -> int:
    raw_vault = a.vault or os.environ.get("KROUTER_REPLAY_VAULT", "")
    if not raw_vault:
        print("real: no vault given (--vault or KROUTER_REPLAY_VAULT); the replay on this machine's messages is skipped")
        return 0
    VAULT = Path(raw_vault).expanduser()
    tmp = Path(tempfile.mkdtemp(prefix="kr-gate-"))
    (tmp / "state").mkdir()
    (tmp / "cache").mkdir()
    import recall_index

    live = Path(os.environ.get("KROUTER_CACHE_DIR") or Path.home() / ".cache" / "krouter")
    for src in live.glob(recall_index.cache_path(VAULT).name + "*"):  # 只读：复制到临时目录
        shutil.copy(src, tmp / "cache" / src.name)
    os.environ.update(KROUTER_STATE_DIR=str(tmp / "state"), KROUTER_CACHE_DIR=str(tmp / "cache"))
    import subprocess

    subprocess.run([sys.executable, str(SCRIPTS / "recall_index.py"), "--vault", str(VAULT), "--stats"], env=os.environ,
                   capture_output=True)
    import recollect as R
    from krouter_redact import human_words

    ri = diag_module()
    C = collections.Counter()
    held = collections.defaultdict(collections.Counter)
    refused = collections.Counter()
    for raw in turns():
        own = human_words(raw)
        said = R.prose(own) if own else ""
        if not said or len(said) > R.PROSE_MAX:
            continue
        C["matchable"] += 1
        res, d = lookup(ri, R, VAULT, own)
        conf = (res or {}).get("confidence")
        C[f"confidence {conf}"] += 1
        if conf == "none":
            refused["+".join(reasons(d)) or "-"] += 1
            continue
        top = ((res or {}).get("hits") or [None])[0]
        if conf in ("medium", "high") and top and not res.get("partial") and top.get("tier") not in ("log", "dead") \
                and (res.get("margin") or 0) < R.RECALL_MARGIN:
            C["held back by the margin"] += 1
            h = held
            h["tier"][top.get("tier")] += 1
            h["margin"][band(res.get("margin") or 0)] += 1
            h["strong"][str(min(d.get("strong") or 0, 6))] += 1
            h["top_over_floor"]["<2" if d["top"] < 2 * d["floor"] else "2-4" if d["top"] < 4 * d["floor"] else ">=4"] += 1
            h["area"][top["rel"].split("/")[0][:2] if "/" in top["rel"] else "root"] += 1
            h["length"]["<=30" if len(said) <= 30 else "31-100" if len(said) <= 100 else ">100"] += 1
    print(json.dumps({"counts": dict(C), "refused_by_criteria": dict(refused.most_common()),
                      "held_back": {k: dict(v) for k, v in held.items()}}, ensure_ascii=False, indent=1))
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


VARIANTS = {
    "c0": [],
    "no_unknown": [("(unknown and strong <= 2)", "(False and unknown)")],
    "unknown_le1": [("(unknown and strong <= 2)", "(unknown and strong <= 1)")],
    "no_offvault": [("or off_vault or bool(unnamed))", "or bool(unnamed))")],
    "offvault_strict": [("off_vault = absent_words >= 2 and absent_words > top_words",
                         "off_vault = absent_words >= 3 and absent_words > 2 * top_words")],
    "no_both": [("(unknown and strong <= 2)", "(False and unknown)"), ("or off_vault or bool(unnamed))", "or bool(unnamed))")],
}


def variant_module(name: str):
    """recall_index with one gate criterion changed, registered as `recall_index` so the hook (recollect) uses it."""
    src = (SCRIPTS / "recall_index.py").read_text(encoding="utf-8")
    for a, b in VARIANTS[name]:
        assert src.count(a) == 1, a
        src = src.replace(a, b)
    spec = importlib.util.spec_from_loader("recall_index", loader=None)
    mod = importlib.util.module_from_spec(spec)
    mod.__file__ = str(SCRIPTS / "recall_index.py")
    sys.modules["recall_index"] = mod
    exec(compile(src, str(SCRIPTS / "recall_index.py"), "exec"), mod.__dict__)
    return mod


def variant(a) -> int:
    variant_module(a.name)
    import run
    import recollect as R

    tmp = Path(tempfile.mkdtemp())
    os.environ.update(KROUTER_CACHE_DIR=str(tmp / "c"), KROUTER_STATE_DIR=str(tmp / "s"))
    v = run.make_vault(tmp)
    sys.modules["recall_index"].recall(v, "warm up the index")
    out = {}
    for cases in a.cases:
        if cases == "set45dev":
            rows = [json.loads(x) for x in (HERE / "set45_dev.jsonl").read_text(encoding="utf-8").split("\n") if x.strip()]
        elif cases == "set32dev":
            rows = run.cases("dev")
        elif cases == "set32held":
            rows = run.cases("heldout")
        elif cases == "set35dev":
            rows = [json.loads(x) for x in (HERE / "set35_dev.jsonl").read_text(encoding="utf-8").split("\n") if x.strip()]
        else:
            raise SystemExit(cases)
        brought = {r["id"]: R.recollect(v, r["text"], R.DEFAULT_ROUTES) for r in rows}
        s = run.score(rows, brought)
        tot = lambda k: s.get(f"{k}_zh", 0) + s.get(f"{k}_en", 0)  # noqa: E731
        out[cases] = {"recall": f"{tot('recall_right')}/{tot('recall_n')}", "changed": f"{tot('changed_right')}/{tot('changed_n')}",
                      "quiet_loud": f"{tot('quiet_loud')}/{tot('quiet_n')}", "near_topic": s.get("quiet_loud_near_topic", 0),
                      "wrong": tot("wrong"), "old": tot("old"),
                      "loud_kinds": {k[11:]: n for k, n in s.items() if k.startswith("quiet_loud_") and k[11:] not in ("zh", "en")}}
    print(json.dumps({"variant": a.name, **out}, ensure_ascii=False))
    return 0


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("set45dev", "real", "variant"))
    ap.add_argument("--name", default="c0")
    ap.add_argument("--cases", action="append", default=[])
    ap.add_argument("--vault", default="", help="real: the vault to replay against (no default)")
    a = ap.parse_args()
    return {"set45dev": set45dev, "real": real, "variant": variant}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
