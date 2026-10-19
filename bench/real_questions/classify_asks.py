#!/usr/bin/env python3
"""Sort a person's typed messages into "asks about their own knowledge" and everything else, with a model.

The real-questions bench needs the messages in which the host asked about something they or their agents had
decided, set up or done, the kind of thing a memory should answer ("how did we settle the release flow?", "where
do the DSH keys live?"), not instructions ("make the video"), general knowledge or chat. Rules cannot tell these
apart, so a model labels them, in batches, with no tools. Input: `extract_asks.py`'s file (already redacted);
output: one label per message in a private file; a re-run skips what is labelled.

    python3 bench/real_questions/classify_asks.py --cli ~/.grok/bin/grok --model grok-4.7 --effort high [--limit N]
    KROUTER_EVAL_KEY=… python3 bench/real_questions/classify_asks.py --openai-base http://127.0.0.1:8317/v1 --model grok-4.7

`--openai-base` calls an OpenAI-compatible endpoint (a local proxy such as CLIProxyAPI, or a provider) with the key in
`KROUTER_EVAL_KEY`; the key is never printed or stored.

The messages go to the CLI's provider (this is the only step that sends them anywhere). Prints counts only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

STATE = Path.home() / ".local/state/krouter-eval/real"
PROMPT = """下面是一个人过去几个月对自己的编程/内容 agent 说过的话，每条一行，前面是编号。给每条打一个标签：

- recall：在问他自己或他的 agent 以前定过、做过、配置过、记录过的东西，也就是一个记忆库/笔记库应该能回答的问题。
  例：「发版流程我们是怎么定的」「DSH 的 key 放哪了」「上次那个中文补丁是怎么修好的」「口播风格的规则是什么」「Codex 的职责边界是什么」。
- task：让 agent 去做事、改东西、写东西、跑命令（哪怕句子里带问号，比如「能帮我把这个视频剪一下吗」）。
- general：问的是通用知识、外部世界、产品功能，答案不在他自己的记录里（例：「Python 的 GIL 是什么」「Claude 有什么新模型」）。
- status：问 agent 当前这一步的进度或结果（「好了吗」「跑完了没」「为什么报错」），只对当时的上下文有意义。
- other：闲聊、情绪、确认、半句话、看不懂的。

只有 recall 需要再给一个 topic：用 4 到 12 个字概括它问的是哪件事（同一件事换说法问，topic 要尽量一样）。
只输出一个 JSON 数组，不要任何解释：[{"id": "<编号>", "label": "<标签>", "topic": "<recall 才填，否则空字符串>"}, ...]

"""
LABELS = {"recall", "task", "general", "status", "other"}


def ask_cli(cli: str, model: str, effort: str, prompt: str) -> str:
    if Path(cli).name in ("claude", "claude-max"):  # Claude Code：不给任何工具，提示词走标准输入
        argv = [cli, "--print", "--tools", "", "--output-format", "text", "--no-session-persistence"]
        argv += ["--model", model] if model else []
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skill/krouter-obsidian/scripts"))
        import llm  # 和夜间任务一样：钥匙文件里的长期 CLI 令牌（钥匙串登录过期也能用）

        res = subprocess.run(argv, input=prompt, capture_output=True, text=True, timeout=1800, env=llm.cli_env())
        return res.stdout
    with tempfile.TemporaryDirectory(prefix="krouter-classify-") as tmp:
        pf = Path(tmp) / "prompt.md"
        pf.write_text(prompt, encoding="utf-8")
        argv = [cli, "--model", model, "--prompt-file", str(pf), "--max-turns", "1", "--cwd", tmp,
                "--sandbox", "strict", "--output-format", "plain"]
        if effort:
            argv += ["--reasoning-effort", effort]
        res = subprocess.run(argv, capture_output=True, text=True, timeout=1800, stdin=subprocess.DEVNULL)
        return res.stdout


def ask_api(base: str, model: str, effort: str, prompt: str) -> str:
    import urllib.request

    body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if effort:
        body["reasoning_effort"] = effort
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=json.dumps(body).encode("utf-8"),
                                 headers={"Authorization": "Bearer " + os.environ.get("KROUTER_EVAL_KEY", ""),
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=1800) as resp:
            data = json.load(resp)
    except Exception as exc:  # noqa: BLE001 - 一批失败就记下来，下次重跑会补上
        print(json.dumps({"error": type(exc).__name__, "detail": str(exc)[:200]}), file=sys.stderr)
        return ""
    return ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""


def parse(text: str, ids: set[str]) -> dict[str, dict]:
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return {}
    try:
        items = json.loads(m.group(0))
    except ValueError:
        return {}
    out = {}
    for it in items:
        if isinstance(it, dict) and str(it.get("id")) in ids and it.get("label") in LABELS:
            out[str(it["id"])] = {"label": it["label"], "topic": str(it.get("topic") or "")[:40]}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asks", default=str(STATE / "asks.jsonl"))
    ap.add_argument("--ids", default=str(STATE / "prefilter_ids.json"))
    ap.add_argument("--out", default=str(STATE / "labels.jsonl"))
    ap.add_argument("--cli", default="")
    ap.add_argument("--openai-base", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--batch", type=int, default=60)
    ap.add_argument("--limit", type=int, default=0, help="label at most this many (a pilot)")
    ap.add_argument("--shard", default="", help="K/N: take every N-th message starting at K (run N in parallel, "
                                                 "each with its own --out)")
    args = ap.parse_args()
    if bool(args.cli) == bool(args.openai_base):
        ap.error("give exactly one of --cli or --openai-base")
    asks = {r["id"]: r for r in map(json.loads, open(args.asks, encoding="utf-8"))}
    want = [i for i in json.load(open(args.ids)) if i in asks]
    out = Path(args.out)
    done = set()
    for f in out.parent.glob(out.stem.split(".")[0] + "*.jsonl"):  # 所有分片的结果都算已完成
        done |= {json.loads(x)["id"] for x in f.read_text(encoding="utf-8").splitlines() if x.strip()}
    todo = [i for i in want if i not in done]
    if args.shard:
        k, n = map(int, args.shard.split("/"))
        todo = todo[k::n]
    todo = todo[: args.limit or None]
    failed = 0
    for start in range(0, len(todo), args.batch):
        batch = todo[start:start + args.batch]
        lines = [f"{n}. " + re.sub(r"\s+", " ", asks[i]["text"])[:400] for n, i in enumerate(batch, 1)]
        call = ask_api if args.openai_base else ask_cli
        got = parse(call(args.openai_base or args.cli, args.model, args.effort, PROMPT + "\n".join(lines)),
                    {str(n) for n in range(1, len(batch) + 1)})
        with out.open("a", encoding="utf-8") as fh:
            for n, i in enumerate(batch, 1):
                if str(n) in got:
                    fh.write(json.dumps({"id": i, **got[str(n)]}, ensure_ascii=False) + "\n")
                else:
                    failed += 1
        os.chmod(out, 0o600)
        print(json.dumps({"batch": start // args.batch + 1, "labelled": len(got), "of": len(batch)}), flush=True)
    labels = [json.loads(x)["label"] for x in out.read_text(encoding="utf-8").splitlines()] if out.is_file() else []
    from collections import Counter
    print(json.dumps({"labelled_total": len(labels), "unlabelled_this_run": failed, "labels": dict(Counter(labels))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
