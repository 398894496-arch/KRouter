# Experience cards: lessons offered across subjects

Recall answers "what was decided about X". This page is about something else: a lesson learned on one task coming back
on another task whose subject is different but whose situation is the same. Example: the stew tasted flat and a
spoonful of sugar fixed it; later the poster's colours look dull, and "when something is flat as a whole, add a little
of the opposite" is worth offering. Code: `skill/krouter/scripts/experience.py`. Measured 2026-11-09;
registrations and logs: [`HELDOUT.md`](../bench/memory_honesty/HELDOUT.md), sets 13 and 15.

**In one line:** handed a digest of every card at session start, Sonnet 5.5 offered the right lesson on 14 of 14
held-out tasks with a new subject in Chinese and 14 of 14 in English, Haiku 5.5 on 11 and 13 of 14, and neither said
anything on any of the 28 held-out tasks that should get nothing. Matching by shared words, the first try, found 0 of
14. Cards the host agent writes itself need no key; on a small check they did not yet reach their bar.

**Status: on by default when the vault has cards** (since set 23, 2026-11-10): the digest at session start, the use records and `krouter_learn`. `KROUTER_EXPERIENCE=0` turns it all off; the model-lane extraction at distill time stays opt-in (`KROUTER_EXPERIENCE=1`), since it spends a call per session-day. With no cards, nothing is printed.

A lesson borne out again and again, or several cards on the same kind of situation, grow into a skill (a procedure
with steps): [`SKILLS.md`](SKILLS.md).

## What it does when on

| Step | Where | What |
|---|---|---|
| Write, in session (no key) | `krouter_learn` (MCP) or `experience.py learn` | The agent that ran the session writes the card; the same checks, a ledger entry, one commit. The MCP server's instructions ask for it when a session solved a problem worth reusing. |
| Write, model lane | `import_sessions.py`, where a session is distilled (session end or nightly) | One more model call through `llm.py` on the same redacted excerpt asks for at most two cards: situation, what was done, what came of it, the lesson without the subject, 3–5 "when" phrases, the source page. A card is kept only if every field is filled, nothing looks like a key, its situation and action share words with the excerpt, its phrases do not name the subject, and no card with the same lesson exists. No model lane: nothing happens. Written cards go into the run's commit and the change ledger (`经验卡：…`), so `--undo` takes them back. |
| Store | `02 经验与方法/经验卡/*.md` | Plain Markdown, `type: experience-card`, `status: provisional`. Read, fix or delete them like any page; `status: retired` drops one; `adopted_at: YYYY-MM-DD` moves it up the digest. |
| Offer | `session_hook.py start` (Claude Code, Codex `SessionStart`; Cursor `sessionStart`) | The digest: one line per card, "situation → what to do〔id〕", subject-free, at most 30, then how to use it: offer at most two, as "别的任务里的经验，可以试试：……〔id〕", only when this task's situation is the same (not just a shared word or subject), otherwise say nothing. The host model judges; nothing is matched. Needs no import consent (it only reads the vault). |
| Remember use | `import_sessions.py` (every turn, no model) | An answer citing a card id in brackets is recorded as `offered`; the next question as `adopted` only if it says the lesson was followed or worked and does not turn it down, and the answer cited only that card or the question names it. Anything unclear stays `offered`. `90 系统文件/自动化/经验卡使用记录.jsonl`. |
| Seen again | `krouter_learn(same_as=…)`, `experience.record_again` | When the digest already has the lesson, the agent names that line's id instead of writing a card: the old card gets an `again` record with this session as its source. The code's lexical same-lesson check does the same as a fallback. Nightly, cards whose lessons share most of their words are listed in `夜间维护.md` to merge by hand; nothing is merged or deleted. |
| Rank | `experience.digest` | Adopted or seen-again cards first (latest first), then by times offered and date; a card offered 3 times and never adopted sinks to the bottom. A hand-set `adopted_at` counts as an adoption. |
| Language | `experience.digest` | English header, lines ("When …, … [id]") and usage line when most cards are English; cards may be written `- Situation:` / `- Lesson:` … |
| Keep apart | `recall_index.py`, `route_knowledge.py` | Cards never appear among recalled facts or in the literal search. |

