#!/usr/bin/env python3
"""Set 32 (bench/memory_honesty/HELDOUT.md): does the prompt hook bring the right page, and only then?

    python3 bench/subconscious/run.py dev [--routes alias,trigger] [--show]
    python3 bench/subconscious/run.py heldout [--save brought.jsonl]     # run once

Each case is one message. `recollect.recollect()` is called on it exactly as `session_hook.py prompt` calls it, on a
temporary copy of `bench/memory_honesty/vault3` with `overlay/` laid into `90 系统文件/`. Scored mechanically: recall
case right = expected page brought, any other page = a wrong page; changed case right = new page brought, the old
page brought = a wrong page and an old-page delivery; quiet case = anything brought counts against it.
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "skill/krouter/scripts"))
import recollect  # noqa: E402

VAULT = REPO / "bench/memory_honesty/vault3"


def make_vault(root: Path) -> Path:
    v = root / "vault"
    shutil.copytree(VAULT, v)
    (v / "90 系统文件/自动化").mkdir(parents=True)
    shutil.copy(HERE / "overlay/canonical_sources.psv", v / "90 系统文件/canonical_sources.psv")
    for f in HERE.glob("overlay/下意识触发词*.psv"):
        shutil.copy(f, v / "90 系统文件/自动化" / f.name)
    return v


def cases(split: str) -> list[dict]:
    if split == "dev":
        text = (HERE / "dev.jsonl").read_text(encoding="utf-8")
    else:
        text = gzip.decompress((HERE / "heldout.jsonl.gz").read_bytes()).decode("utf-8")
    return [json.loads(l) for l in text.splitlines() if l.strip()]


def score(rows: list[dict], brought: dict[str, list[dict]]) -> dict:
    out: Counter = Counter()
    for r in rows:
        pages = [h["real"] for h in brought[r["id"]]]
        L = r["lang"]
        if r["kind"] == "quiet":
            out[f"quiet_n_{L}"] += 1
            if pages:
                out[f"quiet_loud_{L}"] += 1
                out[f"quiet_loud_{r['subkind']}"] += 1
            continue
        out[f"{r['kind']}_n_{L}"] += 1
        if r["expect"] in pages:
            out[f"{r['kind']}_right_{L}"] += 1
        wrong = [p for p in pages if p != r["expect"]]
        out[f"wrong_{L}"] += len(wrong)
        if r.get("old") and r["old"] in pages:
            out[f"old_{L}"] += 1
    return dict(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("split", choices=["dev", "heldout"])
    ap.add_argument("--routes", default="")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--save", default="")
    args = ap.parse_args()
    if args.show and args.split != "dev":
        ap.error("--show is for development only")
    use = tuple(r for r in args.routes.split(",") if r) if args.routes else recollect.DEFAULT_ROUTES
    rows = cases(args.split)
    with tempfile.TemporaryDirectory() as tmp:
        import os

        os.environ["KROUTER_CACHE_DIR"] = str(Path(tmp) / "cache")
        os.environ["KROUTER_STATE_DIR"] = str(Path(tmp) / "state")
        os.environ["KROUTER_NO_QUERY_LOG"] = "1"
        v = make_vault(Path(tmp))
        import recall_index

        recall_index.recall(v, "warm up the index")  # 真实环境里索引由路由、MCP、夜间任务建好；钩子从不自己建
        brought = {r["id"]: recollect.recollect(v, r["text"], use) for r in rows}
        notes = {r["id"]: recollect.render(brought[r["id"]]) for r in rows}
    s = score(rows, brought)
    if args.show:
        for r in rows:
            got = [h["real"] for h in brought[r["id"]]]
            ok = (not got) if r["kind"] == "quiet" else (r["expect"] in got and all(p == r["expect"] for p in got))
            if not ok:
                print(f"✗ {r['id']} [{r['subkind'] or r['kind']}] expect={r['expect']} got={got}")
                print(f"    {r['text'][:300]!r}")
                for h in brought[r["id"]]:
                    print(f"    via {h['route']} 「{h['word']}」")
    if args.save:
        with open(args.save, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps({"id": r["id"], "brought": [h["real"] for h in brought[r["id"]]],
                                     "note": notes[r["id"]]}, ensure_ascii=False) + "\n")
    tot = lambda k: s.get(f"{k}_zh", 0) + s.get(f"{k}_en", 0)
    print(f"routes: {','.join(use)}  split: {args.split}  cases: {len(rows)}")
    for L in ("zh", "en"):
        print(f"  {L}: recall {s.get(f'recall_right_{L}', 0)}/{s.get(f'recall_n_{L}', 0)}  "
              f"changed {s.get(f'changed_right_{L}', 0)}/{s.get(f'changed_n_{L}', 0)}  "
              f"quiet-loud {s.get(f'quiet_loud_{L}', 0)}/{s.get(f'quiet_n_{L}', 0)}  wrong {s.get(f'wrong_{L}', 0)}  "
              f"old {s.get(f'old_{L}', 0)}")
    print(f"  all: recall {tot('recall_right')}/{tot('recall_n')}  changed {tot('changed_right')}/{tot('changed_n')}  "
          f"quiet-loud {tot('quiet_loud')}/{tot('quiet_n')}  wrong {tot('wrong')}  old {tot('old')}")
    print("  quiet-loud by kind: " + ", ".join(f"{k}={s.get('quiet_loud_' + k, 0)}"
                                              for k in ("unrelated", "other_sense", "common_word", "pasted")))
    good = tot("recall_right") + tot("changed_right")
    bad = tot("quiet_loud") + tot("wrong")
    print(f"  choice score: {good} - 3*{bad} = {good - 3 * bad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
