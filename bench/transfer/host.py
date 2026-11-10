#!/usr/bin/env python3
"""Set 15 (bench/memory_honesty/HELDOUT.md): the host model gets the whole experience digest and decides itself.

Set 13 matched a task to a card lexically and found 0 of 14. Here nothing is matched: the session-start hook's digest
(`experience.digest`, every card as one subject-free line plus how to use them) goes to the host model as session
context, the case is the user's message, and the host's reply is scored on the card ids it cites (`〔C08〕`). The host
models are run the way set 12 ran its reader: this script writes prompt batches, Claude Code subagents on the named
model answer every prompt in a batch and write the replies back, and this script scores them.

    python3 bench/transfer/host.py prepare dev --out DIR            # batches of host prompts (14 per file)
    python3 bench/transfer/host.py prepare dev --scale --out DIR    # the same with 40 distractor cards in the vault
    (each DIR/batch_*.jsonl {id, prompt} answered into DIR/replies_<host>/batch_*.jsonl {id, response})
    python3 bench/transfer/host.py score dev --replies DIR/replies_<host>
    (`--set 16` on any of these: the English set, on the English template with the English cards)

Scored mechanically: recalled = a transfer case whose expected card id is cited; quiet case with a suggestion = any id
cited on a case that should get none; wrong cards = ids other than the expected one on transfer cases (a distractor
id counts as wrong). Also counted: replies citing more than two ids.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "skill/krouter-obsidian/scripts"))
import experience  # noqa: E402

BATCH = 14
CITED = re.compile(r"(?<![A-Za-z0-9])([CD]\d{2})(?!\d)")
# 宿主看到的就是 hook 在会话开始时注入的那段上下文，然后是用户的消息。最后一段只为评测：回复写短一点、不真的去执行
HOST = """【会话开始时，系统注入的上下文】
{digest}

【用户消息】
{query}

【评测说明，不是用户说的】请像平时在这个会话里那样回复上面这条用户消息，只写回复的开头，最多五句话，不要真的去执行任何操作或调用工具。"""
HOST_EN = """[Context the system injected at session start]
{digest}

[User message]
{query}

[Bench note, not from the user] Reply to the user message above as you normally would in this session, but write only
the start of the reply, at most five sentences, and do not actually run anything or call any tools."""
# 第 15 套：中文模板库 + 中文卡；第 16 套：英文模板库 + 同样 14 张卡的英文版
SETS = {"15": {"template": "template-zh", "cards": "cards", "host": HOST},
        "16": {"template": "template", "cards": "cards_en", "host": HOST_EN}}
SET = "15"


def load(split: str, which: str | None = None) -> list[dict]:
    which = which or SET
    if split == "dev":
        text = (HERE / f"set{which}_dev.jsonl").read_text(encoding="utf-8")
    else:
        with gzip.open(HERE / f"set{which}_heldout.jsonl.gz", "rt", encoding="utf-8") as fh:
            text = fh.read()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def build_vault(root: Path, scale: bool = False) -> Path:
    vault = root / "vault"
    shutil.copytree(REPO / SETS[SET]["template"], vault)
    folder = vault / experience.FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    for src in [SETS[SET]["cards"]] + (["distractors"] if scale else []):
        for card in sorted((HERE / src).glob("*.md")):
            shutil.copy(card, folder / card.name)
    return vault


def digest_for(scale: bool) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        vault = build_vault(Path(tmp), scale)
        # 规模检查：全部卡都列出来（54 张），看摘要变长后宿主还稳不稳；上限另行报告
        return experience.digest(vault, max_lines=100 if scale else experience.DIGEST_MAX_LINES)


def opaque(case_id: str) -> str:
    return "q" + hashlib.sha1((f"set{SET}:" + case_id).encode("utf-8")).hexdigest()[:8]


def prepare(args) -> None:
    cases = load(args.split)
    digest = digest_for(args.scale)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    # 编号不能透露答案（`C01-x1` 里就有卡号），批里的顺序也要打乱：否则一批全是迁移用例、另一批全是反例
    cases = sorted(cases, key=lambda c: opaque(c["id"]))
    rows = [{"id": opaque(c["id"]), "prompt": SETS[SET]["host"].format(digest=digest, query=c["query"])} for c in cases]
    n = 0
    for i in range(0, len(rows), BATCH):
        n += 1
        (out / f"batch_{n:02d}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows[i:i + BATCH]), encoding="utf-8")
    print(json.dumps({"split": args.split, "scale": args.scale, "cases": len(rows), "batches": n,
                      "digest_lines": digest.count("\n- ") + digest.startswith("- "), "digest_chars": len(digest),
                      "digest_tokens_estimate": experience.token_estimate(digest)}, ensure_ascii=False))


def score_rows(cases: list[dict], replies: dict[str, str]) -> dict:
    recalled = quiet_bad = wrong = over_two = missing = 0
    by_kind: Counter = Counter()
    rows = []
    for c in cases:
        if c["id"] not in replies:
            missing += 1
            continue
        got = list(dict.fromkeys(CITED.findall(replies[c["id"]])))
        over_two += len(got) > 2
        if c["expect"]:
            recalled += c["expect"] in got
            wrong += len([g for g in got if g != c["expect"]])
        elif got:
            quiet_bad += 1
            by_kind[c["kind"]] += 1
        rows.append({"id": c["id"], "kind": c["kind"], "expect": c["expect"], "got": got})
    transfer = sum(1 for c in cases if c["expect"])
    return {"transfer": transfer, "recalled": recalled, "quiet_cases": len(cases) - transfer,
            "quiet_cases_with_suggestion": quiet_bad, "by_kind": dict(by_kind), "transfer_wrong_cards": wrong,
            "replies_citing_more_than_two": over_two, "missing_replies": missing, "rows": rows}


def score(args) -> None:
    replies = {}
    for f in sorted(Path(args.replies).glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                replies[str(r["id"])] = str(r.get("response") or "")
    cases = load(args.split)
    back = {opaque(c["id"]): c["id"] for c in cases}
    replies = {back.get(k, k): v for k, v in replies.items()}
    res = score_rows(cases, replies)
    rows = res.pop("rows")
    print(json.dumps({"split": args.split, **res}, ensure_ascii=False))
    if args.rows and args.split == "dev":
        for r in rows:
            print(json.dumps(r, ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("split", choices=("dev", "heldout"))
    p.add_argument("--scale", action="store_true")
    p.add_argument("--out", required=True)
    s = sub.add_parser("score")
    s.add_argument("split", choices=("dev", "heldout"))
    s.add_argument("--replies", required=True)
    s.add_argument("--rows", action="store_true", help="every case (development only)")
    for sp in (p, s):
        sp.add_argument("--set", default="15", choices=sorted(SETS), help="15 Chinese (default), 16 English")
    args = ap.parse_args()
    global SET
    SET = args.set
    {"prepare": prepare, "score": score}[args.cmd](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