**Size.** 14 cards: 842 characters, about 690 tokens. 30 lines (the cap): about 1 000 characters, about 780 tokens. 54
cards uncapped: 1 906 characters, about 1 520 tokens. Estimates without a tokenizer (one token per CJK character,
one per three other characters), so on the high side. Given once per session, not per prompt.

## How it was measured

**Set 15 (the digest).** Set 13's 14 hand-written cards on the public Chinese template. 56 Chinese task descriptions
written by Fable 5.2, which saw only each card's lesson and a few words naming its original subject (not the
triggers, the digest or its wording): 28 transfer cases (two per card, other subjects), 14 on the card's own subject in
another situation, 8 borrowing a word from a lesson, 6 unrelated. Split by seed; held-out sealed before any host ran.
Hosts were Claude Code subagents on the named model (as set 12 ran its reader), 14 prompts per agent; the cited ids
are counted mechanically (`bench/transfer/host.py`).

| Host | Split | Cards in the digest | Transfer cases recalled | Quiet cases that got a suggestion | Wrong cards |
|---|---|---|---|---|---|
| Sonnet 5.5 | development | 14 | 14 / 14 | 0 / 14 | 0 |
| Haiku 5.5 | development | 14 | 13 / 14 | 0 / 14 | 1 |
| **Sonnet 5.5** | **held-out (run once)** | 14 | **14 / 14** | **0 / 14** | **0** |
| **Haiku 5.5** | **held-out (run once)** | 14 | **11 / 14** | **0 / 14** | **0** |
| Sonnet 5.5 | development, scale check | 54 (40 distractors) | 14 / 14 | 0 / 14 | 0 |
| Haiku 5.5 | development, scale check | 54 (40 distractors) | 13 / 14 | 0 / 14 | 0 |
| Haiku 5.5 | English (set 16), development | 14 | 14 / 14 | 0 / 14 | 0 |
| Sonnet 5.5 | English (set 16), development | 14 | 14 / 14 | 0 / 14 | 0 |
| **Haiku 5.5** | **English (set 16), held-out** | 14 | **13 / 14** | **0 / 14** | **0** |
| **Sonnet 5.5** | **English (set 16), held-out** | 14 | **14 / 14** | **0 / 14** | **0** |
| *Set 13, lexical matcher* | *held-out* | — | *0 / 14* | *2 / 14* | *2* |

Set 16's English cases were written by Sonnet 5.5, also one of the hosts, from the English lessons alone; the
cards are a translation. English digest: 2 522 characters, about 846 tokens by the estimate. In both languages the
usage wording was written once and never revised: the development row is its first run. Pass line, registered
before any host ran: recalled ≥ 8 / 14, at most 1 quiet case, at most 1 wrong card, for each host.

**Limits.** 14 cards and 28 held-out cases: one wrong reply moves a row by 7 points. Each agent answered 14 cases in one
batch and could compare them; the bench asked for short replies; the case writer saw each card's subject; Chinese
only; the cards were written by hand, not by the extraction step, whose card quality is not measured. A real session
also carries the project's decisions and a long system prompt, which this bench does not.

## Why matching by words failed first (set 13)

The first version matched the task's words against each card's "when" phrases (the recall index's tokenizer and word
list, a quiet threshold picked on development). It stayed quiet on a card's own subject, but one situation in other
words rarely shares a word: "差点意思" and "缺点什么", "改过了" and "改了不生效". Held-out: 0 of 14 recalled, 2 of 14 quiet
cases disturbed. The host model reads the task anyway and understands it; with a few dozen short, subject-free lines
it can simply be given all of them. `experience.suggest()` keeps the lexical matcher to reproduce set 13; nothing
calls it.

## Cards the host writes itself (set 17)

Twelve synthetic sessions (7 with a lesson, 3 whose lesson is already a card, 2 with none; Chinese and English), each
given to the host with the digest and `krouter_learn`'s own description; every proposed card went through
`experience.learn()` as the tool would. Scored mechanically against gold terms written before the run.

| | Haiku 5.5 | Sonnet 5.5 | Both | Bar |
|---|---|---|---|---|
| Lesson sessions with a card | 7 / 7 | 7 / 7 | 14 / 14 | ≥ 10 |
| Cards subject-free | 6 / 7 | 6 / 7 | 12 / 14, 86% | ≥ 90% |
| Cards faithful (gold terms in action and result) | 6 / 7 | 4 / 7 | 10 / 14, 71% | ≥ 90% |
| Duplicates written | 0 / 3 | 0 / 3 | 0 / 6 | ≤ 1 |
| Cards on sessions with no lesson | 0 / 2 | 0 / 2 | 0 / 4 | ≤ 1 |

