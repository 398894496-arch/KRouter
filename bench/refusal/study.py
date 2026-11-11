#!/usr/bin/env python3
"""Set 37 (bench/memory_honesty/HELDOUT.md): can a coverage rule turn more "the memory does not have this" questions into
`recall: none`, without refusing questions the memory can answer?

No model is called. For every question it runs KRouter's recall as shipped (the gate, then the memory's pages) and,
when the gate answers, the deterministic coverage signals of `recall_index.coverage_signals` on the pages it gave.
A candidate rule ("also refuse when ...") can only turn an answer into a refusal.

    python3 bench/refusal/study.py collect          # development data only; ~10 minutes
    python3 bench/refusal/study.py rules            # every registered candidate on development data
    python3 bench/refusal/study.py heldout RULE     # the held-out halves, once, for the one rule chosen on dev
    python3 bench/refusal/study.py synthetic        # (A): the synthetic set, the knowledge-base layer as shipped
    python3 bench/refusal/study.py states           # set 38: the three states and strict mode, counted

Development data: LongMemEval's 30 `_abs` questions (seen in sets 7 and 14), the LongMemEval dev half (set 14's
split) and the same half with its answer sessions removed, LoCoMo's dev half (seed 20261110 over question ids,
adversarial and answerable drawn separately), and the memory-honesty sets `dev`, `dev2`, `dev3`. Held out: the other
halves of LongMemEval and LoCoMo, `heldout`, `heldout2`, `heldout3`, and the synthetic set (`synthetic.jsonl` here).

State: `~/.local/state/krouter-eval/kb-refusal/` (`KROUTER_REFUSAL_STATE`). LongMemEval's converted vaults are read
from `KROUTER_LME_STATE` (default `~/.local/state/krouter-eval/lme`), never written; LoCoMo's from
`KROUTER_LOCOMO_STATE` (run `bench/locomo/locomo.py convert` with it set first).
"""

from __future__ import annotations

import gzip
import json
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
# 对比旧版本时指向另一份代码（`git archive <commit> skill/krouter/scripts` 解出来的目录）
SCRIPTS = Path(os.environ.get("KROUTER_REFUSAL_SCRIPTS") or REPO / "skill/krouter/scripts")
STATE = Path(os.environ.get("KROUTER_REFUSAL_STATE") or Path.home() / ".local/state/krouter-eval/kb-refusal")
LME_STATE = Path(os.environ.get("KROUTER_LME_STATE") or Path.home() / ".local/state/krouter-eval/lme")
LOCOMO_STATE = Path(os.environ.get("KROUTER_LOCOMO_STATE") or STATE / "locomo")
SEED = 20261110
MH = REPO / "bench/memory_honesty"

# 候选规则在看任何开发数据之前就定下（HELDOUT.md 第 37 套）：一个信号或两个信号同时成立，只在门槛放行时才可能改成拒答
THRESH = {"cov3": (0.4, 0.5, 0.6, 0.7), "cov1": (0.4, 0.5, 0.6), "line_cov": (0.3, 0.4, 0.5)}
FLAGS = ("rare_miss1", "rare_miss3", "bind_fail")
CONF_GATES = ("any", "not_high")


def candidates() -> dict[str, list[tuple]]:
    """{name: [(signal, threshold or None), ...], conf gate}: one-signal rules and every two-signal AND."""
    singles = [((f, None),) for f in FLAGS] + [((k, t),) for k, ts in THRESH.items() for t in ts]
    singles += [(("unseen", 2),), (("nabsent", 1),)]
    rules = {}
    for gate in CONF_GATES:
        for r in singles:
            rules[f"{gate}:" + "&".join(f"{n}" + ("" if t is None else f"<{t}" if n in THRESH else f">={t}")
                                         for n, t in r)] = (list(r), gate)
        for i, a in enumerate(singles):
            for b in singles[i + 1:]:
                if a[0][0] == b[0][0]:
                    continue
                r = list(a) + list(b)
                rules[f"{gate}:" + "&".join(f"{n}" + ("" if t is None else f"<{t}" if n in THRESH else f">={t}")
                                             for n, t in r)] = (r, gate)
    return rules


def fires(rule: tuple, rec: dict) -> bool:
    conds, gate = rule
    if rec["refused"] or not rec.get("sig"):
        return False
    if gate == "not_high" and rec["conf"] == "high":
        return False
    sig = rec["sig"]
    for name, t in conds:
        v = sig.get(name)
        if v is None:
            return False
        if name in FLAGS and not v:
            return False
        if name in THRESH and not v < t:
            return False
        if name in ("unseen", "nabsent") and not v >= t:
            return False
    return True


# ---------- one lookup ----------

