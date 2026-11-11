#!/usr/bin/env python3
"""Set 39 (bench/memory_honesty/HELDOUT.md): paragraph-level evidence — does it hand over more answers and refuse more
of what the memory does not hold, both at once?

No model is called. Every lookup is KRouter's recall with `KROUTER_EVIDENCE_STUDY=1`, which adds to the result the
first 20 ranked pages (before the gate) with their paragraph evidence (`evidence.page_evidence`). The rules are then
applied offline to those records (`simulate`), and the one chosen on development data is built in and run again.

    python3 bench/evidence/study.py collect dev            # development data (LongMemEval dev half, its 30 `_abs`
                                                           #   and the dev half with answer sessions removed; LoCoMo's
                                                           #   dev half; memory-honesty dev, dev2, dev3; synthetic)
    python3 bench/evidence/study.py signals dev            # each signal's separation on development data
    python3 bench/evidence/study.py heldout                # the held-out halves, once, with the code as built
    python3 bench/evidence/study.py report TAG             # the registered counts for one collected run

State: `~/.local/state/krouter-eval/engine/` (`KROUTER_ENGINE_STATE`); the index cache persists there between runs
(one per vault, rebuilt when the schema changes). Sources are bench/refusal/study.py's, unchanged.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STATE = Path(os.environ.get("KROUTER_ENGINE_STATE") or Path.home() / ".local/state/krouter-eval/engine")


def _refusal_study():
    spec = importlib.util.spec_from_file_location("refusal_study", REPO / "bench/refusal/study.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(REPO / "bench/refusal"))
    spec.loader.exec_module(mod)
    return mod


RS = _refusal_study()


def lme_dates() -> dict[str, str]:
    return {r["id"]: r.get("date", "") for r in RS.lme_rows()}


DEV = {
    "lme_abs": lambda: RS.lme_items("abs"),
    "lme_dev": lambda: RS.lme_items("dev"),
    "lme_ablated_dev": lambda: RS.lme_ablated("dev"),
    "locomo_dev": lambda: RS.locomo_items("dev"),
    "mh_dev": lambda: RS.mh_items("dev"),
    "mh_dev2": lambda: RS.mh_items("dev2"),
    "mh_dev3": lambda: RS.mh_items("dev3"),
    "synthetic": RS.synthetic_items,
}
HELD = {
    "lme_heldout": lambda: RS.lme_items("heldout"),
    "lme_ablated_heldout": lambda: RS.lme_ablated("heldout"),
    "locomo_heldout": lambda: RS.locomo_items("heldout"),
    "mh_heldout": lambda: RS.mh_items("heldout"),
    "mh_heldout2": lambda: RS.mh_items("heldout2"),
    "mh_heldout3": lambda: RS.mh_items("heldout3"),
}


def own_code() -> bool:
    """Whether the lookups run this checkout's code (not a baseline unpacked with `git archive`, set with
    KROUTER_REFUSAL_SCRIPTS)."""
    return Path(RS.SCRIPTS).resolve() == (REPO / "skill/krouter/scripts").resolve()


def _env() -> None:
    os.environ["KROUTER_NO_QUERY_LOG"] = "1"
    os.environ["KROUTER_CACHE_DIR"] = str(STATE / ("cache" if own_code() else "cache-baseline"))
    os.environ["KROUTER_STATE_DIR"] = str(STATE / "state")
    os.environ["KROUTER_EVIDENCE_STUDY"] = "1"
    os.environ.pop("KROUTER_MAP", None)
    sys.path.insert(0, str(RS.SCRIPTS))


def lookup(ri, it: dict, dates: dict) -> dict:
    day = dates.get(it["id"], "")
    if day:
        os.environ["KROUTER_TODAY"] = day
    else:
        os.environ.pop("KROUTER_TODAY", None)
    t0 = time.perf_counter()
    res = ri.recall(Path(it["vault"]), it["q"])
    ms = (time.perf_counter() - t0) * 1000
    refused = res["confidence"] == "none" or not res["hits"]
    rec = {k: v for k, v in it.items() if k != "vault"}
    rec.update({"vault": it["vault"], "conf": res["confidence"], "refused": refused,
                "cited": [] if refused else [h["rel"] for h in res["hits"][:3]],
                "handed": [] if refused else [h["rel"] for h in res["hits"]] + [p["rel"] for p in res.get("assoc") or []]
                + [h["rel"] for h in res.get("more") or []],
                "ev1": (res["hits"][0].get("ev") if res["hits"] else None), "partial": bool(res.get("partial")),
                "study": res.get("study"), "ms": round(ms, 1), "kb": [h["rel"] for h in res.get("kb") or []]})
    if hasattr(ri, "kb_only"):
        rec["memory_none_first"] = ri.kb_only(res)
    return rec


def collect(which: dict, tag: str) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    _env()
    import recall_index as ri

    dates = lme_dates()
    for name, make in which.items():
        items = make()
        recs = []
        for i, it in enumerate(items):
            recs.append(lookup(ri, it, dates))
            if i % 250 == 249:
                print(f"{tag}.{name}: {i + 1}/{len(items)}", file=sys.stderr, flush=True)
        (STATE / f"{tag}.{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs),
                                                   encoding="utf-8")
        print(json.dumps(summary(recs, name)), file=sys.stderr, flush=True)


def load(tag: str, name: str) -> list[dict]:
    return [json.loads(x) for x in (STATE / f"{tag}.{name}.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]


def handed_right(rec: dict) -> bool:
    """Set 38's count: an answerable question whose labelled page is among the three cited, state not `none`."""
    return rec["answerable"] and not rec["refused"] and bool(set(rec["cited"]) & set(rec["gold"]))


