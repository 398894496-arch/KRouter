# Experience cards: lessons offered across subjects (experimental, off by default)

Recall answers "what was decided about X". This page is about something else: a lesson learned on one task coming back
on another task whose subject is different but whose situation is the same. Example: the stew tasted flat and a
spoonful of sugar fixed it; months later the poster's colours look dull, and the lesson "when something is flat as a
whole, add a little of the opposite" would be worth offering. Code: `skill/krouter-obsidian/scripts/experience.py`.
Measured on 2026-11-09; registration and log: [`HELDOUT.md`](../bench/memory_honesty/HELDOUT.md), set 13.

**Status: experimental, off.** On its registered held-out set it recalled 0 of 14 cases it should have, and spoke on
2 of 14 where it should have stayed quiet. The pass line was 8 of 14 and at most 1. It ships off by default.
Turn it on with `KROUTER_EXPERIENCE=1` (in the environment of the hook, the MCP server or the router).

## What it does when on

| Step | Where | What |
|---|---|---|
| Write | `import_sessions.py`, where a session is distilled (session end or nightly) | One more model call through `llm.py` on the same redacted excerpt asks for at most two cards: situation, what was done, what came of it, the lesson without the subject, 3–5 "when" phrases, and the source page. A card is kept only if every field is filled, nothing looks like a key, its situation and action share words with the excerpt, its "when" phrases do not name the subject, and no card with the same lesson exists. With no model lane it does nothing. Written cards go into the run's commit and the change ledger (`经验卡：…`), so `--undo` takes them back. |
| Store | `02 经验与方法/经验卡/*.md` | Plain Markdown, `type: experience-card`, `status: provisional`. Read, fix or delete them like any page; `status: retired` turns one off. |
| Suggest | `route_knowledge.py` (so `krouter_ask`), and the `UserPromptSubmit` hook for Claude Code and Codex | The task's words are matched against each card's "when" phrases and the condition of its lesson. At most two, under `experience_suggestions:` after the facts, each with its source, worded "a lesson from another task, try it if the situation fits". Nothing printed when no card clears the threshold. Cursor's prompt hook cannot add context, so Cursor gets them only through `krouter_ask`. |
| Keep apart | `recall_index.py` | Cards never appear among recalled facts or in the literal search, only as suggestions (unless the lookup is scoped to the card folder). |

## How it was measured

`bench/transfer/`: 14 hand-written cards (each from one subject: nginx, CI, a stew, a production database…) on the
public Chinese template, and 56 Chinese task descriptions: 28 *transfer* cases (two per card, other subjects, same
situation) and 28 that should get nothing (14 on the card's own subject but another situation, 6 that borrow a word from
some card's triggers, 8 unrelated). Split by seed into development and held-out, one transfer case per card in each.
No model is called; `python3 bench/transfer/run.py dev` reproduces the development row.

| | Transfer cases recalled | Quiet cases that got a suggestion | Wrong cards on transfer cases |
|---|---|---|---|
| Development (threshold picked here) | 3 / 14 | 0 / 14 | 1 |
| **Held-out (run once)** | **0 / 14** | **2 / 14** (both word traps) | **2** |
| Loosest development setting tried | 6 / 14 | 2 / 14 | 4 |

The cards, the cases and the matcher were written by the same session; the cases came first and were not edited after
the split, but their author knew the cards' wording. A matcher that cannot reach its own author's held-out cases will not
do better on other people's.

## Why it fails, and what it would take

The matcher is lexical: the recall index's tokenizer (CJK bigrams, Latin words) and its word list. It stays quiet on a
card's own subject (0 of 14 topic traps over both splits), because only the subject-free phrases take part. What it
cannot do is see that two different wordings name the same situation: "差点意思" and "缺点什么", "改过了" and "改了不生效",
"一屏幕的红字" and "满屏报错" share no word. When a transfer case did match, it was because its wording happened to share
two words with a trigger, which also happens on unrelated tasks ("一大堆图片" against "一大堆报错"). Two other lexical rules
tried on development (all of a card's phrases pooled; out-of-list bigrams at half weight) were no better. A phrase made
only of words outside the bundled list (`发平`, `寡淡`) can never match.

So recognising a situation across subjects needs meaning, not shared words. The two candidates are the optional dense
tier ([`DENSE-OPTIN.md`](DENSE-OPTIN.md)) matched against the "when" phrases, or a model call at suggestion time. Neither
was measured here: no embedding model is on the machine this was built on, and downloading one was not approved in
this session; a model call per prompt was out of scope. Either would have to be registered as a new set before it is
run, because the held-out cases above are spent.