def lookup(ri, vault: Path, q: str) -> dict:
    res = ri.recall(vault, q)
    refused = res["confidence"] == "none" or not res["hits"]
    rec = {"conf": res["confidence"], "refused": refused, "cited": [] if refused else [h["rel"] for h in res["hits"][:3]],
           "kb": [h["rel"] for h in res.get("kb") or []]}
    if not refused and hasattr(ri, "coverage_signals"):
        con = ri.connect(ri.cache_path(vault))
        try:
            sig = ri.coverage_signals(con, vault, q, [h["rel"] for h in res["hits"]])
        finally:
            con.close()
        sig["unseen"] = len(ri.unseen_words(vault, res, q))
        rec["sig"] = sig
    if hasattr(ri, "kb_only"):
        rec["memory_none_first"] = ri.kb_only(res)
    return rec


def _env(tmp: Path) -> None:
    os.environ["KROUTER_NO_QUERY_LOG"] = "1"
    os.environ["KROUTER_CACHE_DIR"] = str(tmp / "cache")
    os.environ.pop("KROUTER_MAP", None)
    sys.path.insert(0, str(SCRIPTS))


def run_items(items: list[dict], label: str) -> list[dict]:
    """items: {id, q, vault, ...}; vaults are read in place (the cache goes to a temporary folder)."""
    out = []
    with tempfile.TemporaryDirectory(prefix="krouter-refusal-") as tmp:
        _env(Path(tmp))
        import recall_index as ri

        last = None
        for i, it in enumerate(items):
            if last is not None and last != it["vault"]:
                for f in (Path(tmp) / "cache").glob("recall-*"):
                    f.unlink(missing_ok=True)
            last = it["vault"]
            out.append({**{k: v for k, v in it.items() if k not in ("q",)}, **lookup(ri, Path(it["vault"]), it["q"])})
            if i % 200 == 199:
                print(f"{label}: {i + 1}/{len(items)}", file=sys.stderr)
    return out


# ---------- sources ----------