def wrong_cite(rec: dict) -> bool:
    """Memory honesty: an answer whose first page is not the labelled one (refusals and right answers are not)."""
    if rec["refused"]:
        return False
    return not rec["gold"] or rec["cited"][:1] != rec["gold"][:1]


def summary(recs: list[dict], name: str) -> dict:
    un = [r for r in recs if not r["answerable"]]
    an = [r for r in recs if r["answerable"]]
    out = {"source": name, "unanswerable_none": f"{sum(r['refused'] for r in un)}/{len(un)}",
           "answerable_handed": f"{sum(handed_right(r) for r in an)}/{len(an)}",
           "answerable_none": f"{sum(r['refused'] for r in an)}/{len(an)}"}
    out["all_labelled_handed"] = sum(r["answerable"] and not r["refused"] and bool(r["gold"]) and
                                     set(r["gold"]) <= set(r.get("handed") or []) for r in an)
    out["pages_handed"] = sum(len(r.get("handed") or []) for r in recs if not r["refused"])
    if name.startswith("mh_"):
        out["wrong_cite"] = sum(wrong_cite(r) for r in recs)
        out["gold_first"] = f"{sum(r['answerable'] and not r['refused'] and r['cited'][:1] == r['gold'][:1] for r in an)}/{len(an)}"
    return out


def report(tag: str) -> dict:
    out = {}
    for path in sorted(STATE.glob(f"{tag}.*.jsonl")):
        name = path.name[len(tag) + 1:-6]
        out[name] = summary(load(tag, name), name)
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "collect":
        which = {"dev": DEV, "heldout": HELD}[argv[1]]
        only = set(argv[3:]) if len(argv) > 3 else None
        tag = argv[2] if len(argv) > 2 else argv[1]
        if argv[1] == "heldout" and own_code():  # 基线代码（44c041f）在留出部分上数一遍不算打开：它不调任何参数
            marker = STATE / "heldout.opened"
            why = os.environ.get("KROUTER_HELDOUT_REASON", "").strip()
            if marker.exists() and not why:
                raise SystemExit(f"held-out halves already run ({marker.read_text().strip()}); a later run needs "
                                 "KROUTER_HELDOUT_REASON (logged next to the first, and said in HELDOUT.md)")
            with marker.open("a", encoding="utf-8") as fh:
                fh.write(time.strftime("%Y-%m-%dT%H:%M:%S") + f" {tag} evidence={os.environ.get('KROUTER_EVIDENCE', '')}"
                         + (f" reason: {why}" if why else "") + "\n")
        collect({k: v for k, v in which.items() if not only or k in only}, tag)
        return 0
    if argv[0] == "report":
        print(json.dumps(report(argv[1]), ensure_ascii=False, indent=1))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
