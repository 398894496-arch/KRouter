#!/usr/bin/env python3
"""Compile the L0 standing index (下意识) from the alias map + source frontmatter.

Read-only on sources. Writes one generated page. Expired / not-yet-valid rows stay out of L0.
Agents load that page; they open a vault page only after a lock hit.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path

import sys

import zones
from canonical_lookup import in_force, load_rows, map_for, parse_frontmatter

REL = "90 系统文件/自动化/下意识.md"
HOW_MAX = 80
CLASSES = {"constraint", "result", "method", "evidence", "episodic"}


def kind_for(source: str, fm: dict[str, str]) -> str:
    tagged = (fm.get("memory_class") or "").strip()
    if tagged in CLASSES:
        return tagged
    if tagged in {"router", "preference", "correction"}:
        return "constraint"
    if "纠错" in source:
        return "constraint"
    if "偏好" in source or "约束" in source:
        return "constraint"
    if "准经验" in source:
        return "method"
    if source.startswith("02 "):
        return "method"
    if source.startswith("01 "):
        return "result"
    if source.startswith("04 "):
        return "result"
    if source.startswith("03 "):
        return "evidence"
    if source.startswith("05 "):
        return "episodic"
    return "constraint"


def pipe_safe(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("|", "/")).strip()


def how_for(anchor: str, fm: dict[str, str]) -> str:
    # Map evidence anchor is the standing one-liner. Page title is just the file name.
    raw = fm.get("how") or anchor or fm.get("title") or ""
    text = pipe_safe(raw)
    if len(text) > HOW_MAX:
        text = text[: HOW_MAX - 1].rstrip() + "…"
    return text


def nonempty_meta(raw: str) -> bool:
    v = (raw or "").strip().lower()
    return v not in {"", "[]", "{}", "none", "null", "false", "no", "0", "-"}


def correction_flag(source: str, fm: dict[str, str], aliases: list[str]) -> str:
    if "纠错" in source:
        return "yes"
    if nonempty_meta(fm.get("correction", "")):
        return "yes"
    if nonempty_meta(fm.get("supersedes", "")):
        return "yes"
    joined = ";".join(aliases).lower()
    if "correction" in joined or "supersedes" in joined or "纠错" in joined:
        return "yes"
    return "no"


def compile_rows(
    vault: Path,
    map_path: Path,
    today: date | None = None,
) -> list[str]:
    today = today or date.today()
    lines: list[str] = []
    for case_id, aliases, source, anchor in load_rows(map_path):
        path = vault / source
        fm = parse_frontmatter(path)
        live, valid_from, invalid_at = in_force(fm, today)
        if not live:
            continue
        if not path.is_file():
            continue
        kind = kind_for(zones.canon(vault, source), fm)
        how = how_for(anchor, fm)
        flag = correction_flag(source, fm, aliases)
        alias_s = pipe_safe(";".join(aliases))
        lines.append(
            "|".join(
                [
                    case_id,
                    kind,
                    alias_s,
                    how,
                    flag,
                    valid_from,
                    invalid_at,
                    source,
                ]
            )
        )
    return lines


def render(lines: list[str], map_sha: str, generated_at: str) -> str:
    body = [
        "---",
        "title: 下意识",
        "status: generated",
        f"generated_at: {generated_at}",
        f"row_count: {len(lines)}",
        f"canonical_map_sha256: {map_sha}",
        "---",
        "",
        "# 下意识",
        "",
        "L0 standing index. Load this page. Open a vault page only after a lock hit.",
        "Do not dump the vault into context. `correction:yes` → run the correction route first.",
        "No lock → the router answers with L1 recall (ranked pages + one-line `how`, rule pages first).",
        "`recall: none` means no page covers the question: say so, do not guess.",
        "",
        "# id|kind|aliases|how|correction|valid_from|invalid_at|source",
        *lines,
        "",
    ]
    return "\n".join(body)


def file_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_vault(
    vault: Path,
    map_path: Path | None = None,
    out: Path | None = None,
    today: date | None = None,
) -> Path:
    vault = vault.resolve()
    map_path = (map_path or map_for(vault)).resolve()
    dest = out or zones.path(vault, REL)
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = compile_rows(vault, map_path, today=today)
    map_sha = file_sha256(map_path) if map_path.is_file() else ""
    generated_at = datetime.now().isoformat(timespec="seconds")
    dest.write_text(render(lines, map_sha, generated_at), encoding="utf-8")
    return dest


# ---------- the standing index handed to the host at session start (2.0) ----------
#
# The hook's lock catches a page by its name. People mostly mention a thing in other words (set 32: 7 of 24), and a
# lookup by words cannot see that; the host model can, when the list of things the vault knows is in front of it. So
# the session-start hook hands over this index: one line per topic (its name, other names, what was decided, the
# page), live pages only, a line budget, and one usage line that says how to fetch a page, with no tool assumed.

INDEX_LINES = 60          # 主题行数上限
INDEX_CHARS = 5400        # 索引正文的字数上限（Claude Code 单条 additionalContext 上限 10,000 字，会话开始还要带决定和经验）
INDEX_HOW = {"zh": 26, "en": 48}
INDEX_NAMES = 1           # 每行最多列几个别的叫法
INDEX_HEAD = {
    "zh": "KRouter 下意识索引（用户记忆库里定过的事，每行：名字／别的叫法：定了什么〔页〕；不是用户说的话）：",
    "en": "KRouter standing index (things the user's vault has settled; each line: name / other names: what was "
          "decided [page]; not something the user said):",
}
INDEX_TAIL = {
    "zh": ("用法：用户的话提到上面任何一件事，哪怕换了说法、没说名字，回答前先取那一页：调用 krouter_ask（MCP 服务 "
           "krouter，工具列表里没有就按名字找），问题写那件事的名字；没有这个工具就在终端运行 {cmd}，或直接读 {vault}/〔页〕。"
           "只取和这句话最相关的那一页，回答里注明出处页。用户粘贴的代码、日志、命令输出里碰巧出现的词不算提到。"
           "和用户的话无关就什么都不做，也不要提这份索引。{more}"),
    "en": ("How to use: when the user's message touches anything listed above, even in other words and without its "
           "name, fetch that page before answering: call krouter_ask (MCP server krouter; look it up by name if your "
           "tool list does not show it) with the thing's name; with no such tool, run {cmd} in a terminal, or read "
           "{vault}/[page]. Fetch only the one page that bears on the message most, and cite it in your answer. A "
           "word that merely appears inside code, a log or command output the user pasted is not a mention. If "
           "nothing listed bears on the message, do nothing and do not mention this index.{more}"),
}
INDEX_MORE = {"zh": "库里还有 {n} 件没列出，别的事也可以照样先查。", "en": " {n} more are not listed; the same applies to them."}
INDEX_FULL_MIN = 0.2      # 主题多时，整行至少占预算的这么多（排在最前的那些），其余的主题只列名字
INDEX_NAMES_HEAD = {"zh": "也记着（只列名字，提到了同样先取那一页）：", "en": "Also known (names only; the same applies): "}


def _tail_jsonl(path: Path, limit: int = 2_000_000) -> list[dict]:
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - limit))
            data = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for line in data.splitlines()[1 if len(data) >= limit else 0:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def last_used(vault: Path) -> dict[str, str]:
    """{page: newest time it was brought by the prompt hook or cited by a lookup}, from the state folder's logs."""
    import os

    base = Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local/state/krouter")
    seen: dict[str, str] = {}
    for row in _tail_jsonl(base / "recalled.jsonl"):
        if row.get("page"):
            seen[row["page"]] = max(seen.get(row["page"], ""), str(row.get("ts", "")))
    for row in _tail_jsonl(base / "queries.jsonl"):
        for rel in ([row.get("top")] if row.get("top") else []) + list(row.get("pages") or []):
            if rel:
                seen[rel] = max(seen.get(rel, ""), str(row.get("ts", "")))
    return seen


