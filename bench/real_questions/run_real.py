#!/usr/bin/env python3
"""Run retrieval systems on the frozen real questions, against one fixed snapshot of the host's vault.

The vault is exported from its own git history at `--vault-commit` (`git archive`, read-only: the working copy and
uncommitted edits are never touched or used). Each system answers every question with up to three cited pages or a
refusal, with the same functions the memory honesty bench uses, so the systems differ only in how they choose:

- `krouter`: KRouter as an agent calls it, `route_knowledge.py search <question>` (the alias lock first, then ranked
  recall), from `--repo` (default: this checkout); the cited pages are read off its receipt;
- `bm25-floor`: BM25 over Chinese character pairs and English words, superseded pages skipped, a floor picked on dev3;
- any of the above from another checkout (`--repo`, e.g. the dense candidate), labelled with `--name`.

    python3 bench/real_questions/run_real.py --vault ~/Vault --vault-commit 57b6019 --system krouter
    python3 bench/real_questions/run_real.py … --system krouter --repo <checkout> --name dense-candidate-1

Writes one JSON line per question to `<state>/outputs.<name>.jsonl` (private). Prints counts only.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = Path.home() / ".local/state/krouter-eval/real"


def bench_from(repo: Path):
    spec = importlib.util.spec_from_file_location(f"mh_bench_{abs(hash(str(repo)))}", repo / "bench/memory_honesty/run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def route_answers(repo: Path, rows: list[dict], vault: Path, cache: Path, route: str = "search") -> list[dict]:
    """KRouter's own entry point, one question at a time; cited pages read off the receipt."""
    env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_CACHE_DIR": str(cache), "KROUTER_NO_QUERY_LOG": "1"}
    env.pop("KROUTER_MAP", None)  # 用快照库里自己的别名表
    script = repo / "skill/krouter-obsidian/scripts/route_knowledge.py"
    out = []
    for it in rows:
        text = subprocess.run(["python3", str(script), route, it["q"]], env=env, capture_output=True, text=True,
                              timeout=300, stdin=subprocess.DEVNULL).stdout
        cited: list[str] = []
        if re.search(r"(?m)^canonical_match: true", text):
            m = re.search(r"(?m)^source: (.+)$", text)
            if m:
                cited = [os.path.relpath(m.group(1).strip(), vault)]
        elif not re.search(r"(?m)^recall: none", text) and "\nrecall:\n" in text:
            block = text.split("\nrecall:\n", 1)[1]
            cited = [m.group(1) for m in re.finditer(r"(?m)^- (.+?\.md) tier=", block)][:3]
        mode = "canonical_match" if re.search(r"(?m)^canonical_match: true", text) else ("recall" if cited else "none")
        out.append({"id": it["id"], "cited": cited, "refused": not cited, "mode": mode})
    return out


def pool_of(bench, system: str, rows: list[dict], vault: Path, cache: Path, repo: Path) -> dict[str, list[str]]:
    """Each question's top 5 pages without the refusal gate: the judge's candidate pool for "was there an answer"."""
    if system == "bm25-floor":
        scored = bench.bm25_scored(rows, skip_superseded=True, vault_src=vault, cjk=True)
        return {qid: [p for p, _ in hits[:5]] for qid, hits in scored}
    import sys

    sys.path.insert(0, str(repo / "skill/krouter-obsidian/scripts"))
    os.environ["KROUTER_CACHE_DIR"] = str(cache)
    import recall_index as ri

    return {it["id"]: [h["rel"] for h in ri.recall(vault, it["q"], limit=5, gate=False)["hits"]] for it in rows}


def snapshot(vault: Path, commit: str, dest: Path) -> None:
    dest.mkdir(parents=True)
    arch = subprocess.run(["git", "-C", str(vault), "archive", commit], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=arch, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True)
    ap.add_argument("--vault-commit", required=True)
    ap.add_argument("--questions", default=str(STATE / "frozen.jsonl"))
    ap.add_argument("--system", choices=["krouter", "bm25-floor"], required=True)
    ap.add_argument("--repo", default=str(HERE.parents[1]))
    ap.add_argument("--name", default="")
    ap.add_argument("--prebuild-dense", action="store_true",
                    help="build the snapshot's page vectors first (the dense candidate; needs its venv and config)")
    ap.add_argument("--without-learning", action="store_true",
                    help="remove the learned triggers from the snapshot (90 系统文件/自动化/下意识触发词-自学习.psv)")
    args = ap.parse_args()
    os.environ["KROUTER_NO_QUERY_LOG"] = "1"
    bench = bench_from(Path(args.repo))
    rows = [json.loads(x) for x in Path(args.questions).read_text(encoding="utf-8").splitlines() if x.strip()]
    tmp = Path(tempfile.mkdtemp(prefix="krouter-real-"))
    try:
        vault = tmp / "vault"
        snapshot(Path(args.vault), args.vault_commit, vault)
        if args.without_learning:
            for f in vault.rglob("*自学习*.psv"):
                f.unlink()
        if args.prebuild_dense:  # 不先建好向量，第一次查询会退回纯字面，测不出向量的效果
            env = {**os.environ, "OBSIDIAN_VAULT": str(vault), "KROUTER_CACHE_DIR": str(tmp / "cache"),
                   "KROUTER_NO_QUERY_LOG": "1"}
            res = subprocess.run(["python3", str(Path(args.repo) / "skill/krouter-obsidian/scripts/dense.py"), "--build",
                                  "--vault", str(vault)], env=env, capture_output=True, text=True, timeout=7200)
            print(json.dumps({"dense_build": (res.stdout.strip().splitlines() or [""])[-1][:200],
                              "rc": res.returncode}))
        pool = pool_of(bench, args.system, rows, vault, tmp / "pool-cache", Path(args.repo))
        if args.system == "krouter":
            answers = route_answers(Path(args.repo), rows, vault, tmp / "cache")
        else:
            scored = bench.bm25_scored(rows, skip_superseded=True, vault_src=vault, cjk=True)
            floor = bench.pick_floor(bench.questions("dev3"), bench.bm25_scored(
                bench.questions("dev3"), skip_superseded=True, vault_src=bench.vault_of("dev3"), cjk=True))
            answers = bench.floor_answers(scored, floor)
        name = (args.name or args.system) + (".no-learning" if args.without_learning else "")
        out = STATE / f"outputs.{name}.jsonl"
        with out.open("w", encoding="utf-8") as fh:
            for a in answers:
                fh.write(json.dumps({"id": a["id"], "system": name, "cited": (a.get("cited") or [])[:3],
                                     "refused": bool(a.get("refused") or not a.get("cited")),
                                     "mode": a.get("mode", ""), "pool": pool.get(a["id"], [])},
                                    ensure_ascii=False) + "\n")
        os.chmod(out, 0o600)
        refused = sum(1 for a in answers if a.get("refused") or not a.get("cited"))
        print(json.dumps({"system": name, "questions": len(rows), "refused": refused, "vault_commit": args.vault_commit,
                          "out": str(out)}))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
