# Codex / AGENTS snippet

Add this to the Codex handbook the host actually uses. Do not paste someone else's private vault path.

```
Knowledge-dependent tasks: set OBSIDIAN_VAULT, then follow
~/.agents/skills/krouter/SKILL.md
and run ~/.agents/skills/krouter/scripts/route_knowledge.sh status first.
If the receipt has host_action:, tell the host that line (paste *_API_KEY on
the vault key page, or log in grok / official Codex / claude). Do not print secrets.
Then run route_knowledge.sh for the needed route.
Do not read 下意识.md. If canonical_match is true, answer from how when it closes the question; cite canonical_source. Open the page only if how does not close it.
If the receipt has host_prompt:, ask the host that sentence and stop; do not pick a winner.
If the receipt lists suggestions and conflict is no, retry one suggested alias once.
At the start of work, run python3 ~/.agents/skills/krouter/scripts/ask_product.py ask --query "<user text>". If trigger.ask is set, ask prompt and wait. record does not write active; promote after this task succeeds.
```
