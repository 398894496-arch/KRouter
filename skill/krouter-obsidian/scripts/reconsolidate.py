#!/usr/bin/env python3
"""Nightly trigger learning from the router's own query log (retrieval-driven reconsolidation).

Reads queries the router could not answer well (literal fallback, or low-confidence recall), shows
a model the top recall candidates for each with the start of each page, and asks which page answers it — or none —
and to copy the sentence on that page that answers it. A pick is learned only if that quote is on the page, is a real
sentence (at least QUOTE_TOKENS words) and shares a content word with the query. That stops a made-up quote and an
unrelated or fragmentary one; telling a neighbour page (same subject, does not answer) from the answer is still the
model's judgement, which the prompt asks for. Inputs pages (`03 资料与证据`: clipped and pasted text, which may carry
instructions) are never candidates; `Clippings/` is not indexed at all. Accepted pairs are appended to
`下意识触发词-自学习.psv` as `rel|original query`: recall-only, never a lock, no paraphrase invented. Half of real
router calls repeat an earlier question, so one fix pays again. Pages marked secret are never shown to the model.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm  # noqa: E402
import recall_index as ri  # noqa: E402

MISS = {"bounded-literal-search-complete"}
DEFAULT_OUT = "90 系统文件/自动化/下意识触发词-自学习.psv"
PROMPT = """下面是一个个人知识库路由器没答好的查询。每条给出：查询原文，以及召回排名前列的候选页（路径 + 页面开头的原文）。
判断哪一个候选页能回答这个查询。规则：
- 只有页面原文里有一句话直接回答了这个查询，才选它，并把那句话原样抄出来（一字不改）。
- 查询问到的具体对象（某个工具、系统、文件、场景、数字）在那页原文里没有出现，就是 none：同一话题不等于答案。
- 只能从该条给出的候选里选，原样输出路径；候选都不对就输出 none。宁可 none，不要硬选。
- 查询问的是库外常识、闲聊、或候选只是碰巧有相同字词，一律 none。
只输出 JSON：{"<id>": {"page": "<候选路径>", "quote": "<页面上回答它的那句原文>"}, ...}，答不了的写 "<id>": "none"。

