#!/usr/bin/env python3
"""Public benchmark for "mention it and it comes to mind": give a system a message and a small knowledge base, ask which
pages it hands over (none = stays quiet), and score it the way set 45 was registered
(bench/memory_honesty/HELDOUT.md, "Set 45"). No model, no network, no key; standard library only.

    python3 bench/subconscious/public/score.py --adapter krouter-hook                 # the registered development half
    python3 bench/subconscious/public/score.py --adapter bm25-naive --opt floor=6
    python3 bench/subconscious/public/score.py --adapter my_adapter.py --cases set35dev
    python3 bench/subconscious/public/score.py --adapter bm25-naive --sweep floor=0,2,4,6,8

Without writing Python: `--export DIR` writes the pages (`pages.jsonl`) and the messages (`messages.jsonl`, text only, no
answers); put each message's answer in `answers.jsonl` (one line `{"id": ..., "pages": ["Handbook/X.md", ...]}`, an empty
list for "stayed quiet") and run `--answers answers.jsonl`.

An adapter is a Python file with two functions (see README.md in this folder):

    def setup(pages, **options): ...      # once; pages = [{"path", "title", "text", "status", "names"}, ...]
    def handle(message): return [...]     # the page paths handed over for one message; [] = stays quiet

Cases: the development halves of sets 32, 35 and 45 (`set32dev`, `set35dev`, `set45dev`; default `set45dev`). The held-out
halves are sealed and are not reachable from here: they are used by the maintainer to confirm a result, once, and a
system tuned on a development half has shown nothing about them.

Scoring (unchanged from the registration, and the same code path as `bench/subconscious/run.py`):
  recall case   right = the expected page is among the pages handed over
  changed case  right = the new page is among them (the replaced page handed over is also an old-page delivery)
  quiet case    loud = anything was handed over (counted against it)
  wrong page    any handed-over page other than the expected one, on a recall or changed case
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUB = HERE.parent
REPO = HERE.parents[2]
VAULT = REPO / "bench/memory_honesty/vault3"
ALIASES = SUB / "overlay/canonical_sources.psv"
QUIET_KINDS = ("unrelated", "other_sense", "common_word", "pasted", "near_topic", "ack")
DEV_HALVES = {"set32dev": SUB / "dev.jsonl", "set35dev": SUB / "set35_dev.jsonl", "set45dev": SUB / "set45_dev.jsonl"}
SEALED = ("set32held", "set35held", "set45held", "heldout", "held")


def load_cases(name: str) -> list[dict]:
    if name in SEALED or "held" in name:
        raise SystemExit(f"{name}: the held-out halves are sealed and not part of the public benchmark "
                         f"(they are for the maintainer's one confirming run); use one of {', '.join(DEV_HALVES)}")
    if name not in DEV_HALVES:
        raise SystemExit(f"unknown cases {name!r}; choose from {', '.join(DEV_HALVES)}")
    return [json.loads(l) for l in DEV_HALVES[name].read_text(encoding="utf-8").splitlines() if l.strip()]


def load_pages() -> list[dict]:
    names: dict[str, list[str]] = {}
    for line in ALIASES.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or line.count("|") != 3:
            continue
        _id, ns, src, _anchor = line.split("|")
        names.setdefault(src, []).extend(n.strip() for n in ns.split(";") if n.strip())
    pages = []
    for p in sorted(VAULT.rglob("*.md")):
        rel = p.relative_to(VAULT).as_posix()
        text = p.read_text(encoding="utf-8")
        st = re.search(r"^status:\s*(\S+)", text, re.M)
        ti = re.search(r'^title:\s*"?(.+?)"?\s*$', text, re.M)
        pages.append({"path": rel, "title": ti.group(1) if ti else p.stem, "text": text,
                      "status": st.group(1) if st else "active", "names": names.get(rel, [])})
    return pages


def load_adapter(spec: str):
    path = Path(spec)
    if not path.suffix:
        path = HERE / "adapters" / (spec.replace("-", "_") + ".py")
    if not path.is_file():
        raise SystemExit(f"no adapter at {path}")
    mod_spec = importlib.util.spec_from_file_location("adapter_" + path.stem, path)
    mod = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(mod)
    for fn in ("setup", "handle"):
        if not callable(getattr(mod, fn, None)):
            raise SystemExit(f"{path}: needs a function {fn}()")
    return mod


def parse_opts(items: list[str]) -> dict:
    out: dict = {}
    for it in items or []:
        k, _, v = it.partition("=")
        try:
            out[k] = float(v) if "." in v else int(v)
        except ValueError:
            out[k] = {"true": True, "false": False}.get(v.lower(), v)
    return out


def score(rows: list[dict], given: dict[str, list[str]]) -> dict:
    """Same counting as bench/subconscious/run.py `score`: the registered rules, not changed."""
    out: Counter = Counter()
    for r in rows:
        pages = given[r["id"]]
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
        out[f"wrong_{L}"] += len([p for p in pages if p != r["expect"]])
        if r.get("old") and r["old"] in pages:
            out[f"old_{L}"] += 1
    return dict(out)


def summary(rows: list[dict], given: dict[str, list[str]]) -> dict:
    s = score(rows, given)
    tot = lambda k: s.get(f"{k}_zh", 0) + s.get(f"{k}_en", 0)
    res = {"cases": len(rows),
           "recall": [tot("recall_right"), tot("recall_n")], "changed": [tot("changed_right"), tot("changed_n")],
           "quiet_loud": [tot("quiet_loud"), tot("quiet_n")], "wrong_pages": tot("wrong"), "old_pages": tot("old"),
           "by_language": {L: {"recall": [s.get(f"recall_right_{L}", 0), s.get(f"recall_n_{L}", 0)],
                               "changed": [s.get(f"changed_right_{L}", 0), s.get(f"changed_n_{L}", 0)],
                               "quiet_loud": [s.get(f"quiet_loud_{L}", 0), s.get(f"quiet_n_{L}", 0)],
                               "wrong_pages": s.get(f"wrong_{L}", 0), "old_pages": s.get(f"old_{L}", 0)} for L in ("zh", "en")},
           "quiet_loud_by_kind": {k: [s.get(f"quiet_loud_{k}", 0),
                                      sum(1 for r in rows if r["kind"] == "quiet" and r.get("subkind") == k)]
                                  for k in QUIET_KINDS if any(r["kind"] == "quiet" and r.get("subkind") == k for r in rows)}}
    rec = [r for r in rows if r["kind"] == "recall"]
    if rec and all("named_mech" in r for r in rec):
        for flag, name in ((False, "recall_not_named"), (True, "recall_named")):
            sel = [r for r in rec if r["named_mech"] is flag]
            res[name] = [sum(1 for r in sel if r["expect"] in given[r["id"]]), len(sel)]
    good = tot("recall_right") + tot("changed_right")
    bad = tot("quiet_loud") + tot("wrong")
    res["choice_score"] = good - 3 * bad - 9 * tot("old")
    return res


def show(label: str, res: dict) -> None:
    print(f"{label}: {res['cases']} messages")
    for L in ("zh", "en"):
        b = res["by_language"][L]
        print(f"  {L}: recall {b['recall'][0]}/{b['recall'][1]}  changed {b['changed'][0]}/{b['changed'][1]}  "
              f"quiet-loud {b['quiet_loud'][0]}/{b['quiet_loud'][1]}  wrong {b['wrong_pages']}  old {b['old_pages']}")
    print(f"  all: recall {res['recall'][0]}/{res['recall'][1]}  changed {res['changed'][0]}/{res['changed'][1]}  "
          f"quiet-loud {res['quiet_loud'][0]}/{res['quiet_loud'][1]}  wrong {res['wrong_pages']}  old {res['old_pages']}")
    print("  quiet-loud by kind: " + ", ".join(f"{k}={v[0]}/{v[1]}" for k, v in res["quiet_loud_by_kind"].items()))
    for key, name in (("recall_not_named", "recall that uses none of the page's names"), ("recall_named", "recall that uses a name")):
        if key in res:
            print(f"  {name}: {res[key][0]}/{res[key][1]}")
    print(f"  choice score: right {res['recall'][0] + res['changed'][0]} - 3*(quiet-loud {res['quiet_loud'][0]} + wrong "
          f"{res['wrong_pages']}) - 9*old {res['old_pages']} = {res['choice_score']}")


def run_adapter(spec: str, opts: dict, rows: list[dict], pages: list[dict]) -> dict[str, list[str]]:
    mod = load_adapter(spec)
    mod.setup(pages, **opts)
    try:
        out = {}
        for r in rows:
            got = mod.handle(r["text"])
            if not isinstance(got, (list, tuple)) or not all(isinstance(g, str) for g in got):
                raise SystemExit(f"{spec}: handle() must return a list of page paths (got {got!r})")
            out[r["id"]] = list(dict.fromkeys(got))
        return out
    finally:
        if callable(getattr(mod, "close", None)):
            mod.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--adapter", help="short name (krouter-hook, bm25-naive) or the path of an adapter .py")
    ap.add_argument("--cases", default="set45dev")
    ap.add_argument("--opt", action="append", default=[], help="key=value passed to the adapter's setup()")
    ap.add_argument("--sweep", default="", help="key=v1,v2,... run the adapter once per value and print one line each")
    ap.add_argument("--answers", default="", help="score a JSONL of {id, pages} instead of running an adapter")
    ap.add_argument("--export", default="", help="write pages.jsonl and messages.jsonl for a non-Python system")
    ap.add_argument("--json", action="store_true", help="print the numbers as JSON")
    ap.add_argument("--show", action="store_true", help="list the cases that went wrong (development halves only)")
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):  # messages and --json carry Chinese; a cp1252 console would raise UnicodeEncodeError
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    rows = load_cases(a.cases)
    pages = load_pages()
    if a.export:
        d = Path(a.export)
        d.mkdir(parents=True, exist_ok=True)
        (d / "pages.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in pages), encoding="utf-8")
        (d / "messages.jsonl").write_text("".join(json.dumps({"id": r["id"], "text": r["text"]}, ensure_ascii=False) + "\n"
                                                  for r in rows), encoding="utf-8")
        print(f"wrote {len(pages)} pages and {len(rows)} messages to {d}")
        return 0
    if a.answers:
        given = {json.loads(l)["id"]: json.loads(l)["pages"] for l in Path(a.answers).read_text(encoding="utf-8").splitlines() if l.strip()}
        missing = [r["id"] for r in rows if r["id"] not in given]
        if missing:
            raise SystemExit(f"{len(missing)} messages have no answer, first: {missing[0]}")
        results = [("answers " + a.answers, summary(rows, given), given)]
    else:
        if not a.adapter:
            ap.error("--adapter or --answers is needed")
        opts = parse_opts(a.opt)
        if a.sweep:
            key, _, vals = a.sweep.partition("=")
            runs = [{**opts, key: parse_opts([f"{key}={v}"])[key]} for v in vals.split(",")]
        else:
            runs = [opts]
        results = []
        for o in runs:
            given = run_adapter(a.adapter, o, rows, pages)
            results.append((f"adapter {a.adapter} {o if o else ''}".strip(), summary(rows, given), given))
    if a.json:
        print(json.dumps([{"label": l, **r} for l, r, _ in results], ensure_ascii=False, indent=1))
        return 0
    if a.sweep:
        print(f"cases: {a.cases}   (right = recall + changed; loud = quiet cases that got a page)")
        for label, r, _ in results:
            print(f"  {label}: recall {r['recall'][0]}/{r['recall'][1]}  changed {r['changed'][0]}/{r['changed'][1]}  "
                  f"quiet-loud {r['quiet_loud'][0]}/{r['quiet_loud'][1]}  wrong {r['wrong_pages']}  old {r['old_pages']}  "
                  f"choice {r['choice_score']}")
        return 0
    label, res, given = results[0]
    show(f"{label}  on {a.cases}", res)
    if a.show:
        for r in rows:
            got = given[r["id"]]
            ok = (not got) if r["kind"] == "quiet" else (r["expect"] in got and all(p == r["expect"] for p in got))
            if not ok:
                print(f"x {r['id']} [{r.get('subkind') or r['kind']}] expect={r.get('expect')} got={got}")
                print(f"    {r['text'][:300]!r}")
    print("  cases sha256 (the message texts, in order): "
          + hashlib.sha256("\n".join(r["text"] for r in rows).encode("utf-8")).hexdigest()[:16])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
