#!/usr/bin/env python3
"""Pick one canonical row for a literal query. Exit 1 if none or ambiguous."""
from __future__ import annotations

import argparse
import os
import sys
import unicodedata
from datetime import date
from pathlib import Path

# 别名表是宿主的资产，放在库里（跟着库同步、进库的 git 快照），代码目录里那份只是样例兜底。
MAP_REL = "90 系统文件/canonical_sources.psv"


def map_for(vault: Path | None) -> Path:
    """The alias table in force: `KROUTER_MAP`, else the vault's own table, else the shipped sample."""
    raw = os.environ.get("KROUTER_MAP", "").strip()
    if raw:
        return Path(raw)
    if vault is not None:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import zones

        if zones.path(vault, MAP_REL).is_file():
            return zones.path(vault, MAP_REL)
    return Path(__file__).resolve().parent / "canonical_sources.psv"


PARTICLES = set("的了着过地得")


def parse_frontmatter(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    found: dict[str, str] = {}
    for raw in parts[1].splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        name, val = line.split(":", 1)
        found[name.strip()] = val.strip().strip('"').strip("'")
    return found


def parse_day(raw: str) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


DEAD_STATUSES = {"superseded", "retired", "rejected", "deprecated", "archived"}


def in_force(fm: dict[str, str], today: date) -> tuple[bool, str, str]:
    valid_from = parse_day(fm.get("valid_from") or fm.get("verified_at") or "")
    invalid_at = parse_day(fm.get("invalid_at") or "")
    valid_s = valid_from.isoformat() if valid_from else ""
    invalid_s = invalid_at.isoformat() if invalid_at else ""
    # a replaced or rejected page must not be claimed by the lock or listed in L0
    if (fm.get("status") or "").strip().lower() in DEAD_STATUSES:
        return False, valid_s, invalid_s
    if valid_from and valid_from > today:
        return False, valid_s, invalid_s
    if invalid_at and invalid_at <= today:
        return False, valid_s, invalid_s
    return True, valid_s, invalid_s


def live_rows(
    rows: list[tuple[str, list[str], str, str]],
    vault: Path | None,
    today: date | None = None,
) -> list[tuple[str, list[str], str, str]]:
    """Drop expired / not-yet-valid / missing sources when a vault is given."""
    if vault is None:
        return rows
    today = today or date.today()
    kept: list[tuple[str, list[str], str, str]] = []
    for case_id, aliases, source, anchor in rows:
        path = vault / source
        if not path.is_file():
            continue
        live, _, _ = in_force(parse_frontmatter(path), today)
        if live:
            kept.append((case_id, aliases, source, anchor))
    return kept


def normalize(value: str) -> str:
    chars: list[str] = []
    for char in value:
        if char in PARTICLES or char.isspace():
            continue
        if unicodedata.category(char).startswith(("P", "S")):
            continue
        chars.append(char.lower())
    return "".join(chars)


def load_rows(path: Path) -> list[tuple[str, list[str], str, str]]:
    rows: list[tuple[str, list[str], str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith("#"):
            continue
        parts = raw.split("|", 3)
        if len(parts) != 4:
            raise ValueError(f"routing map row: {raw}")
        case_id, aliases_raw, source, anchor = parts
        aliases = [item.strip() for item in aliases_raw.split(";") if item.strip()]
        rows.append((case_id, aliases, source, anchor))
    return rows


def stands_in_for(q: str, a: str) -> bool:
    """A query shorter than the alias may stand in for it only when it is most of it.

    `how` sits inside `how to handle clippings` without meaning it, so a latin
    fragment has to carry the alias. One CJK character already carries a word.
    """
    if all(ord(char) < 128 for char in q):
        return len(q) >= 4 and len(q) * 2 >= len(a)
    return len(q) >= 2


LOCK_BAND = 100


def carries(a: str, q: str) -> bool:
    """An alias inside a longer question locks only when it carries the question.

    `日更` sits inside `日更能不能交给云端跑` without being what the question is about.
    """
    return len(a) >= 4 or len(a) * 2 >= len(q)


def alias_score(query: str, alias: str) -> int:
    q = normalize(query)
    a = normalize(alias)
    if not q or not a:
        return 0
    if a == q:
        return 1000 + len(a)
    if a in q:
        # below LOCK_BAND: still ranks the suggestion, never claims the page
        return 500 + len(a) if carries(a, q) else 60 + len(a)
    if q in a and stands_in_for(q, a):
        return 100 + len(q)
    return 0


HINT_FUNCTION = set("的了我你他她它吗呢吧啊么什怎样哪是有在要不能会该这那个")


def is_cjk(char: str) -> bool:
    return "\u3400" <= char <= "\u9fff"


def near_score(query: str, alias: str) -> int:
    """Weaker overlap for suggestions only. Never used as a canonical hit."""
    hit = alias_score(query, alias)
    if hit:
        return hit
    q = normalize(query)
    a = normalize(alias)
    if len(q) < 2 or len(a) < 2:
        return 0
    n = 0
    for left, right in zip(q, a):
        if left != right:
            break
        n += 1
    if n >= 2:
        return 40 + n
    # 汉字只算连着的双字，而且不算虚字双字：零散的单字（「剪辑」和「剪藏原件」共有「剪」「件」）、
    # 「什么」这种问句词，都不说明问的是这一页
    shared = {q[i:i + 2] for i in range(len(q) - 1)} & {a[i:i + 2] for i in range(len(a) - 1)}
    shared = {b for b in shared if is_cjk(b[0]) and is_cjk(b[1]) and not set(b) & HINT_FUNCTION}
    if shared:
        return 21 + len(shared)
    overlap = len({c for c in set(q) & set(a) if not is_cjk(c)})
    if overlap >= 2:
        return 20 + overlap
    return 0


def scores_for(query: str, rows: list[tuple[str, list[str], str, str]]) -> dict[str, int]:
    scores: dict[str, int] = {}
    for case_id, aliases, _source, _anchor in rows:
        best = 0
        for alias in aliases:
            best = max(best, alias_score(query, alias))
        if best >= LOCK_BAND:
            scores[case_id] = best
    return scores


def pick(scores: dict[str, int], source_by_id: dict[str, str]) -> str | None:
    if not scores:
        return None
    top = max(scores.values())
    winners = [case_id for case_id, score in scores.items() if score == top]
    if len(winners) == 1:
        return winners[0]
    if len({source_by_id[case_id] for case_id in winners}) == 1:
        return sorted(winners)[0]
    return None


def lookup(
    query: str,
    rows: list[tuple[str, list[str], str, str]],
    vault: Path | None = None,
    today: date | None = None,
) -> tuple[str, str, str] | None:
    rows = live_rows(rows, vault, today)
    source_by_id = {case_id: source for case_id, _aliases, source, _anchor in rows}
    winner = pick(scores_for(query, rows), source_by_id)
    if winner is None and len(query.split()) > 1:
        # Token fallback: only whole-alias hits count. A token that is just a fragment of an
        # alias (`纠错` in `纠错优先级`) must not speak for the rest of `Claude Code 纠错`.
        token_scores: dict[str, int] = {}
        for token in query.split():
            for case_id, score in scores_for(token, rows).items():
                if score < 500:
                    continue
                token_scores[case_id] = token_scores.get(case_id, 0) + score
        winner = pick(token_scores, source_by_id)
    if winner is None:
        return None
    for case_id, _aliases, source, anchor in rows:
        if case_id == winner:
            return case_id, source, anchor
    return None


def suggestions(
    query: str,
    rows: list[tuple[str, list[str], str, str]],
    limit: int = 5,
    vault: Path | None = None,
    today: date | None = None,
) -> list[tuple[int, str, str, str]]:
    rows = live_rows(rows, vault, today)
    ranked: list[tuple[int, str, str, str]] = []
    for case_id, aliases, source, _anchor in rows:
        best = 0
        best_alias = aliases[0] if aliases else ""
        for alias in aliases:
            score = near_score(query, alias)
            if score > best:
                best = score
                best_alias = alias
        if best:
            ranked.append((best, case_id, best_alias, source))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ranked[:limit]


def query_conflict(
    query: str,
    rows: list[tuple[str, list[str], str, str]],
    vault: Path | None = None,
    today: date | None = None,
) -> dict | None:
    """Ask the host when a miss is a tie between two different pages in the hit band.

    Hit band is alias_score >= 100. Weak overlap hints (20–40) are not a choice.
    """
    live = live_rows(rows, vault, today)
    if lookup(query, rows, vault=vault, today=today) is not None:
        return None
    source_by_id = {case_id: source for case_id, _aliases, source, _anchor in live}
    scores = scores_for(query, live)
    if not scores:
        token_scores: dict[str, int] = {}
        for token in query.split():
            for case_id, score in scores_for(token, live).items():
                token_scores[case_id] = token_scores.get(case_id, 0) + score
        scores = token_scores
    if not scores:
        return None
    top = max(scores.values())
    if top < 100:
        return None
    winners = [case_id for case_id, score in scores.items() if score == top]
    files = {source_by_id[cid] for cid in winners if cid in source_by_id}
    if len(winners) < 2 or len(files) < 2:
        return None
    left_id, right_id = sorted(winners)[:2]

    def named(case_id: str) -> tuple[str, str]:
        for cid, aliases, source, _anchor in live:
            if cid != case_id:
                continue
            best = 0
            name = aliases[0] if aliases else case_id
            for alias in aliases:
                score = alias_score(query, alias)
                if score > best:
                    best = score
                    name = alias
            return name, source
        return case_id, ""

    left_alias, left_source = named(left_id)
    right_alias, right_source = named(right_id)
    return {
        "kind": "ambiguous-query",
        "left": (left_id, left_alias, left_source, top),
        "right": (right_id, right_alias, right_source, top),
        "host_prompt": (
            f"「{query}」同时打到 {left_id}（{left_alias} → {left_source}）"
            f"和 {right_id}（{right_alias} → {right_source}）。锁不能猜。选一个，或说都不是。"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", required=True)
    parser.add_argument("--vault", required=True)
    parser.add_argument("--query", default="")
    parser.add_argument("--suggest", action="store_true")
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    rows = load_rows(Path(args.map))
    vault = Path(args.vault)

    if args.explain:
        if not args.query:
            return 2
        conflict = query_conflict(args.query, rows, vault=vault)
        if not conflict:
            sys.stdout.write("conflict: no\n")
            return 0
        left_id, left_alias, left_source, left_score = conflict["left"]
        right_id, right_alias, right_source, right_score = conflict["right"]
        sys.stdout.write("conflict: yes\n")
        sys.stdout.write(f"conflict_kind: {conflict['kind']}\n")
        sys.stdout.write(
            f"conflict_left: {left_id}|{left_alias}|{left_source}|{left_score}\n"
        )
        sys.stdout.write(
            f"conflict_right: {right_id}|{right_alias}|{right_source}|{right_score}\n"
        )
        sys.stdout.write(f"host_prompt: {conflict['host_prompt']}\n")
        return 0

    if args.suggest:
        if not args.query:
            return 2
        for score, case_id, alias, relative_source in suggestions(
            args.query, rows, args.limit, vault=vault
        ):
            source = vault / relative_source
            if not source.is_file():
                continue
            sys.stdout.write(f"{case_id}|{alias}|{relative_source}|{score}\n")
        return 0

    if not args.query:
        return 2
    hit = lookup(args.query, rows, vault=vault)
    if hit is None:
        return 1
    case_id, relative_source, anchor = hit
    source = vault / relative_source
    if not source.is_file():
        print(f"Canonical source missing: {source}", file=sys.stderr)
        return 1
    sys.stdout.write(f"{case_id}|{relative_source}|{anchor}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
