#!/usr/bin/env python3
"""Memory checkup (no model calls). Writes one generated page; never edits sources.

1. Lock rows / triggers whose source page is missing or superseded (supersede propagation).
2. Tenure check: for every `supersedes:` pair that resolves to two pages, recall on the old
   page's title must rank the live page above the replaced one.
3. Rule pages nobody read or recalled in the window (utility signal; a list for the human, no demotion).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recall_index as ri  # noqa: E402

DEFAULT_OUT = "90 系统文件/自动化/下意识体检.md"
LINK = re.compile(r"\[\[([^\]|#]+)")


def resolve(vault: Path, ref: str) -> str | None:
    ref = ref.strip().strip('"').strip("'")
    m = LINK.search(ref)
    if m:
        ref = m.group(1)
    ref = ref.strip()
    for cand in (ref, ref + ".md"):
        if (vault / cand).is_file():
            return cand
    return None


def supersede_pairs(vault: Path) -> list[tuple[str, str]]:
    pairs = []
    for path, rel in ri.iter_markdown(vault):
        text = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        if not text.startswith("---\n"):
            continue
        fm = text[4 : text.find("\n---", 4)]
        m = re.search(r"^supersedes:\s*\n((?:\s+-.*\n?)+)", fm, re.M)
        if not m:
            continue
        for line in m.group(1).splitlines():
            old = resolve(vault, line.strip()[1:])
            if old and old != rel:
                pairs.append((rel, old))
    return pairs


def usage_counts(vault: Path, days: int) -> Counter:
    """Pages an agent actually read or that the router returned, from local transcripts + query log."""
    since = time.time() - days * 86400
    roots = [Path.home() / ".codex" / "sessions", Path.home() / ".claude" / "projects", Path.home() / ".cursor" / "projects"]
    prefix = str(vault) + "/"
    pat = re.compile(re.escape(prefix) + r"([^\"'\\\n|]+?\.md)")
    used: Counter = Counter()
    for root in roots:
        for f in glob.glob(str(root) + "/**/*.jsonl", recursive=True):
            try:
                if os.path.getmtime(f) < since:
                    continue
                for rel in pat.findall(open(f, encoding="utf-8", errors="replace").read()):
                    used[rel] += 1
            except OSError:
                continue
    log = Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local/state/krouter") / "queries.jsonl"
    if log.is_file():
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                top = json.loads(line).get("top")
            except json.JSONDecodeError:
                continue
            if top:
                used[top] += 1
    return used


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=os.environ.get("KROUTER_VAULT") or os.environ.get("OBSIDIAN_VAULT", ""))
    ap.add_argument("--map", default="", help="alias table (default: KROUTER_MAP, the vault's table, the sample)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="vault-relative")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    vault = Path(args.vault)
    con = ri.connect(ri.cache_path(vault))
    ri.refresh(vault, con)
    tier = dict(con.execute("SELECT rel, tier FROM docs").fetchall())
    status = dict(con.execute("SELECT rel, status FROM docs").fetchall())

    # 1. lock rows + triggers pointing at missing / superseded pages
    stale_locks = []
    from canonical_lookup import map_for

    for line in (Path(args.map) if args.map else map_for(vault)).read_text(encoding="utf-8").splitlines():
        parts = line.split("|", 3)
        if line.startswith("#") or len(parts) != 4:
            continue
        cid, _aliases, src, _anchor = parts
        if not (vault / src).is_file():
            stale_locks.append((cid, src, "missing"))
        elif tier.get(src) == "dead":
            stale_locks.append((cid, src, status.get(src) or "dead"))
    aliases, _ = ri.alias_map(vault)
    stale_triggers = sorted({rel for rel in aliases if rel not in tier or tier.get(rel) == "dead"})

    # 2. tenure: old title must surface the live replacement first
    pairs = supersede_pairs(vault)
    tenure_ok, tenure_bad = 0, []
    for new, old in pairs:
        if tier.get(new) == "dead":
            continue
        title = Path(old).stem
        rels = [h["rel"] for h in ri.recall(vault, title, limit=10, refresh_first=False, gate=False, assoc=False)["hits"]]
        if new in rels and (old not in rels or rels.index(new) < rels.index(old)):
            tenure_ok += 1
        else:
            tenure_bad.append((title, new, old))

    # 3. answer cards: stale (page changed), not verbatim (specifics missing from the page), question off the page,
    #    nothing checkable (pure prose: only a human can tell if it says what the page says), too broad
    stale_cards, unfaithful_cards, offpage_cards, unchecked_cards, broad_cards = 0, [], [], [], []
    unverified_cards = 0
    page_hash: dict[str, str] = {}
    page_text: dict[str, str] = {}
    for rel, cards in ri.load_cards(vault).items():
        path = vault / rel
        if not path.is_file():
            stale_cards += len(cards)
            continue
        data = path.read_bytes()
        page_hash[rel] = ri.card_hashes(data)
        page_text[rel] = data.decode("utf-8", errors="replace")
        for card in cards:
            if card.get("sha") not in page_hash[rel]:
                stale_cards += 1
                continue
            if not ri.faithful(card["a"], page_text[rel]):
                unfaithful_cards.append((rel, card["q"]))
            elif not ri.grounded(card, page_text[rel]):
                offpage_cards.append((rel, card["q"]))
            elif not card.get("v"):
                unverified_cards += 1
                if not ri.card_specifics(card["a"]):
                    unchecked_cards.append((rel, card["q"]))
            if ri.broad_question(con, card["q"]):
                broad_cards.append((rel, card["q"]))

    # 4. rule pages with no use in the window
    used = usage_counts(vault, args.days)
    rules = sorted(r for r, t in tier.items() if t == "rule")
    unused = [r for r in rules if used.get(r, 0) == 0]

    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "stale_locks": stale_locks,
        "stale_triggers": stale_triggers,
        "tenure_pairs": len(tenure_bad) + tenure_ok,
        "tenure_ok": tenure_ok,
        "tenure_bad": tenure_bad,
        "rule_pages": len(rules),
        "unused_rule_pages": unused,
        "stale_cards": stale_cards,
        "unfaithful_cards": unfaithful_cards,
        "offpage_cards": offpage_cards,
        "unchecked_cards": unchecked_cards,
        "unverified_cards": unverified_cards,
        "broad_cards": broad_cards,
        "window_days": args.days,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    lines = [
        "---", "title: 下意识体检", "status: generated", f"generated_at: {report['generated_at']}",
        f"tenure: \"{tenure_ok}/{report['tenure_pairs']}\"", f"stale_locks: {len(stale_locks)}",
        f"unused_rule_pages: {len(unused)}", f"stale_cards: {stale_cards}",
        f"unfaithful_cards: {len(unfaithful_cards)}", f"offpage_cards: {len(offpage_cards)}",
        f"unverified_cards: {unverified_cards}", f"unchecked_cards: {len(unchecked_cards)}",
        f"broad_cards: {len(broad_cards)}", "---", "",
        "# 下意识体检", "",
        "机器生成，不改任何来源页。只列需要人看的项。", "",
        "## 锁指向失效页", "",
        *([f"- {c} → `{s}`（{why}）" for c, s, why in stale_locks] or ["- 无"]), "",
        "## 触发词指向失效页", "",
        *([f"- `{r}`" for r in stale_triggers] or ["- 无"]), "",
        f"## 取代后召回（{tenure_ok}/{report['tenure_pairs']} 通过）", "",
        "问旧页标题时，接替它的页必须排在旧页前面。", "",
        *([f"- 「{t}」：`{n}` 没排在 `{o}` 前面" for t, n, o in tenure_bad] or ["- 全部通过"]), "",
        "## 问答卡", "",
        f"- 过期（页面改过、卡未重写，已不参与排序和答案）：{stale_cards} 张",
        f"- 答案里的数字/路径/命令在原文找不到（读取时已拦下）：{len(unfaithful_cards)} 张",
        *[f"  - `{r}`：{q}" for r, q in unfaithful_cards[:20]],
        f"- 问题跟这页无关（问题里没有一个实词在原页出现，读取时已拦下）：{len(offpage_cards)} 张",
        *[f"  - `{r}`：{q}" for r, q in offpage_cards[:20]],
        f"- 还没经过模型核对（问题是否在问这一页、答案是否答对、有没有说反；夜间会补核）：{unverified_cards} 张",
        f"- 其中答案也没有可核对的数字/路径/英文词（只能人看）：{len(unchecked_cards)} 张",
        f"- 问题过宽（实词不到 2 个，可能把无关提问召回到这一页）：{len(broad_cards)} 张",
        *[f"  - `{r}`：{q}" for r, q in broad_cards[:30]], "",
        f"## 近 {args.days} 天没人读、也没被召回的规则页（{len(unused)}/{len(rules)}）", "",
        "只是提醒，不降权、不删除。确认没用了再标 superseded / retired。", "",
        *[f"- `{r}`" for r in unused], "",
    ]
    out = ri.zones.path(vault, args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    if not args.json:
        print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in report.items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
