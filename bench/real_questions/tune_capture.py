#!/usr/bin/env python3
"""Tune the distill step on sessions that are not the set-6 measurement sessions, and compare variants side by side.

Same machinery as capture_bench.py, in its own state folder (`~/.local/state/krouter-eval/capture-tune/`): 10 other
sessions (seed 20261017, set 6's sessions excluded), a reference proposed by Grok and checked by GPT under the
maintainer's own definition (what the maintainer said, or went along with when the agent proposed it, counts; steps
and discussion do not), and three distill variants scored on missed rate, wrong rate and changes of mind captured,
together, because they trade against each other:

- `current`: the shipped distill, one call per session-day, up to 8 lines;
- `segmented`: the session-day cut into segments of about SEGMENT_CHARS, each distilled, changes of mind first, merged;
- `segmented+strict`: the same, with a prompt that says what is not a decision.

    KROUTER_EVAL_KEY=… tune_capture.py --cli /opt/homebrew/bin/claude --openai-base http://127.0.0.1:8317/v1
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import capture_bench as cb  # noqa: E402

imp = cb.imp
SEGMENT_CHARS = 6000
MAX_LINES = 24
VERIFY_USER = cb.VERIFY.replace(
    "- 一条候选算数，必须在摘录里看得到这个人自己说出来、或者明确同意了（\"好\"\"就这样\"\"按这个来\"、接着照做等）。agent 自己提议、他没表态的，不算；纯操作步骤、临时排查、一次性的事，不算。",
    "- 一条候选算数：这个人自己说出来的，或者 agent 提议、他接受了或接着照做的（这个人的标准：他事后看原文，认为大多数 agent 提议他都同意过）。纯操作步骤、临时排查、一次性的事、只是讨论过的，不算。")
STRICT_TAIL = """
不算「定下来的事」的（不要列）：
- 操作步骤和执行过程（「先跑一下测试」「重启服务」「打开某文件看看」）；
- 排查和讨论（「可能是缓存问题」「对比了两种方案」），除非最后选定了其中一个；
- 一次性的事（「把这段文字翻译一下」）。
agent 提议、这个人接受了或接着照做的，算。
"""


CHANGES_PROMPT = """下面是一个人和他的编程 agent 在 {day} 的一段会话摘录（项目：{project}；只有提问和每轮最后的回答，已脱敏）。

只做一件事：找出这段会话里**改主意**的地方：先定了（或在用）A，后来改成了 B。每条一行，写成「原来 A → 改成 B」，行尾用括号标出改的那一轮的提问时间，例如（14:05）。最多 8 条。
- 只写摘录里明确出现的改动；A 和 B 都要写清楚，让人不看原文也知道改了什么。
- agent 提议改、这个人接受了或接着照做的，也算。
- 没有就只回一行「- （这段会话没有改主意的事）」。
- 输出纯 Markdown 列表，不要前言和总结。

摘录：

