# Skills: experience that keeps coming back grows into a procedure

An experience card ([`EXPERIENCE.md`](EXPERIENCE.md)) is one lesson from one task. When a lesson is borne out again
and again, or when several cards turn out to describe the same kind of situation, KRouter drafts a **skill**: a
Markdown page with a name, one sentence on when to use it, numbered steps, and where it came from. Drafts are offered
as suggestions; a draft people keep adopting becomes a skill; one nobody adopts is withdrawn. Nobody has to approve
anything, and every change is one git commit you can take back. Code: `skill/krouter/scripts/skills.py`. Measured
2026-11-10; registrations and logs: [`HELDOUT.md`](../bench/memory_honesty/HELDOUT.md), sets 24–26.

**In one line:** on held-out, the drafting step drafted the right skill in 16 of 16 scenarios that should grow one,
every draft was judged faithful to its cards and free of their subjects, and it drafted nothing in 16 that should not;
given the list at session start, Haiku 5.5 and Sonnet 5.5 fetched the right skill on 12 of 12 tasks it fits, followed
it on all 12, and said nothing about skills on 12 it does not fit.

**Status: on by default when the vault has skills** (since sets 24 and 25 passed, 2026-11-10): the list at session
start, `krouter_skill`, and the nightly step. `KROUTER_SKILLS=0` turns it all off. With no skills nothing is printed
and the tool is not offered; with no model lane nothing is drafted.

## What happens, and where