def lme_rows() -> list[dict]:
    return [json.loads(x) for x in (LME_STATE / "questions.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]


def lme_split(rows: list[dict]) -> dict[str, str]:
    ids = sorted(r["id"] for r in rows if not r["abs"])  # 与 lme.split_of 相同（第 14、18 套）
    dev = set(random.Random(SEED).sample(ids, len(ids) // 2))
    return {r["id"]: "abs" if r["abs"] else ("dev" if r["id"] in dev else "heldout") for r in rows}


def lme_items(part: str) -> list[dict]:
    rows = lme_rows()
    split = lme_split(rows)
    out = []
    for r in rows:
        if split[r["id"]] != part:
            continue
        answer = set(r["answer_sessions"])
        gold = sorted(p for p, m in r["pages"].items() if m["sid"] in answer)
        out.append({"id": r["id"], "q": r["q"], "vault": r["vault"], "answerable": not r["abs"], "gold": gold})
    return out


def lme_ablated(part: str) -> list[dict]:
    """The half's answerable questions with every labelled answer session removed (set 14's `make_ablated`), copied
    into this study's own state folder."""
    base = STATE / "lme-ablated"
    out = []
    for it in lme_items(part):
        dst = base / it["id"]
        if not dst.exists():
            shutil.copytree(it["vault"], dst)
            for rel in it["gold"]:
                (dst / rel).unlink(missing_ok=True)
        out.append({"id": it["id"], "q": it["q"], "vault": str(dst), "answerable": False, "gold": []})
    return out


def locomo_items(part: str) -> list[dict]:
    rows = [json.loads(x) for x in (LOCOMO_STATE / "questions.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    rng = random.Random(SEED)
    adv = sorted(r["id"] for r in rows if r["abs"])
    ans = sorted(r["id"] for r in rows if not r["abs"] and r["evidence_sessions"])
    dev = set(rng.sample(adv, len(adv) // 2)) | set(rng.sample(ans, len(ans) // 2))
    out = []
    for r in rows:
        if not r["abs"] and not r["evidence_sessions"]:
            continue
        if (r["id"] in dev) != (part == "dev"):
            continue
        gold = sorted(p for p, n in r["pages"].items() if n in set(r["evidence_sessions"]))
        out.append({"id": r["id"], "q": r["q"], "vault": r["vault"], "answerable": not r["abs"], "gold": gold,
                    "category": r["category"]})
    out.sort(key=lambda x: (x["vault"], x["id"]))
    return out


def mh_items(name: str) -> list[dict]:
    sys.path.insert(0, str(MH))
    import run as mh

    vault = STATE / "mh-vaults" / name
    if not vault.exists():
        shutil.copytree(mh.vault_of(name), vault)
    return [{"id": it["id"], "q": it["q"], "vault": str(vault), "answerable": it["kind"] != "refuse",
             "gold": [it["gold"]] if it.get("gold") else [], "kind": it["kind"]} for it in mh.questions(name)]


def synthetic_items() -> list[dict]:
    import synthetic  # noqa: E402  bench/refusal/synthetic.py

    return synthetic.items(STATE / "synthetic")


def right(rec: dict) -> bool:
    """An answerable question the shipped gate answers with a labelled page: first (memory honesty) or in the top 3."""
    if rec["refused"] or not rec["answerable"]:
        return False
    if "kind" in rec:
        return bool(rec["cited"]) and rec["cited"][0] in rec["gold"]
    return bool(set(rec["cited"]) & set(rec["gold"]))


DEV = {
    "lme_abs": lambda: lme_items("abs"),
    "lme_dev": lambda: lme_items("dev"),
    "lme_ablated_dev": lambda: lme_ablated("dev"),
    "locomo_dev": lambda: locomo_items("dev"),
    "mh_dev": lambda: mh_items("dev"),
    "mh_dev2": lambda: mh_items("dev2"),
    "mh_dev3": lambda: mh_items("dev3"),
}
HELD = {
    "lme_heldout": lambda: lme_items("heldout"),
    "lme_ablated_heldout": lambda: lme_ablated("heldout"),
    "locomo_heldout": lambda: locomo_items("heldout"),
    "mh_heldout": lambda: mh_items("heldout"),
    "mh_heldout2": lambda: mh_items("heldout2"),
    "mh_heldout3": lambda: mh_items("heldout3"),
    "synthetic": synthetic_items,
}


def collect(which: dict, tag: str) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    for name, make in which.items():
        path = STATE / f"{tag}.{name}.jsonl"
        recs = run_items(make(), name)
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
        print(json.dumps(summary(recs, name)), file=sys.stderr)


def load(tag: str, name: str) -> list[dict]:
    path = STATE / f"{tag}.{name}.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def summary(recs: list[dict], name: str) -> dict:
    un = [r for r in recs if not r["answerable"]]
    an = [r for r in recs if r["answerable"]]
    return {"source": name, "unanswerable_refused": f"{sum(r['refused'] for r in un)}/{len(un)}",
            "answerable_right": f"{sum(right(r) for r in an)}/{len(an)}",
            "answerable_refused": f"{sum(r['refused'] for r in an)}/{len(an)}"}


def effect(rule: tuple, recs: list[dict]) -> dict:
    """What one rule changes on one source: unanswerable questions newly refused, right answers lost, any answers
    refused."""
    un = [r for r in recs if not r["answerable"]]
    an = [r for r in recs if r["answerable"]]
    return {"un_gain": sum(fires(rule, r) for r in un), "un_n": len(un),
            "un_now": sum(r["refused"] for r in un),
            "right_lost": sum(fires(rule, r) for r in an if right(r)), "right_now": sum(right(r) for r in an),
            "ans_refused": sum(fires(rule, r) for r in an), "an_n": len(an)}


# 开发部分的过关线（第 37 套登记时定死）：可答题命中每一组最多掉 1 个百分点，自家各组一题不掉；不可答题净多拒的要明显
def passes_dev(eff: dict[str, dict]) -> bool:
    for name, e in eff.items():
        if name.startswith("mh_"):
            if e["right_lost"] > 0:
                return False
        elif e["right_now"] and e["right_lost"] > 0.01 * e["an_n"]:
            return False
    gain = sum(e["un_gain"] for n, e in eff.items() if n in ("lme_abs", "locomo_dev"))
    return gain >= 10


def rules_report() -> dict:
    recs = {name: load("dev", name) for name in DEV}
    base = {name: summary(r, name) for name, r in recs.items()}
    rows = []
    for name, rule in candidates().items():
        eff = {src: effect(rule, r) for src, r in recs.items()}
        rows.append({"rule": name, "passes": passes_dev(eff),
                     "un_gain": {s: e["un_gain"] for s, e in eff.items() if e["un_n"]},
                     "right_lost": {s: e["right_lost"] for s, e in eff.items() if e["an_n"]},
                     "ans_refused": {s: e["ans_refused"] for s, e in eff.items() if e["an_n"]}})
    rows.sort(key=lambda x: (-x["passes"], -(x["un_gain"].get("lme_abs", 0) + x["un_gain"].get("locomo_dev", 0)),
                             sum(x["right_lost"].values())))
    report = {"baseline": base, "rules": len(rows), "passing": sum(r["passes"] for r in rows), "top": rows[:40]}
    (STATE / "rules.dev.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def heldout(rule_name: str) -> dict:
    marker = STATE / "heldout.opened"
    if marker.exists():
        raise SystemExit(f"the held-out halves were already run once ({marker.read_text().strip()}); not again")
    rule = candidates()[rule_name]
    marker.write_text(rule_name + "\n")
    collect(HELD, "heldout")
    out = {"rule": rule_name, "sources": {}}
    for name in HELD:
        recs = load("heldout", name)
        out["sources"][name] = {**summary(recs, name), **effect(rule, recs)}
    (STATE / "heldout.result.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def synthetic_report(tag: str = "synthetic") -> dict:
    """(A) on the synthetic set: per configuration and kind, what the memory did and whether the knowledge-base block
    lists the article that answers it."""
    recs = run_items(synthetic_items(), tag)
    (STATE / f"{tag}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
    out: dict = {}
    for r in recs:
        row = out.setdefault(r["config"], {}).setdefault(r["kind"], {"n": 0, "memory_refused": 0, "memory_right": 0,
                                                                     "memory_wrong": 0, "kb_lists_gold": 0,
                                                                     "memory_none_first": 0})
        row["n"] += 1
        row["memory_refused"] += r["refused"]
        row["memory_right"] += bool(r["gold"]) and not r["refused"] and r["cited"][:1] == r["gold"]
        row["memory_wrong"] += not r["refused"] and r["cited"][:1] != r["gold"][:1]
        row["kb_lists_gold"] += bool(r.get("kb_gold")) and r["kb_gold"][0] in r.get("kb", [])
        row["memory_none_first"] += bool(r.get("memory_none_first"))
    (STATE / f"{tag}.result.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


# ---------- set 38: the three-state receipt and strict mode, counted ----------

STATE_SOURCES = {
    "lme_abs": lambda: lme_items("abs"),
    "locomo_heldout": lambda: locomo_items("heldout"),
    "lme_heldout": lambda: lme_items("heldout"),
    "mh_dev": lambda: mh_items("dev"), "mh_dev2": lambda: mh_items("dev2"), "mh_dev3": lambda: mh_items("dev3"),
    "mh_heldout": lambda: mh_items("heldout"), "mh_heldout2": lambda: mh_items("heldout2"),
    "mh_heldout3": lambda: mh_items("heldout3"),
    "synthetic": synthetic_items,
}


def _locked(vault: str, q: str) -> bool:
    """An alias lock, as the router takes it, when the vault has its own alias table (not the sample one)."""
    import canonical_lookup as cl
    import zones

    mp = zones.path(Path(vault), "90 系统文件/canonical_sources.psv")
    if not mp.is_file():
        return False
    try:
        return cl.lookup(q, cl.load_rows(mp), vault=Path(vault)) is not None
    except Exception:  # noqa: BLE001
        return False


def states() -> dict:
    """Set 38: per source, unanswerable and answerable questions by state, default and strict."""
    out: dict = {}
    for name, make in STATE_SOURCES.items():
        items = make()
        if name == "synthetic":  # 只数「记忆这一边」：近似题、库外题、知识库里的资料题算不可答；记忆题和资料在记忆里的算可答
            items = [it for it in items]
        recs = run_items(items, name)
        sys.path.insert(0, str(SCRIPTS))
        import recall_index as ri

        row = {"unanswerable": {"n": 0, "direct": 0, "related": 0, "none": 0},
               "answerable": {"n": 0, "direct": 0, "related": 0, "none": 0, "page_default": 0, "page_strict": 0}}
        for it, r in zip(items, recs):
            res = {"hits": [{"rel": c} for c in r["cited"]], "confidence": r["conf"]}
            st = ri.answer_state(res, locked=_locked(it["vault"], it["q"]))
            side = row["answerable" if r["answerable"] else "unanswerable"]
            side["n"] += 1
            side[st] += 1
            if r["answerable"]:
                found = st != "none" and bool(set(r["cited"]) & set(r["gold"]))
                side["page_default"] += found
                side["page_strict"] += found and st == "direct"
        out[name] = row
        print(json.dumps({name: row}), file=sys.stderr)
    (STATE / "states.result.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(HERE))
    if argv and argv[0] == "states":
        print(json.dumps(states(), ensure_ascii=False, indent=1))
        return 0
    if argv and argv[0] == "synthetic":
        print(json.dumps(synthetic_report(argv[1] if len(argv) > 1 else "synthetic"), ensure_ascii=False, indent=1))
        return 0
    if not argv or argv[0] not in ("collect", "rules", "heldout", "baseline-heldout"):
        print(__doc__)
        return 2
    if argv[0] == "collect":
        collect(DEV, "dev")
    elif argv[0] == "rules":
        rep = rules_report()
        print(json.dumps({k: rep[k] for k in ("baseline", "rules", "passing")}, ensure_ascii=False, indent=1))
        for r in rep["top"][:15]:
            print(json.dumps(r, ensure_ascii=False))
    elif argv[0] == "heldout":
        print(json.dumps(heldout(argv[1]), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