**Not passed.** Read afterwards (not part of the score): the four "unfaithful" cards say what the session says in
other words than the gold terms ("明显减少" for 少了, "唯一标识" for 请求 id); the two subject leaks are real, one
`when` phrase each ("新人总来问", "no reply to my email"), while both cards' lessons, the only field the digest shows,
are subject-free. Both hosts skipped every duplicate themselves; the code's lexical same-lesson check caught none.

## Cards the host writes itself, round two (sets 19 and 20)

Set 17 is spent, so set 19 wrote 16 longer sessions (8 to 10 turns, drift, changes of course) by another model, and
judged each card by a model that did not write it. Then the card instructions were revised on set 19 and checked once
on set 20's new sessions. Both hosts together:

| | Set 19, first run | Set 19, round 5 (in-sample) | Set 20, held-out | Set 21, held-out, numbers checked | **Set 23, held-out, repeats linked** | Bar |
|---|---|---|---|---|---|---|
| Lesson sessions with a card | 16 / 16 | 14 / 16 | 16 / 16 | 15 / 16 | **13 / 16** | ≥ 12 |
| Judged faithful | 14 / 16, 87.5% | 14 / 14 | 16 / 18, 88.9% | 15 / 15, 100% | **12 / 13, 92.3%** | ≥ 90% |
| Judged subject-free | 14 / 16, 87.5% | 14 / 14 | 17 / 18, 94.4% | 15 / 15, 100% | **12 / 13, 92.3%** | ≥ 90% |
| New cards on duplicate sessions | 0 / 8 | 0 / 8 | 1 / 8 | 2 / 8 | **0 / 8** (8 linked right) | ≤ 1 |
| No-lesson sessions with a card | 0 / 8 | 0 / 8 | 0 / 8 | 0 / 8 | **0 / 8** | ≤ 1 |

What changed between them: no `when` phrases; one plain sentence each for situation, action, result; action only for
steps actually carried out, result as the session ends (corrected figures, nothing added); a `subject` list the host
names, and the code refuses a lesson or title using one of those words and says why, so the agent rewrites it once
(as the MCP tool returns its reason); record only when something did not work, a way out was tried and its outcome
seen; a self-test that the lesson reads the same to someone fixing a bug, writing a report and cooking.

**Set 21 added a mechanical check: every number left in a card must be in the session** (the host's `quotes` for a card it writes, since the MCP server does not see the session; the excerpt in the model lane), and the advice to leave numbers out of action and result. On new held-out sessions faithfulness and subject-freedom were then 100%, but two cards were written on a session meant as a duplicate of a stored lesson (both hosts drew a different lesson from it, arguably a new one), so set 21 missed on duplicates. Before that, on set 20: subject-freedom 94%, faithfulness one card short (89%). Both unfaithful cards are
Haiku's and misstate a figure; Sonnet's 9 were all judged faithful. The digest shows only the lesson, so a wrong figure
in a card's result does not change what is offered, but it is on the page a person reads, and the bar counts it.

## Not done, and the recommendation

- **Default on since set 23.** A repeated lesson is no longer refused by comparing words: the host names the digest
  line it repeats (`same_as`) and the old card is recorded as seen again; on set 23 all 8 duplicate sessions were linked
  to the right card. The duplicate labels were confirmed by a second model before scoring; none was disputed.
- **Whether a host calls `krouter_learn` on its own** at the end of a real session, unprompted, is not measured; set 17
  asked it directly.
- **The no-key model lane** (the agent's own CLI on the user's subscription) is built with a daily cap, a visible record
  and a switch, but its one real run failed on a lapsed login: [`HOST-LANE.md`](HOST-LANE.md).
- **The cap's order now has use records to go on** (offered, adopted), but only once sessions are imported (import
  consent); with no records, ties still fall to date and file name, which is how the set 15 scale vault would have
  dropped every real card.
- **Recommendation:** once a card-writing check passes, set `DEFAULT_ON`: the digest, the use records and
  `krouter_learn` on whenever the vault has cards (no cards, nothing printed), the 30-line cap kept, and the model-lane
  extraction still opt-in, since it spends a call per distilled session-day.