{text}
"""


def pick(exclude: set[str]) -> None:
    rng = random.Random(20261017)
    pool: dict[str, list[str]] = {a: [] for a in cb.QUOTA}
    for agent, root in imp.roots().items():
        if agent not in cb.QUOTA or not root.is_dir():
            continue
        for p in sorted(root.rglob("*.jsonl")):
            if str(p) in exclude or "subagents" in p.parts or (agent == "cursor" and "agent-transcripts" not in p.parts):
                continue
            s = {"claude-code": imp.read_claude, "codex": imp.read_codex, "cursor": imp.read_cursor}[agent](p)
            n, answered = len(s["turns"]), sum(1 for t in s["turns"] if t["answer"])
            if 8 <= n <= 60 and answered >= 0.7 * n and "DSH-KRouter" not in s.get("cwd", ""):
                pool[agent].append(str(p))
    chosen = [{"agent": a, "path": p, "first_day": ""} for a, k in cb.QUOTA.items() for p in rng.sample(sorted(pool[a]), k)]
    cb.STATE.mkdir(parents=True, exist_ok=True)
    (cb.STATE / "sessions.json").write_text(json.dumps(chosen, ensure_ascii=False, indent=1), encoding="utf-8")


def segments(excerpt: str) -> list[str]:
    turns = cb.turns_of(excerpt)
    if not turns:
        return [excerpt]
    out, cur = [], ""
    for _, block in turns:
        if cur and len(cur) + len(block) > SEGMENT_CHARS:
            out.append(cur)
            cur = ""
        cur += block + "\n"
    return out + ([cur] if cur else [])


def distill_variant(u: dict, variant: str) -> list[str]:
    e = u["entry"]
    if variant == "current":
        digest, _ = imp.distill(e, u["page"], cb.STATE, False)
        lines = digest.splitlines()
    elif variant.endswith("+changes") and (cb.STATE / "distilled.segmented+strict.jsonl").is_file():
        base = {r["unit"]: r["lines"] for r in map(json.loads, open(cb.STATE / "distilled.segmented+strict.jsonl",
                                                                       encoding="utf-8"))}
        lines = [f"- {ln}" for ln in base.get(u["unit"], [])]  # 切段 + 严格的结果已经有了，只补改主意那一遍
    else:
        import llm

        prompt_base = imp.DISTILL_PROMPT.replace("摘录：", STRICT_TAIL + "\n摘录：", 1) if "strict" in variant \
            else imp.DISTILL_PROMPT
        lines = []
        for seg in segments(u["excerpt"]):
            text = llm.complete(prompt_base.format(day=e["day"].isoformat(), project=e["project"] or "?", text=seg),
                                cb.STATE)
            lines += [ln.rstrip() for ln in imp.redact(text).splitlines() if ln.strip().startswith(("-", "*"))]
    if variant.endswith("+changes"):  # 整段只找改主意：切段以后「先定 A」和「后改 B」常落在不同段里
        import llm

        text = llm.complete(CHANGES_PROMPT.format(day=e["day"].isoformat(), project=e["project"] or "?",
                                                  text=u["excerpt"]), cb.STATE)
        lines += [ln.rstrip() for ln in imp.redact(text).splitlines() if ln.strip().startswith(("-", "*")) and "→" in ln]
    lines = [re.sub(r"^[-*]\s*", "", ln) for ln in lines if "没有定下来的事" not in ln and "没有改主意的事" not in ln]
    lines = list(dict.fromkeys(lines))
    if variant != "current":
        lines = sorted(lines, key=lambda ln: "→" not in ln)[:MAX_LINES]  # 改主意的排在前面，挤掉的先是普通条目
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", default="")
    ap.add_argument("--openai-base", required=True)
    ap.add_argument("--propose-model", default="grok-4.7")
    ap.add_argument("--judge-model", default="gpt-5.5")
    ap.add_argument("--variants", default="current,segmented,segmented+strict")
    args = ap.parse_args()
    measured = {s["path"] for s in json.loads((cb.STATE / "sessions.json").read_text(encoding="utf-8"))}
    cb.STATE = Path.home() / ".local/state/krouter-eval/capture-tune"
    if args.cli:
        os.environ["KROUTER_LEARN_CLI"] = args.cli
    if not (cb.STATE / "sessions.json").is_file():
        pick(measured)
    units = cb.units()
    a = argparse.Namespace(openai_base=args.openai_base, cli="", model=args.propose_model, effort="high")
    if not (cb.STATE / "proposed.jsonl").is_file():
        cb.propose(a)
    if not (cb.STATE / "verified_by_model.json").is_file():
        cb.VERIFY = VERIFY_USER
        cb.verify(argparse.Namespace(**{**vars(a), "model": args.judge_model}))
    report = {"units": len(units)}
    for variant in args.variants.split(","):
        path = cb.STATE / f"distilled.{variant}.jsonl"
        if not path.is_file():
            rows = [{"unit": u["unit"], "agent": u["agent"], "lines": distill_variant(u, variant)} for u in units]
            path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        (cb.STATE / "distilled.jsonl").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        cb.score(argparse.Namespace(answers=str(cb.STATE / "verified_by_model.json"), openai_base=args.openai_base,
                                    cli="", model=args.judge_model, effort="high"))
        report[variant] = json.loads((cb.STATE / "score.json").read_text(encoding="utf-8"))
    (cb.STATE / "tune_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
