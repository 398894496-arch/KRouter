#!/usr/bin/env python3
"""Judge two systems' answers to the frozen real questions, blind, by the rules registered in HELDOUT.md (set 5).

For each question the judge sees the question and its date, a candidate pool of pages that existed before the ask
(all systems' cited pages and their top 5 without a refusal gate, each with date, status and its first characters),
and the outputs of systems X and Y rendered the same way. It says whether the pool holds a page that answered the
question before it was asked, and scores each non-refusing output 0 / 1 / 2. Refusals are scored by rule: 0 when such
a page existed, 2 when it did not; any citation scores 0 when it did not. A cited page counts only if it provably
existed before the ask (in a vault backup older than the ask, or its own date is earlier) and is not a session excerpt
or time log from the ask's day or later. Every pair is judged twice, the second time with X and Y swapped.

    KROUTER_EVAL_KEY=… python3 bench/real_questions/judge_real.py --vault ~/Vault --vault-commit 57b6019 \\
        --a krouter.no-learning --b bm25-floor --openai-base http://127.0.0.1:8317/v1 --model grok-4.7

Writes per-question scores to a private file; prints aggregates only (means, paired bootstrap interval, by month).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import tarfile
import tempfile
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "skill/krouter-obsidian/scripts"))
import classify_asks as ca  # noqa: E402
from krouter_redact import redact  # noqa: E402

STATE = ca.STATE
BACKUPS = Path.home() / "KnowledgeArchive/backups"
DATED = re.compile(r"(?m)^(created|date|created_at|first_seen)\s*:\s*['\"]?(\d{4}-\d{2}-\d{2})")
LOG_DIRS = ("05 时间日志/",)
PROMPT = """你是一个公正的评委，评判两个"个人知识库检索系统"对同一个真实提问的回答。每题给出：
- 问题和提问日期；
- 候选页池：在提问之前就已经存在的页（路径、日期、状态、开头的文字）；
- 系统 X 和系统 Y 的输出：它们引用的页（同样格式），或者「拒答」。

对每题做两件事：
1. exists：候选页池里，有没有一页在提问时就能回答这个问题（yes / no）。只记录了"这个问题被问过"、没有给出答案的页不算。
2. 给 X 和 Y 中没有拒答的输出打分：2 = 引用的页直接回答了问题；1 = 相关，但 agent 还得继续找；0 = 没用。只记录了问题本身的页算 0。
   拒答的输出写 null。

只输出一个 JSON 数组，不要解释：[{"q": <题号>, "exists": "yes" 或 "no", "x": 0/1/2 或 null, "y": 0/1/2 或 null}, ...]