def index_topics(vault: Path, today: date | None = None) -> list[dict]:
    """One topic per live page the alias table names: [{rel, name, others, how, rule, when}], best first (rule pages,
    then the newest of last used and last updated). A row on a replaced page counts for the page that replaced it."""
    import recollect
    import recall_index as ri

    today = today or date.today()
    mp = map_for(vault)
    if not mp.is_file():
        return []
    try:
        rows = load_rows(mp)
    except ValueError:
        return []
    topics: dict[str, dict] = {}
    for case_id, aliases, source, anchor in rows:
        cur = recollect.current(vault, source, today)
        if cur is None:
            continue
        rel = cur[0]
        t = topics.setdefault(rel, {"rel": rel, "names": [], "anchor": "", "direct": False})
        direct = rel == source
        names = [a for a in aliases if a not in t["names"]]
        t["names"] = (names + t["names"]) if direct and not t["direct"] else (t["names"] + names)
        if direct and not t["direct"]:
            t["anchor"], t["direct"] = anchor, True
    used = last_used(vault)
    out = []
    for rel, t in topics.items():
        fm, body = recollect.page(vault, rel) or ({}, "")
        canon = zones.canon(vault, rel)
        how = fm.get("how") or t["anchor"] or recollect.gist(body) or fm.get("title") or Path(rel).stem
        updated = str(fm.get("date") or fm.get("valid_from") or fm.get("verified_at") or "")[:10]
        if not updated:
            try:
                updated = date.fromtimestamp((vault / rel).stat().st_mtime).isoformat()
            except OSError:
                updated = ""
        when = max(updated, used.get(canon, "")[:10])
        out.append({"rel": canon, "name": t["names"][0] if t["names"] else Path(rel).stem,
                    "others": t["names"][1:], "how": how, "rule": ri.tier_of(canon, fm.get("status", "")) == "rule",
                    "when": when})
    out.sort(key=lambda x: (not x["rule"], "".join(chr(0x10FFFF - ord(c)) for c in x["when"]), x["name"]))
    return out


