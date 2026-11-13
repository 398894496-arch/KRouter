#!/usr/bin/env python3
"""Set 45 (bench/memory_honesty/HELDOUT.md): mention it the way people actually say it.

    python3 bench/subconscious/set45.py split RAW_ZH RAW_EN        # check the writers' files, split, write the two case files
    python3 bench/subconscious/set45.py run CASES [--routes R] [--crowd N] [--show] [--save F] [--sealed]
    python3 bench/subconscious/set45.py compare BASE.jsonl NEW.jsonl CASES

`CASES` is one of set32dev, set32held, set35dev, set35held, set45dev, set45held. `run` calls `recollect.recollect()` on
each message exactly as `session_hook.py prompt` does, on a temporary copy of vault3 with the overlay laid into
`90 系统文件/` (and with `--crowd N` the set 35 distractor topics added). Nothing is sent anywhere and no model is called.
`--sealed` (for a held-out half) saves the pages brought, prints only how many rows and the file's SHA-256, and prints no
score, so a baseline can be stored without anyone reading it. `SET45_SCRIPTS` points at another copy of
`skill/krouter/scripts` (the new configuration being compared with C0).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import random
import re
import sys
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SCRIPTS = Path(os.environ.get("SET45_SCRIPTS") or REPO / "skill/krouter/scripts")
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))
import recollect  # noqa: E402
import run as set32  # noqa: E402

SEED = 20261145
VAULT = REPO / "bench/memory_honesty/vault3"
QUIET_KINDS = ("unrelated", "other_sense", "common_word", "pasted", "near_topic", "ack")
DEV = HERE / "set45_dev.jsonl"
HELD = HERE / "set45_heldout.jsonl.gz"
QUOTA = {"recall": 48, "changed": 24}
BUCKETS = ((30, "<=30"), (100, "31-100"), (500, "101-500"), (2000, "501-2000"))


def read_gz(path: Path) -> list[dict]:
    return [json.loads(l) for l in gzip.decompress(path.read_bytes()).decode("utf-8").splitlines() if l.strip()]


def case_file(name: str) -> list[dict]:
    if name == "set32dev":
        return set32.cases("dev")
    if name == "set32held":
        return set32.cases("heldout")
    if name == "set35dev":
        return [json.loads(l) for l in (HERE / "set35_dev.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if name == "set35held":
        return read_gz(HERE / "set35_heldout.jsonl.gz")
    if name == "set45dev":
        return [json.loads(l) for l in DEV.read_text(encoding="utf-8").splitlines() if l.strip()]
    if name == "set45held":
        return read_gz(HELD)
    raise SystemExit(f"unknown case file {name}")


# ---------- split ----------

def norm(s: str) -> str:
    return "".join(c.lower() for c in unicodedata.normalize("NFKC", s) if not (c.isspace() or unicodedata.category(c).startswith(("P", "S"))))


def alias_names() -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for line in (HERE / "overlay/canonical_sources.psv").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or line.count("|") != 3:
            continue
        _id, names, src, _anchor = line.split("|")
        out[src].extend(n.strip() for n in names.split(";") if n.strip())
    return out


def page_info(rel: str) -> tuple[str, str]:
    p = VAULT / rel
    if not p.is_file():
        return "", ""
    text = p.read_text(encoding="utf-8")
    status = re.search(r"^status:\s*(\S+)", text, re.M)
    title = re.search(r'^title:\s*"?(.+?)"?\s*$', text, re.M)
    return (status.group(1) if status else "active"), (title.group(1) if title else p.stem)


def validate(rows: list[dict]) -> list[str]:
    bad: list[str] = []
    ids = [r.get("id") for r in rows]
    if len(set(ids)) != len(ids):
        bad.append("duplicate ids")
    names = alias_names()
    for r in rows:
        k, sk, e, o = r.get("kind"), r.get("subkind", ""), r.get("expect", ""), r.get("old", "")
        if k not in ("recall", "quiet", "changed") or not isinstance(r.get("text"), str) or not r["text"].strip():
            bad.append(f"{r.get('id')}: kind or text")
            continue
        if k == "quiet":
            if sk not in QUIET_KINDS or e or o:
                bad.append(f"{r['id']}: quiet fields")
            continue
        if sk or not e:
            bad.append(f"{r['id']}: subkind/expect")
            continue
        st, _ = page_info(e)
        if st in ("", "superseded"):
            bad.append(f"{r['id']}: expect is missing or superseded")
        if k == "changed":
            so, _ = page_info(o)
            if so != "superseded":
                bad.append(f"{r['id']}: old is not a superseded page")
            else:
                txt = (VAULT / o).read_text(encoding="utf-8")
                if Path(e).stem not in txt:
                    bad.append(f"{r['id']}: old page does not point at expect")
        elif o:
            bad.append(f"{r['id']}: old on a recall case")
    return bad


def mech_named(r: dict, names: dict[str, list[str]]) -> bool:
    if r["kind"] == "quiet":
        return False
    _st, title = page_info(r["expect"])
    cands = names.get(r["expect"], []) + [title]
    t = norm(r["text"])
    return any(norm(c) and norm(c) in t for c in cands)


def split(raw_zh: Path, raw_en: Path) -> int:
    rows = []
    for f in (raw_zh, raw_en):
        rows += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    bad = validate(rows)
    for lang in ("zh", "en"):
        mine = [r for r in rows if r["lang"] == lang]
        c = Counter(r["kind"] for r in mine)
        qk = Counter(r["subkind"] for r in mine if r["kind"] == "quiet")
        print(f"{lang}: {len(mine)} rows, kinds {dict(c)}, quiet kinds {dict(qk)}")
        for k, n in QUOTA.items():
            if c[k] != n:
                bad.append(f"{lang}: {k} is {c[k]}, not {n}")
        if c["quiet"] != 48 or any(qk[k] != 8 for k in QUIET_KINDS):
            bad.append(f"{lang}: quiet is not 48 = 6 x 8")
        unnamed = sum(1 for r in mine if r["kind"] == "recall" and not r.get("named"))
        print(f"  recall named=false (writer's mark) {unnamed}/48")
        if unnamed < 32:
            bad.append(f"{lang}: fewer than 32 unnamed recall cases")
    if bad:
        print("PROBLEMS:\n  " + "\n  ".join(bad[:40]))
        return 1
    names = alias_names()
    for r in rows:
        r["named_mech"] = mech_named(r, names)
        r["old"] = r.get("old", "")
    strata: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        strata[(r["lang"], r["kind"], r["subkind"], bool(r.get("named")))].append(r)
    rnd = random.Random(SEED)
    dev, held, toggle = [], [], 0
    for key in sorted(strata):
        g = sorted(strata[key], key=lambda r: r["id"])
        rnd.shuffle(g)
        half = len(g) // 2
        dev += g[:half]
        held += g[half:2 * half]
        if len(g) % 2:  # the odd case of each stratum goes to the two sides in turn, strata taken in sorted order
            (dev if toggle % 2 == 0 else held).append(g[-1])
            toggle += 1
    dev.sort(key=lambda r: r["id"])
    held.sort(key=lambda r: r["id"])
    dev_text = "\n".join(json.dumps(r, ensure_ascii=False) for r in dev) + "\n"
    held_text = "\n".join(json.dumps(r, ensure_ascii=False) for r in held) + "\n"
    DEV.write_text(dev_text, encoding="utf-8")
    with open(HELD, "wb") as fh:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0) as gz:
            gz.write(held_text.encode("utf-8"))
    print(f"dev {len(dev)} held-out {len(held)}")
    print(f"held-out text SHA-256 {hashlib.sha256(held_text.encode('utf-8')).hexdigest()}")
    for name, part in (("dev", dev), ("held-out", held)):
        c = Counter((r["lang"], r["kind"]) for r in part)
        print(f"  {name}: {dict(sorted(c.items()))}")
    allr = dev + held
    lens = Counter()
    for r in allr:
        n = len(r["text"])
        lens[next((lab for lim, lab in BUCKETS if n <= lim), ">2000")] += 1
    print("length mix (all 240):", {k: f"{v} ({v * 100 // len(allr)}%)" for k, v in lens.items()})
    rec = [r for r in allr if r["kind"] == "recall"]
    print(f"recall unnamed by writer's mark {sum(1 for r in rec if not r['named'])}/{len(rec)}, by the mechanical check "
          f"{sum(1 for r in rec if not r['named_mech'])}/{len(rec)}")
    return 0


# ---------- run ----------

def run_cases(rows: list[dict], use: tuple[str, ...], crowd: int) -> dict[str, list[dict]]:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["KROUTER_CACHE_DIR"] = str(Path(tmp) / "cache")
        os.environ["KROUTER_STATE_DIR"] = str(Path(tmp) / "state")
        os.environ["KROUTER_NO_QUERY_LOG"] = "1"
        v = set32.make_vault(Path(tmp))
        if crowd:
            import both

            both.add_crowd(v, crowd, newer=False)
        import recall_index

        recall_index.recall(v, "warm up the index")
        return {r["id"]: recollect.recollect(v, r["text"], use) for r in rows}


def report(rows: list[dict], brought: dict[str, list[dict]], label: str) -> None:
    s = set32.score(rows, brought)
    tot = lambda k: s.get(f"{k}_zh", 0) + s.get(f"{k}_en", 0)
    print(f"{label}  cases: {len(rows)}")
    for L in ("zh", "en"):
        print(f"  {L}: recall {s.get(f'recall_right_{L}', 0)}/{s.get(f'recall_n_{L}', 0)}  "
              f"changed {s.get(f'changed_right_{L}', 0)}/{s.get(f'changed_n_{L}', 0)}  "
              f"quiet-loud {s.get(f'quiet_loud_{L}', 0)}/{s.get(f'quiet_n_{L}', 0)}  wrong {s.get(f'wrong_{L}', 0)}  "
              f"old {s.get(f'old_{L}', 0)}")
    print(f"  all: recall {tot('recall_right')}/{tot('recall_n')}  changed {tot('changed_right')}/{tot('changed_n')}  "
          f"quiet-loud {tot('quiet_loud')}/{tot('quiet_n')}  wrong {tot('wrong')}  old {tot('old')}")
    kinds = [k for k in QUIET_KINDS if any(r["kind"] == "quiet" and r.get("subkind") == k for r in rows)]
    print("  quiet-loud by kind: " + ", ".join(f"{k}={s.get('quiet_loud_' + k, 0)}/{sum(1 for r in rows if r['kind'] == 'quiet' and r['subkind'] == k)}" for k in kinds))
    rec = [r for r in rows if r["kind"] == "recall"]
    if rec and "named_mech" in rec[0]:
        for flag, name in ((False, "not named (mechanical)"), (True, "named (mechanical)")):
            sel = [r for r in rec if r["named_mech"] is flag]
            ok = sum(1 for r in sel if r["expect"] in [h["real"] for h in brought[r["id"]]])
            print(f"  recall {name}: {ok}/{len(sel)}")
    routes = Counter(h["route"] for r in rows for h in brought[r["id"]])
    print(f"  pages brought by route: {dict(routes)}")
    good = tot("recall_right") + tot("changed_right")
    bad = tot("quiet_loud") + tot("wrong")
    print(f"  choice score: {good} - 3*{bad} - 9*{tot('old')} = {good - 3 * bad - 9 * tot('old')}")


def run(args: argparse.Namespace) -> int:
    rows = case_file(args.cases)
    held = args.cases.endswith("held")
    if args.show and held:
        raise SystemExit("--show is for development halves only")
    if args.sealed and not held:
        raise SystemExit("--sealed is for held-out halves")
    use = tuple(r for r in args.routes.split(",") if r) if args.routes else recollect.DEFAULT_ROUTES
    brought = run_cases(rows, use, args.crowd)
    if args.save:
        with open(args.save, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps({"id": r["id"], "brought": [h["real"] for h in brought[r["id"]]],
                                     "routes": [h["route"] for h in brought[r["id"]]]}, ensure_ascii=False) + "\n")
    if args.sealed:
        sha = hashlib.sha256(Path(args.save).read_bytes()).hexdigest() if args.save else ""
        print(f"sealed: {len(rows)} rows saved, SHA-256 {sha}; no score printed")
        return 0
    report(rows, brought, f"routes: {','.join(use)}  cases: {args.cases}  crowd: {args.crowd}")
    if args.show:
        for r in rows:
            got = [h["real"] for h in brought[r["id"]]]
            ok = (not got) if r["kind"] == "quiet" else (r["expect"] in got and all(p == r["expect"] for p in got))
            if not ok:
                print(f"x {r['id']} [{r.get('subkind') or r['kind']}] expect={r.get('expect')} got={got}")
                print(f"    {r['text'][:300]!r}")
                for h in brought[r["id"]]:
                    print(f"    via {h['route']} {h['word']!r}")
    return 0


def compare(args: argparse.Namespace) -> int:
    rows = {r["id"]: r for r in case_file(args.cases)}
    a = {json.loads(l)["id"]: json.loads(l)["brought"] for l in Path(args.base).read_text(encoding="utf-8").splitlines() if l.strip()}
    b = {json.loads(l)["id"]: json.loads(l)["brought"] for l in Path(args.new).read_text(encoding="utf-8").splitlines() if l.strip()}
    gain = lost = same = diff_loud = 0
    for i, r in rows.items():
        if r["kind"] == "quiet":
            if bool(a[i]) != bool(b[i]):
                diff_loud += 1
            continue
        ra, rb = r["expect"] in a[i], r["expect"] in b[i]
        gain += (not ra) and rb
        lost += ra and not rb
        same += a[i] == b[i]
    print(f"right gained {gain}, right lost {lost}; quiet cases whose silence changed {diff_loud}; "
          f"cases with identical pages brought {same}/{len(rows)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("split")
    s.add_argument("raw_zh", type=Path)
    s.add_argument("raw_en", type=Path)
    r = sub.add_parser("run")
    r.add_argument("cases")
    r.add_argument("--routes", default="")
    r.add_argument("--crowd", type=int, default=0)
    r.add_argument("--show", action="store_true")
    r.add_argument("--save", default="")
    r.add_argument("--sealed", action="store_true")
    c = sub.add_parser("compare")
    c.add_argument("base")
    c.add_argument("new")
    c.add_argument("cases")
    a = ap.parse_args()
    if a.cmd == "split":
        return split(a.raw_zh, a.raw_en)
    if a.cmd == "run":
        return run(a)
    return compare(a)


if __name__ == "__main__":
    raise SystemExit(main())
