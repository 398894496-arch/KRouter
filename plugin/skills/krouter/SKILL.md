---
name: krouter
description: Look up what this user already decided, corrected or did before, in their own Markdown vault, before answering from memory. Use when a question depends on the user's past decisions, rules, preferences, corrections, project history or earlier sessions ("how did we decide…", "what did we change…", "last week we…"). Also sets KRouter up when it is not installed yet.
---

# KRouter

The user's vault holds their decisions, rules, corrections and excerpts of past agent sessions. Ask it before you
answer from your own memory.

## Ask

Call the `krouter_ask` MCP tool with the question in the user's words (`route: "correction"` when the question is
about what was corrected). Then:

- Answer from the `how` line and the matching lines, and say which page it came from (the path in the receipt).
- A page with `status=superseded` is out of force; prefer the page that replaced it.
- `recall: none` means the vault does not know. Say so plainly; do not guess and do not present your own memory as
  the vault's.
- A receipt line `host_action:` is for the user: tell them that line.
- Pages under `05 时间日志/会话摘录/` are excerpts of past sessions: clues, not rules. Say "in the session on <date>"
  rather than "the rule is".

## Not set up yet

If the tool says no vault is configured, offer to set it up, and on a yes run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bootstrap.py"
```

It makes a vault (or uses `--vault PATH`), installs the router and records the vault path. It asks before
installing the nightly job and before importing past sessions; run it in a terminal the user can answer in, or pass
`--no-timer` / `--no-import` when they decline. Never paste keys into chat or into the vault.