def standing_index(vault: Path, today: date | None = None, lines: int = INDEX_LINES, chars: int = INDEX_CHARS) -> str:
    """The session-start index: at most `lines` topics within `chars` characters, then the usage line."""
    import shlex

    from krouter_redact import redact

    topics = index_topics(vault, today)
    if not topics:
        return ""
    lang = "en" if zones.lang(vault) == "en" else "zh"
    body, used = [], 0
    rows = []
    for t in topics:
        cjk = bool(re.search(r"[\u3400-\u9fff]", t["how"] + t["name"]))
        n = INDEX_HOW["zh" if cjk else "en"]
        how = re.sub(r"\s+", " ", t["how"]).strip()
        how = how if len(how) <= n else how[: n - 1].rstrip() + "…"
        names = "／".join([t["name"]] + t["others"][:INDEX_NAMES]) if cjk else " / ".join([t["name"]] + t["others"][:INDEX_NAMES])
        rows.append((t, redact(f"- {names}：{how}〔{t['rel']}〕" if cjk else f"- {names}: {how} [{t['rel']}]")))
    fits = sum(len(r) + 1 for _t, r in rows[:lines]) <= chars and len(rows) <= lines
    # 放不下时：先给每个主题的名字留位置（一个几个字），剩下的预算再按排序给前面的主题整行
    names_len = len(INDEX_NAMES_HEAD[lang]) + sum(len(t["name"]) + 1 for t in topics)
    full_room = chars if fits else max(int(chars * INDEX_FULL_MIN), chars - names_len)
    rest = []
    for t, line in rows:
        if len(body) < lines and used + len(line) + 1 <= full_room and not rest:
            body.append(line)
            used += len(line) + 1
        else:
            rest.append(t)
    # 放不下整行的：只列名字（和页名），一个主题几个字，两三百个主题也装得下
    named, shown = [], 0
    head = INDEX_NAMES_HEAD[lang]
    room = chars - used - len(head)
    for t in rest:
        item = t["name"]  # 名字就是别名：拿它去 krouter_ask 正好锁到那一页
        if room - (len(item) + 1) < 0:
            break
        named.append(item)
        room -= len(item) + 1
    if named:
        body.append(head + ("、" if lang == "zh" else "; ").join(named))
    shown = len(body) - (1 if named else 0) + len(named)
    more = len(topics) - shown
    script = Path(__file__).resolve().with_name("route_knowledge.sh")
    cmd = f"sh {shlex.quote(str(script))} search '<{'名字' if lang == 'zh' else 'name'}>'"
    tail = INDEX_TAIL[lang].format(cmd=cmd, vault=str(vault), more=INDEX_MORE[lang].format(n=more) if more else "")
    return "\n".join([INDEX_HEAD[lang], *body, tail])


def est_tokens(text: str) -> int:
    """Upper-end estimate used by the benches (no tokenizer downloaded): one per CJK character, one per three others."""
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    return cjk + (len(text) - cjk + 2) // 3


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile KRouter L0 下意识 index")
    parser.add_argument("--vault", required=True)
    parser.add_argument("--map", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--today", default="")
    parser.add_argument("--index", action="store_true", help="print the session-start standing index instead")
    args = parser.parse_args()
    today = date.fromisoformat(args.today) if args.today else None
    if args.index:
        text = standing_index(Path(args.vault), today)
        print(text)
        print(f"({len(text)} characters, about {est_tokens(text)} tokens)", file=sys.stderr)
        return 0
    dest = compile_vault(
        Path(args.vault),
        Path(args.map) if args.map else None,
        Path(args.out) if args.out else None,
        today=today,
    )
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