| Step | Where | What |
|---|---|---|
| Draft | `nightly.py` step `skills` → `skills.draft_step` | At most one model call a night, through the host lane (`llm.complete`: a key you set, else your agent's own logged-in CLI, with its daily cap and call record). Only when the cards that could grow into a skill changed since the last attempt. A card may become a skill on its own once adopted + seen again 3 times (`DRAFT_EVIDENCE`); two or more cards may become one when the model judges them the same kind of situation. The code checks every draft: its cards exist and are in no other skill, a single card has the evidence, every number is in the cards, no key-shaped text, the steps share words with the cards; at most 3 drafts a night. **No model lane: drafting is skipped quietly** and the nightly report says so. |
| Page | `02 经验与方法/技能/` (`02 Methods/Skills/` in an English vault) | `type: krouter-skill`, `status: draft`, `skill_id`, `use_when`, `cards`; the body has "什么时候用 / When to use", "做法 / Steps", "出处 / Sources" (each card with its adopted and seen-again counts, the sessions where that happened, when and through which lane it was drafted). Plain Markdown: fix it, delete it, or set `status: retired`. |
| Offer | `session_hook.py start` (Claude Code, Codex, Cursor) | After the experience digest: one line per skill, "name: when to use [id]", active skills first, then drafts under their own heading ("not yet confirmed; suggestions only, may be wrong"), and how to use them: fetch the full text only when the task is exactly that situation, follow it, say which skill (with its id); otherwise say nothing. Full text is never injected. |
| Fetch | MCP tool `krouter_skill(id)`, or the page itself | Offered only when the vault has skills; its description lists them (so a host with MCP and no hook, such as Claude Desktop, sees them too). A fetch is recorded as `fetched`, which counts for nothing. |
| Count use | `import_sessions.py` → `experience.record_uses` (no model) | As for cards: a skill id cited in an answer is `offered`; the next message saying it was done or worked is `adopted` (`experience.ADOPT`, `ADOPT_MORE`), unless it turns it down (`REJECT`) or is unsure or partly done (`UNSURE`). |
| Promote / withdraw | `skills.lifecycle` (nightly, no model) | A draft adopted 2 times (`PROMOTE_ADOPTED`) becomes `active`. A draft offered 4 times and never adopted (`WITHDRAW_OFFERED`), or 45 days old and never adopted (`WITHDRAW_DAYS`), or whose cards are all gone, becomes `retired`. A draft offered 2 times and never adopted (`SINK_OFFERED`) goes to the bottom of the list. |
| Take back | `skills.py undo <run>` (or `import_sessions.py --undo <run>`) | Every draft, promotion and withdrawal is its own commit tagged `[krouter-run <run>]`, with a readable message ("技能转正：「…」（被采纳 2 次，门槛 2；提出 3 次）") and a line in `记忆变更记录.md` that names the command. |
| See | `夜间维护.md` (nightly report) | New drafts with the counts they rest on, promotions with their adoptions, withdrawals with the reason. |
| Export | `skills.py export --app claude|codex|cursor` or `--dest DIR [--format agent-skills|cursor-rule]` | Only when you run it. Writes active skills (drafts with `--drafts`) as `<slug>/SKILL.md` (name, description; the format Claude Code and Codex read) or `<slug>.mdc` (Cursor rules, `alwaysApply: false`); re-running removes the files it wrote before that are no longer exported, and touches nothing else. |

**Switch.** `KROUTER_SKILLS=1` on, `KROUTER_SKILLS=0` off, otherwise the default (`skills.DEFAULT_ON`).
`KROUTER_EXPERIENCE=0` turns skills off too. Skills never appear among recalled facts, in the literal search, or among
associated pages.

## How it was measured

All material was written by fresh Sonnet 5.5 subagents that saw neither the prompts nor the code; hosts and judges
were Claude Code subagents on the named model (as sets 15–23 ran theirs), each answering a batch of prompts as if
each were the only one; no key and no stored login were used. Registered before anything was written; development
and held-out halves split by seed; held-out run once.

**Set 24, drafting.** 32 scenarios of 5–7 cards with use counts: *single* (one card borne out ≥ 3 times), *group* (2–3
cards on the same kind of situation in different subjects), *none* (unrelated), *trap* (sharing a subject, tool or
word, not the situation); 6 Chinese and 2 English of each. The prompt is the one `draft_step` sends; replies go through
the code's checks. Right draft = within the group the writer named; each right draft judged by the other host.

| | Development, round 1 | Round 4 (wording frozen) | **Held-out, run once** | Bar |
|---|---|---|---|---|
| Right drafts (*single* + *group*) | 16 / 16 | 16 / 16 | **16 / 16** | ≥ 13 / 16 |
| Judged faithful | 15 / 16 | 16 / 16 | **16 / 16** | ≥ 90% |
| Judged subject-free | 10 / 16, 62% | 16 / 16 | **16 / 16** | ≥ 90% |
| Drafts on *none* + *trap* | 1 / 16 | 1 / 16 | **0 / 16** | ≤ 2 / 16 |
| Drafts taking a card outside the group | 0 | 0 | **2** | ≤ 2 |

What changed between round 1 and round 4: name and "when to use" taken from the cards' lessons, not their situations,
with general-word examples and the bug / report / cooking self-test; lessons that only share broad advice ("go
gradually") not merged; 1 to 6 steps, each found in the cards, no padding; the language to write in named (both hosts
once wrote Chinese steps for English cards, which the code's word check then dropped).

**Set 25, use.** The Chinese template with set 13's 14 cards and 6 skills (4 active, 2 drafts); 24 messages: 12 that a
skill fits (a subject its wording does not suggest), 6 sharing a word or subject with a skill, 6 unrelated. Phase 1:
the session-start context and `krouter_skill`'s description as the code builds them, and the message; the host writes
a tool call or starts its reply. Phase 2: the tool's answer, then the reply, judged by the other host.

| | Development | **Held-out, run once** | Bar |
|---|---|---|---|
| Right skill fetched | 12 / 12 | **12 / 12** | ≥ 10 / 12 |
| Judged as following it | 12 / 12 | **12 / 12** | ≥ 90% |
| Wrong skill fetched | 0 | **0** | ≤ 1 |
| Quiet cases with a skill fetched or cited | 0 / 12 | **0 / 12** | ≤ 1 / 12 |

The skills part of the digest for 6 skills: 521 characters. Wording written once, not revised.

**Set 26, adoption and the thresholds.** 40 follow-up messages after a reply that followed a skill (adopt, reject,
ignore, unclear; 30 Chinese, 10 English). The adoption cues as they were recorded 1 of 5 development adoptions, so the
registered threshold rule had no answer; the cues were extended on the development half (logged as a deviation;
shared with cards): in-sample 5 / 5 and no false adoption of 17. **Held-out, once: 4 of 5 adoptions recorded, 0 of 13
false.** The rule then gives promote at 2 adoptions, withdraw at 4 offers with none (a draft that never fits is
promoted before withdrawal with probability ≤ 0.23% at a 2% false-adoption rate; one that always fits, ≥ 97% at the
held-out 80%).

**Limits.** Small sets: one reply moves a row by 6 to 12 points. Scenarios are written at the card level, not from
sessions; set 25 is Chinese only and one-shot with a bench note, the tool call a line the host writes; the case
writers saw the skills; Sonnet wrote all material, is a host and judges Haiku; Haiku is the weaker judge; the drafting
wording was revised three times on 16 development scenarios.

## Choices, and what is not done

- **The default writes into no agent's configuration.** Skills stay in the memory folder; every app connected to
  KRouter gets the list at session start or in the tool's description and fetches the text. Writing into an app's
  own skill folder is `skills.py export`, an explicit command.
- **Adoption is the user's word, not the agent's.** A fetch, or the host saying it followed a skill, counts for
  nothing; only the user's next message does. So with session import off (no `import_sessions.py --consent`),
  drafts are never promoted and are withdrawn after 45 days.
- **The thresholds rest on 22 development items** (set 26) and an independence assumption; the adoption cues were
  extended on those items, which also changes how card adoptions are recorded.
- **Drafting needs a model lane.** With no key and no logged-in CLI, no skill is ever drafted; the in-session path
  that cards have (`krouter_learn`) has no counterpart for skills yet.
- **Not measured:** a real vault over months; whether a host, unprompted, cites the skill id when it follows one
  outside the bench; English for set 25.
