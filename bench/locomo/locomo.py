#!/usr/bin/env python3
"""LoCoMo (Maharana et al., ACL 2024): KRouter, BM25 and the dense prototype on someone else's long conversations.

LoCoMo gives 10 conversations between two people, 19 to 32 dated sessions each, and 1 986 questions with the
authors' evidence labels (`D3:5` = session 3, turn 5) and a category. Category 5 (446 questions) is adversarial: it
asks about something the conversation does not say (often what one speaker did, asked of the other), and the right
answer is "not mentioned". Each conversation becomes one vault, one Markdown page per session, as KRouter's own
session import would write it; each system answers with up to three cited pages or a refusal. Scoring needs no model:

- evidence first (categories 1-4): the first cited page is an evidence session;
- evidence cited: any of the (up to three) cited pages is an evidence session;
- refused although answerable (categories 1-4);
- adversarial refused (category 5). An answered category-5 question is a wrong citation, as a neighbour question is
  on the honesty bench.

The category numbers are reported as the dataset has them; papers do not agree on their names (multi-hop / temporal /
open-domain / single-hop), so none are given here.

The dataset is not in this repository and this script downloads nothing; pass the file you fetched
(`github.com/snap-research/locomo`, `data/locomo10.json`, CC BY-NC 4.0):

    python3 bench/locomo/locomo.py convert --data locomo10.json
    python3 bench/locomo/locomo.py run --system krouter          # also bm25, bm25-floor
    KROUTER_DENSE_MODEL=BAAI/bge-m3 python3 bench/locomo/locomo.py run --system agree   # dense, dense-floor, rescue
    python3 bench/locomo/locomo.py score

Floors (`bm25-floor`, `dense-floor`, `agree`, `rescue`) are picked on dev3 (vault2), as everywhere else: nothing is
tuned on LoCoMo. State lives in `~/.local/state/krouter-eval/locomo/` (`KROUTER_LOCOMO_STATE` to move it).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STATE = Path(os.environ.get("KROUTER_LOCOMO_STATE") or Path.home() / ".local/state/krouter-eval/locomo")
SESSIONS = "05 时间日志/会话摘录"  # KRouter 自己导入会话时放的位置
SEED = 20261030
RESAMPLES = 10_000
DENSE_SYSTEMS = {"dense", "dense-floor", "agree", "rescue"}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bench():
    return _load("mh_bench_locomo", REPO / "bench/memory_honesty/run.py")


def dense():
    return _load("mh_dense_locomo", REPO / "bench/memory_honesty/dense.py")


def model_tag() -> str:
    from_env = os.environ.get("KROUTER_DENSE_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    return re.sub(r"[^A-Za-z0-9]+", "-", from_env.split("/")[-1]).strip("-").lower()


def day_of(raw: str) -> str:
    """LoCoMo dates look like `1:56 pm on 8 May, 2023`."""
    m = re.search(r"(\d{1,2}) (\w+),? (\d{4})", raw or "")
    if not m:
        return ""
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def convert(data: Path) -> None:
    convs = json.loads(data.read_text(encoding="utf-8"))
    vaults = STATE / "vaults"
    if vaults.exists():
        shutil.rmtree(vaults)
    meta = []
    for conv in convs:
        sample = re.sub(r"[^A-Za-z0-9_-]", "_", conv["sample_id"])
        c = conv["conversation"]
        root = vaults / sample / SESSIONS
        root.mkdir(parents=True)
        pages = {}
        n = 1
        while f"session_{n}" in c:
            raw = c.get(f"session_{n}_date_time", "")
            day = day_of(raw)
            name = f"{day} session_{n}.md"
            body = [f"---\ntitle: Session {n}, {raw}\ndate: {day}\nsource: locomo\n---\n", f"# Session {n}, {raw}\n"]
            for t in c[f"session_{n}"]:
                text = t.get("text", "").strip()
                if t.get("blip_caption"):
                    text += f" [shares a photo: {t['blip_caption']}]"
                body.append(f"**{t.get('speaker', '?')}:** {text}\n")
            (root / name).write_text("\n".join(body), encoding="utf-8")
            pages[f"{SESSIONS}/{name}"] = n
            n += 1
        for i, qa in enumerate(conv["qa"]):
            ev = sorted({int(m) for e in qa.get("evidence") or [] for m in re.findall(r"D(\d+):", e)})
            meta.append({"id": f"{sample}-{i:03d}", "q": qa["question"], "category": qa["category"],
                         "abs": qa["category"] == 5, "evidence_sessions": ev, "vault": str(root.parents[1]),
                         "pages": pages})
    (STATE / "questions.jsonl").write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in meta),
                                           encoding="utf-8")
    print(json.dumps({"conversations": len(convs), "questions": len(meta), "abs": sum(m["abs"] for m in meta),
                      "sessions": sum(len(set(m["pages"].values())) for m in {x["vault"]: x for x in meta}.values()),
                      "no_evidence": sum(not m["evidence_sessions"] for m in meta)}))


def load_questions() -> list[dict]:
    return [json.loads(x) for x in (STATE / "questions.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]


def by_vault(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for it in rows:
        out.setdefault(it["vault"], []).append(it)
    return out


def run(system: str, limit: int) -> None:
    rows = load_questions()[: limit or None]
    b = bench()
    out = []
    if system in DENSE_SYSTEMS:
        d = dense()
        floors = d.session_floors()
        for vault, items in by_vault(rows).items():
            for a in d.session_answers(system, Path(vault), items, floors):
                out.append({"id": a["id"], "cited": a["cited"][:3], "refused": a["refused"]})
        name = f"{system}.{model_tag()}"
        print(json.dumps({"floors": floors}), file=sys.stderr)
    elif system == "krouter":
        d = dense()
        for vault, items in by_vault(rows).items():
            for a in d._krouter_raw(items, Path(vault)):
                cited = [] if a["refused"] else a["cited"][:3]
                out.append({"id": a["id"], "cited": cited, "refused": a["refused"]})
        name = system
    else:
        floor = None
        if system == "bm25-floor":
            dev = b.questions("dev3")
            floor = b.pick_floor(dev, b.bm25_scored(dev, vault_src=b.vault_of("dev3"), cjk=True))
        for vault, items in by_vault(rows).items():
            scored = b.bm25_scored(items, vault_src=Path(vault), cjk=True)
            for a in b.floor_answers(scored, floor if floor is not None else float("-inf")):
                out.append({"id": a["id"], "cited": a["cited"][:3], "refused": a["refused"]})
        name = system
    path = STATE / f"outputs.{name}.jsonl"
    path.write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in out), encoding="utf-8")
    print(json.dumps({"system": name, "questions": len(out), "refused": sum(o["refused"] for o in out)}))


def judge(it: dict, ans: dict) -> dict:
    cited = [it["pages"].get(rel) for rel in ans["cited"]] if not ans["refused"] else []
    ev = set(it["evidence_sessions"])
    return {"answerable": not it["abs"], "category": it["category"], "refused": ans["refused"],
            "first": bool(cited) and cited[0] in ev, "cited": bool(ev & set(cited)),
            "answered": not ans["refused"], "wrong": not ans["refused"] and (it["abs"] or not cited or cited[0] not in ev)}


METRICS = {
    "evidence_first": ("answerable", "first"),
    "evidence_cited": ("answerable", "cited"),
    "refused_answerable": ("answerable", "refused"),
    "abs_refused": ("abs", "refused"),
}


def rate(outs: list[dict], subset: str, field: str) -> tuple[int, int]:
    pool = [o for o in outs if (not o["answerable"] if subset == "abs" else o[subset])]
    return sum(o[field] for o in pool), len(pool)


def paired(a: dict, b: dict, subset: str, field: str, rng: random.Random) -> dict | None:
    ids = sorted(i for i in a.keys() & b.keys() if (not a[i]["answerable"] if subset == "abs" else a[i][subset]))
    if not ids:
        return None
    d = [int(a[i][field]) - int(b[i][field]) for i in ids]
    boots = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(RESAMPLES))
    return {"diff": round(sum(d) / len(d), 4),
            "ci95": [round(boots[int(0.025 * RESAMPLES)], 4), round(boots[int(0.975 * RESAMPLES)], 4)], "n": len(ids)}


def score() -> None:
    qs = {q["id"]: q for q in load_questions()}
    systems = {}
    for path in sorted(STATE.glob("outputs.*.jsonl")):
        name = path.name[len("outputs."):-len(".jsonl")]
        ans = {a["id"]: a for a in map(json.loads, path.read_text(encoding="utf-8").splitlines())}
        systems[name] = {qid: judge(qs[qid], a) for qid, a in ans.items() if qid in qs}
    report: dict = {"questions": len(qs), "systems": {}}
    for name, res in systems.items():
        outs = list(res.values())
        row = {m: "{}/{}".format(*rate(outs, *spec)) for m, spec in METRICS.items()}
        answered = sum(o["answered"] for o in outs)
        row["wrong_citation_rate"] = f"{sum(o['wrong'] for o in outs)}/{answered}"
        row["by_category_first"] = {str(c): "{}/{}".format(sum(o["first"] for o in outs if o["category"] == c),
                                                           sum(1 for o in outs if o["category"] == c))
                                    for c in (1, 2, 3, 4)}
        report["systems"][name] = row
    if "krouter" in systems:
        report["paired_vs_krouter"] = {}
        for name, res in systems.items():
            if name == "krouter":
                continue
            rng = random.Random(SEED)
            report["paired_vs_krouter"][name] = {m: paired(res, systems["krouter"], *spec, rng)
                                                 for m, spec in METRICS.items()}
    report["scored_at"] = datetime.now().isoformat(timespec="seconds")
    (STATE / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert")
    c.add_argument("--data", required=True)
    r = sub.add_parser("run")
    r.add_argument("--system", choices=["krouter", "bm25", "bm25-floor", *sorted(DENSE_SYSTEMS)], required=True)
    r.add_argument("--limit", type=int, default=0)
    sub.add_parser("score")
    args = ap.parse_args()
    os.environ["KROUTER_NO_QUERY_LOG"] = "1"
    STATE.mkdir(parents=True, exist_ok=True)
    if args.cmd == "convert":
        convert(Path(args.data))
    elif args.cmd == "run":
        run(args.system, args.limit)
    else:
        score()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
