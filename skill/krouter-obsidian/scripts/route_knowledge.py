#!/usr/bin/env python3
"""Windows-safe twin of route_knowledge.sh. Same routes, same receipt keys."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zones
from krouter_home import vault_path
from krouter_redact import redact
from canonical_lookup import (
    map_for,
    load_rows,
    lookup,
    parse_frontmatter,
    query_conflict,
    suggestions,
)

HERE = Path(__file__).resolve().parent
ALLOWED = {
    "status",
    "preference",
    "correction",
    "memory",
    "project",
    "search",
    "suggest",
}
STATUS_FIELDS = (
    "snapshot_at",
    "verified_at",
    "routing_correction_recorded_at",
    "runtime_observed_at",
    "task_runtime_permission_status",
    "daily_automation_cron_status",
    "daily_automation_document_sync_status",
    "daily_automation_sync_reproducibility_status",
    "semantic_retrieval_status",
    "semantic_answers",
    "historical_canonical_source_precision",
    "current_canonical_routing_status",
    "canonical_routing_map_status",
    "canonical_routing_baseline_cases",
    "canonical_routing_baseline_aliases",
    "canonical_routing_increment_cases",
    "canonical_routing_increment_aliases",
    "canonical_routing_cases",
    "canonical_routing_aliases",
    "canonical_routing_verified_at",
    "semantic_retrieval_rerun_status",
    "knowledge_route_receipt_status",
    "obsidian_app_version",
    "unresolved_links_status",
    "overall_execution_gate",
    "status",
    "updated",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def emit_receipt(source: Path, retrieval_status: str, route: str, query: str, vault: Path, map_path: Path) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print("receipt_version: knowledge-route-v2")
    print(f"observed_at: {now}")
    print(f"requested_route: {route}")
    print(f"query: {query}")
    print(f"retrieval_status: {retrieval_status}")
    print(f"source: {source}")
    if source.is_file():
        meta = parse_frontmatter(source)
        if meta.get("status"):
            print(f"source_status: {meta['status']}")
        if meta.get("verified_at"):
            print(f"source_verified_at: {meta['verified_at']}")
        print(f"source_sha256: {sha256_file(source)}")
    if map_path.is_file():
        print(f"canonical_map: {map_path}")
        print(f"canonical_map_sha256: {sha256_file(map_path)}")
    l0 = zones.path(vault, "90 系统文件/自动化/下意识.md")
    if l0.is_file():
        print(f"subconscious: {l0}")
        print(f"subconscious_sha256: {sha256_file(l0)}")
        rows = sum(1 for line in l0.read_text(encoding="utf-8", errors="replace").splitlines() if line.startswith("Q") and line[1:2].isdigit())
        print(f"subconscious_rows: {rows}")
    else:
        print("subconscious: missing")


def emit_daily_seal(health: Path) -> None:
    """Seal date lives only on the health page. Do not copy it onto Agent第二大脑."""
    if not health.is_file():
        print("daily_seal: missing")
        return
    sealed = "missing"
    pending = ""
    through = ""
    for raw in health.read_text(encoding="utf-8", errors="replace").splitlines():
        if raw.startswith("- 最近已封："):
            mark = raw.split("`", 2)
            sealed = mark[1] if len(mark) >= 2 else "none"
        elif raw.startswith("- 待总结"):
            parts = raw.split("`")
            if len(parts) >= 2:
                pending = parts[1]
            found = re.search(r"\d{4}-\d{2}-\d{2}", raw)
            if found:
                through = found.group(0)
    print(f"daily_seal_source: {health}")
    print(f"daily_seal: {sealed}")
    if through:
        print(f"daily_seal_through: {through}")
    if pending:
        print(f"daily_seal_pending: {pending}")


def emit_host_action(health: Path) -> None:
    if not health.is_file():
        return
    meta = parse_frontmatter(health)
    lamp = meta.get("lamp") or "unset"
    key = meta.get("self_evolution_key") or "missing"
    writer = meta.get("krouter_writer") or "missing"
    print(f"health: {health}")
    print(f"lamp: {lamp}")
    print(f"self_evolution_key: {key}")
    print(f"krouter_writer: {writer}")
    if key != "present" or writer != "present":
        print(
            "host_action: Distill needs a callable model. Paste *_API_KEY on "
            "90 系统文件/自动化/自进化钥匙.md (flagship is auto-locked), or log in "
            "grok / official Codex / claude (your subscription); other CLIs (opencode, kimi, …) run unconfined and "
            "are used only with KROUTER_ALLOW_UNCONFINED=1 in the keys file. Timer already on. "
            "Do not print secrets."
        )
    nightly = meta.get("nightly") or ""
    if nightly:
        at = meta.get("nightly_at") or ""
        print(f"nightly: {nightly}")
        print(f"nightly_at: {at}")
        stale = False
        try:
            stale = lamp == "running" and (datetime.now() - datetime.fromisoformat(at)).days >= 3
        except ValueError:
            pass
        if nightly in {"skipped", "failed"} or stale:
            why = "has not run for 3+ days" if stale and nightly not in {"skipped", "failed"} else nightly
            print(f"host_action: Nightly upkeep {why}; see 90 系统文件/自动化/夜间维护.md for each step's reason. "
                  "Model steps need the writer's lane (a *_API_KEY, or a logged-in grok / Codex / claude / …).")


def emit_suggestions(query: str, vault: Path, map_path: Path) -> None:
    if not query or not map_path.is_file():
        return
    rows = load_rows(map_path)
    conflict = query_conflict(query, rows, vault=vault)
    if conflict:
        left_id, left_alias, left_source, left_score = conflict["left"]
        right_id, right_alias, right_source, right_score = conflict["right"]
        print("conflict: yes")
        print(f"conflict_kind: {conflict['kind']}")
        print(f"conflict_left: {left_id}|{left_alias}|{left_source}|{left_score}")
        print(f"conflict_right: {right_id}|{right_alias}|{right_source}|{right_score}")
        print(f"host_prompt: {conflict['host_prompt']}")
    else:
        print("conflict: no")
    hits = suggestions(query, rows, 5, vault=vault)
    if not hits:
        return
    print("canonical_match: false")
    print("suggestions:")
    for score, case_id, alias, source in hits:
        if (vault / source).is_file():
            print(f"- {case_id} alias={alias} source={source} score={score}")


def how_for(vault: Path, case_id: str, anchor: str) -> tuple[str, bool]:
    l0 = zones.path(vault, "90 系统文件/自动化/下意识.md")
    if not l0.is_file():
        return anchor, False
    for line in l0.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split("|")
        if parts and parts[0] == case_id and len(parts) >= 4:
            flag = parts[4].strip() if len(parts) > 4 else ""
            return parts[3], flag == "yes"
    return anchor, False



def log_query(route: str, query: str, status: str, top: str = "", confidence: str = "") -> None:
    """One JSONL line per routed query, outside the vault. Feeds nightly trigger learning. Never fails the route."""
    if not query or os.environ.get("KROUTER_NO_QUERY_LOG") == "1":
        return
    try:
        import json

        base = Path(os.environ.get("KROUTER_STATE_DIR") or Path.home() / ".local" / "state" / "krouter")
        base.mkdir(parents=True, exist_ok=True)
        row = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "route": route, "q": redact(query),
               "status": status, "top": top, "confidence": confidence}
        with (base / "queries.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass

def canonical_lookup(query: str, vault: Path, map_path: Path, route: str) -> bool:
    if not query or not map_path.is_file():
        return False
    rows = load_rows(map_path)
    hit = lookup(query, rows, vault=vault)
    if hit is None:
        return False
    case_id, relative, anchor = hit
    source = vault / relative
    if not source.is_file():
        print(f"Canonical source missing: {source}", file=sys.stderr)
        return False
    emit_receipt(source, "canonical-match", route, query, vault, map_path)
    log_query(route, query, "canonical-match", relative, "lock")
    print("route: canonical")
    print(f"canonical_id: {case_id}")
    print(f"canonical_source: {source}")
    print("canonical_match: true")
    how, correction_first = how_for(vault, case_id, anchor)
    if correction_first:
        print("correction_first: yes")
    print(f"how: {how}")
    print("open_page: only if how does not close the question")
    return True


def md_search(needle: str, scope: Path, max_per_file: int = 4, max_lines: int = 24) -> None:
    rg = shutil.which("rg")
    if rg:
        proc = subprocess.run(
            [
                rg,
                "-L",
                "-F",
                "-n",
                "-i",
                "-C",
                "1",
                "-m",
                str(max_per_file),
                "--glob",
                "*.md",
                "--glob",
                "!Clippings/**",
                "--",
                needle,
                str(scope),
            ],
            capture_output=True,
            text=True,
        )
        lines = (proc.stdout or "").splitlines()
    else:
        lines = []
        needle_l = needle.lower()
        paths = [scope] if scope.is_file() else list(scope.rglob("*.md"))
        for path in paths:
            if "Clippings" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            hits = 0
            body = text.splitlines()
            for idx, line in enumerate(body):
                if needle_l not in line.lower():
                    continue
                hits += 1
                start = max(0, idx - 1)
                end = min(len(body), idx + 2)
                for j in range(start, end):
                    lines.append(f"{path}:{j + 1}:{body[j]}")
                if hits >= max_per_file:
                    break
    from krouter_redact import is_secret_page

    hit = re.compile(r"^(.*?\.md)[:-]\d+[:-]")
    lines = [ln for ln in lines if not ((m := hit.match(ln)) and is_secret_page(m.group(1).rsplit("/", 1)[-1]))]
    for i, line in enumerate(lines):
        if i >= max_lines:
            print("[truncated after 24 lines]")
            return
        print(redact(line))  # 字面搜索打出来的原文行也不能带出密钥；机密页的行整行不出


def print_recall(res: dict, vault: Path, lines: int) -> None:
    from recall_index import PARTIAL_NOTE, best_lines

    print(f"recall_confidence: {res.get('confidence', 'none')}")
    print(f"recall_margin: {res.get('margin', 0)}")
    print(f"recall_strong_terms: {res.get('strong', 0)}")
    if res.get("partial"):
        print(PARTIAL_NOTE)
    print("recall:")
    for h in res["hits"]:
        flag = f" status={h['status']}" if h["status"] else ""
        print(f"- {h['rel']} tier={h['tier']}{flag} score={h['score']}")
        if h.get("answer"):
            print(f"  answer (generated): {redact(h['answer'])}")
        if h["how"]:
            print(f"  how: {h['how']}")
        for ln, text in best_lines(vault / h["rel"], res["query_tokens"], lines):
            print(f"  L{ln}: {text}")


def bounded_search(scope: Path, vault: Path, map_path: Path, route: str, query: str) -> None:
    res = None
    try:
        from recall_index import recall

        rel = "" if scope == vault else scope.relative_to(vault).as_posix()
        res = recall(vault, query, rel, limit=3)
    except Exception:  # 召回缓存不可用时退回字面检索
        res = None
    widened = False
    if (res is None or not res["hits"] or res.get("confidence") == "none") and scope != vault:
        # 路由范围（单个偏好/纠错页、01 项目）里没有答案：扩到全库，规则页优先，并如实标出
        try:
            wide = recall(vault, query, "", limit=3)
            if wide["hits"] and wide.get("confidence") != "none":
                res, widened = wide, True
        except Exception:
            pass
    if res and res["hits"] and res.get("confidence") != "none":
        emit_receipt(scope, "ranked-recall-complete", route, query, vault, map_path)
        log_query(route, query, "ranked-recall-complete" + ("+widened" if widened else ""), res["hits"][0]["rel"], res.get("confidence", ""))
        emit_suggestions(query, vault, map_path)
        print(f"route: {route}")
        print(f"scope: {scope}")
        if widened:
            print("scope_widened: vault (the route scope had no page covering this question)")
        print_recall(res, vault, 4 if (scope.is_file() and not widened) else 1)
        print("open_page: only the top recall hit, and only if its how does not close the question")
        return
    emit_receipt(scope, "bounded-literal-search-complete", route, query, vault, map_path)
    log_query(route, query, "bounded-literal-search-complete")
    emit_suggestions(query, vault, map_path)
    print(f"route: {route}")
    print(f"scope: {scope}")
    if res is not None:
        print("recall: none (no page covers enough of the question; do not guess)")
    md_search(query, scope)


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "usage: route_knowledge.py {status|preference|correction|memory|project|search|suggest} [literal query]",
            file=sys.stderr,
        )
        return 2
    route = sys.argv[1]
    query = sys.argv[2] if len(sys.argv) > 2 else ""
    vault_raw = vault_path()
    if not vault_raw:
        print("set OBSIDIAN_VAULT to your vault root (or run the one-line install, which records it)", file=sys.stderr)
        return 2
    vault = Path(vault_raw)
    if not vault.is_dir():
        print(f"Vault not found: {vault}", file=sys.stderr)
        return 1
    if route not in ALLOWED:
        print(
            "usage: route_knowledge.py {status|preference|correction|memory|project|search|suggest} [literal query]",
            file=sys.stderr,
        )
        return 2
    map_path = map_for(vault)
    canonical = zones.path(vault, "Agent第二大脑.md")
    health = zones.path(vault, "90 系统文件/自动化/日更健康.md")
    scopes = {
        "preference": zones.path(vault, "02 经验与方法/Agent/用户偏好与工作约束.md"),
        "correction": zones.path(vault, "90 系统文件/Agent记忆/纠错与取代记录.md"),
        "memory": zones.path(vault, "90 系统文件/Agent记忆/可靠记忆索引.md"),
        "project": zones.path(vault, "01 项目"),
        "search": vault,
    }
    if route in scopes and query and canonical_lookup(query, vault, map_path, route):
        return 0
    if route == "status":
        emit_receipt(canonical, "requested-fields-returned", route, query, vault, map_path)
        print("route: status")
        print("evidence_scope: selected-frontmatter-fields")
        print("l0: how is on the lock receipt; do not ingest 下意识.md")
        if canonical.is_file():
            meta = parse_frontmatter(canonical)
            for field in STATUS_FIELDS:
                if field in meta:
                    print(f"{field}: {meta[field]}")
        emit_daily_seal(health)
        emit_host_action(health)
        return 0
    if route == "suggest":
        if not query:
            print(
                "usage: route_knowledge.py {status|preference|correction|memory|project|search|suggest} [literal query]",
                file=sys.stderr,
            )
            return 2
        emit_receipt(map_path, "alias-suggestions", route, query, vault, map_path)
        emit_suggestions(query, vault, map_path)
        return 0
    if route in scopes:
        if not query:
            print(
                "usage: route_knowledge.py {status|preference|correction|memory|project|search|suggest} [literal query]",
                file=sys.stderr,
            )
            return 2
        bounded_search(scopes[route], vault, map_path, route, query)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
