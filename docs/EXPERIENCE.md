# Experience cards: lessons offered across subjects

Recall answers "what was decided about X". This page is about something else: a lesson learned on one task coming back
on another task whose subject is different but whose situation is the same. Example: the stew tasted flat and a
spoonful of sugar fixed it; later the poster's colours look dull, and "when something is flat as a whole, add a little
of the opposite" is worth offering. Code: `skill/krouter-obsidian/scripts/experience.py`. Measured 2026-11-09;
registrations and logs: [`HELDOUT.md`](../bench/memory_honesty/HELDOUT.md), sets 13 and 15.

**In one line:** handed a digest of every card at session start, Sonnet 5.5 offered the right lesson on 14 of 14
held-out tasks with a new subject and Haiku 5.5 on 11 of 14, and neither said anything on any of the 14 tasks that
should get nothing. Matching by shared words, the first try, found 0 of 14.

**Status: off by default** (`KROUTER_EXPERIENCE=1` turns it on). It passed its registered line; whether to turn the
digest on by default is the maintainer's call (recommendation at the end).

## What it does when on

| Step | Where | What |
|---|---|---|
| Write | `import_sessions.py`, where a session is distilled (session end or nightly) | One more model call through `llm.py` on the same redacted excerpt asks for at most two cards: situation, what was done, what came of it, the lesson without the subject, 3–5 "when" phrases, the source page. A card is kept only if every field is filled, nothing looks like a key, its situation and action share words with the excerpt, its phrases do not name the subject, and no card with the same lesson exists. No model lane: nothing happens. Written cards go into the run's commit and the change ledger (`经验卡：…`), so `--undo` takes them back. |
| Store | `02 经验与方法/经验卡/*.md` | Plain Markdown, `type: experience-card`, `status: provisional`. Read, fix or delete them like any page; `status: retired` drops one; `adopted_at: YYYY-MM-DD` moves it up the digest. |
| Offer | `session_hook.py start` (Claude Code, Codex `SessionStart`; Cursor `sessionStart`) | The digest: one line per card, "situation → what to do〔id〕", subject-free, at most 30, then how to use it: offer at most two, as "别的任务里的经验，可以试试：……〔id〕", only when this task's situation is the same (not just a shared word or subject), otherwise say nothing. The host model judges; nothing is matched. Needs no import consent (it only reads the vault). |
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
| *Set 13, lexical matcher* | *held-out* | — | *0 / 14* | *2 / 14* | *2* |

The usage wording was written once and never revised: the development row is its first run. Pass line, registered
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

## Not done, and the recommendation

- **The cap's order has nothing to go on yet.** Nothing writes `adopted_at` (there is no signal yet that a suggestion
  was taken), so past 30 cards the digest keeps the newest by `date`, and ties fall to file-name order. In the scale
  check's vault the cap would have kept 30 distractors and none of the real cards; the check listed all 54, as
  registered. Before the cap matters, something has to mark adoption (or the cap has to rise).
- **Extraction quality is unmeasured**: the write path is tested with a stub model only.
- **Recommendation:** turn the digest on by default when the vault has cards (no cards, nothing printed, so a vault
  without them sees no change), keep the 30-line cap, and keep extraction opt-in (`KROUTER_EXPERIENCE=1`), since it
  adds a model call per distilled session-day and its output has not been measured.