"""


def frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    out = {}
    for line in text.split("\n---", 1)[0].splitlines()[1:]:
        if ":" in line and not line.startswith((" ", "-")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip("'\"")
    return out


def backup_index() -> list[tuple[str, set[str]]]:
    """[(day, pages present)] for each vault backup, oldest first."""
    out = []
    for d in sorted((BACKUPS / "obsidian-vault").glob("20??-??-??")):
        out.append((d.name, {p.relative_to(d).as_posix() for p in d.rglob("*.md")}))
    for tgz in sorted(BACKUPS.glob("20??-??-??T*/ObsidianVault.tar.gz")):
        with tarfile.open(tgz) as tf:
            names = {n.split("/", 1)[1] for n in tf.getnames() if n.endswith(".md") and "/" in n}
        out.append((tgz.parent.name[:10], names))
    return sorted(out)


class Pages:
    def __init__(self, vault: Path):
        self.vault = vault
        self.backups = backup_index()
        self.cache: dict[str, dict] = {}

    def info(self, rel: str) -> dict:
        if rel not in self.cache:
            p = self.vault / rel
            text = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
            meta = frontmatter(text)
            days = [d for d, names in self.backups if rel in names]
            m = DATED.search(text.split("\n---", 1)[0]) if text.startswith("---") else None
            fn = re.search(r"(\d{4}-\d{2})/(\d{2})｜", rel) or re.search(r"(\d{4}-\d{2}-\d{2})", Path(rel).name)
            own = m.group(2) if m else ((fn.group(1) + "-" + fn.group(2)) if fn and fn.lastindex == 2 else
                                        (fn.group(1) if fn else ""))
            body = text.split("\n---", 1)[1] if text.startswith("---") and "\n---" in text else text
            self.cache[rel] = {"exists": bool(text), "backup_day": days[0] if days else "", "own_day": own,
                               "status": meta.get("status", ""), "excerpt": redact(re.sub(r"\s+", " ", body))[:400]}
        return self.cache[rel]

    def valid(self, rel: str, ask_day: str) -> bool:
        i = self.info(rel)
        if not i["exists"]:
            return False
        if rel.startswith(LOG_DIRS) and (not i["own_day"] or i["own_day"] >= ask_day):
            return False  # 当天及以后的时间日志、会话摘录：是这次提问留下的，不是答案
        return (bool(i["backup_day"]) and i["backup_day"] < ask_day) or (bool(i["own_day"]) and i["own_day"] < ask_day)

    def render(self, rel: str) -> str:
        i = self.info(rel)
        day = i["own_day"] or (f"≤{i['backup_day']}" if i["backup_day"] else "?")
        return f"〔{rel} ｜ {day} ｜ {i['status'] or '-'}〕 {i['excerpt']}"


def load(name: str) -> dict[str, dict]:
    return {r["id"]: r for r in map(json.loads, open(STATE / f"outputs.{name}.jsonl", encoding="utf-8"))}


def snapshot(vault: Path, commit: str, dest: Path) -> None:
    dest.mkdir(parents=True)
    arch = subprocess.run(["git", "-C", str(vault), "archive", commit], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=arch, check=True)


def bootstrap(diffs: list[float], n: int = 10000, seed: int = 0) -> tuple[float, float]:
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(n))
    return round(means[int(0.025 * n)], 3), round(means[int(0.975 * n) - 1], 3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True)
    ap.add_argument("--vault-commit", required=True)
    ap.add_argument("--a", required=True, help="system A's outputs name (e.g. krouter.no-learning)")
    ap.add_argument("--b", required=True)
    ap.add_argument("--pool-from", default="", help="comma-separated extra output names whose pages join the pool")
    ap.add_argument("--openai-base", default="")
    ap.add_argument("--cli", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--ids", default="", help="judge only these question ids (a JSON list), e.g. the agreement sample")
    ap.add_argument("--tag", default="", help="suffix for the output file, e.g. claude for a second judge")
    args = ap.parse_args()
    questions = [json.loads(x) for x in open(STATE / "frozen.jsonl", encoding="utf-8")]
    if args.ids:
        keep = set(json.loads(Path(args.ids).read_text(encoding="utf-8")))
        questions = [q for q in questions if q["id"] in keep]
    outs = {k: load(k) for k in {args.a, args.b, *filter(None, args.pool_from.split(","))}}
    tmp = Path(tempfile.mkdtemp(prefix="krouter-judge-"))
    snapshot(Path(args.vault), args.vault_commit, tmp / "vault")
    pages = Pages(tmp / "vault")
    call = ca.ask_api if args.openai_base else ca.ask_cli
    results: dict[str, list[dict]] = defaultdict(list)
    for swap in (False, True):
        for start in range(0, len(questions), args.batch):
            batch = questions[start:start + args.batch]
            blocks, meta = [], {}
            for n, q in enumerate(batch, 1):
                day = q["ts"][:10]
                pool = []
                for o in outs.values():
                    r = o.get(q["id"]) or {}
                    pool += (r.get("cited") or []) + (r.get("pool") or [])
                pool = [p for p in dict.fromkeys(pool) if pages.valid(p, day)][:8]
                sides = {}
                for side, name in (("X", args.b if swap else args.a), ("Y", args.a if swap else args.b)):
                    r = outs[name].get(q["id"]) or {}
                    cited = [p for p in r.get("cited") or [] if pages.valid(p, day)]
                    sides[side] = {"name": name, "refused": bool(r.get("refused")), "cited": cited,
                                   "invalid_only": not r.get("refused") and not cited}
                meta[str(n)] = (q, sides)
                show = lambda s: "拒答" if s["refused"] else ("（引用的页都不是提问前就有的）" if s["invalid_only"]
                                                            else "\n    ".join(pages.render(p) for p in s["cited"]))
                blocks.append(f"### 第 {n} 题（提问日期 {day}）\n问题：{redact(q['q'])[:300]}\n候选页池：\n    "
                              + ("\n    ".join(pages.render(p) for p in pool) or "（无）")
                              + f"\nX：{show(sides['X'])}\nY：{show(sides['Y'])}\n")
            text = call(args.openai_base or args.cli, args.model, args.effort, PROMPT + "\n".join(blocks))
            m = re.search(r"\[.*\]", text, re.S)
            try:
                verdicts = {str(v.get("q")): v for v in json.loads(m.group(0))} if m else {}
            except ValueError:
                verdicts = {}
            for n, (q, sides) in meta.items():
                v = verdicts.get(n)
                if not v:
                    continue
                exists = str(v.get("exists")).lower() == "yes"
                for side in ("X", "Y"):
                    s = sides[side]
                    if s["refused"]:
                        score = 0 if exists else 2
                    elif s["invalid_only"] or not exists:
                        score = 0
                    else:
                        raw = v.get(side.lower())
                        score = int(raw) if raw in (0, 1, 2) else 0
                    results[q["id"]].append({"system": s["name"], "score": score, "exists": exists, "swap": swap})
            print(json.dumps({"pass": 2 if swap else 1, "batch": start // args.batch + 1, "judged": len(verdicts)}),
                  flush=True)
    out = STATE / f"judge.{args.a}__vs__{args.b}{'.' + args.tag if args.tag else ''}.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for qid, rs in results.items():
            fh.write(json.dumps({"id": qid, "results": rs}, ensure_ascii=False) + "\n")
    os.chmod(out, 0o600)
    # 汇总：每题每个系统两遍取平均；配对差值的 bootstrap 区间；按月份
    by_q = {}
    for qid, rs in results.items():
        a = [r["score"] for r in rs if r["system"] == args.a]
        b = [r["score"] for r in rs if r["system"] == args.b]
        if a and b:
            by_q[qid] = (sum(a) / len(a), sum(b) / len(b))
    month = {q["id"]: q["ts"][:7] for q in questions}
    diffs = [a - b for a, b in by_q.values()]
    report = {"a": args.a, "b": args.b, "questions_scored": len(by_q),
              "mean_a": round(sum(a for a, _ in by_q.values()) / len(by_q), 3),
              "mean_b": round(sum(b for _, b in by_q.values()) / len(by_q), 3),
              "a_minus_b_ci95": bootstrap(diffs),
              "exists_yes_share": round(sum(1 for rs in results.values() if rs and rs[0]["exists"]) / len(results), 3),
              "by_month": {}}
    for mth in sorted(set(month.values())):
        ks = [k for k in by_q if month[k] == mth]
        if ks:
            report["by_month"][mth] = {"n": len(ks), "mean_a": round(sum(by_q[k][0] for k in ks) / len(ks), 3),
                                       "mean_b": round(sum(by_q[k][1] for k in ks) / len(ks), 3)}
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
