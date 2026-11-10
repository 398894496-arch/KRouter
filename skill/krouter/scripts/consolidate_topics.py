#!/usr/bin/env python3
"""Topic dossiers: merge facts scattered across daily logs into one provisional page per topic.

The missing middle layer between episodic logs and curated rule pages. A topic that shows up in
44 daily logs but on no page gets one page: what it is, where it stands, what went wrong, where
each fact came from. Authority pages are linked, not copied. Frontmatter is written here, not by
the model; every wikilink in the body must resolve or it is demoted to plain text. Pages are
regenerated only when their evidence changes.

List: `90 系统文件/自动化/主题档案清单.psv`, one row per topic: `slug|标题|检索词;…|权威页;…`
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm  # noqa: E402
import recall_index as ri  # noqa: E402

LIST = "90 系统文件/自动化/主题档案清单.psv"
OUT_DIR = "02 经验与方法/主题档案"
EVIDENCE_MAX = 30000
SKIP = ("90 系统文件/自动化/下意识", "90 系统文件/自动化/下意识体检")
LOG_RE = re.compile(r"^05 时间日志/(\d{4}-\d{2})/(\d{2})｜")
LINK = re.compile(r"\[\[([^\]|#]+)(#[^\]|]*)?(\|[^\]]*)?\]\]")
SECTIONS = ["一句话", "当前状态", "关键事实", "用户纠错与踩过的坑", "时间线", "未决与不确定", "相关页面"]
PROMPT = """你在为个人知识库写一页「主题档案」。下面是关于主题「{title}」的全部证据：先是权威页，然后是其它页面和按日期从新到旧的时间日志摘录，每段标了来源路径。

硬规则：
1. 只用证据里出现的事实。不知道就不写，不要补常识，不要猜。
2. 每条事实行末尾用 [[来源路径去掉.md]] 标出处；时间日志同时写日期。只能引用证据里出现过的路径。
3. 「当前状态」以最近日期的证据为准，写明截至哪天。新旧说法冲突时，旧说法写进「未决与不确定」或注明已被取代，并给出双方出处。
4. 用户纠正过的做法、踩过的坑，单独写进「用户纠错与踩过的坑」，保留用户原话要点。
5. 有权威页时，「相关页面」把权威页放第一，正文只做摘要和导航，不整段照抄。
6. 不写密钥、token、cookie、账号密码、私人财务细节。
7. 只输出正文，从「## 一句话」开始，依次是这些二级标题：{sections}。最后单独一行：TRIGGERS: 用户以后可能怎么问这个主题的 6–10 个口语短语，用 ; 分隔。

