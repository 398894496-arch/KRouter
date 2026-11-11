#!/usr/bin/env python3
"""Alias cold start: propose lock rows for the host to tick. Nothing reaches the table unticked.

Coverage comes from the host's nouns, and writing the first fifty is the steepest step. This script
drafts candidates from the vault itself — rule, topic and method pages that no alias locks yet,
ranked by how often real router traffic landed on them without a lock — and writes a checklist to
`90 系统文件/自动化/别名候选.md`:

    - [ ] Q31|日更;每日进化|90 系统文件/自动化/日更健康.md|日更健康页是权威

Tick the rows you want (`- [x]`) and run `--apply`: ticked rows are re-checked (the page still
exists, no alias would now lock a different page, the alias is not already taken) and appended to
the alias table in force; the checklist keeps the rest. A lock is a human decision — two steps,
same as promotion. Lexical by default (nothing leaves the machine); `--model` asks the model lane
for short nouns per page as well.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recall_index as ri  # noqa: E402
import zones  # noqa: E402
from canonical_lookup import load_rows, lookup, map_for, normalize  # noqa: E402

OUT = "90 系统文件/自动化/别名候选.md"
ROW_RE = re.compile(r"^- \[([ xX])\] (Q\d+\|[^|]*\|[^|]+\|.*)$")
SPLIT_RE = re.compile(r"[｜|/、，,；;：:（）()\[\]【】「」—–]+|\s+-\s+")
MIN_LEN, MAX_LEN = 2, 12  # 中文名词；英文名词按整段算，放宽到 24 个字符
LATIN_MAX = 24
PROMPT = """给下面每一页想 2–4 个「锁名词」：用户以后最可能用来直接点名这一页的短名词，2–8 个字，像项目名、工具名、规则名，
不要句子、不要泛词（规则、方法、记录、总结）。只输出 JSON：{"<页面路径>": ["名词", ...], ...}

