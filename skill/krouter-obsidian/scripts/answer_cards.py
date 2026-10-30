#!/usr/bin/env python3
"""Answer cards (sleep-time compute): precompute the questions a page will be asked, and its answers.

Real router traffic repeats itself (half the calls repeat an earlier question), so the questions are
predictable. For every rule / topic page, a model writes 3–5 `question → one-line answer` pairs taken
only from that page. Cards live in `90 系统文件/自动化/下意识问答.jsonl` (machine file; no source page
is edited), carry the page's content hash, and are rewritten only when the page changes. The router
uses card questions as recall triggers and prints the best-matching card as `answer (generated):`.
A card is kept only if its specifics appear in the page as whole tokens, its question shares a content word with
the page (recall_index.grounded) and names enough of its subject not to be too broad (recall_index.broad_question);
a second model pass checks meaning. Cards already on file are held to the same checks on every run: a card written
before a check was tightened is dropped and its page asked again, instead of sitting in the file blocked at read time.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm  # noqa: E402
import recall_index as ri  # noqa: E402

CARDS = "90 系统文件/自动化/下意识问答.jsonl"
PAGE_MAX = 3500
BATCH = 6
# 卡片写进库前过滤：像密钥、token、口令的串一律丢弃（prompt 里的"不写密钥"不算保证）
SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_-]{12,}|bearer\s+\S+|api[_-]?key\s*[=:]|password\s*[=:]|token\s*[=:])", re.I)
LONG_RUN = re.compile(r"[A-Za-z0-9_-]{24,}")


def secret_like(text: str) -> bool:
    """Key-shaped text. A long run counts when one unbroken piece of it is ≥ 24 characters mixing letters and
    digits (a key, a 40-hex token); a long id made of short `-`/`_` pieces (`20260811-090406-v4-flash`) does not."""
    if SECRET_RE.search(text):
        return True
    for run in LONG_RUN.findall(text):
        for piece in re.split(r"[-_]", run):
            if len(piece) >= 24 and re.search(r"[A-Za-z]", piece) and re.search(r"\d", piece):
                return True
    return False
PROMPT = """下面是个人知识库里的若干页面。为每一页写 3–5 张「问答卡」：用户以后最可能怎么问这一页能回答的问题，以及一句话答案。
规则：
- 问题：口语化中文，像用户随口问 Agent，6–20 字；覆盖这一页不同的要点，不要五张卡问同一件事。
- 问题里带上这一页特有的主语（项目名、工具名、哪一期、哪个账号），只看问题就知道问的是哪件事：
  写「Roadster 那期音效比人声低多少？」，不写「音效该比人声低多少？」——后者换到别的页也成立。
- 答案：只能来自这一页原文，一到两句、不超过 90 字，写结论和关键细节（数字、路径、命令、日期、谁说的），不要写"见本页""详见"。
- 数字、日期、路径、型号、命令照原文原样抄：原文写 08-16 就写 08-16，不改成 8/16；原文分开列的几个值照原文列，
  不用 / 拼成一串；不自己换算比例、总数或时区。
- 这一页只是导航/索引、没有可回答的结论，就给空数组。
- 不写密钥、token、密码、私人财务细节。
只输出 JSON：{"<页面路径>": [{"q": "...", "a": "..."}, ...], ...}

"""


VERIFY_PROMPT = """下面每一页后面跟着几张问答卡。逐张判断，三条都满足才算 ok：
1. 问题问的是这一页讲到的事，不是借了页面里的一个词去问别的事；
2. 答案确实回答了这个问题，不是同一页里另一个问题的答案；
3. 答案的每个说法在这一页都有依据：没有说反、没有把条件或数字改掉、没有添加页面没有的内容。
拿不准就判 false。只输出 JSON：{"<页面路径>": [{"id": <卡号>, "ok": true 或 false}, ...], ...}

