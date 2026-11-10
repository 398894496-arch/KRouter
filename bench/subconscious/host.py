#!/usr/bin/env python3
"""Set 33 (bench/memory_honesty/HELDOUT.md): does the host use what the prompt hook brought, and ignore what does not fit?

    python3 bench/subconscious/host.py prepare --out DIR      # DIR/batch.jsonl {id, prompt}; DIR/key.json (not for the host)
    (a subagent on the named model answers every prompt into DIR/replies_<host>.jsonl {id, response})
    python3 bench/subconscious/host.py score --dir DIR --host haiku

Cases: set 32's held-out recall and changed cases on which the hook brought the expected page (its saved run,
`results/heldout-brought.jsonl`), at most 8 per language in file order. Each three ways: (A) with the hook's own note,
(B) with the note of the next case of the same language, (C) with no note.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
ZH = """{ctx}【用户消息】
{text}

【评测说明，不是用户说的】请像平时在这个会话里那样回复上面这条用户消息，只写回复的开头，最多五句话，不要真的去执行任何操作或调用工具。"""
ZH_CTX = "【这一轮系统随用户消息附上的上下文（应用的钩子加的，用户看不到）】\n{note}\n\n"
EN = """{ctx}[User message]
{text}

[Bench note, not from the user] Reply to the user message above as you normally would in this session, but write only
the start of the reply, at most five sentences, and do not actually run anything or call any tools."""
EN_CTX = "[Context the app's hook attached to this user message this turn (the user does not see it)]\n{note}\n\n"


def cases() -> list[dict]:
    rows = [json.loads(l) for l in gzip.decompress((HERE / "heldout.jsonl.gz").read_bytes()).decode().splitlines()]
    got = {j["id"]: j for j in map(json.loads, (HERE / "results/heldout-brought.jsonl").read_text().splitlines())}
    out = {"zh": [], "en": []}
    for r in rows:
        g = got[r["id"]]
        if r["kind"] != "quiet" and r["expect"] in g["brought"] and len(out[r["lang"]]) < 8:
            out[r["lang"]].append({**r, "note": g["note"]})
    return out["zh"] + out["en"]


def prepare(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    cs = cases()
    by_lang = {L: [c for c in cs if c["lang"] == L] for L in ("zh", "en")}
    items, key = [], {}
    for L, group in by_lang.items():
        for i, c in enumerate(group):
            other = group[(i + 1) % len(group)]
            for cond, note, page in (("A", c["note"], c["expect"]), ("B", other["note"], other["expect"]), ("C", "", "")):
                tpl, ctx = (ZH, ZH_CTX) if L == "zh" else (EN, EN_CTX)
                prompt = tpl.format(ctx=ctx.format(note=note) if note else "", text=c["text"])
                pid = hashlib.sha1(f"{c['id']}|{cond}".encode()).hexdigest()[:10]
                items.append({"id": pid, "prompt": prompt})
                key[pid] = {"case": c["id"], "cond": cond, "expect": c["expect"], "injected": page}
    random.Random(20261133).shuffle(items)
    (out / "batch.jsonl").write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")
    (out / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(items)} prompts, {len(cs)} cases ({len(by_lang['zh'])} zh, {len(by_lang['en'])} en)")


def has(reply: str, terms: list[str]) -> bool:
    low = reply.lower()
    return any(t.lower() in low for t in terms)


def cited(reply: str, rel: str) -> bool:
    stem = rel[:-3] if rel.endswith(".md") else rel
    name = Path(rel).name
    return any(x in reply for x in (rel, stem, name))


def score(d: Path, host: str) -> None:
    terms = json.loads((HERE / "keyterms.json").read_text(encoding="utf-8"))
    key = json.loads((d / "key.json").read_text(encoding="utf-8"))
    rep = {j["id"]: j["response"] for j in map(json.loads, (d / f"replies_{host}.jsonl").read_text().splitlines()) if j}
    n = {"A": 0, "B": 0, "C": 0}
    used = cite = pulled = base = missing = 0
    for pid, k in key.items():
        r = rep.get(pid)
        if r is None:
            missing += 1
            continue
        n[k["cond"]] += 1
        if k["cond"] == "A":
            used += has(r, terms[k["expect"]])
            cite += cited(r, k["expect"])
        elif k["cond"] == "B":
            pulled += has(r, terms[k["injected"]]) or cited(r, k["injected"])
        else:
            base += has(r, terms[k["expect"]])
    print(f"{host}: (A) used {used}/{n['A']} cited {cite}/{n['A']}  (B) pulled {pulled}/{n['B']}  "
          f"(C) key term without the note {base}/{n['C']}  missing replies {missing}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prepare", "score"])
    ap.add_argument("--out", default="")
    ap.add_argument("--dir", default="")
    ap.add_argument("--host", default="")
    a = ap.parse_args()
    if a.cmd == "prepare":
        prepare(Path(a.out))
    else:
        score(Path(a.dir), a.host)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