"""
CANDS = 4          # 每条查询给模型看几个候选
EXCERPT = 600      # 每个候选给看多少字的正文
QUOTE_TOKENS = 4   # 引用至少这么多个词（英文单词 / 中文双字）才算一句话：挡住 "stored in" 这类碎片
UNTRUSTED = ("03 资料与证据/",)  # 剪藏、粘贴进来的资料：可能夹带指令，不当学习候选


def state_dir() -> Path:
    return Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local" / "state" / "krouter")


def load_misses(log: Path, since: str) -> list[dict]:
    seen: dict[str, dict] = {}
    if not log.is_file():
        return []
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("ts", "") <= since:
            continue
        weak = row.get("status") in MISS or row.get("confidence") == "low"
        if weak and row.get("q"):
            seen.setdefault(row["q"].strip(), row)
    return list(seen.values())


def learned(out: Path) -> set[tuple[str, str]]:
    pairs = set()
    if out.is_file():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and "|" in line:
                rel, words = line.split("|", 1)
                pairs.update((rel, w) for w in words.split(";"))
    return pairs


def page_text(vault: Path, rel: str) -> str | None:
    """The page body as the learner may see it (redacted); None for a secret page or a missing one."""
    try:
        text = ri.redact((vault / rel).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    meta, body = ri.split_frontmatter(text)
    if ri.is_secret_page(ri.zones.canon(vault, rel), meta):
        return None
    return re.sub(r"\s+", " ", body).strip()


def grounded(pick, cands: dict[str, str], query: str) -> str:
    """The page a verdict names, if its quote is on that page, is a sentence and shares a content word with the
    query; "" otherwise (a bare path no longer counts)."""
    if not isinstance(pick, dict):
        return ""
    rel, quote = str(pick.get("page") or "").strip(), re.sub(r"\s+", " ", str(pick.get("quote") or "")).strip()
    body = cands.get(rel)
    quote = quote.strip("。.\"'「」 ")
    if not body or quote not in body:
        return ""
    words = set(ri.tokens(quote))
    content = {t for t in ri.question_terms(query) if t not in ri.EN_FUNCTION}  # 去掉 where / the / for 这类虚词
    if len(words) < QUOTE_TOKENS or not words & content:
        return ""  # 碎片，或者跟问题一个实词都不沾：页面上确实有，但不是在回答这个问题
    return rel


def ask(vault: Path, prompt: str) -> dict:
    text = llm.complete(prompt, vault)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise RuntimeError("learner model output was not JSON")
    return json.loads(m.group(0))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT", ""))
    ap.add_argument("--out", default=os.environ.get("KROUTER_LEARNED_TRIGGERS", DEFAULT_OUT), help="vault-relative")
    ap.add_argument("--cli", default="")
    ap.add_argument("--model", default=os.environ.get("KROUTER_LEARN_MODEL", ""))
    ap.add_argument("--since", default="", help="ISO ts; default = last run cursor")
    ap.add_argument("--max", type=int, default=40)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.cli:
        os.environ["KROUTER_LEARN_CLI"] = args.cli
    if args.model:
        os.environ["KROUTER_LEARN_MODEL"] = args.model
    if not args.vault:
        print("set KROUTER_VAULT (or OBSIDIAN_VAULT) to your memory folder, or pass --vault", file=sys.stderr)
        return 2
    vault = Path(args.vault)
    out = ri.zones.path(vault, args.out)
    cursor = state_dir() / "reconsolidate.cursor"
    since = args.since or (cursor.read_text().strip() if cursor.is_file() else "")
    misses = load_misses(state_dir() / "queries.jsonl", since)[: args.max]
    have = learned(out)
    items = []
    for row in misses:
        res = ri.recall(vault, row["q"], limit=8, gate=False)
        cands = {}
        for h in res["hits"]:
            trusted = h["tier"] != "dead" and not ri.zones.canon(vault, h["rel"]).startswith(UNTRUSTED)
            body = page_text(vault, h["rel"]) if trusted else None
            if body and len(cands) < CANDS:
                cands[h["rel"]] = body
        if cands and not any((rel, row["q"]) in have for rel in cands):
            items.append({"id": str(len(items)), "q": row["q"], "cands": cands})
    report = {"misses": len(misses), "asked": len(items), "learned": 0, "none": 0}
    if args.dry_run:
        report["chars"] = len(PROMPT) + sum(len(it["q"]) + sum(len(rel) + min(len(b), EXCERPT) + 8 for rel, b in
                                                               it["cands"].items()) for it in items) if items else 0
        report["sends"] = ("router queries the router did not answer well, candidate page paths and the start of each "
                           "candidate page (redacted; secret pages never)") if items else "nothing"
        report["writes"] = [args.out] if items else []
    if items and not args.dry_run:
        blocks = []
        for it in items:
            lines = "\n".join(f"  - {rel} ｜ {body[:EXCERPT]}" for rel, body in it["cands"].items())
            blocks.append(f"### id={it['id']} 查询：{ri.redact(it['q'])}\n候选：\n{lines}\n")
        try:
            verdict = ask(vault, PROMPT + "\n".join(blocks))
        except llm.NoModel as exc:
            print(f"learning skipped: {exc}", file=sys.stderr)
            return 0
        new_lines = []
        for it in items:
            pick = grounded(verdict.get(it["id"]), it["cands"], it["q"])
            if pick:
                new_lines.append(f"{pick}|{it['q'].replace('|', '／').replace(';', '，')}")
                report["learned"] += 1
            else:
                report["none"] += 1
        if new_lines:
            out.parent.mkdir(parents=True, exist_ok=True)
            head = "" if out.is_file() else (
                "# 夜间自学习触发词（reconsolidate.py）：来自路由器没答好的真实查询，经模型从召回候选中确认。\n"
                "# 只参与召回，不参与锁定；status: provisional。rel|查询原文\n")
            with out.open("a", encoding="utf-8") as fh:
                fh.write(head + "\n".join(new_lines) + "\n")
    if not args.dry_run:
        cursor.parent.mkdir(parents=True, exist_ok=True)
        cursor.write_text(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
