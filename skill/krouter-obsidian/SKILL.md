---
name: krouter-obsidian
description: KRouter Obsidian — route knowledge-dependent tasks to the smallest current evidence set in an Obsidian vault using deterministic local search. Use when a request depends on durable user preferences, prior corrections or superseded claims, long-term project history or results, reusable methods or evidence, or the current vault and automation state. Return evidence in-process; do not spawn a retrieval model or add embeddings.
---

# KRouter Obsidian

Set `OBSIDIAN_VAULT` to the vault root. Run retrieval in the current process. Do not spawn a retrieval agent. Do not add vector storage.

Router script (after install): `$HOME/.agents/skills/krouter-obsidian/scripts/route_knowledge.sh`. On Windows use `python3 route_knowledge.py` (same routes).

## Workflow

1. Run `route_knowledge.sh status`. If the receipt has `host_action:`, tell the host that line (paste `*_API_KEY` on `90 系统文件/自动化/自进化钥匙.md`, or log in `grok` / official Codex / `claude` once; or the nightly upkeep is skipped / failing — `nightly:` says which, `90 系统文件/自动化/夜间维护.md` says why). Do not print secrets. Then continue the user's question.
2. Choose one route: `status` for current system state; otherwise `preference`, `correction`, `memory`, `project`, or `search`.
3. Send one distinguishing noun, or a short question (a few words). Do not paste the whole conversation. Do not string unrelated keywords together as if they were AND.
4. Run the router script: `route_knowledge.sh <route> [query]` (Windows: `python3 route_knowledge.py`).
5. If the receipt has `canonical_match: true`, cite `canonical_source` as the source. Do not substitute the preferences note unless that is the mapped source.
6. If the receipt has `host_prompt:`, ask the host that sentence and stop. Do not pick a winner among suggestions.
7. On a miss the receipt carries `recall:` — ranked pages, each with `how`, the best matching line, and sometimes `answer (generated):`. The generated answer is a precomputed summary of that page, checked against it lexically and by a second model pass; use it to decide, but quote and act from the page itself. Open only the top hit, and only if its `how` / answer does not close the question. `scope_widened: vault` means the route's own page had nothing; say where the answer came from.
   - After the hits, `associated:` lists up to two pages the vault connects to them (a link, a replacement, the same session, words they share, or being cited together; the `via:` line says which). The question did not name them: read one only when the hits leave part of the question open, and say it came by association. `recall_conflict:` before the hits means two pages disagree; the newer one is listed first.
8. `recall: none` means no page in the vault covers the question. Say so plainly; do not guess and do not answer from memory as if it were the vault.
9. Answer and stop when complete. If there is no `canonical_match: true`, no useful `recall:`, `conflict: no`, and `suggestions:` are listed, retry **one** suggested alias. Do not treat a suggestion as a hit until the next receipt says `canonical_match: true`. Report any remaining gap.

## Ask (L3)

At the start of a user utterance that is **starting work**, run:

`python3 $HOME/.agents/skills/krouter-obsidian/scripts/ask_product.py ask --query "<user text>"`

If `trigger.ask` is set, ask `prompt` and wait. At most one. After adopt / reject / defer, run `record --file NAME.md --decision …`. `record` does not write `active`. If adopt, do the work; on success run `promote --file NAME.md`. Only `promote` sets `status: active`. Miss / ambiguous / already-asked: continue. Triggers live on the provisional page (`triggers: a; b`) or the vault sidecar; this clone does not ship someone else’s table.

## Secrets

A page named or marked as secret (凭据 / 密钥 / 钥匙 / credential / secret / password, or `secret: true`) shows only its path; never open it to quote it. Key values anywhere print as `<redacted>`. Never ask the host to paste a key into chat or into the vault; keys go in `~/.dsh-krouter-keys.env`.

## Aliases

The alias table is the host's: `90 系统文件/canonical_sources.psv` in the vault (`canonical_map:` on every receipt says which table is in force). To help a host start one, run `python3 $HOME/.agents/skills/krouter-obsidian/scripts/propose_aliases.py` and point them at `90 系统文件/自动化/别名候选.md`; they tick rows, then `--apply` appends only those. Never tick rows for them.

## Boundaries

- The script is read-only. Semantic vault writes need an explicit assignment.
- Prefer canonical, current, `active` evidence. Use `correction` for `supersedes` conflicts.
- Skip `Clippings/`, backups, and cold mirrors. If the mapped source is `candidate`, read it. A superseded / retired / rejected page never locks; if a recall hit shows `status=superseded`, prefer the page that replaced it.
- Do not restart Obsidian or print secrets. Never echo API keys.
- If `status` prints `host_action:`, tell the host. Do not skip that reminder.
- A complete `status` result needs no second lookup.
