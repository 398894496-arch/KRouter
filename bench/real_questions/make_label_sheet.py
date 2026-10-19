#!/usr/bin/env python3
"""A local page on which the maintainer scores a sample of the real questions, blind, for the judge-agreement figure.

Picks `--n` questions at random (seed 20261016, as registered), shows each with its date, the candidate pool and the
two systems' outputs as X and Y in a random order (names hidden; the key goes to a separate private file), and asks
the same three things the judge answers: was there an answer page before the ask, and X's and Y's scores. Answers
stay in the browser (localStorage) until "导出" saves them as a JSON file. The page holds private messages: it is
written to the private state folder and never published.

    python3 bench/real_questions/make_label_sheet.py --vault ~/Vault --vault-commit 57b6019 --a krouter.no-learning --b bm25-floor
"""

from __future__ import annotations

import argparse
import html
import json
import os
import random
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import judge_real as jr  # noqa: E402

PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>真实提问手标</title><style>
:root{--bg:#fff;--fg:#1d1d1f;--mute:#6e6e73;--line:#e5e5ea;--card:#f7f7f9;--acc:#0a7d5a}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--fg:#ececf0;--mute:#9a9aa2;--line:#2c2c31;--card:#1c1c20;--acc:#4fd1a5}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 -apple-system,"PingFang SC",sans-serif}
main{max-width:900px;margin:0 auto;padding:24px 16px 80px}h1{font-size:22px;margin:0 0 6px}p.note{color:var(--mute);margin:0 0 20px}
section{border-top:1px solid var(--line);padding:18px 0}.q{font-weight:600}.d{color:var(--mute);font-size:13px}
.pool,.out{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin:8px 0;font-size:13px;white-space:pre-wrap;word-break:break-word}
.row{display:flex;flex-wrap:wrap;gap:14px;margin-top:8px}.row label{white-space:nowrap}
#bar{position:fixed;left:0;right:0;bottom:0;background:var(--bg);border-top:1px solid var(--line);padding:10px 16px;display:flex;gap:12px;align-items:center;justify-content:center}
button{font:inherit;padding:6px 14px;border:1px solid var(--acc);color:var(--acc);background:transparent;border-radius:6px;cursor:pointer}
</style></head><body><main><h1>真实提问手标（__N__ 题）</h1>
<p class="note">每题回答三件事：① 候选页池里有没有一页在提问时就能回答这个问题；② X 的得分；③ Y 的得分。2 = 引用的页直接回答了；1 = 相关但还得继续找；0 = 没用。拒答的一侧不用打分。只记录了"这个问题被问过"的页算 0。X、Y 是哪个系统是保密的。</p>
__ITEMS__</main><div id="bar"><span id="done"></span><button onclick="exportIt()">导出</button></div>
<script>
const KEY="krouter-label-sheet-v1";let st={};try{st=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){}
document.querySelectorAll("input[type=radio]").forEach(r=>{if(st[r.name]===r.value)r.checked=true;r.addEventListener("change",()=>{st[r.name]=r.value;try{localStorage.setItem(KEY,JSON.stringify(st))}catch(e){}count()})});
function count(){const n=document.querySelectorAll("section").length;let d=0;document.querySelectorAll("section").forEach(s=>{const id=s.dataset.id;if(st[id+"|exists"])d++});document.getElementById("done").textContent=`已标 ${d} / ${n}`}
function exportIt(){const b=new Blob([JSON.stringify(st,null,1)],{type:"application/json"});const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download="label_sheet_answers.json";a.click()}
count();
</script></body></html>"""


def radios(name: str, values: list[tuple[str, str]]) -> str:
    return "".join(f'<label><input type="radio" name="{name}" value="{v}"> {html.escape(t)}</label>' for v, t in values)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True)
    ap.add_argument("--vault-commit", required=True)
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--pool-from", default="")
    ap.add_argument("--n", type=int, default=45)
    args = ap.parse_args()
    questions = [json.loads(x) for x in open(jr.STATE / "frozen.jsonl", encoding="utf-8")]
    rng = random.Random(20261016)
    sample = rng.sample(questions, args.n)
    outs = {k: jr.load(k) for k in {args.a, args.b, *filter(None, args.pool_from.split(","))}}
    tmp = Path(tempfile.mkdtemp(prefix="krouter-label-"))
    jr.snapshot(Path(args.vault), args.vault_commit, tmp / "vault")
    pages = jr.Pages(tmp / "vault")
    items, key = [], {}
    for q in sample:
        day = q["ts"][:10]
        pool = []
        for o in outs.values():
            r = o.get(q["id"]) or {}
            pool += (r.get("cited") or []) + (r.get("pool") or [])
        pool = [p for p in dict.fromkeys(pool) if pages.valid(p, day)][:8]
        order = [args.a, args.b]
        rng.shuffle(order)
        key[q["id"]] = {"X": order[0], "Y": order[1]}
        shown = {}
        for side, name in zip("XY", order):
            r = outs[name].get(q["id"]) or {}
            cited = [p for p in r.get("cited") or [] if pages.valid(p, day)]
            shown[side] = "拒答" if r.get("refused") else (
                "（引用的页都不是提问前就有的，按规则 0 分）" if not cited else "\n".join(pages.render(p) for p in cited))
        items.append(
            f'<section data-id="{q["id"]}"><div class="q">{html.escape(jr.redact(q["q"])[:300])}</div>'
            f'<div class="d">{q["id"]} · 提问日期 {day}</div>'
            f'<div class="pool"><b>候选页池</b>\n{html.escape(chr(10).join(pages.render(p) for p in pool) or "（无）")}</div>'
            f'<div class="out"><b>X</b>\n{html.escape(shown["X"])}</div><div class="out"><b>Y</b>\n{html.escape(shown["Y"])}</div>'
            f'<div class="row">① {radios(q["id"] + "|exists", [("yes", "有答案页"), ("no", "没有")])}</div>'
            f'<div class="row">② X：{radios(q["id"] + "|x", [("2", "2"), ("1", "1"), ("0", "0"), ("na", "拒答")])}</div>'
            f'<div class="row">③ Y：{radios(q["id"] + "|y", [("2", "2"), ("1", "1"), ("0", "0"), ("na", "拒答")])}</div></section>')
    out = jr.STATE / "label_sheet.html"
    out.write_text(PAGE.replace("__N__", str(args.n)).replace("__ITEMS__", "\n".join(items)), encoding="utf-8")
    (jr.STATE / "label_sheet.key.json").write_text(json.dumps(key, ensure_ascii=False), encoding="utf-8")
    for f in (out, jr.STATE / "label_sheet.key.json"):
        os.chmod(f, 0o600)
    print(json.dumps({"sheet": str(out), "questions": len(items)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