"""


def state_log() -> Path:
    return Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local/state/krouter") / "queries.jsonl"


def demand(vault: Path) -> Counter:
    """Pages real traffic reached through recall, not a lock: the ones a lock would help most."""
    out: Counter = Counter()
    log = state_log()
    if not log.is_file():
        return out
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("top") and row.get("status") != "canonical-match":
            out[row["top"]] += 1
    return out


def words_of(title: str, meta_terms: str) -> list[str]:
    raw = [title, *SPLIT_RE.split(title), *re.split(r"[;；,，]", meta_terms or "")]
    out = []
    for w in raw:
        w = unicodedata.normalize("NFKC", w).strip().strip("#*`\"'")
        cap = LATIN_MAX if re.fullmatch(r"[A-Za-z0-9 ._+#-]+", w) else MAX_LEN
        if not (MIN_LEN <= len(w) <= cap) or w.isdigit() or re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", w):
            continue
        if w in ri.QUERY_STOP or w.lower() in {"md", "readme", "index"}:
            continue
        if w not in out:
            out.append(w)
    return out


def free_aliases(cands: list[str], rel: str, rows: list, taken: set[str], vault: Path) -> list[str]:
    """Drop aliases already in the table, or that would lock a different page today."""
    keep = []
    for alias in cands:
        if normalize(alias) in taken:
            continue
        hit = lookup(alias, rows, vault=vault)
        if hit is not None and hit[1] != rel:
            continue
        keep.append(alias)
    return keep


def next_ids(rows: list, n: int) -> list[str]:
    used = [int(m.group(1)) for cid, *_ in rows if (m := re.fullmatch(r"Q(\d+)", cid))]
    start = max(used, default=0) + 1
    return [f"Q{start + i:02d}" for i in range(n)]


def model_nouns(vault: Path, rels: list[str]) -> dict[str, list[str]]:
    import llm

    blocks = []
    for rel in rels:
        _meta, body = ri.split_frontmatter(ri.redact((vault / rel).read_text(encoding="utf-8", errors="replace")))
        blocks.append(f"### {rel}\n{body.strip()[:600]}\n")
    out: dict[str, list[str]] = {}
    for i in range(0, len(blocks), 20):
        try:
            text = llm.complete(PROMPT + "\n".join(blocks[i : i + 20]), vault)
        except RuntimeError as exc:
            print(f"model nouns skipped: {exc}", file=sys.stderr)
            return out
        m = re.search(r"\{.*\}", text, re.S)
        try:
            data = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            data = {}
        out.update({k: [str(x) for x in v if isinstance(x, str)] for k, v in data.items() if isinstance(v, list)})
    return out


def propose(vault: Path, limit: int, use_model: bool, out: Path | None = None) -> tuple[Path, int]:
    table = map_for(vault)
    rows = load_rows(table) if table.is_file() else []
    locked = {source for _cid, _aliases, source, _anchor in rows}
    taken = {normalize(a) for _cid, aliases, _s, _a in rows for a in aliases}
    con = ri.connect(ri.cache_path(vault))
    ri.refresh(vault, con)
    pages = con.execute("SELECT rel, tier, status, how, title FROM docs WHERE tier IN ('rule', 'topic')").fetchall()
    want = demand(vault)
    pages = [p for p in pages if p[0] not in locked and (p[2] or "") not in ri.DEAD_STATUS
             and not ri.is_secret_page(zones.canon(vault, p[0]),
                                       ri.split_frontmatter((vault / p[0]).read_text(encoding="utf-8", errors="replace"))[0])]
    pages.sort(key=lambda p: (-want.get(p[0], 0), p[1] != "rule", p[0]))
    pages = pages[:limit]
    nouns = model_nouns(vault, [p[0] for p in pages]) if use_model and pages else {}
    drafts = []
    proposed: set[str] = set()  # 同一批里一个名词只给排序靠前的那一页，两页都勾上会成歧义锁
    for rel, tier, _status, how, _title in pages:
        meta, _body = ri.split_frontmatter((vault / rel).read_text(encoding="utf-8", errors="replace"))
        title = meta.get("title") or Path(rel).stem
        cands = [*nouns.get(rel, []), *words_of(title, meta.get("topic_terms", "") or meta.get("aliases", ""))]
        cands = free_aliases(list(dict.fromkeys(c for c in cands if MIN_LEN <= len(c) <= LATIN_MAX)), rel, rows, taken, vault)[:5]
        cands = [c for c in cands if normalize(c) not in proposed]
        proposed.update(normalize(c) for c in cands)
        if cands:
            drafts.append((rel, tier, want.get(rel, 0), cands, (how or title).replace("|", "／")[:40]))
    ids = next_ids(rows, len(drafts))
    lines = [
        "---", "title: 别名候选", "status: generated", f"table: {table}", "---", "",
        "# 别名候选", "",
        "机器起草，**不会自动进别名表**。把要的行改成 `- [x]`，可以先删改名词，然后运行 "
        "`propose_aliases.py --apply`：勾过的行再核一遍（页面还在、名词没被占用、不会锁到别的页）后追加进别名表。", "",
        "排序：真实查询经召回落到这页、却没有锁的次数（需求）在前，规则页在前。", "",
    ]
    for cid, (rel, tier, n, cands, anchor) in zip(ids, drafts):
        lines.append(f"<!-- {tier}，需求 {n} 次 -->")
        lines.append(f"- [ ] {cid}|{';'.join(cands)}|{rel}|{anchor}")
    out = out or zones.path(vault, OUT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out, len(drafts)


def apply(vault: Path) -> dict:
    out = zones.path(vault, OUT)
    table = map_for(vault)
    if not out.is_file() or not table.is_file():
        return {"applied": 0, "reason": "no checklist or no alias table"}
    lock = table.resolve().parent / "canonical_sources.lock.json"
    if lock.is_file():
        return {"applied": 0, "reason": f"alias table is locked by another writer: {lock}"}
    rows = load_rows(table)
    taken = {normalize(a) for _cid, aliases, _s, _a in rows for a in aliases}
    used_ids = {cid for cid, *_ in rows}
    added, refused, rest = [], [], []
    for line in out.read_text(encoding="utf-8").splitlines():
        m = ROW_RE.match(line)
        if not m or m.group(1) == " ":
            rest.append(line)
            continue
        cid, aliases_raw, rel, anchor = m.group(2).split("|", 3)
        aliases = [a.strip() for a in aliases_raw.split(";") if a.strip()]
        why = ""
        if not (vault / rel).is_file():
            why = "page missing"
        elif cid in used_ids:
            why = f"id {cid} taken"
        else:
            free = free_aliases(aliases, rel, rows, taken, vault)
            if free != aliases:
                why = "alias taken or would lock another page: " + ";".join(a for a in aliases if a not in free)
        if why:
            refused.append({"row": m.group(2), "why": why})
            rest.append(line)
            continue
        row = f"{cid}|{';'.join(aliases)}|{rel}|{anchor}"
        added.append(row)
        rows.append((cid, aliases, rel, anchor))
        taken.update(normalize(a) for a in aliases)
        used_ids.add(cid)
    if added:
        text = table.read_text(encoding="utf-8")
        tmp = table.resolve().with_suffix(".psv.tmp")
        tmp.write_text(text + ("" if text.endswith("\n") else "\n") + "\n".join(added) + "\n", encoding="utf-8")
        tmp.replace(table.resolve())
        out.write_text("\n".join(rest) + "\n", encoding="utf-8")
    return {"applied": len(added), "rows": added, "refused": refused, "table": str(table)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT", ""))
    ap.add_argument("--limit", type=int, default=40, help="at most this many pages")
    ap.add_argument("--model", action="store_true", help="also ask the model lane for short nouns (sends page heads)")
    ap.add_argument("--apply", action="store_true", help="append the ticked rows to the alias table")
    ap.add_argument("--out", default="", help="write the checklist here instead of the vault (preview)")
    args = ap.parse_args()
    if not args.vault:
        print("set KROUTER_VAULT (or OBSIDIAN_VAULT) to your memory folder, or pass --vault", file=sys.stderr)
        return 2
    vault = Path(args.vault)
    if args.apply:
        print(json.dumps(apply(vault), ensure_ascii=False, indent=1))
        return 0
    out, n = propose(vault, args.limit, args.model, Path(args.out) if args.out else None)
    print(json.dumps({"checklist": str(out), "pages": n}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