"""


# 系统每天自动改写的状态页：卡片当天就会过期，每晚重写只是白花钱；它要回答的问题由规则页回答
VOLATILE_PAGES = ("90 系统文件/自动化/日更健康.md",)


def page_sha(path: Path) -> str:
    """The hash a new card is written against: the page body (frontmatter edits do not stale a card)."""
    return ri.body_hash(path.read_bytes())


def load_cards(vault: Path) -> list[dict]:
    out = []
    system = ri.zones.path(vault, "90 系统文件")
    for path in sorted(system.rglob("下意识问答*.jsonl")) if system.is_dir() else []:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("rel") and (row.get("empty") or (row.get("q") and row.get("a"))):
                out.append(row)
    return out


def targets(vault: Path) -> list[str]:
    con = ri.connect(ri.cache_path(vault))
    ri.refresh(vault, con)
    rels = [r for (r,) in con.execute("SELECT rel FROM docs WHERE tier IN ('rule', 'topic') ORDER BY rel")]
    def secret(rel: str) -> bool:
        meta, _ = ri.split_frontmatter((vault / rel).read_text(encoding="utf-8", errors="replace"))
        return ri.is_secret_page(ri.zones.canon(vault, rel), meta)

    # 机密页（钥匙页、凭据页、secret: true）永不外发；每天被系统改写的状态页不配卡
    return [r for r in rels if not secret(r) and ri.zones.canon(vault, r) not in VOLATILE_PAGES]


def block(vault: Path, rel: str) -> str:
    _meta, body = ri.split_frontmatter(ri.redact((vault / rel).read_text(encoding="utf-8", errors="replace")))
    body = re.sub(r"\n{3,}", "\n\n", body).strip()[:PAGE_MAX]
    return f"### 页面路径: {rel}\n{body}\n"


def ask(vault: Path, rels: list[str]) -> dict:
    prompt = PROMPT + "\n".join(block(vault, r) for r in rels)
    last = ""
    for _ in range(2):
        try:
            text = llm.complete(prompt, vault)
        except RuntimeError as exc:  # NoModel is a RuntimeError: propagate so the run is skipped, not emptied
            if isinstance(exc, llm.NoModel):
                raise
            last = str(exc)
            continue
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return {k: v for k, v in json.loads(m.group(0)).items() if k in rels and isinstance(v, list)}
            except json.JSONDecodeError:
                last = "model output was not JSON"
    print(f"batch failed at {rels[0]}: {last[-200:]}", file=sys.stderr)
    return {}


def verify(vault: Path, by_rel: dict[str, list[dict]], jobs: int = 3) -> dict[str, list[bool]] | None:
    """A second model pass over finished cards: question on the page, answer answers it, answer says what
    the page says. Lexical checks cannot tell a half-off-topic question or a flipped sentence from a real
    card; this pass is what can. None when no model is reachable (cards stay unverified)."""
    rels = [r for r in by_rel if by_rel[r]]
    chunks = [rels[i : i + BATCH] for i in range(0, len(rels), BATCH)]

    def one(chunk: list[str]) -> dict[str, list[bool]]:
        parts = []
        for rel in chunk:
            cards = "\n".join(f"卡 {n}：问：{c['q']}　答：{c['a']}" for n, c in enumerate(by_rel[rel]))
            parts.append(block(vault, rel) + "\n" + cards + "\n")
        try:
            text = llm.complete(VERIFY_PROMPT + "\n".join(parts), vault)
        except RuntimeError as exc:
            if isinstance(exc, llm.NoModel):
                raise
            print(f"verify failed at {chunk[0]}: {str(exc)[-160:]}", file=sys.stderr)
            return {}
        m = re.search(r"\{.*\}", text, re.S)
        try:
            data = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            data = {}
        got: dict[str, list[bool]] = {}
        for rel in chunk:
            rows = data.get(rel, []) if isinstance(data, dict) else []
            verdict = {int(x["id"]): x.get("ok") is True for x in rows if isinstance(x, dict) and str(x.get("id", "")).isdigit()}
            if verdict:  # a page the model skipped stays unverified rather than failed
                got[rel] = [verdict.get(n, False) for n in range(len(by_rel[rel]))]
        return got

    out: dict[str, list[bool]] = {}
    try:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            for got in ex.map(one, chunks):
                out.update(got)
    except llm.NoModel:
        return None
    return out


def accept(item: object, page_text: str, con=None) -> str:
    """'' if the card is kept, else the reason it is dropped. `con` (the recall index) adds the too-broad check."""
    if not isinstance(item, dict) or not item.get("q") or not item.get("a"):
        return "malformed"
    if secret_like(item["q"] + " " + item["a"]):
        return "secret-like"
    if not ri.faithful(item["a"], page_text):
        return "not-verbatim"
    if not ri.grounded(item, page_text):
        return "question-off-page"
    if con is not None and ri.broad_question(con, item["q"]):
        return "too-broad"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT", ""))
    ap.add_argument("--cli", default="", help="pick a CLI explicitly (goes before any API key)")
    ap.add_argument("--model", default="")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0, help="only the first N stale pages (0 = all)")
    ap.add_argument("--no-verify", action="store_true", help="skip the second model pass (cards stay unverified)")
    ap.add_argument("--dry-run", action="store_true", help="list what would be sent and written; no model call")
    args = ap.parse_args()
    if args.cli:
        os.environ["KROUTER_LEARN_CLI"] = args.cli
    if args.model:
        os.environ["KROUTER_LEARN_MODEL"] = args.model
    vault = Path(args.vault)
    out = ri.zones.path(vault, CARDS)
    cards = load_cards(vault)
    pages = targets(vault)
    sha = {rel: page_sha(vault / rel) for rel in pages}
    valid = {rel: ri.card_hashes((vault / rel).read_bytes()) for rel in pages}
    fresh = {c["rel"] for c in cards if c.get("sha") in valid.get(c["rel"], ())}
    keep = [c for c in cards if c["rel"] in fresh]
    con = ri.connect(ri.cache_path(vault))  # targets() refreshed it
    # 旧卡也按现在的规则复核：检查收紧前写进来的卡（2026-10-10 那批）不该永远躺在文件里、读取时才被拦下。
    # 有卡没过的页整页重问一次；新卡同样过滤，所以下一晚不会再重问
    recheck: set[str] = set()
    page_texts: dict[str, str] = {}
    for c in keep:
        if c.get("empty"):
            continue
        text = page_texts.setdefault(c["rel"], (vault / c["rel"]).read_text(encoding="utf-8", errors="replace"))
        why = accept(c, text, con)
        if why:
            recheck.add(c["rel"])
    if recheck:
        keep = [c for c in keep if c["rel"] not in recheck]
        fresh -= recheck
    stale = [rel for rel in pages if rel not in fresh]
    if args.limit:
        stale = stale[: args.limit]
    batches = [stale[i : i + BATCH] for i in range(0, len(stale), BATCH)]
    if args.dry_run:
        unverified = [c for c in keep if not c.get("empty") and "v" not in c]
        chars = sum(len(PROMPT) + sum(len(block(vault, r)) for r in b) for b in batches)
        chars += sum(len(VERIFY_PROMPT) + len(block(vault, r)) for r in {c["rel"] for c in unverified}) if not args.no_verify else 0
        print(json.dumps({"would_send_pages": stale, "rechecked_pages": sorted(recheck), "would_verify_cards": 0 if args.no_verify else len(unverified),
                          "chars": chars, "writes": [CARDS] if stale or unverified else []}, ensure_ascii=False))
        return 0
    made = empty = 0
    dropped: dict[str, int] = {}
    try:
        with ThreadPoolExecutor(max_workers=args.jobs) as ex:
            parts = list(ex.map(lambda b: ask(vault, b), batches))
    except llm.NoModel as exc:
        print(f"answer cards skipped: {exc}", file=sys.stderr)
        return 0
    fresh_by_rel: dict[str, list[dict]] = {}
    for part in parts:
        for rel, items in part.items():
            page_text = (vault / rel).read_text(encoding="utf-8", errors="replace")
            good = []
            for it in items:
                why = accept(it, page_text, con)
                if why:
                    dropped[why] = dropped.get(why, 0) + 1
                else:
                    good.append({"rel": rel, "sha": sha[rel], "q": it["q"].strip(), "a": it["a"].strip()[:160]})
            fresh_by_rel[rel] = good[:5]
    # 第二遍：模型逐张核对（问题在问这一页、答案答的是这个问题、没说反没添加）。
    # 新写的卡和还没核对过的旧卡一起核对；没有模型可用时卡片保持"未核对"，不当作失败
    pending = {rel: cards for rel, cards in fresh_by_rel.items() if cards}
    for c in keep:
        if not c.get("empty") and "v" not in c:
            pending.setdefault(c["rel"], []).append(c)
    verdict = verify(vault, pending, jobs=args.jobs) if pending and not args.no_verify else None
    failed = set()
    for rel, cards in pending.items():
        for card, ok in zip(cards, (verdict or {}).get(rel, [])):
            if ok:
                card["v"] = 1
            else:
                failed.add(id(card))
    if failed:
        dropped["verify-failed"] = len(failed)
        keep = [c for c in keep if id(c) not in failed]
    for rel, cards in fresh_by_rel.items():
        cards = [c for c in cards if id(c) not in failed]
        if not cards:
            # 导航页或全被拦下：记下这页的哈希，页面不变就不再每晚重问
            keep.append({"rel": rel, "sha": sha[rel], "empty": True})
            empty += 1
        keep.extend(cards)
        made += len(cards)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in keep), encoding="utf-8")
    tmp.replace(out)
    print(json.dumps({"pages": len(pages), "stale": len(stale), "rechecked_pages": len(recheck),
                      "cards_written": made, "dropped": dropped,
                      "verified": sum(1 for c in keep if c.get("v")),
                      "unverified": sum(1 for c in keep if not c.get("empty") and not c.get("v")),
                      "pages_without_cards": empty, "cards_total": sum(1 for c in keep if not c.get("empty"))},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
