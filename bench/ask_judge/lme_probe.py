"""Development probe for set 54 (not a registered run): `KROUTER_ASK_JUDGE` as set 53 ships it, on LongMemEval's
development data only (set 14's `dev` half of the answerable questions and the 30 `_abs` ones, both used for
development before). The held-out half is not touched here.

For each question: KRouter's recall over the question's own vault with the gate off, the first five pages, set 53's
prompt (`ask_reader.prompt`), `deepseek-flash`. The page named goes first; the variant `--keep` then adds KRouter's
other candidates up to three pages (multi-session questions need several sessions), the variant without it cites the
page alone as set 53 does. 0 is a refusal. Scored with `lme.judge` from the authors' labels.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "skill/krouter/scripts"))
sys.path.insert(0, str(HERE))

import ask_judge as bench  # noqa: E402
import ask_reader  # noqa: E402

spec = importlib.util.spec_from_file_location("lme", REPO / "bench/longmemeval/lme.py")
lme = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lme)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="after the page named, KRouter's other candidates up to 3")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--heldout", action="store_true", help="set 54's registered run: the held-out half, once")
    args = ap.parse_args()
    rows = lme.load_questions()
    split = lme.split_of(rows)
    want = ("heldout",) if args.heldout else ("dev", "abs")
    rows = [r for r in rows if split[r["id"]] in want][: args.limit or None]
    reader = bench.Reader(bench.MODEL, bench.URL)
    import recall_index as ri

    prompts, cands = {}, {}
    with tempfile.TemporaryDirectory(prefix="krouter-lme54-") as tmp:
        os.environ["KROUTER_NO_QUERY_LOG"] = "1"
        for it in rows:
            os.environ["KROUTER_CACHE_DIR"] = str(Path(tmp) / it["id"])
            v = Path(it["vault"])
            c = [h["rel"] for h in ri.recall(v, it["q"], "", gate=False)["hits"]][: ask_reader.K]
            cands[it["id"]] = c
            if c:
                prompts[it["id"]] = ask_reader.prompt(it["q"], v, c)
    with ThreadPoolExecutor(8) as ex:
        replies = dict(zip(prompts, ex.map(reader, prompts.values())))
    shipped = {a["id"]: a for a in map(json.loads, (lme.STATE / "outputs.krouter.jsonl").read_text().splitlines())}
    outs, base = [], []
    for it in rows:
        c = cands[it["id"]]
        got = ask_reader.pick(replies.get(it["id"], {}).get("reply", ""), len(c))
        res = ask_reader.outcome(Path(it["vault"]), [{"rel": x} for x in c], got) if c else None
        if res is None:  # 照没开开关时查：KRouter 自己的答案
            outs.append(lme.judge(it, shipped[it["id"]]))
        else:
            outs.append(lme.judge(it, {"cited": [h["rel"] for h in res][:3], "refused": not res}))
        base.append(lme.judge(it, shipped[it["id"]]))
    tag = "set 54 engine"
    print("pages named per answered question:", round(sum(len(x) for x in [ask_reader.pick(replies.get(i, {}).get("reply", ""), 5) for i in prompts] if x) / max(1, sum(1 for i in prompts if ask_reader.pick(replies.get(i, {}).get("reply", ""), 5))), 2))
    for name, o in (("shipped KRouter (3 pages)", base), (f"engine reader, {tag}", outs)):
        print(name, {m: "{}/{}".format(*lme.rate(o, *spec)) for m, spec in lme.METRICS.items()})
    print("calls made:", reader.spent, "| questions:", len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