证据：
{evidence}
"""


def load_list(vault: Path) -> list[dict]:
    path = ri.zones.path(vault, LIST)
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = (line.split("|") + ["", "", "", ""])[:4]
        slug, title, terms, auth = (p.strip() for p in parts)
        rows.append({"slug": slug, "title": title, "terms": [t for t in terms.split(";") if t],
                     "auth": [a for a in auth.split(";") if a]})
    return rows


def gather(vault: Path, topic: dict) -> tuple[str, list[str], str]:
    pat = re.compile("|".join(re.escape(t) for t in topic["terms"]), re.I)
    out_prefix = f"{OUT_DIR}/"
    auth_blocks, page_blocks, log_blocks = [], [], []
    latest = ""
    for path, real_rel in ri.iter_markdown(vault):
        rel = ri.zones.canon(vault, real_rel)  # 分类用默认区名；出处写库里的真实路径
        if rel.startswith(out_prefix) or rel.startswith(SKIP):
            continue
        raw_text = path.read_text(encoding="utf-8", errors="replace")
        if ri.is_secret_page(rel, ri.split_frontmatter(raw_text)[0]):
            continue
        text = ri.redact(raw_text)
        is_auth = real_rel in topic["auth"] or real_rel[:-3] in topic["auth"]
        if is_auth:
            auth_blocks.append((real_rel, text[:3500]))
            continue
        lines = text.splitlines()
        hits = [i for i, line in enumerate(lines) if pat.search(line)]
        if not hits:
            continue
        keep: list[str] = []
        last = -9
        for i in hits[:12]:
            lo, hi = max(0, i - 1), min(len(lines), i + 2)
            if lo <= last:
                lo = last + 1
            keep.extend(lines[lo:hi])
            last = hi - 1
        snippet = "\n".join(x for x in keep if x.strip())[:1800]
        m = LOG_RE.match(rel)
        if m:
            day = f"{m.group(1)}-{m.group(2)}"
            latest = max(latest, day)
            log_blocks.append((day, real_rel, snippet))
        else:
            page_blocks.append((len(hits), real_rel, snippet))
    log_blocks.sort(reverse=True)
    page_blocks.sort(reverse=True)
    parts, sources, size = [], [], 0
    for rel, body in auth_blocks:
        parts.append(f"### [权威页] {rel}\n{body}")
        sources.append(rel)
    for _n, rel, snip in page_blocks:
        parts.append(f"### [页面] {rel}\n{snip}")
        sources.append(rel)
    for day, rel, snip in log_blocks:
        parts.append(f"### [时间日志 {day}] {rel}\n{snip}")
        sources.append(rel)
    evidence = ""
    used = []
    for block, src in zip(parts, sources):
        if size + len(block) > EVIDENCE_MAX:
            break
        evidence += block + "\n\n"
        size += len(block)
        used.append(src)
    return evidence, used, latest


def resolve(vault: Path, target: str) -> bool:
    t = target.strip()
    return (vault / t).is_file() or (vault / f"{t}.md").is_file()


def clean_links(vault: Path, body: str) -> tuple[str, int]:
    bad = 0

    def fix(m: re.Match) -> str:
        nonlocal bad
        if resolve(vault, m.group(1)):
            return m.group(0)
        bad += 1
        return f"`{m.group(1)}`（未找到此页）"

    return LINK.sub(fix, body), bad


def call_model(vault: Path, prompt: str) -> str:
    text = llm.complete(prompt, vault)
    if "## 一句话" not in text:
        raise RuntimeError("model output had no 「## 一句话」 section")
    return text[text.index("## 一句话"):].strip()


def llm_label(vault: Path) -> str:
    steps = llm.plan(vault)
    if not steps:
        return "no model"
    kind, detail = steps[0]
    return f"{kind} {Path(detail).name if kind == 'cli' else detail}"


def build(vault: Path, topic: dict, force: bool) -> dict:
    name = f"主题｜{topic['title']}"
    dest = ri.zones.path(vault, f"{OUT_DIR}/{name}.md")
    evidence, sources, latest = gather(vault, topic)
    if not sources:
        return {"slug": topic["slug"], "status": "no-evidence"}
    sha = hashlib.sha1(evidence.encode("utf-8")).hexdigest()[:16]
    if dest.is_file() and not force and f"evidence_sha: {sha}" in dest.read_text(encoding="utf-8"):
        return {"slug": topic["slug"], "status": "unchanged"}
    body = call_model(vault, PROMPT.format(title=topic["title"], sections="、".join(SECTIONS), evidence=evidence))
    triggers = ""
    m = re.search(r"^TRIGGERS:\s*(.+)$", body, re.M)
    if m:
        triggers = m.group(1).strip()
        body = body[: m.start()].rstrip()
    missing = [s for s in SECTIONS if f"## {s}" not in body]
    body, bad = clean_links(vault, body)
    trig = ";".join(dict.fromkeys([*topic["terms"], *[t.strip() for t in triggers.split(";") if t.strip()]]))
    fm = [
        "---", f'title: "{name}"', "type: topic", "status: provisional", "memory_class: result",
        f"triggers: {trig.replace(':', '：')}",
        f"topic_terms: {';'.join(topic['terms'])}",
        f"evidence_through: {latest or '无日志'}", f"evidence_sha: {sha}", f"evidence_sources: {len(sources)}",
        f"generated_at: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}",
        f"generated_by: consolidate_topics.py ({llm_label(vault)})",
        "last_change_writer: krouter-topic-consolidator", "source_kind: vault-evidence-merge", "---", "",
        f"# {name}", "",
        f"> 机器整合的主题档案（provisional），只用库内证据，每条带出处；证据截至 {latest or '—'}。"
        f"采纳并核对后可转 active；权威页以「相关页面」第一条为准。", "", "",
    ]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(fm) + body + "\n", encoding="utf-8")
    return {"slug": topic["slug"], "status": "written", "sources": len(sources), "bad_links": bad,
            "missing_sections": missing, "bytes": dest.stat().st_size}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=os.environ.get("KROUTER_VAULT") or os.environ.get("OBSIDIAN_VAULT", ""))
    ap.add_argument("--cli", default="", help="pick a CLI explicitly (goes before any API key)")
    ap.add_argument("--model", default="")
    ap.add_argument("--only", default="", help="comma-separated slugs")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--dry-run", action="store_true", help="list what would be sent and written; no model call")
    args = ap.parse_args()
    if args.cli:
        os.environ["KROUTER_LEARN_CLI"] = args.cli
    if args.model:
        os.environ["KROUTER_LEARN_MODEL"] = args.model
    vault = Path(args.vault)
    topics = load_list(vault)
    if args.only:
        wanted = set(args.only.split(","))
        topics = [t for t in topics if t["slug"] in wanted]
    from concurrent.futures import ThreadPoolExecutor

    if args.dry_run:
        for t in topics:
            evidence, sources, _latest = gather(vault, t)
            dest = ri.zones.path(vault, f"{OUT_DIR}/主题｜{t['title']}.md")
            sha = hashlib.sha1(evidence.encode("utf-8")).hexdigest()[:16]
            same = dest.is_file() and not args.force and f"evidence_sha: {sha}" in dest.read_text(encoding="utf-8")
            print(json.dumps({"slug": t["slug"], "would": "skip-unchanged" if same or not sources else "send",
                              "chars": 0 if same or not sources else len(PROMPT) + len(evidence),
                              "writes": [] if same or not sources else [dest.relative_to(vault).as_posix()]}, ensure_ascii=False))
        return 0

    def run(t):
        try:
            return build(vault, t, args.force)
        except llm.NoModel as exc:
            return {"slug": t["slug"], "status": "skipped", "error": str(exc)[:200]}
        except Exception as exc:  # 单个主题失败不影响其它主题
            return {"slug": t["slug"], "status": "failed", "error": str(exc)[:200]}

    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for res in ex.map(run, topics):
            print(json.dumps(res, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
