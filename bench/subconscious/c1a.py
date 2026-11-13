#!/usr/bin/env python3
"""Set 45, C1a (keywords computed with no model corroborate a full-text top page that is not `RECALL_MARGIN` ahead):
the bench side.

    python3 bench/subconscious/c1a.py diff [--ref d7f409a] [--cases FILE ...]   # N6: hook output, switch off vs C0, byte for byte
    python3 bench/subconscious/c1a.py rungs --cases FILE [--rung 2.0 --rung 1.5:1 ...]   # development counts per rung
    python3 bench/subconscious/c1a.py bigvault DIR      # 10,000 pages + 2,000 alias rows + 10,000 trigger lines (for speed.py)

`diff` runs `session_hook.py prompt` as the app runs it (one process per message, a new session id each) for the engine at
`--ref` (extracted with `git archive`) and for this checkout with `KROUTER_RECALL_MARGIN_LOW` unset, on vault3 + overlay,
each engine with its own cache and state, no `*_API_KEY` in the environment; it prints the number of messages and of
outputs that differ. Built in: sets 32 and 35 (both halves) and set 36's pairs; `--cases` adds more files (JSON Lines with
`text`, or gzip). `rungs` calls `recollect.recollect()` per rung, as `run.py` does, and scores with `run.score`.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import run  # noqa: E402  (run.py puts this checkout's scripts on the path)

ENV_LOW, ENV_MIN = "KROUTER_RECALL_MARGIN_LOW", "KROUTER_RECALL_KEYWORDS_MIN"


def load(path: Path) -> list[dict]:
    raw = gzip.decompress(path.read_bytes()).decode("utf-8") if path.suffix == ".gz" else path.read_text(encoding="utf-8")
    return [json.loads(x) for x in raw.split("\n") if x.strip()]


def texts(extra: list[str]) -> list[str]:
    out = []
    for f in ("dev.jsonl", "heldout.jsonl.gz", "set35_dev.jsonl", "set35_heldout.jsonl.gz"):
        out += [r["text"] for r in load(HERE / f)]
    for r in load(HERE / "set36.jsonl"):
        out += [r[k] for k in ("text", "first", "second") if r.get(k)]
    for f in extra:
        out += [r["text"] for r in load(Path(f))]
    return out


def base_env() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY") and k not in (ENV_LOW, ENV_MIN)}
    env.update(KROUTER_NO_QUERY_LOG="1", KROUTER_RECALL_PROMPT="1")
    return env


def hook_outputs(scripts: Path, vault: Path, msgs: list[str], tmp: Path) -> list[bytes]:
    env = {**base_env(), "KROUTER_VAULT": str(vault), "KROUTER_CACHE_DIR": str(tmp / "cache"),
           "KROUTER_STATE_DIR": str(tmp / "state")}
    subprocess.run([sys.executable, str(scripts / "recall_index.py"), "--vault", str(vault), "--stats"], env=env,
                   capture_output=True, check=True)
    out = []
    for i, m in enumerate(msgs):
        r = subprocess.run([sys.executable, str(scripts / "session_hook.py"), "prompt"], env=env, capture_output=True,
                           input=json.dumps({"prompt": m, "session_id": f"s{i}"}).encode())
        out.append(r.stdout)
    return out


def diff(a) -> int:
    msgs = texts(a.cases)
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        old = tmp / "old"
        old.mkdir()
        tar = subprocess.run(["git", "-C", str(REPO), "archive", a.ref, "skill"], capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(old)], input=tar, check=True)
        v = run.make_vault(tmp)
        (tmp / "a").mkdir(), (tmp / "b").mkdir()
        before = hook_outputs(old / "skill/krouter/scripts", v, msgs, tmp / "a")
        after = hook_outputs(REPO / "skill/krouter/scripts", v, msgs, tmp / "b")
    differ = [i for i, (x, y) in enumerate(zip(before, after)) if x != y]
    print(json.dumps({"ref": a.ref, "messages": len(msgs), "printed_c0": sum(bool(x.strip()) for x in before),
                      "differ": len(differ), "bytes_c0": sum(map(len, before)), "bytes_new": sum(map(len, after))}))
    return 1 if differ else 0


def rungs(a) -> int:
    import recollect

    rows = []
    for f in a.cases:
        rows += load(Path(f))
    plan = [("off", None, None)] + [(r, *(r.split(":") + ["1"])[:2]) for r in a.rung]
    with tempfile.TemporaryDirectory() as t:
        os.environ.update(KROUTER_CACHE_DIR=str(Path(t) / "cache"), KROUTER_STATE_DIR=str(Path(t) / "state"),
                          KROUTER_NO_QUERY_LOG="1")
        v = run.make_vault(Path(t))
        import recall_index

        recall_index.recall(v, "warm up the index")
        base = None
        for name, low, need in plan:
            for k in (ENV_LOW, ENV_MIN):
                os.environ.pop(k, None)
            if low:
                os.environ[ENV_LOW], os.environ[ENV_MIN] = low, need
            brought = {r["id"]: recollect.recollect(v, r["text"], recollect.DEFAULT_ROUTES) for r in rows}
            s = run.score(rows, brought)
            tot = lambda k: s.get(f"{k}_zh", 0) + s.get(f"{k}_en", 0)  # noqa: E731
            pages = {i: [h["real"] for h in b] for i, b in brought.items()}
            if base is None:
                base = pages
            near = s.get("quiet_loud_near_topic", 0)
            line = {"rung": name, "recall": f"{tot('recall_right')}/{tot('recall_n')}",
                    "recall_zh_en": [s.get("recall_right_zh", 0), s.get("recall_right_en", 0)],
                    "changed": f"{tot('changed_right')}/{tot('changed_n')}", "quiet_loud": f"{tot('quiet_loud')}/{tot('quiet_n')}",
                    "near_topic_loud": near, "wrong": tot("wrong"), "old": tot("old"),
                    "differs_from_off": sum(pages[i] != base[i] for i in pages)}
            line["choice_score"] = (tot("recall_right") + tot("changed_right") - 3 * (tot("quiet_loud") + tot("wrong"))
                                    - 9 * tot("old"))
            print(json.dumps(line, ensure_ascii=False))
            if a.show and name != "off":
                for r in rows:
                    if pages[r["id"]] != base[r["id"]]:
                        print("   ", r["id"], r["kind"], r.get("subkind"), "expect", r.get("expect"), "got", pages[r["id"]],
                              [h["word"] for h in brought[r["id"]]])
    return 0


def bigvault(a) -> int:
    root = Path(a.dir)
    subprocess.run([sys.executable, str(REPO / "bench/scale/gen.py"), "10000", str(root)], check=True, capture_output=True)
    pages = sorted(str(p.relative_to(root)) for p in root.rglob("*.md") if not p.name.startswith("."))
    rng = random.Random(10000)
    words = "发版 流程 封面 标题 规则 客户 报价 合同 部署 服务器 端口 数据库 备份 视频 剪辑 字幕 口播 选题 预算 采购".split()
    sysdir = root / "90 系统文件"
    (sysdir / "自动化").mkdir(parents=True, exist_ok=True)
    with (sysdir / "canonical_sources.psv").open("a", encoding="utf-8") as fh:
        for i in range(2000):
            fh.write(f"S{i:04d}|{''.join(rng.sample(words, 2))}{i}|{rng.choice(pages)}|合成别名 {i}\n")
    with (sysdir / "自动化/下意识触发词.psv").open("w", encoding="utf-8") as fh:
        for i in range(10000):
            fh.write(f"{rng.choice(pages)}|{''.join(rng.sample(words, 3))}{i}号\n")
    print(json.dumps({"pages": len(pages), "aliases": 2000, "trigger_lines": 10000}))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("diff")
    d.add_argument("--ref", default="d7f409a")
    d.add_argument("--cases", action="append", default=[])
    r = sub.add_parser("rungs")
    r.add_argument("--cases", action="append", required=True)
    r.add_argument("--rung", action="append", default=[], help="LOW or LOW:KEYWORDS_MIN, e.g. 2.0, 1.5, 1.15:2")
    r.add_argument("--show", action="store_true")
    b = sub.add_parser("bigvault")
    b.add_argument("dir")
    a = ap.parse_args()
    return {"diff": diff, "rungs": rungs, "bigvault": bigvault}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
