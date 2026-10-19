#!/usr/bin/env python3
"""Group the recall asks by intent and mark the ones that only make sense inside their conversation.

One model call sees every recall ask at once, so the same question asked in different words (weeks apart, to
different agents) lands in one group; per-batch topics cannot be merged afterwards. Each ask gets `standalone`
(would a stranger, or a memory, know what is being asked without the conversation around it?) and a `group` key.
Writes a private file; prints counts only. Same endpoint options as classify_asks.py.

    KROUTER_EVAL_KEY=… python3 bench/real_questions/group_asks.py --openai-base http://127.0.0.1:8317/v1 --model grok-4.7
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import classify_asks as ca  # noqa: E402

PROMPT = """下面是同一个人几个月里问自己的 agent 的问题，都是在问他自己以前定过、做过、配置过的事。每条前面是编号。对每条给出：
- standalone：离开当时的对话，别人（或一个笔记库）能不能看懂它在问什么。指代不明（「当时做了什么」「那个怎么样了」「这个对吗」）就是 false。
- group：用 4 到 12 个字概括它问的是哪一件事。**同一件事、换了说法或隔了很久再问，必须用一字不差的同一个 group**；不同的事用不同的 group。
只输出一个 JSON 数组：[{"id": "<编号>", "standalone": true 或 false, "group": "<事项>"}, ...]

"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=str(ca.STATE))
    ap.add_argument("--cli", default="")
    ap.add_argument("--openai-base", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--effort", default="high")
    args = ap.parse_args()
    state = Path(args.state)
    asks = {r["id"]: r for r in map(json.loads, open(state / "asks.jsonl", encoding="utf-8"))}
    labels = [json.loads(x) for f in sorted(state.glob("labels*.jsonl")) for x in f.read_text(encoding="utf-8").splitlines()
              if x.strip()]
    rec = sorted({l["id"] for l in labels if l["label"] == "recall"}, key=lambda i: asks[i]["ts"])
    lines = [f"{n}. " + re.sub(r"\s+", " ", asks[i]["text"])[:300] for n, i in enumerate(rec, 1)]
    call = ca.ask_api if args.openai_base else ca.ask_cli
    text = call(args.openai_base or args.cli, args.model, args.effort, PROMPT + "\n".join(lines))
    m = re.search(r"\[.*\]", text, re.S)
    items = json.loads(m.group(0)) if m else []
    out = state / "groups.jsonl"
    n_ok = 0
    with out.open("w", encoding="utf-8") as fh:
        for it in items:
            k = str(it.get("id"))
            if not k.isdigit() or not 1 <= int(k) <= len(rec):
                continue
            fh.write(json.dumps({"id": rec[int(k) - 1], "standalone": bool(it.get("standalone")),
                                 "group": str(it.get("group") or "")[:40]}, ensure_ascii=False) + "\n")
            n_ok += 1
    os.chmod(out, 0o600)
    rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    groups = Counter(r["group"] for r in rows if r["standalone"])
    print(json.dumps({"recall": len(rec), "grouped": n_ok, "standalone": sum(r["standalone"] for r in rows),
                      "groups": len(groups), "groups_asked_twice_or_more": sum(1 for v in groups.values() if v >= 2)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
