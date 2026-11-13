# Changelog

**Release pace.** 1.1.x was held to fixes from 2026-10-15; 1.2.0 shipped on 2026-10-19, ahead of the planned
2026-11-12, at the maintainer's call; 1.3.0 on 2026-11-09; 2.0.0 on 2026-11-10; 2.1.0 on 2026-11-11; 2.1.1 on 2026-11-12. The early weeks shipped many versions a day; that pace was development, not a
support promise.

Minor releases (new features) at most once a week; patch releases (fixes, docs, benchmark updates) when ready. 1.0.0 to
1.0.2 went out on one day: 1.0.0 at the maintainer's call, 1.0.1 and 1.0.2 as fixes from outside reviews. From 1.0.0 the version follows
semantic versioning; what counts as the stable surface is listed in [`docs/DETAILS.md`](docs/DETAILS.md#stability-and-versions). Each entry starts with what you will
notice, then the details.

## Unreleased

Nothing yet.

## 2.1.1 — 2026-11-12

What you will notice: fewer of your own pages are taken for reference material (a page now needs a source address, an author or a byline, or to read as prose), and experience cards and hook trigger phrases you have not used for 60 days step back behind the ones in use. The index is rebuilt once on the first lookup (`recall-v19`).

Experience cards and the prompt hook's trigger phrases that go unused for 60 days step back (`hot.py`). A card not adopted or seen again for `hot_days` days (being offered does not count; a card never used counts from its date), and a generated or learned trigger phrase that has not brought a page for as long (counted from the first night that saw it), sort after the others of their kind: in the session-start digest, among suggestions, among the hook's two pages a message. Nothing is deleted or changed, no approval is needed, a lookup by name still finds it, and one use makes it hot again at once. Rule pages, corrections, the alias table and its pages, and recall itself are not affected. `hot_days|60` / `hot_days|off` in `krouter-settings.psv` (or `KROUTER_HOT_DAYS`); the nightly report counts what went cold and what came back; `krouter why` marks a cold card; the checkup page now says which pages are and are not weighed down. `KROUTER_TODAY` sets "today" for tests. Registered counts unchanged.

Reference material is recognised on positive evidence (set 42). On a real vault 2.1.0 took about 6% of the owner's own pages for reference material: records, daily reports and hand-over notes their own pipelines write (long, impersonal, English field names, lists, no decisions). Now a source counts only with an address (a `来源：` field naming your own record does not), and a page with no source address, author or byline that is not narrative prose is never reference material and does not count toward its folder's majority. Held-out half of that vault: own pages misjudged 30 → 3 of 692, outside pages recognised 43 → 43 of 46; set 40's synthetic held-out half unchanged. One vault, tuned on half of it. Index schema `recall-v19` (rebuilt once on the first lookup).

Docs: the ten-project comparison table (what each project's own page says, no ranking) is now on the README's front page, in both languages, with links from DETAILS and the README's document list; the full version stays in `docs/COMPARE-ALL.md`.

Docs: four places on the pages that disagreed now agree: one latency statement with its conditions (the registered set 34 and set 39 numbers), the opening's "no key, no server" limited to personal use, the team section's "tested on one machine only" moved to its first sentence, and "every message looked up" qualified by the hosts that have a per-message hook (not Cursor). No registered number changed.

Set 41 gets a third reader: Claude Opus 5.5, run once on the same 130 questions and prompt files (registered before its run). LongMemEval's 30 unanswerable questions: 24 said the memory does not have it; LoCoMo's 60 adversarial: 47; the 40 answerable controls: 5 wrongly refused. The bar fixed beforehand is met by Opus and not by Haiku or Sonnet. The "nothing" row was not run for Opus.

## 2.1.0 — 2026-11-11

**Windows: the commands the install prints now run as printed ([#74](https://github.com/398894496-arch/KRouter/issues/74)).** The closing lines used to print `set "PYTHONPATH=…" && python -m krouter.cli doctor`, which failed in PowerShell 5.1 (`&&`) and PowerShell 7 (`set` does not set an environment variable, so the module could not be imported), and `… search "question"`, which the Python command line rejects (its command is `ask`). They now print `python "<…>\scripts\krouter_run.py" doctor` and `… ask "question"`: one command, no `&&`, no variable to set. The same `ask` replaces `search` in the lines printed on macOS and Linux. Tests check the printed line and that the command line's own argument parser accepts the printed arguments; **a real PowerShell 5.1, PowerShell 7 and cmd have not run it yet** (that waits for CI's Windows machine after the push).

**Paragraph-level evidence (set 39): built, measured both ways, off by default because it missed the bar.** Pages
are now cut into paragraphs (a session into its turns) at index time, and every lookup records the best paragraph of
each of the first 20 pages; the receipt marks it on the first quoted line: `L8 (passage L6-L8): …`. Questions that add
up or list (`how many times`, `in total`, `都有哪些`) get 8 pages instead of 5 (the 3 extra come after the usual 5, under `more:`): that part is **on** (LongMemEval held-out
half, every labelled session handed over 203 → 205 of 235, 16% more pages; nothing else moves). The rest is **off**,
behind `KROUTER_EVIDENCE=1` or `evidence|on` in `krouter-settings.psv`: the first 20 pages re-ranked by their best
paragraph, pages inside a time cue's window (`last Saturday`, `in March`, `三个月前`) counted double, and two refusals —
the first page's best paragraph holds under a quarter of the question, or the question names a speaker (or asks about
"I") and what that speaker said holds under 0.4 of what the other speaker said. Chosen on development data, held-out
halves run once: **LoCoMo improved on both sides** (adversarial questions answered `none` 18 → 61 of 223; answerable
questions whose page is handed over 613 → 619 of 768), but **LongMemEval's 30 unanswerable questions moved 9 → 10**
(the bar was 14), its held-out half handed over 211 of 235 (212 before), and `heldout3` gained one wrong citation
(36 → 37), so by the bar registered before the run it does not ship on. The answer-type check (does the best
paragraph hold a number, a duration, a date, an amount, a frequency, an age when the question asks for one) does not
separate (AUC 0.50 / 0.46) and is unused.

**Reference material recognised without declaring (set 40).** Pages not in a declared folder are sorted by where they
came from (KRouter's own folders and frontmatter, alias-table targets and `krouter kb mine` marks are your memory) and
then page by page by how they read (a source or byline line, an article's title and shape, another language, the
folder's majority; decision structure and your own annotations count against). Labelled synthetic vaults, held out and
run once: 30 of 32 outside pages recognised, 0 of 43 of your own pages taken for reference material; on by default
(`KROUTER_KB_AUTO=0` or `kb_auto|off` turns it off). On one real vault (1,473 pages, read once, read-only, declarations removed) it found 74 of 84 research pages, but about 80 of the owner's own pages (about 5.8%, an estimate; 12 sampled, all own) were taken for reference material, above the 2% line; `krouter kb mine PAGE` corrects a wrong call, and `kb_auto|off` turns it off. `krouter kb mine` / `unmine` mark a page or folder as yours;
`krouter why` and `krouter view` say why a page is reference material; the nightly report counts the pages recognised
and lists the new ones. On set 37's synthetic set with nothing declared, of the 6 questions only an article answers, the
memory now refuses 5 (was 2) and the article is listed for 5 (was 3); the 15 memory questions stay 15 of 15.

- `skill/krouter/scripts/evidence.py` (new): paragraphs, speakers, answer types, time windows, aggregation questions,
  the re-ranking and the two refusals; its constants are the chosen values. Index schema `recall-v18` (rebuilt once).
- Set 18's coverage count (LongMemEval held-out half, every answer session among k pages) is 187 / 210 / 215 at k = 3 / 5 / 8, as at 44c041f.
- `bench/evidence/study.py`, `bench/kb_auto/make.py`, `bench/kb_auto/run.py`, `tests/test_evidence.py`.

What you will notice: the memory folder now has a **knowledge base**, a layer of its own for reference material
(articles, clippings, research, documents someone else wrote). Declare a folder with `krouter kb add FOLDER` (or one
line in `krouter-kb.txt` at the memory folder's root); clipping folders and web-clipper pages count without it, as in
2.0. Its pages are still found, with their source, but a lookup lists them in a `knowledge_base:` block of their own
and they never set the confidence: when only reference material matches, the receipt's first line is
`memory: none` and the memory's answer is `recall: none`. `krouter kb suggest` (and `krouter doctor`) name folders
that look like reference material and are not declared (a suggestion only); `krouter kb import FILE` turns a PDF, Word
or HTML file into a Markdown page in the knowledge base with the converter already on the machine (`markitdown`,
`pandoc`, `pdftotext`; plain HTML without any), and says which to install when there is none.

A second change was **researched and not shipped**: a rule that would refuse more near misses (questions about
something close to what the memory holds). Registered first as set 37; of 216 candidate rules on development data none
refused at least 10 more of LongMemEval's and LoCoMo's unanswerable questions within a 1-point loss of answers (the best
refused 3 more), so the held-out halves were not opened and the gate is unchanged
([`HELDOUT.md`](bench/memory_honesty/HELDOUT.md#set-37-reference-material-apart-from-your-memory-and-saying-the-memory-does-not-have-this-more-often-registered-2026-11-10-before-any-development-number-was-looked-at),
[`docs/NUMBERS.md`](docs/NUMBERS.md)). The retrieval-layer refusal numbers stay what they were.

- `skill/krouter/scripts/kb.py` (new): declaring, recognising, suggesting and importing. Recognising clippings moved
  here from `recall_index.py` (same rules).
- Recall ranks and gates your memory and the knowledge base separately. A knowledge-base page never raises the memory's
  confidence: the memory's lead is still measured against the best reference page, and when the top three are all
  reference pages the 2.0 cap for clippings applies (at most `low`; `none` when the question has a word the memory
  never holds). Associated pages never come from the knowledge base; the literal-search fallback does not print its
  lines; the prompt hook and the session-start index never bring its pages.
- With no folder declared and no clippings, every lookup of the six memory-honesty sets gives the same result and the
  same printed receipt as 2.0.1 (405 lookups, compared byte for byte); set 18's held-out count reproduces (210 of 235 at
  five pages); the prompts of sets 15, 16 and 35 are unchanged.
- `krouter why` lists the reference pages apart and says when only they matched; `krouter view` marks them; the
  Python `Answer` has `.references` and `.memory_none`; `krouter_ask`'s description, the server instructions and
  `SKILL.md` say how to read the block.
- `bench/refusal/study.py` and `bench/refusal/synthetic.py` (set 37): the rule study and a synthetic set (a Chinese
  memory with English reference articles, declared and not; 41 questions in three configurations).
- `recall_index.coverage_signals` (the signals the study measured) is in the code, unused by the gate.
- README (en/zh) reordered so the install is the fourth thing on the page (line 41 / 33): headline, one line on
  what it is, the shortest example, the install, the three points, what you can check, what it does not do, then
  the rest. The second example, the long benchmark sections, each app's full test notes and the reference
  sections moved word for word to [`docs/OVERVIEW.md`](docs/OVERVIEW.md) / `OVERVIEW.zh.md` (464 → 321 lines in
  English). The agent table names DeepSeek Harness, Hermes and OpenClaw with what was tried in each: Hermes's MCP
  connection and tool list in a separate config folder (no question asked); OpenClaw run in real use as a skill
  (1.2.x; 2.x not yet). How to connect both: `docs/INSTALL.md`.
- **Three states on the receipt's first line** (set 38): `memory: direct` (an alias lock or `high`), `memory: related`
  (only related pages: answer only from a sentence that states it outright, else say the memory does not have it),
  `memory: none`; the same pages and confidence as before. **Strict mode** (`KROUTER_STRICT=1` or `strict|on` in
  `krouter-settings.psv`, off by default) hands `related` over as `none`; on memories of session pages it answers
  almost nothing (LongMemEval held-out: 0 of 235 answers handed over), so it is for curated memories with rule pages.
  `docs/NUMBERS.md` adds the cost curve of refusing more, from set 37's development data.
- [`docs/COMPARE.md`](docs/COMPARE.md) / `COMPARE.zh.md` (new): KRouter next to MemOS and Hindsight on ten rows,
  KRouter's cells from the registered numbers, theirs only from their own READMEs (read 2026-11-11), with how to
  read it (the three were never measured under the same conditions); a five-row version in the README.

Also in this release (prepared as 2.0.1, never released on its own): the README puts the team server and its ten-people test back on the first page, keeps the
install to its shortest path (importing past sessions is its own section), says plainly that KRouter is also for any
app that speaks MCP (a Claude Desktop + Obsidian example, with a receipt actually run on a sample vault), and states
the refusal numbers in two layers: of LongMemEval's 30 unanswerable questions KRouter's receipt refuses 9; the reader
model answers "not mentioned" for 29, but also for all 30 when given nothing, so that layer is mostly the model's.
One small code change: when the confidence is not `high` and a content word of the question never appears on the top
page, the receipt adds a `recall_note:` naming those words and saying that, unless the page states the answer
outright, the question is not covered (in the vault's language). Ranking, confidence and the refusal gate are
unchanged: the memory-honesty questions run against their three vaults (1,215 lookups) give results byte-identical to `main` before the change; only the printed receipt gains the line. **Its effect on a reader's refusal rate is not
measured** ([`docs/NUMBERS.md`](docs/NUMBERS.md)).

- Added `docs/examples/writer-vault` and `writer-vault-zh` (three notes each) and `tests/test_readme_example.py`, which
  checks that the receipt printed in each README is what the sample vault gives.
- README (en/zh): a section on using KRouter as a knowledge base over an existing Markdown folder (Markdown only, no
  vector search, how to mark reference material), an "Engineering facts" list of things that can be checked now, and a
  link to the new [`ROADMAP.md`](ROADMAP.md) / `ROADMAP.zh.md`.
- `server.json` (the registry entry) still names v2.0.0 and its `KRouter.mcpb` hash until 2.1.0 is released; the two
  version tests now allow that while the top changelog section is unreleased.
- `krouter_ask`'s tool description, the server instructions and `SKILL.md` say how to read the new line.

- KRouter 2.0.0 is in the official MCP Registry as `io.github.398894496-arch/krouter`; `server.json` names the
  release's `KRouter.mcpb` (with its SHA-256) instead of a PyPI package, since KRouter is not on PyPI.

## 2.0.0 — 2026-11-10

What you will notice: mention something and the agent recalls what was
decided about it, with its page; a lesson from one task is offered on another in the same situation, and lessons that
keep coming back grow into skills; a lookup gives five pages, two of them ones the vault connects to the answer; a change of mind holds with no key; the default install
is lighter, says what it changed and is English end to end on an English machine; the memory is a plain folder,
Obsidian optional; `krouter why` explains how a lookup came out and `krouter view` shows what the memory holds on a read-only page of its own; a team server knows who wrote what and holds ten callers at once; LangGraph can keep its long-term memory in the
folder; Codex, Cursor and Claude Desktop were tested inside the apps, and Linux in a clean container. 2.0 because the receipt and the
install path change (below).

### Mention it and it comes to mind (on by default)

- **Two layers, both on.** The session-start hook now hands the host a standing index: one line per live topic of
  the alias table (its name, one other name, what was decided, the page; a replaced page's row counted under the page
  that replaced it), rule pages first, then most recently used or updated, at most 60 full lines and 5,400 characters,
  then one line on how to fetch a page: `krouter_ask`, or the route command, or the file path, since some hosts show
  the model no tool list. With more topics than that, every topic keeps its name in one "also known" line and the
  first ones keep full lines (300 topics: 16 full lines and all 300 names, about 2,500 tokens). And the prompt hook
  looks up every message on this machine (`recollect.py`, no model call): a name from the alias table (the lock's
  rules, Latin names as whole words), a trigger word or a learned question, and full-text recall only when one page
  leads by 2.5 × or more; a name match also needs a second key (recall over the whole message must not refuse it, or
  the page must match at least four of its content words). The hook brings at most two pages in that turn's context,
  each with its conclusion, its path and a mark that it is memory, not something you said; an old page brings the
  page that replaced it and says an earlier page said otherwise; superseded, expired and secret pages never come.
  Code fences and lines that read like pasted code, logs, diffs or command output are not matched; a page comes once
  per session (again if its conclusion changed), at most ten per session; nothing matched, nothing printed. Every page
  brought is listed in `~/.local/state/krouter/recalled.jsonl` for `why` and the viewer. `KROUTER_RECALL_PROMPT=0`,
  `KROUTER_RECALL_INDEX=0` or `KROUTER_INJECT=0` turn them off.
- **Measured.** The hook alone (set 32, cases written blind by Sonnet 5.5): quiet (1 of 24 should-be-quiet messages
  brought a page, no wrong or superseded page) but only 7 of 24 mentions, because people mostly say a thing in other
  words. Both layers (set 35, 120 new cases, two thirds of the mentions without the page's names; held-out, run once
  per host): **Sonnet 5.5 remembered 24 / 24 mentions and 12 / 12 changed rules, 1 of 24 quiet messages moved either
  layer, no wrong page; Haiku 5.5 23 / 24, 12 / 12, 2 of 24, no wrong page.** The hook found 7 of the 24, the host
  the rest from the index. With 240 unrelated topics in the index (development): Sonnet 23 / 24, Haiku 21 / 24, no
  noisier. Hosts given a page the hook brought used it and cited it 10–11 of 11 times and were not pulled off course
  by a page that did not fit (set 33). The whole prompt hook takes 83–126 ms at the median, at most 144 ms at p95
  warm, on 110 and on 10,000 pages (62 ms with the lookup off). Claude Code and Codex get the hook's note as
  `additionalContext` (checked with the real Codex CLI 0.155 against a local mock model: a developer message right
  after yours); Cursor gets the index at session start but its `beforeSubmitPrompt` cannot add context, so the
  prompt hook does not run there.
- **Learning how you say things (experimental, off).** With `KROUTER_RECALL_LEARN=1` the turn hook notes a page the
  agent fetched and used after the prompt hook said nothing, and the nightly `learn_mentions` step adds the message's
  most distinctive phrase as a provisional trigger word (`下意识触发词-待验证.psv`, recall only; a phrase the agent
  later passes over is dropped). Set 36: after learning, the hook alone brought the right page for 6 of 13 later
  messages that reused a team expression (English 5 / 8, Chinese 1 / 5) and quiet messages were no louder (1 of 32
  before and after); the line was 7 of 13, so it stays off. Chinese phrases are cut in the wrong places without word
  segmentation.
- **What a session starts with, in one order and under one cap.** This project's decisions (at most 1,600
  characters), the experience digest (at most 3,000: fewer card lines when longer), the skills list (at most 2,000:
  drafts, then the last skills left out), the standing index (what is left, at most 5,400; left out under 800), then
  one line on the write tools and on `recall: none`; 9,400 characters in all, under the 10,000 Claude Code shows in
  full. How to call each tool is said once: `krouter_ask` by the index's closing line, `krouter_skill` by the skills
  list, `krouter_correct` and `krouter_learn` by the last line (with no index, that line names `krouter_ask` too). The
  prompts the development sets were written on (sets 15, 16, 24, 25, 33, 35) are unchanged by this, word for word;
  the real-session sets 30 and 31 saw the opening before it. `tests/test_session_start.py`.

### Lessons that carry over to other tasks

- **Experience that keeps coming back grows into a skill.** The nightly run drafts a skill (a Markdown page: a name,
  when to use it, numbered steps, which cards and sessions it came from) from a card adopted or seen again 3 times, or
  from several cards on the same kind of situation; one model call at most, through the host lane, and only when the
  cards changed (no lane: skipped, and the nightly report says so). Drafts are listed at session start apart from the
  facts and marked as drafts; a draft adopted twice becomes a skill, one offered 4 times or 45 days with no adoption is
  withdrawn, each change one commit (`skills.py undo <run>`), and the nightly report lists what was drafted, promoted
  and withdrawn with the counts. The host gets names and "when to use" only and fetches the steps with the new MCP tool
  `krouter_skill`; nothing is written into any app's configuration, and `skills.py export --app claude|codex|cursor`
  does that only when you run it. On by default when the vault has skills (`KROUTER_SKILLS=0` off). Held-out (sets
  24–26, registered first, material by fresh Sonnet 5.5 subagents): **the right draft in 16 of 16 scenarios, all 16
  judged faithful and subject-free, no draft in 16 that should get none; the right skill fetched and followed on 12 of
  12 tasks it fits, nothing said on 12 it does not**; follow-ups recorded as adopted 4 of 5, falsely 0 of 13. The
  adoption cues were widened on development to get there ("已经把…发给他了", "the fan is quiet again"), which also
  applies to experience cards. `docs/SKILLS.md`, `bench/skills/`.
- **Experience cards are on by default when your vault has some.** The digest at session start, the use records and
  `krouter_learn` now default on (`KROUTER_EXPERIENCE=0` turns them off; extraction through the model lane stays
  opt-in). Cards no longer carry `when` phrases; the agent names the session's subject and a lesson that still uses it
  is sent back; every number left in a card must be in the session; and a lesson the digest already has is recorded
  on the old card as seen again (`same_as`) instead of written twice, which also moves that card up the digest.
  Nightly lists near-duplicate cards to merge by hand. Set 23 (new sessions by another model, duplicate labels
  confirmed by a second model, each card judged by the host that did not write it): a card for 13 of 16 lesson
  sessions, faithful 92%, subject-free 92%, no new card on any of 8 duplicates, none on empty sessions: passed.
- **Experience cards: a lesson from one task offered on another task in the same situation, measured.** With `KROUTER_EXPERIENCE=1`, distilling a session also asks the model lane for at most two cards
  (situation, action, result, the lesson without the subject, source) in `02 经验与方法/经验卡/`, checked before they
  are written and recorded in the change ledger (no model lane, nothing happens), and the session-start hook gives the
  host model a digest of every card (one subject-free line each, at most 30, about 780 tokens at the cap) with one line
  on how to use it: offer at most two, as lessons from another task with their id, only when the situation is the
  same. Cards never appear among recalled facts. Set 15 (`bench/memory_honesty/HELDOUT.md`, registered before any
  host ran; 56 cases written by Fable 5.2 from the lessons alone): on held-out, **Sonnet 5.5 recalled 14 of 14 and
  Haiku 5.5 11 of 14 tasks with a new subject, and neither spoke on any of the 14 that should get nothing**; with 40
  distractor cards added (development), 14 and 13 of 14, still none. The first version matched by shared words
  (set 13) and found 0 of 14: one situation in other words shares no words. (Off by default at this stage; set 23 turned it on, above.) `docs/EXPERIENCE.md`, `bench/transfer/`.
- **Experience cards, round three: in English, written by the agent itself, ranked by use.**
  The digest is English on an English vault; on set 16 (English, cases by Sonnet 5.5) held-out Sonnet 5.5 offered the
  right lesson on 14 of 14 and Haiku 5.5 on 13 of 14, and neither spoke on any of the 14 that should get nothing. The
  agent that ran a session can write the card itself, with no key: `krouter_learn` over MCP or `experience.py learn`.
  Session imports record when a card was offered (its id in an answer) and, conservatively, when it was adopted (the
  next question says it was followed or worked); the digest lists adopted cards first and sinks cards offered three
  times and never taken. Set 17 checked twelve synthetic sessions: a card for every one with a lesson, none for
  duplicates or empty ones, but subject-free 86% and faithful 71% against a 90% bar, so the "on when the vault has
  cards" default (`experience.DEFAULT_ON`) stayed off here (set 23, above, passed).

### Pages the vault connects, not only pages that match

- **A lookup now gives five pages: three that match the question, then up to two the vault connects to them.** The
  recall cache keeps an edge table (links, `supersedes:`, same imported session, same day, shared rare words, and
  co-citation), and recall spreads from the first three direct hits along it. The first three places are always direct
  hits; associated pages take places four and five (with fewer than three direct hits they may move up), and a place
  they do not need goes to the next direct hit. Hub pages (index, overview, 12+ links) and replaced pages are never
  offered; a page joined only by shared words needs at least six of them. A refusal stays a refusal: with no direct hit
  nothing is associated. The receipt lists them apart, under `associated:`, each with the edge it came along (`via:`).
  Built in, no switch. Set 18 (`bench/memory_honesty/HELDOUT.md`, registered before the path was written; LongMemEval
  split in half, tuned on one half, the other run), "every answer session among the pages", held-out half at five
  pages: multi-session **40 of 47** (BM25's top five 31, KRouter's five direct hits 32; paired against BM25 [+4,
  +15]), temporal 58 of 73 (54, 53), all **210 of 235** (198, 198; [+3, +21]). Against the three pages KRouter gave
  before: 28, 50 and 187. LoCoMo, a check that decided nothing: 1 185 of 1 536 at five pages, BM25 1 181, five direct
  hits 1 204, the old three pages 1 104; on its short sessions the associated pages cost places four and five that a
  direct hit had right. Memory honesty, six sets: unchanged. Cost: the receipt is about a fifth longer (median 1 692 →
  1 952 characters, 2.6 → 3.8 pages listed on the bench questions), a CLI lookup 71 → 77 ms, in-process 12.5 → 17.7
  ms at 10,000 pages; building the cache for 10,000 pages 3.6 s → 6.0 s, 29 → 38 MB (50,000 pages: 25 → 32 s, 150
  → 193 MB, measured with other jobs running). `recall(..., assoc=False)` gives the direct ranking alone (the nightly
  checkup and reconsolidation use it). Offline count, no model: `bench/longmemeval/assoc.py`.
- **Pages a confident lookup returned together get a stronger edge, overnight.** The router's query log now records
  the direct hits each lookup returned (`pages`; never the associated ones, so the path cannot feed itself), and a
  new nightly step, `cocite` (after `checkup`, no model, writes only a file in the state directory), adds one to the
  co-citation weight of every pair a `high` or `medium` lookup returned, reading each log line once. The weight
  saturates at five.
- **The MCP server tells the agent how to read the new receipt lines:** answer from the page listed first when
  `recall_conflict:` says an earlier page says otherwise (read both when it says `possible`), and read a page under
  `associated:` only when the direct hits leave part of the question open, never citing it as the answer alone.

### No key needed, a change of mind included

- **When the vault changed its mind and nothing has been distilled yet, the newer page now comes first, and the
  receipt says an earlier page says otherwise.** No model needed. Two of the top three pages that match the question
  about as well, share most of its words and carry dates, where the newer one has a line saying something was
  changed (`switched … to`, `instead of`, `no longer`, `改成`, `换成`, …) that names the subject: the newer page is
  listed first, both are marked (`conflict=newer` / `conflict=older`), and the receipt prints
  `recall_conflict: an earlier page says otherwise. …`. When the dates cannot order them (the same day) the pages are
  marked `possible` and the order is kept; anything less is left alone. The audit's case (Monday PostgreSQL,
  Wednesday SQLite, imported, no key; the old page was first) is a test. On LongMemEval's answerable questions it
  fires as "sure" for 42 of 470 and reorders 21; the newest answer session is first for 44 instead of 39 of the 72
  knowledge-update questions, and an answer session is first for 420 of 470 either way (counted without the
  refusal gate; not a registered set). Memory honesty, six sets: unchanged. On by default; `KROUTER_CONFLICT=0` turns it off.
- **"Use SQLite from now on" holds at once, with no key.** The agent calls `krouter_correct` in the turn you correct
  something (or `corrections.py apply`): a correction page that supersedes the old one, the old page marked
  `superseded` (or its line annotated when it says other things too), the corrections page and the change ledger, one
  commit. And the nightly distill now marks a session page `superseded` when a later change of mind replaced every
  decision on it, so a lookup stops giving the old answer as current. "改用" now counts as a correction.
  `docs/AUTO_CAPTURE.md` §4, `tests/test_correct_now.py`.
- **The nightly run works with no key, on the agent you are logged in to.** Run for real in a throwaway vault: the
  nightly job found the logged-in Codex CLI by itself, distilled two sessions and settled the correction candidate in 6
  calls, each on the subscription record page, stopped at the cap. The install's nightly question says, in one
  sentence, that it uses that CLI's subscription, the daily cap and how to turn it off. `docs/HOST-LANE.md`.
- **Model steps can borrow the agent you already use, with a cap you can see.** With no key, the nightly steps run
  through the agent's own CLI on your login (`claude --print`, `codex exec`, …), at most 30 calls a day
  (`KROUTER_HOST_CLI_MAX`), each one a line in `90 系统文件/自动化/订阅调用记录.md` (metadata only); this spends your
  subscription, and `KROUTER_HOST_CLI=0` turns it off. KRouter never reads or reuses an app's login or keychain. A key
  you set still goes first. MCP sampling is not used (deprecated; Claude Code does not support it); the server records
  whether a client declares it. The nightly report lists what is off when there is no lane at all. The one real run on
  the author's machine failed on a lapsed CLI login. `docs/HOST-LANE.md`.
- **A correction the distill misses is no longer lost.** When no line of the session's digest covers a correction you
  typed, it is written into the digest in your own words (`补记`) and listed in the change ledger, instead of being
  settled as not holding. Settling no longer counts the correction wording itself (`改成` on both sides) as shared
  content: a match needs a shared model, number or name, or at least three shared Chinese terms. On the
  maintainer's pages, 7 of 10 candidates had been tied to an unrelated line, three of them corrections the distill had
  missed (`docs/AUTO_CAPTURE.md` §5).
- **The correction catcher keeps only what you typed.** Blocks the app attached and documents you pasted in are left
  out before matching, and a question (ending in 吗 / 呢 / ？) or a suggestion ("要不要再…") is not a correction. On
  the same 11 days: 12 kept lines, 7 of them corrections, became 6 kept, all corrections.

### A lighter install that says what it changes

- **Recommended once after installing: bring in your past sessions.** The README gives three commands of
  `import_sessions.py`: a preview (`--days 3650 --dry-run --distill`: how many sessions, how many to distill, how many
  characters; writes and sends nothing), the import of all of them with no model (`--local`), and distilling the
  newest 40 (`--distill --distill-max 40`, on a key or a logged-in agent's subscription; at least one call per session;
  30 calls a day through a CLI). 2.0 does not work through the whole history by itself: run the third again with a
  larger number. `docs/INSTALL.md` has the details and how to take a run back; `docs/FOR-AGENTS.md` tells an installing
  agent to offer it, show the preview's numbers, and go on only on a yes. A manual `--distill` with no model lane now
  says `distill skipped` once and exits 0 (it failed once per session). Checked in a throwaway home with five
  synthetic sessions.
- **The default install no longer imports past sessions.** It makes the memory folder, connects the apps it finds
  (each settings file it changes is copied to `*.krouter-bak` first, and every file it created or changed is listed
  at the end) and records sessions from then on. Its last line gives the one command that imports the last 7 days;
  `--all` does that up front, with claude-mem's memory (the old default). `--no-import` / `--minimal` stay lookup only; `import_sessions.py --revoke` stops the recording.
  (Earlier in this release's development the default imported the last 7 days; that is `--all` now.)
- **Install:** the README line saves the script to a file before running it, so a failed download exits non-zero
  (`curl … | sh` exited 0 on a 404). `--minimal` installs lookup only (no session import, nightly job, Claude Code
  plugin, hooks or Cursor rules) and connects only the apps named with `--apps`. Run with no terminal (by an agent),
  the installer no longer opens Obsidian; `--open` forces it. `--dry-run` lists every vault file, the router, the
  rules, the recorded path, the plugin and its marketplace. The install output and the README say what works without
  a model, what still holds a change of mind without one, and what does not ("No key needed" above). The
  health page's `lamp` is `running` only when a nightly job is installed. A `~/.codex` holding only `tmp/` (left by
  probing the Codex app's login) no longer counts as a Codex install.
- **`krouter doctor`** (and `scripts/krouter doctor` from a clone or `~/.dsh-krouter/current`, no pip needed): one
  verdict, OK or what is missing with the command that fixes it. The installer prints where `krouter` is.
- **Uninstall** also uninstalls the Claude Code plugin and removes its marketplace when it points at a folder on this
  machine (its session hooks kept firing before); `--purge` also removes `~/.dsh-krouter`. The README's Install
  section has the uninstall command. `first_run.sh` no longer requires ripgrep (the router already fell back to a
  built-in search). The release package now carries `sdk/krouter`, `.claude-plugin/`, `hooks/` and `plugin/`, so a
  release install gets the plugin and `krouter doctor` like a clone does.
- **The one-line install's script comes from the release too.** Releases attach `bootstrap.sh` and `bootstrap.ps1`
  (in `SHA256SUMS`, with a provenance attestation), and the install lines read
  `https://github.com/398894496-arch/KRouter/releases/latest/download/…` instead of `main`. Until the first release that
  carries them, that address does not resolve: publish the release before pointing people at the new line.
- **Release checks you can run before tagging:** `scripts/release_pack.sh` builds the assets exactly as the release
  workflow does (the workflow now calls it) and fails when a README links an asset the release would not attach or the
  package lacks what a release install runs (2.0's new modules included: associated pages, experience cards, the
  host lane, in-session corrections). `scripts/release_smoke.py` runs every install command in both READMEs
  against the real addresses (assets, the one-line install with its checksum, `uvx --from`, `pipx install`, the
  Claude Code marketplace); a new `smoke` job runs it after each release. Against today's addresses it fails, as it
  should: `releases/latest/download/bootstrap.sh` is a 404 and `main` has no `pyproject.toml` yet.
- **One install wires every app it finds.** Besides Claude Code and Codex, the installer now writes KRouter into the
  MCP settings of Claude Desktop, Cursor, VS Code (Copilot), GitHub Copilot CLI, Gemini CLI, Kiro and Zed when each is
  installed, in the format each app documents (checked 2026-11-09): everything else in the file is kept and copied to
  `.krouter-bak`, a file it cannot parse (Zed's comments, say) or a `krouter` entry it did not write is left alone,
  and `uninstall.sh` takes out only its own entries (`bootstrap.py --unregister-mcp`). `tests/test_mcp_apps.py`
  checks each format. Not yet tested inside these apps.
- **The Claude Code plugin is installed with the rest**, from the same checksummed release added as a local
  marketplace, not from GitHub's `main`; an older Claude Code without `claude plugin` gets the one-line hint as before.
- **Cline CLI** is wired by the installer too (`~/.cline/data/settings/cline_mcp_settings.json`, per Cline's docs).
- **A Python package and a `krouter` command.** `pyproject.toml` builds `krouter` (standard library only):
  `krouter.ask()` returns the page, the one-line answer, whether it refused and the confidence; `krouter.status()`;
  `krouter.note()`; the command `krouter ask|status|note|mcp`. Install with
  `pipx install "git+https://github.com/398894496-arch/KRouter"`; not on PyPI yet. `tests/test_sdk.py`.
- **`krouter demo`**: decide, change your mind, ask, on a throwaway memory in a few seconds, with no install and no
  key (`uvx --from git+https://github.com/398894496-arch/KRouter krouter demo`, `--lang zh`); the templates ship in
  the package for it. The README opens with it and with a "Start here" table.
- **Your AI can write a line down.** A third MCP tool, `krouter_note` (text up to 500 characters; kind `decision`,
  `correction` or `note`), appends one line to that day's notes page `05 时间日志/会话摘录/<date>｜agent 记下.md`
  (status `provisional`, so a clue, never a rule page), with secrets redacted and the calling app's name from MCP
  `initialize`. Each note is a change-ledger entry and, in a git vault, one `[krouter-run <id>]` commit that
  `import_sessions.py --undo <id>` takes back. On by default over stdio; the HTTP server keeps it off unless started
  with `--allow-write`.

### English all the way through

- **An English install is English all the way through, and the install says what it changes.** A new English vault
  gets English folder and file names (`Home.md`, `02 Methods/`, `90 System/Automation/Daily health.md`, …) from
  `skill/krouter/scripts/zones_en.psv`, recorded in the vault's `krouter-zones.psv`; `krouter demo`, `status`,
  receipts' `how` lines, `first_run.sh` and the correction-candidates page (`YYYY-MM-DD｜Correction candidates.md`)
  follow it. Vaults with the default (Chinese) names keep working unchanged; nothing is migrated. The language is
  `--lang`, then `LC_ALL` / `LC_MESSAGES` / `LANG`, then the system's (an English terminal on a Mac set to Chinese
  used to get the Chinese install).
- **Corrections in an English vault link the vault's own pages.** `krouter_correct` / `corrections.py apply` wrote
  links and reported paths with the default layout's names (`05 时间日志/会话摘录/…`) where the page is
  `05 Journal/Sessions/…`; they now use the vault's own path, as do the import's `writes` list and a secret page's
  `how` line (English in an English vault). Found by the no-key change-of-mind check in a throwaway home.
- **An English vault's session pages say Q and A.** Imported session pages in an English vault now label turns
  `**Q**` / `**A**` under `## Excerpt` instead of the Chinese 问 / 答 / 摘录; every parser reads both, so existing pages
  and Chinese vaults are unchanged.

### Independent of Obsidian

- **`KROUTER_VAULT`** is the memory folder's name. `OBSIDIAN_VAULT` still works for older installs; when both are set,
  `KROUTER_VAULT` wins (an explicit `--vault` / `vault=` beats both). Messages and the README say "memory folder";
  Obsidian is one optional way to open it.
- **Messages, the README and the MCP server say "memory folder"**: a plain Markdown folder; Obsidian is one optional
  way to open it, and nothing needs it installed.

### See what it remembers

- **`krouter why "<a sentence>"` explains a lookup in words.** Which alias or words matched, why each page sits where it
  does (the words it holds and where, text relevance × tier weight), why the confidence is that one, which pages came
  along a connection and from which page by which kind of edge, which page replaced which, the experience cards that
  go with the question, and, when the memory does not know, which word it could not find and which check refused. In
  the memory's language (`--lang`, `--json`). It writes nothing and logs nothing: a `why` is not a question the
  nightly job should learn from. The refusal reasons are recomputed from recall's own helpers; a test keeps them in
  step with `recall`, and when a refusal cannot be reproduced the output says so instead of guessing.
- **`krouter view` opens a read-only page about the memory, on this machine only.** It prints
  `http://127.0.0.1:<free port>/` and opens nothing unless you add `--open` (`--demo` shows a made-up sample memory).
  Pages with search (paged, so a memory of tens of thousands of pages costs one screen a request), one page with what
  replaced it and what it connects to, the connections around a page with why each exists and how strong, the
  experience cards with times offered, adopted and met again, what the last nights did (report, ledger, git history of
  the report), and a box that shows what `why` shows. English and Chinese, light and dark, phone width. Python's
  standard library and three hand-written files in `sdk/krouter/view_ui/`; no new dependency. It binds 127.0.0.1 only,
  answers GET and HEAD only (every other method is 405, there is no endpoint that writes), refuses a request whose
  `Host` is not its own address, and sends a Content-Security-Policy that allows nothing from outside; none of its
  responses names an external address. `tests/test_why.py` and `tests/test_view.py` check these over HTTP without a
  browser. On a synthetic memory of 10,000 pages (M2): first index 6–7 s, later starts 0.06 s, the first screen
  of rows 0.05–0.3 s after the page loads, one explanation about 0.1 s ([how to read it](docs/DETAILS.md#see-what-it-remembers-krouter-why-and-krouter-view)).
- `krouter.sample` builds the sample memory (and, for timing, a synthetic memory of any size) the page, its tests and
  the README screenshot use.
- **`krouter view` and `krouter why` show what the hook and the skills did.** The viewer lists skills and drafts
  with how often each was offered and adopted, and a "Brought to mind" tab lists every page the prompt hook brought
  (from `recalled.jsonl`; empty when there is none). `krouter why` says, for a sentence, whether the prompt hook would
  bring the page itself and by which route, whether the page is in the session-start index (so an agent that used it
  without the hook fetched it after reading the index), and when the hook brought it before.

### Tested inside the apps

- **Claude Desktop: no more entries lost on restart, and a one-click extension.** Claude Desktop keeps its settings in
  memory while it runs and writes the whole `claude_desktop_config.json` back when it quits, so an entry the installer
  wrote while the app was open disappeared after the next restart. The installer now checks whether the app is running
  (macOS: a process whose executable is `…/Claude.app/Contents/MacOS/Claude`; Windows: a `Claude` process under
  `AnthropicClaude` or `WindowsApps`) and, if so, leaves the file alone and offers two ways: quit the app and run
  `bootstrap.py --connect claude-desktop`, or double-click `KRouter.mcpb`, built for your memory folder. Uninstall
  leaves the file alone too while the app runs, and says so. `krouter doctor` reports when Claude Desktop is installed
  but KRouter is in neither its settings file nor its extensions. The extension (`scripts/build_mcpb.py`, MCPB
  manifest 0.3, Python server, the memory folder as a `directory` setting) is a release asset; `release_pack.sh` and
  the release smoke check its structure and start it from the unpacked bundle for a real MCP round trip.
  Tested inside the app (Claude Desktop 4.23118.1, macOS, 2026-11-10) with a test build pinned to a sample memory
  folder: one press of Install, no restart, about 7 seconds of online checking with nothing on screen, then 3 tools
  connected; in an ordinary chat one question was answered with its page (`02 Methods/Automation/Seal the day from the
  log file.md`) and one refused (`recall: none`). The README says to press Install once and wait (a second press
  removed it). The test build named the full Python path, as the installer's build does; the release file's plain
  `python3` takes another launch path in the app and is not yet tested there.
- **Codex and Cursor tested through their command line agents (2026-11-09).** Codex (codex-cli 0.155.0-alpha.9.2, a real
  model, a copy of the sample vault): the MCP tools were found, a question the vault answers was answered with its page, one
  it does not answer was refused; the hooks noted a typed correction and ran the turn-end and session-end imports. Cursor
  (agent CLI 2026.11.05-86047df, `-p --force`; `--mode ask` rejects MCP calls in print mode): the project-level MCP entry
  was found, its tools listed, a question answered with its page, another refused; the turn-end and session-end hooks wrote
  the session pages, but the CLI's non-interactive mode did not run `beforeSubmitPrompt`, so a typed correction is not
  noted there (the hook handles Cursor's payload when fed it by hand). Both vendors document that the command line and
  the editor read the same MCP configuration (Cursor) / configuration layers (Codex, CLI and IDE extension). Claude Desktop
  4.23118.1: the config entry's command started the server, listed the three tools, answered with its page and refused
  outside the app; three restarts did not load an entry written while the app was running (it writes its in-memory
  settings back when it quits). That finding is why the installer now leaves the file alone while the app runs and
  builds the extension instead, which was then tested inside the app (the Claude Desktop entry above). Also found: a Codex `hooks.json` with top-level event names
  is skipped whole (already documented); `krouter_ask` takes `query`, not `question`.
- **Claude Desktop is set up by the installer.** When its settings folder exists, `bootstrap.py` merges
  `mcpServers.krouter` into `claude_desktop_config.json` (other servers kept, a backup `.krouter-bak` written, a file
  it cannot parse or a `krouter` entry it did not write left alone); `uninstall.sh` removes only that entry.
  `KROUTER_CLAUDE_DESKTOP_CONFIG` points it elsewhere. Checked by `tests/test_claude_desktop.py`. While the app runs the
  file is now left alone and the extension built instead (the first entry in this group).
- **Codex and Cursor now remember turn by turn too, not only overnight.** Once you said yes to importing, the
  installer merges KRouter's session hooks into `~/.codex/hooks.json` and `~/.cursor/hooks.json` (each app's
  documented format, checked 2026-11-09), keeping every hook already there and a `.krouter-bak` copy; `uninstall.sh`
  takes out only its own. In all three agents a session starts with this repository's recorded decisions, each turn is
  written to its page as it ends (`import_sessions.py --file … --local`: no model call even when distilling is on,
  0.4–0.9 s in the background on 80–355 MB transcripts), a correction is noted the moment it is typed (`codex:` /
  `cursor:` candidates, settled by the next distill), and the session is distilled when it ends if you said yes to
  that. Claude Code's plugin gains the same per-turn `Stop` hook. A page distilled when its session was shorter now
  keeps that digest (and the turn count it covers) until the next distill, instead of losing it when the session
  grows. Checked in codex-cli 0.155 against a local mock model: the decisions arrive as developer context, the
  correction is noted, `Stop` and `SessionEnd` run the import. Codex runs a hook only after you trust it (`/hooks`),
  and the installer says so. A Codex `hooks.json` with event names at the top level (no `"hooks"` key) is skipped
  whole by Codex (`unknown field`); the installer leaves such a file alone and says why. Cursor's hooks are checked
  by tests against its documented format, not yet inside Cursor. `tests/test_live_hooks.py`.
- **Agent frameworks and JavaScript.** `krouter.integrations.llamaindex.KRouterRetriever` (a LlamaIndex retriever:
  the answering page as a node with its source, no node on `recall: none`; `pip install "krouter[llamaindex]"`),
  a JavaScript / TypeScript client with no dependencies (`sdk/js`: stdio or a team server over HTTP; not on npm yet),
  and `docs/FRAMEWORKS.md` (and `.zh.md`) with the way LangChain, the OpenAI Agents SDK, Pydantic AI, Google ADK,
  CrewAI and the Vercel AI SDK load the server, each tested against it on 2026-11-09 in its own environment
  (`tests/test_frameworks.py`, `tests/frameworks/vercel/`; langchain 1.4, openai-agents 0.24, pydantic-ai-slim 2.66,
  google-adk 2.14, crewai 1.15, ai 7.0), LangChain, Pydantic AI and the Vercel AI SDK through their whole agent loop
  with their own stand-in models; CI runs each one (jobs `frameworks`, `vercel-ai-sdk`). Testing caught that
  google-adk 2.x needs its `mcp` extra (`pip install "google-adk[mcp]"`). The official MCP Python SDK is tested
  over stdio and Streamable HTTP (`tests/test_mcp_official_sdk.py`).
- **LangGraph long-term memory, without MCP.** `krouter.integrations.langgraph.KRouterStore` is a LangGraph
  `BaseStore` (sync and async): a namespace such as `("users", "ada")` is a folder, each item a Markdown page you can
  edit, and a query search runs KRouter's recall on that namespace alone, with the page it came from (`item.page`)
  and an empty list when the namespace does not know. Writing a key again keeps the old page in `.history/` marked
  superseded (`supersedes`, `store.history()`); `delete` keeps it marked retired; `store.purge()` removes a key with
  its history. Optional: `pip install "krouter[langgraph]"` once 2.0.0 is on PyPI (from a clone until then), which
  adds only `langgraph>=1.0,<2`; the core package still has no dependencies. Tested in real graphs on langgraph 1.0.0
  (langgraph-checkpoint 2.1.0) and 1.2.20 (4.3.1), no model called (`tests/test_langgraph_store.py`, CI job
  `langgraph-store`); `python -m krouter.integrations.langgraph_demo` runs a two-turn graph with no key. With 300
  users of 5 memories, 320 questions in one user's namespace gave the right page first for 100 of 129 answerable,
  nothing for all 191 the user never answered, and no other user's page (`bench/scale/langgraph_store.py`).
  Associations, the experience digest and corrections through `krouter_correct` are not on this path.
  `docs/FRAMEWORKS.md#langgraph-store-long-term-memory`.
- **Try it in your app.** `CONTRIBUTING.md` lists every app, framework and deployment still marked "not yet run by
  us", and a "Works in my app" issue form takes the report that moves it to tested.
- **Linux tested in a clean `python:3.12-slim` container** from the release package: install, upgrade from the pre-2.0
  folder (the old path becomes a link to the new one), lookup, refusal, `doctor`, `krouter mcp`, uninstall, cold
  install. **Windows was not tested for 2.0** (no reachable Windows host); the junction fallback of the folder move is
  covered by a test that runs on any OS. [`docs/VERIFY.md`](docs/VERIFY.md#platforms-and-real-sessions-200-candidate-2026-11-10)

### Team server

- **A token per person, and every write says who made it.** `--users FILE` takes one line per person or agent
  (`name|sha256:<hash>|write or read|banks`; only the hash is kept; `team.py add-user` writes a new token to a file of
  its own, mode 600, and `remove-user` stops it at once; the file is re-read without a restart). The shared tokens
  (`--token-file`, `--bank-token`) keep working beside it; their writes are recorded as the shared token's. A `read`
  token is not offered the write tools; a token limited to some banks gets 403 on the others. Every note, correction
  and lesson names its person on the page (`— 来自 alice（MCP，claude-code）`, `author:`, `superseded_by_author:`), in
  the change ledger, in a new journal (`90 系统文件/自动化/团队变更.jsonl`: order, time, person, app, pages, conflicts)
  and as the git commit's author. `krouter_changes` (and `team.py changes`) answers who changed a page and when. The
  access log names the person; no token is written anywhere. The app name a client gives at `initialize` is kept per
  person, not in one global shared by every caller.
- **Two corrections of the same thing: the later one holds, the earlier one is kept.** Writes to one memory now run
  one at a time (a lock in the server and a file lock), pages are replaced in one step, and two writes in one second
  get different run ids. A correction that names a page someone has already corrected replaces the correction now in
  force at the end of the `superseded_by` chain, instead of leaving two corrections in force; one on a line that
  already has a `⚠ 已改` note replaces the corrections those notes point to. The reply names each replaced correction,
  its author and time (`conflict: … Rule: the later correction holds`), as do the journal and
  `krouter_correction_conflicts_total`. Before, the second correction overwrote the old page's `superseded_by` and left
  the first one active, and two corrections with the same words in the same second could overwrite each other's page.
- **Ten people at once, measured and in CI.** `bench/team/load.py`: 10 clients with their own tokens ask, note,
  correct one shared page and contradict one decision at once, then check from the vault, the journal, git and every
  reply that nothing acknowledged is missing, no page is broken, every write is attributed to its token, each
  contested decision ends with the last correction in force, and every answer names a page ([set 27](bench/memory_honesty/HELDOUT.md)).
  All held at 136, 10,136 and 50,136 pages; reads p50 / p95 39 / 129 ms, 102 / 284 ms, 446 / 2,010 ms; about 8, 5
  and 2.5 writes a second (git commits are most of a write); no errors (`docs/TEAM.md` §5). `tests/test_team_concurrency.py`
  runs a smaller version on every platform in CI. Thirty minutes at 10,000 pages (21,218 calls): 0 errors, memory
  195 MB at 5 minutes and 205 MB at the end, every property held, on the third run; the first two failed and are kept
  in set 28's log.
- **Long-running fixes the 30-minute run found** (set 28's first run failed on both): a correction now follows the
  supersede chain to its end (it stopped after 100 steps, so from the 101st correction of one decision on, each new
  one superseded nothing and two or more stood in force), and a chain that is broken or goes round is reported in the
  reply (`unresolved`) instead of passing silently; the change ledger moves whole to
  `90 系统文件/自动化/记忆变更记录/<time>.md` once it passes 256 KB, with a link from the new page and in the same
  commit, because every write re-indexed all of it (at 1.6 MB, 945 ms with the index locked, so lookups queued
  behind writes and slowed as the server ran).
- **A replaced correction stops answering the old page's questions.** When a correction page is itself replaced, the
  title words it took from the page it replaced are cleared (correction pages only). After 544 corrections of one
  decision, the 80 full-text candidates a lookup starts from were all replaced corrections and the answer was
  `recall: none`; now the correction in force is found. A question worded like the corrections themselves can still
  miss once more than about 80 nearly identical corrections of one thing exist (the candidate limit; not changed).
- **A write no longer makes every lookup re-walk the vault.** After a note or correction, each resident lookup
  process re-reads just the files that write changed, instead of every file's modification time (the full re-check
  every 2 s stays, for changes from a `git pull`). Each write also starts fewer git processes (5 instead of 8 for a
  note): 176 ms → 86 ms per note on the template on our laptop.
- **A correction page answers with the new decision.** Its `how:` is now `现在：<new>` (before, the receipt's `how`
  was the page's first line, `原来：<old>`), and it carries the title of the page it replaces in `topic_terms`, so a
  question worded like the old page finds the correction too (at 10,000 pages it did not before).

- **The team server is 15–25 times faster and holds up under load.** At 10,000 pages a lookup over HTTP takes 13 ms
  instead of 210 ms and the server answers 301 questions a second with 32 callers instead of 15; at 50,000 pages,
  54 ms and 75/s instead of 980 ms and 3/s (`bench/scale/serve_load.py`, new; the table is in the README's new
  "Running it for a team" section and `docs/TEAM.md` §4). Each memory keeps up to 4 resident lookup processes
  (`route_worker.py`; `--workers N`, `--workers 0` for the old one process per lookup), which re-check the vault's
  files at most every 2 s (`--refresh-every`; a note written through the server is found by the next lookup); a
  lookup that hangs is cut off after 120 s and its process replaced. The literal fallback (what a question the vault
  cannot answer costs) now reads only the pages the index says can hold the question, and prints the same lines as
  reading every file (2,442 pieces of page text compared; `tests/test_resident_lookups.py`); this also makes a
  one-shot lookup at 50,000 pages 0.35 s instead of 0.53 s. The index cache keeps each page's frontmatter for that
  check (cache schema v14: rebuilt once on upgrade). Resident memory is about 200–270 MB with 4 processes, against
  15–29 MB before; `/metrics` gains `krouter_lookup_workers`.
- **Several isolated memories on one team server, and metrics.** `--bank NAME=PATH` (repeat) serves each vault at
  `/mcp/NAME`, with its own index, its own label on every receipt and, with `--bank-token NAME=FILE`, its own token; the
  server refuses to start off loopback while any bank has no token. `GET /metrics` is Prometheus text (tool calls by
  vault, tool and outcome; refusals; a latency histogram; index build time), counts only, behind the tokens.
  `deploy/docker-compose.yml`: two banks, read-only, non-root, with a container pulling each vault every five
  minutes (checked with `docker compose config`). `docs/TEAM.md` gains a "Running it" table. `tests/test_mcp_banks.py`.
- **A memory for a team, self-hosted.** `mcp_server.py --http HOST:PORT` serves the same two read-only tools over
  Streamable HTTP (`POST /mcp`, JSON replies; `GET /healthz`). It binds to 127.0.0.1 unless told otherwise and refuses
  any other address without `--token-file` (bearer token, compared in constant time, at least 16 characters). Browser
  origins other than localhost are refused unless listed (`--allow-origin`); bodies over 1 MB get 413. The access log
  is one JSON line a request with a SHA-256 prefix of the question, never its text, and questions are not written to
  the query log unless `--log-queries`. The index is built before the server listens. `--label NAME` stamps
  `vault_label: NAME` on every receipt (stdio too), so an answer says which memory it came from; `--vault` names the
  vault to serve. `docs/TEAM.md`: a team vault in its own git repository, pulled every few minutes, served read-only,
  added by each person as a second MCP server next to the personal one, which stays on stdio and on the machine.
  Tested with a plain client (`tests/test_mcp_http.py`) and with Claude Code over `--transport http`.
- **Docker image** for the team server (`Dockerfile`: Python slim, standard library only, user 10001, the vault
  mounted read-only, health check on `/healthz`). Every PR builds it and runs `scripts/docker_smoke.sh` (healthy,
  token enforced, labelled receipt, hashed question in the log, vault untouched, not root); a published release
  pushes `ghcr.io/398894496-arch/krouter:<tag>` and `:latest` with a build-provenance attestation, after the same
  smoke test.
- **Kubernetes and systemd.** `deploy/kubernetes/krouter.yaml` (Deployment and Service: an init container clones
  each memory, a sidecar pulls it, tokens and deploy key from Secrets, read-only root filesystem, `/healthz` probes,
  Prometheus annotations) and a hardened `deploy/systemd/krouter.service`, next to the Compose file. Checked by
  `tests/test_deploy.py`; not yet applied to a cluster or a systemd host by us.
- **Scale bench** (`bench/scale/`): a synthetic vault of N pages and the time of one lookup as the MCP server runs it.
  On an Apple M2 laptop: 1,000 pages 0.08 s per lookup (p50), 10,000 0.12 s, 50,000 0.53 s (p95 1.1 s, 76 MB peak);
  the first lookup, which builds the index, takes 0.4 s, 4.8 s and 24 s. Over HTTP, 16 parallel callers on 10,000
  pages right after 200 pages changed: no errors. `docs/BENCHMARK.md` → Scale.
- **`server.json`** for the MCP registry (`io.github.398894496-arch/krouter`, the PyPI package run as `uvx krouter mcp`)
  and the `mcp-name` marker in the README; `tests/test_server_json.py` keeps its version in step with `pyproject.toml`.
  Not listed yet: it needs the package on PyPI first.

### Measured, and what the numbers say

- **Real sessions, measured for the first time** (sets 30 and 31): Codex CLI, a Claude Sonnet 5.5 subagent and the Cursor
  agent CLI, given small tasks that never mention the memory. They mention a stored lesson when the situation matches
  (2 of 4 on both full runs) and never when it does not; they rarely call `krouter_learn` (0 of 4 on both hosts) and
  Codex never called `krouter_correct` (0 of 4; the Claude subagent 3 of 4). Cause on Codex: this version shows the model
  no krouter tool and none of the server's instructions. **Changed:** the session hook now ends with one line naming
  `krouter_ask`, `krouter_correct` and `krouter_learn` and when to call each, and the server's instruction sentences for
  the last two say the same (after the merge with the standing index, that line names only the two write tools, since
  the index's own closing line says how to call `krouter_ask`; sets 30 and 31 were measured on the opening before that
  merge). On a development set the Claude subagent went from 1 of 3 to 2 of 3 on `krouter_learn`
  and stayed at 3 of 3 on `krouter_correct`; the Codex check could not run (its usage limit was reached), so the change is
  not verified on the host it was made for.
- **An answer-accuracy number you can set next to other projects'.** LongMemEval S, all 500 questions: a
  reader given only the pages KRouter 1.3.0 cites answered 400 right (80.0%, 95% interval 76.4–83.4), with the
  benchmark's own reader and judge prompts; reader and judge are Claude Sonnet 5.5, not GPT-4o. Registered before the
  run as set 11 (`bench/memory_honesty/HELDOUT.md`); `bench/longmemeval/qa.py` writes the prompts and scores the
  replies; every reply and verdict is in `bench/longmemeval/results/`.
- **How much of the 80% answer accuracy is KRouter: measured, and the answer is "no more than keyword search".** Set
  12 (`bench/memory_honesty/HELDOUT.md`, registered before the run) keeps set 11's reader, judge and prompts and
  changes only what the reader is given. Nothing: 30 of 500 right, 0 of the 470 answerable. Plain BM25's top three
  sessions: 405 (81.0% [77.4, 84.4]). KRouter's cited pages: 400 (80.0% [76.4, 83.4]). Paired, KRouter minus BM25:
  −1.0 points [−2.8, +0.8], no difference shown. The benchmark's own answer sessions (perfect
  retrieval): 492 (98.4% [97.2, 99.4]), +18.4 points over KRouter [15.0, 21.8], so the missing 18 points are lost in
  retrieval, not by the reader: mostly multi-session (69 → 117 of 121) and temporal (97 → 125 of 127) questions,
  where three pages miss a session. (That row was paused for cost after 26 of 75 reader batches and finished the same
  day; nothing was scored before all 500 replies existed.) `bench/longmemeval/qa.py` gains `baseline`, `collect` and
  `compare`; results in `bench/longmemeval/results/2026-11-09-sonnet-qa.{none,bm25,oracle}.jsonl`.
- **The refusal gate was checked against LongMemEval's unanswerable questions: no change, and the "3 of 30" is stale.**
  Set 14 (`bench/memory_honesty/HELDOUT.md`, no model called) found: 3 of 30 is 1.1.1 at the retrieval layer; the shipped
  gate refuses 9 of 30, and the answer says "not mentioned" for 29 of 30 (sets 11 and 12, same for plain BM25). These
  questions ask for a detail that a related session in the vault does not give, so the best page is an answer session
  for 22 of 30. 49,288 one- and two-signal rules searched on the development half (a seed-drawn half of the 470
  answerable questions, the 30 `_abs`, and the half with its answer sessions removed): none refuses clearly more within a
  1-point loss of answerable questions (at most 2 more of the 21 still answered; 5 more at 2.1 points lost). With
  the answer sessions removed from each vault the unchanged gate refuses 220 of 470 (46.8%). Nothing in the product
  changed; the held-out half was not opened. `bench/longmemeval/lme.py` gains `ablate`, new `gate_study.py` reproduces
  the search. README, STATUS and the doc banners still say 3 of 30: to fix with the next README pass.
- **README: "level with keyword search" replaced by what was measured since, and said at which layer.** The main
  line is now the retrieval result at five pages (set 18's held-out half: every needed session handed over for 210 of
  235 questions against BM25's 198, multi-session 40 of 47 against 31). The same-reader table (6.0 / 81.0 / 80.0 /
  98.4%) measured the three-page 1.3.0 and moved to `docs/NUMBERS.md` with its version and page count; the README
  says the five-page answer accuracy has not been rerun (set 22, registered, not run). LoCoMo's 19 fewer than five
  direct hits is in `docs/NUMBERS.md` and the README's weak spots. `README.zh.md` matches.
- **README, a fifth shorter** (4,611 → about 3,700 words): the same-reader table above, a "Words used here" glossary
  (receipt, floor, superseded, distill, change ledger, bank, …), and the full numbers table moved, unchanged apart
  from the new row, to `docs/NUMBERS.md` (`docs/NUMBERS.zh.md`); the README keeps only what its other sections do not
  already say. Plugin version notes moved to `docs/DETAILS.md`. `README.zh.md` matches.
- **README shows what capture did on the maintainer's machine** (30 runs, 714 lines, 407 changes of mind; 5 of 8
  hand-recorded corrections in the memory by the next run), with a per-day chart, and the decision-capture bench's
  numbers.
- **README:** a team server and remote-MCP apps in "Works with"; "no hosted service, a self-hosted team server is
  fine"; the install line says the script installs the latest release tag, not `main`; the Chinese ledger path and
  the terms receipt, floor and answer cards are explained where they first appear.
- **`MAINTAINERS.md`:** one maintainer, said plainly; what you keep if the project stops (your Markdown folder, the
  MIT standard-library code, no hosted service), how a fork releases and re-measures, when the repository would be
  handed over, and how to become a maintainer.

### Fixes

- **Fixed: a question you had asked before came back as its own answer.** With sessions recorded, asking the vault
  about something it does not hold left an excerpt page whose only matching line was your question; asked again, that
  page came back `medium`. An undistilled excerpt where the question's words match only your own questions (and no
  answer has them, or every answer that does says the vault has nothing) is no longer evidence: it is left out of the
  ranking, and when what is left is weak the receipt says `recall: none` and `recall_note: you asked this before (…),
  but no answer was recorded`. A line where you stated something, and any answer with the content, still count.
  Found on the maintainer's own vault, not in a registered set; the six memory-honesty sets and set 18 are unchanged.
  `tests/test_asked_before.py` (English and Chinese).
- **Fixed: what a machine put into your turn was taken as your words.** A message from another agent session
  (`<\~cross-session-message …>`) was noted as a correction candidate; the same would have been imported as one of
  your turns. The prompt hook, the turn record and the session import now skip messages from other sessions,
  background task notices, system reminders, sub-session and CI events and text a KRouter hook injected (the blocks
  are taken out of a message; a message made only of them is not a turn). Found on the maintainer's own vault, not in
  a registered set. `tests/test_machine_input.py`.
- **A nightly job that did not install is no longer reported as installed.** On a machine with no systemd user session
  and no crontab (a container, a minimal server) `--timer` printed "HOST ACTION: no systemd … and no crontab" and then
  went on to say, in its summary line and on the health page, that the job was running, and `krouter doctor` failed
  with "no job is installed". The install now checks that a job exists after asking for one and says "The nightly job
  was NOT installed". The "keeps up by itself" line also no longer comes out empty when the nightly job is on and no app
  has hooks.
- **An English question in a mostly Chinese vault no longer comes back `medium` from English web clippings that
  only share its common words.** Seen on a real vault (reproduced on a synthetic one, a test now): "What is the
  production database password of the billing service?" matched three clipped articles on `production`, `billing` and
  `service`, while `database` and `password` appear nowhere in the vault; the rule for words the vault has never seen
  let it through because three other words matched. Now, when every one of the top three pages is a web clipping (a
  folder named for clippings, `剪藏`, `Clippings`, `Web clips`, or clipper frontmatter: a `source:` URL, a `clippings`
  tag, `type: clipping`), confidence is at most `low` and the receipt says the pages are someone else's writing; and if
  the question also has a word of four or more letters that no word in the vault even starts like (`password`, but not
  `move` when `moved` is there), it is `recall: none`. The stricter version without the clipping condition was tried
  first, on development data: it would refuse 3 to 7 answerable LongMemEval dev questions and one dev2 correction, so
  it was not used. No page in the memory-honesty vaults or the LongMemEval haystacks is a clipping: the rule fired on
  none of 395 development questions, and the six memory-honesty sets are unchanged.
- **Fixed: running the install again could make a second memory folder.** 1.x named the folder from the
  system's language; 2.0 reads the terminal's. Upgrading a 1.3.0 install made on a Mac set to Chinese from an English
  terminal created `Second Brain` beside `第二大脑` and pointed the nightly job at it (found by the upgrade check in a
  throwaway home). The installer now uses the folder the first install recorded (`~/.config/krouter/vault`) while it
  exists, after `--vault` and `KROUTER_VAULT`, before the default name.
- **Fixed: two lookups that found the same changed pages at once could index them twice.** Each then indexed the
  pages it had seen change, and the index held two entries for a page (the old one-process-per-lookup server and
  parallel `krouter ask` runs could hit it too; reproduced 3 of 3 times with 6 processes and 150 changed pages).
  Re-indexing now takes SQLite's write lock and re-reads what is indexed first, and a refresh that finds nothing
  changed takes no lock. Also fixed: `recall()` left its SQLite connection open until the garbage collector ran
  (about 2.7 MB each in a long-running process).
- **Fixed: `krouter.ask()` gave the vault folder as `page` and an empty `how` for ordinary lookups.** They now come
  from recall's best live hit (the locked page on an exact match), and `Answer.hits` lists every hit with its tier and
  status, a replaced page included but never as the answer.

### Not compatible, and how to upgrade

- **The router moved.** `skill/krouter-obsidian` is `skill/krouter`; the install is `~/.agents/skills/krouter`
  (was `~/.agents/skills/krouter-obsidian`) and the Cursor rule `~/.cursor/rules/krouter.mdc` (was
  `krouter-obsidian.mdc`). Upgrading moves the code and your alias table there, leaves the old path as a link to
  the new folder (so a path you pasted into your own notes or agent rules keeps working), registers the MCP entries,
  the Codex / Cursor hooks and the nightly job at the new path, and removes the old Cursor rule. Uninstall removes
  both paths. `krouter doctor` names any settings file that still starts KRouter from the old path. Tested in a
  throwaway home: a 1.3.0 install (nightly job, Codex hooks, Claude Code MCP and plugin) upgraded, looked up through
  both paths with the same answer, doctor OK, uninstalled with no KRouter entry left. Not tested on Windows, where
  the link is a symlink or, without the right to make one, a directory junction.
- **The receipt has more in it.** A lookup lists up to five pages: three direct hits under `recall:`, then up to
  two under `associated:` (each with `via:`). Hit lines can carry `conflict=newer` / `conflict=older`, and a receipt
  can have a `recall_conflict:` line. A reader that takes the first `recall:` hit is unaffected; one that counts
  pages or reads the whole block should skip `associated:` (`recall(..., assoc=False)` in process gives the direct
  ranking alone). The recall cache is rebuilt by itself on first use (schema `recall-v15`).
- **Defaults that changed:** the install imports nothing from the past (`--all` for the old default); the
  language is the terminal's (`--lang`, then `LC_ALL` / `LC_MESSAGES` / `LANG`), not the system's; the experience
  digest is on when the vault has cards (`KROUTER_EXPERIENCE=0`); with no key, the nightly steps run on a logged-in
  agent CLI and spend its subscription, at most 30 calls a day, each listed (`KROUTER_HOST_CLI=0` turns it off).
  Every message is now looked up on this machine by the prompt hook and the session starts with the standing index
  (`KROUTER_RECALL_PROMPT=0`, `KROUTER_RECALL_INDEX=0`); skills are listed and drafted overnight when there are cards
  to grow them from (`KROUTER_SKILLS=0`); a team server started with `--users` needs each caller's own token.
- **`KROUTER_VAULT`** names the memory folder; `OBSIDIAN_VAULT` still works.
- **To upgrade,** run the install line again (from a clone, `python3 scripts/bootstrap.py`), then `krouter doctor`.
  It keeps the memory folder it recorded, every file in it, and what you said yes to before.
- **Benchmark numbering:** the refusal-gate study is set 14 in `bench/memory_honesty/HELDOUT.md` (two
  branches had both called theirs 13); no registered number changed.

## 1.3.0 — 2026-11-09

**What you will notice**
- **Once you said yes to importing, the memory keeps itself current, and shows you everything it changed.** Distilled
  decisions take effect without a confirmation step and a new session starts from all of them, corrections first.
  Each run writes what it added and what it replaced to `90 系统文件/自动化/记忆变更记录.md`; in a vault that is a git
  repository each run is also one commit, and `import_sessions.py --undo <run>` takes it back.
  `KROUTER_INJECT=confirmed` keeps the 1.2 behaviour.
- **Corrections are written down the moment you make them.** With the Claude Code plugin, a line that reads like a
  correction is kept as a candidate on the spot (local, no model call) and settled by the next distill. A long
  conversation is also recorded before it is compacted.
- **Daytime capture** at two set times, from an optional timer (`extras/host-daily-evolution/intraday_capture.py`).
- **Keep a session out** with `#nocapture` / `#不记` in a question, or a whole folder with `--exclude-root`.
- **A manual install (`install.sh`) now records where the vault is**, so the hooks work there too.
- **The README speaks to anyone with one AI app**, and leads with benchmarks other people wrote (LongMemEval, LoCoMo),
  with what they do not measure and the weakness they show.

**Details**
- **Answer cards: old cards are re-checked, broad questions are dropped.** Cards written before the whole-token check
  (the 2026-10-10 batch) stayed in the file for good, blocked only when read; each run now holds kept cards to the
  current checks and asks a page again once when one fails. A question too broad for the checkup page is dropped when
  it is written, and the prompt asks for the page's own subject and for values copied as written. Layout spaces
  (`1 : 3.3`, `6230 / N70 / N73`, `1.2MB / 498`) and a trailing `_` (`session_item_`) no longer fail a verbatim
  answer: on the author's vault 6 of the 8 cards the checkup listed as unfaithful were this; the other 2 rewrote a
  date (`08-16` → `8/16`) and are still refused.
- **Session import next to another collector, and forks.** A session a `type: daily-log` page already lists, or a
  day its collector covered, is linked to that log (`covered_by`) or, with `--overlap skip`, not written. A fork or
  resume that copied another session's turns no longer writes them twice. Session-end distilling sends only the
  turns added since the last digest, waits for a running import instead of sending the same session twice, and uses
  the lane named at consent. `docs/AUTO_CAPTURE.md`.
- **Decision-capture bench** (`bench/decision_capture/`): 14 fixed sessions, recall and false-extraction rate scored
  by rule, no judge model.
- **Daytime capture, corrections on the spot, and a way to keep a session out.** `import_sessions.py --intraday`
  imports and distills today and yesterday with the lane recorded at consent, and does nothing before it;
  `extras/host-daily-evolution/intraday_capture.py` runs it at fixed wall-clock slots (default 12:10 and 18:10 in
  `Asia/Shanghai`) from an hourly timer, catches up the latest missed slot after sleep and tries a failed slot once
  more, then leaves it to the nightly job. `session_hook.py prompt` (UserPromptSubmit) writes a typed correction
  ("改成", "以后一律", "锁死", "from now on") to the day's `纠正候选` page as a provisional candidate: local pattern
  match, redacted, no model call; rhetorical questions ("不是吗", "对不对") and KRouter's own model calls
  (`KROUTER_IN_DISTILL`) are not captured. A session with `#不记` (or `#nocapture`) in a question, or under a root
  on `--exclude-root`, is neither imported nor distilled, and a page already written for it is removed.
- **Capture takes effect without a yes; every run is visible and reversible.** Distilled lines are no longer marked
  "待你确认" and the SessionStart hook brings all of them (corrections first; `KROUTER_INJECT=confirmed` keeps the old
  gate). Correction candidates are settled by the next distill of their session (成立 with the matching line, or
  不成立). Each run that changes something makes one git commit of exactly its files (`[krouter-run <id>]`) and one
  entry in `90 系统文件/自动化/记忆变更记录.md` (added lines, replaced decisions, source session, verdicts);
  `import_sessions.py --undo <id>` reverts the run and keeps its record.
- **`install.sh` records the vault path for hooks and the MCP server.** They do not inherit `OBSIDIAN_VAULT` from
  the host app; bootstrap already wrote `~/.config/krouter/vault`, `install.sh` did not, so after a manual install
  the correction hook and the session-end import found no vault and did nothing, silently. An existing record is
  left alone.
- **README speaks to anyone with one AI app.** The first screen no longer assumes several coding agents: one AI app is
  enough, and any app that runs a local stdio MCP server gets a five-line config ("Works with", marked untested
  where it is). Someone else's benchmarks now lead the numbers: LongMemEval S (439 / 470 answer sessions cited, 70 / 72
  newest facts) and LoCoMo (991 / 1,540 evidence first), with what they do not measure and the abstention weakness
  they show (3 / 30, 37 / 446). The stale real-traffic row is replaced by the 2026-10-16 run and why it is not
  evidence. The bench-only LoCoMo adapter and the dense opt-in evaluation (`docs/DENSE-OPTIN.md`) are merged; nothing
  in the product changed.
- **Off-machine backups.** `backup.py init --dir <folder>` turns on a nightly, encrypted archive of the whole vault
  (its `.git` included, editor state and caches left out) in a folder that syncs elsewhere (iCloud Drive, OneDrive,
  Dropbox, a Netdisk sync folder, a USB disk; several, separated by `|`). AES-256 via openssl with an HMAC; each
  archive is restored into a temporary folder (page count, `git fsck`) before it counts; the newest 7, plus one per
  week for 4 weeks and one per month for 6 months, are kept. The passphrase lives in the keys file, outside the vault;
  `status` asks the agent to tell you while it is not saved anywhere else, or when no backup has restored cleanly for
  three days. KRouter talks to no cloud. Restoring needs only openssl and tar. DETAILS → Backing up your vault.
  Empty folders and symbolic links come back as they were; what a link points to outside the vault is not in the
  archive, and each run says how many such links there are (`links_outside`).

## 1.2.1 — 2026-10-20

**What you will notice**
- **Security fix: the `claude` nightly writer can no longer read files outside the vault.** Up to 1.2.0 its Grep and
  Glob were allowed with no path, so it could print lines from any file in the account, the keys file included. Only
  a nightly job on the `claude` lane (installed by `install.sh`, `--ask` or `--timer`) was affected; upgrade by
  running the install line again.

**Details**
- **Security: the claude nightly writer could read files outside the vault through Grep.** Its allow-list scoped Read
  and Edit to the vault but allowed Glob and Grep with no path; in a test with a canary file outside the vault, Grep
  printed the canary line (Read was refused). Glob and Grep now carry the vault path too; the same test leaks nothing
  and Grep and Glob still work inside the vault. Affects only the nightly job installed by `install.sh` or `--ask` /
  `--timer` on the `claude` lane; the API-key, grok and Codex lanes, and the model steps (no tools at all), are not
  affected. Found by an outside review.
- `first_run.sh` ends by pointing at `bootstrap.py --dry-run` and the lookup-only install, not at `install.sh` (which
  installs the nightly job).

## 1.2.0 — 2026-10-19

**What you will notice**
- **Installing changes nothing you did not ask for.** The one-line install is lookup only, asks nothing and sends
  nothing; `bootstrap.py --ask` turns remembering on. A logged-in Codex, which can read the whole account, is no
  longer picked as the nightly writer unless you name it.
- **Session distill writes down more of what was decided, changes of mind first:** on the registered measurement set,
  missed 52% → 41% and changes of mind 11 → 15 of 24.
- **A new session no longer starts from an answer you already changed.**
- **Fewer confident wrong answers:** a question that names something no page mentions is refused, and one that matches
  a single word of a page says so. This release ships the refusal change before the registered real-traffic blind
  judge (it waits for 50 fresh queries); its result will be logged in `bench/memory_honesty/HELDOUT.md` against 1.0.3.
- **Outside numbers:** on LongMemEval (questions and labels by its authors, scored without a model), KRouter cites an
  answer session for 439 of 470 answerable questions and the latest update for 70 of 72, level with plain BM25. See
  HELDOUT.md, set 7.

**Details**
- **Session distill writes down more of what was decided, changes of mind first.** A long session-day is distilled
  in segments of about 6 000 characters, plus one pass over the whole excerpt for changes of mind (decided early,
  changed later, often in different segments); near-duplicates are merged; changes come first; up to 24 lines per page
  (a new session still gets 8, changes first). The prompt says what is not a decision (steps, discussion, one-offs) and
  that a proposal the user accepted counts. On ten tuning sessions (not the measurement set): missed 44% → 22%,
  changes of mind 13 → 15 of 17, steps-or-fabricated share 29% → 31% (fabricated 1 → 7 of 202). More model calls per
  page (one per segment, plus one). On the
  registered measurement set (set 6: 22 session-days never used for tuning, scored by Grok against the same
  131-item reference): missed 51.9% → 40.5%, changes of mind 11 → 15 of 24, steps-or-fabricated 21.7% → 17.1%;
  all three registered criteria met.
- **The one-line install is lookup only and asks nothing.** It makes or finds the vault, installs the router,
  connects the agents, and stops: no session import, no nightly job, nothing leaves the machine. Its last lines say
  how to turn remembering on: `bootstrap.py --ask` puts the two questions it used to put at install (import recent
  sessions? install the nightly job?), with the same preview of what is sent; `--import`, `--import-distill` and
  `--timer` still say yes in advance. An upgrade where you said yes before (session import consent, or a nightly job
  on disk) keeps it and is not told it is off.
- **Codex is no longer picked as the nightly writer on its own.** It writes only the vault but can read the
  whole account, keys file included. It is used when you name it (`KROUTER_WRITER`, `KROUTER_LEARN_CLI`) or set
  `KROUTER_ALLOW_CODEX=1`; otherwise a logged-in grok or claude, both limited to the vault, is used instead, and a
  Codex-only machine is told why distilling was skipped (`codex:reads-account`).
- **A question that names something the vault never mentions is refused** (shipped before the real-traffic blind judge; see above).
  "Which did I start first, the Ferrari model or the Porsche model?" on a vault that has never mentioned a Porsche was
  answered from the Ferrari page. Now a capitalised word in mid-sentence (`Porsche`, `Seattle`, `iPad`) that no page
  contains refuses the question; sentence-initial capitals, two-letter words such as `OK`, and month and day names do
  not count. Tuned on LongMemEval S's 30 unanswerable questions (now a development set: refused 3 → 9, answerable
  questions refused 12 → 14 of 470) and dev3 (one more neighbour refused, nothing lost). heldout3, run once: wrong
  citations 26.6% → 26.1%, neighbours refused 46 → 47 of 80, answerable right 102 of 120 unchanged.
- **A question that matches one word of a page now says so.** On a 20-page vault, "小红书的笔记几点发？" was answered at
  medium confidence from a page about sealing days, on the single word 笔记: the score floors scale with vault size,
  so a new vault lets a one-word match through. On the dev sets such answers are right half the time and the score
  does not tell which half, so whether to answer is unchanged (dev, dev2, dev3 identical). What changes: confidence is
  `low`, the receipt carries a `recall_note:` line (only one word matched; say the vault may not cover the question),
  and no generated answer is attached. Alias hints no longer come from scattered characters or question words
  ("剪辑" was offered "剪藏原件"; "标题有什么讲究" was offered a page on 什么): a hint needs a shared two-character word.
- Docs: retrieval described as it is. PROTOCOL, ARCHITECTURE, DETAILS (en, zh) and VERIFY still called it "a lock on short
  nouns" and quoted "25/25 paraphrases miss" without saying that tests the alias lock alone; outside agents read that
  as "you must maintain an alias table and any rewording misses". Ranked recall answers most questions; the alias lock
  is an optional fast path that needs no upkeep. FOR-AGENTS gains "Common misreadings" (no alias upkeep, rewording,
  what leaves the machine, the earlier names Runtime36 and DSH-KRouter and what pages about them describe, stale
  version numbers).
- **A new session no longer starts from an answer you already changed.** The SessionStart hook injected a
  decision next to the later correction that replaced it ("本地 API 端口用 8080" beside "原来 8080 → 改成 9090"), so
  the agent saw both. Lines are ordered by page date, then their (HH:MM), then their place on the page; a line is left
  out when a later correction replaced the value it still holds ("8080", not just the shared words "本地 API") on the
  same subject, unless an even later correction restores it (same-day revert); chains (30 → 10, then 10 → 5) keep only
  the newest; unrelated decisions, and the same value on another subject, stay. A line that holds the replaced value
  but only part of the correction's subject ("测试环境 API 端口用 8080" against "本地 API 端口 8080 → 9090") is kept and
  marked "可能已被上面的「→」改过，先核对" instead of dropped. Found while designing the injection bench; an outside
  review caught two regressions in the first version and one remaining case in the second, now tests.
  `tests/test_stale_injection.py`.
- Docs: 1.1.x is the stable line (fixes only until 2026-11-12, at most one patch a week); DETAILS lists what the
  stability promise covers (core) and what is best-effort (extras); FOR-AGENTS and the status block name the smallest
  install, router only with nothing in the background.
- Docs: what outside reviews misread, checked against the code (FOR-AGENTS "Common misreadings": Obsidian is optional,
  no writer skips permission prompts, an existing vault or router is left alone, not only for code); ARCHITECTURE no
  longer says the claude and grok writers skip permission prompts (untrue since 0.12.0).
- Docs: `docs/img/demo-content.gif`, the same story as `demo.gif` for short-video work, recorded the same way; plugin,
  skill and package text call Obsidian optional.
- Bench: sets 7 (LongMemEval, scored from its authors' labels; `bench/longmemeval/lme.py`), 8 (answers over the
  vault's own git history) and 9 (written by people: corrections and their neighbours) registered before any run; set
  7 run and amended (S's unanswerable questions became a development set).

## 1.1.1 — 2026-10-15

**What you will notice**
- **The nightly learner stops making recall worse.** Up to 1.1.0 it could learn a question onto a page that only
  shares its subject; on the dev sets one night of that raised wrong citations (2 → 5, 7 → 9). It now has to copy the
  sentence that answers the question, and learns only when that sentence is on the page and is about the question.
  Triggers it learned before stay; look at `90 系统文件/自动化/下意识触发词-自学习.psv` if your recall got worse.
- **CLIs KRouter cannot confine are no longer used without your yes.** If your only logged-in CLI is opencode, kimi,
  pi, vibe, antigravity or cursor-agent, the nightly job and model steps now skip it and say why; set
  `KROUTER_ALLOW_UNCONFINED=1` in `~/.dsh-krouter-keys.env` to keep using it. grok, Codex, claude and API keys are
  unchanged.
- **Every page an agent may land on tells the same, current story**, checked in CI against the bench and the version.

**Details**
- Release: the release workflow refuses to pack when the tag, `package.json`, `plugin.json`, `extras/dsh/package.json`,
  the newest CHANGELOG heading and the status block do not name the same version, or when changes are still listed
  under "Unreleased". The status block now says it describes `main` and names the latest release.
- Docs: every entry file an agent may read on its own (PROTOCOL, SECURITY, VERIFY, ARCHITECTURE, BENCHMARK, DETAILS,
  FOR-AGENTS) now opens with the same current-status block: the held-out numbers and that they are not real traffic,
  that BM25 with the two rules is level, that the real-traffic blind test has not run, who wrote the questions, how the
  nightly job is installed and what each writer lane can reach. One source (`docs/STATUS.md`, `docs/STATUS.zh.md`),
  copied by `scripts/sync_status.py`; a test fails when a copy drifts.
- Docs: who the "outside reviewer" is, said plainly in HELDOUT.md, BENCHMARK.md and FOR-AGENTS.md: Claude Opus in
  claude.ai chat sessions the maintainer starts, not a human, same model family as the coding sessions. A set written
  by a person is planned.
- **CLIs KRouter cannot confine are no longer picked on their own.** The nightly writer and the model steps use grok,
  Codex and claude without asking (a kernel sandbox, a write sandbox, a tool allow-list). opencode, kimi, pi, vibe,
  antigravity and cursor-agent run with no confinement KRouter can set, so a logged-in one is now skipped, and a
  confined CLI further down the list is used instead, unless you set `KROUTER_ALLOW_UNCONFINED=1` (environment or
  keys file). A pinned `KROUTER_WRITER` or `KROUTER_LEARN_CLI` follows the same rule; the writer and `host_action` say
  why one was skipped.
- **The nightly learner no longer learns from neighbour pages.** On the dev sets it picked pages that only share a
  question's subject and so made recall worse after one night (wrong citations 2 → 5 and 7 → 9). It now sees the start
  of each candidate page and must copy the sentence that answers the question; a pick is learned only if that quote is
  on the page, is a sentence (four words or more) and shares a content word with the question. The old bare-path
  answer no longer counts. After one night on the dev sets: no wrong triggers, and few learned at all (3 and 0); no
  gain shown yet. Secret pages and `03 资料与证据` (clipped, pasted text) are never candidates. The learner now sends,
  per unanswered question, up to 4 candidate pages' first 600 characters, redacted (SECURITY.md). `learn_bench.py`
  measures this.
- Benchmark: `bench/memory_honesty/human_set/` (instructions, template, checker) for a held-out set written by a
  person, each thing asked twice in different words; `learn_bench.py` ("learns from use": week 1 through the router
  and one night of learning, week 2 scored before and after).
- Docs: one story for the nightly job everywhere. `PROTOCOL.md`, `first_run.sh`, `install.sh` and the nightly writer's
  files said "timer on by default"; the one-line install asks first, and only the manual `install.sh` installs it.
- Docs: the comparison with claude-mem and basic-memory says up front that neither can refuse, so their 0 of 80 is
  structural, and that BM25 with KRouter's two rules is level with it; the answerable-right column (102 / 72 / 45 of
  120) is the comparison that does not depend on refusing. Their heldout3 per-question output is stored and regraded
  in CI. `extras/hooks/exec-gate.py` is described as an accident guard, not a security boundary.

## 1.1.0 — 2026-10-14

**What you will notice**
- **Cursor users get their history on day one.** The install's "import the agent sessions already on this machine?"
  now covers Cursor agent sessions as well as Claude Code and Codex: one page per session and day, your questions and
  each turn's closing answer, redacted, nothing leaving the machine.

**Details**
- **Cursor sessions import too.** Cursor agent transcripts (`~/.cursor/projects/*/agent-transcripts/`) become
  session pages like Claude Code and Codex ones: your questions (the `<user_query>` part), each turn's closing answer,
  redacted, on the day and minute Cursor stamped on the question. The project folder is recovered from Cursor's
  folder name by checking which path exists. `KROUTER_CURSOR_PROJECTS` points at another root. Closes #26.

## 1.0.4 — 2026-10-14

**What you will notice**
- **Two popular memory tools measured on 200 questions.** On the outside reviewer's third bench (200 held-out
  questions in English and Chinese, 80 the vault cannot answer, 20 daily logs as distractors), every system at its
  defaults: KRouter cites a wrong page 27% of the time, claude-mem 13.39 64%, basic-memory 0.23 78%. KRouter refuses
  46 of the 80 unanswerable questions; they refuse none. Every difference is significant. Recall is unchanged since
  1.0.3, so these numbers hold for 1.0.4.
- **The README is written for someone deciding.** The numbers come first, with a command that reruns them in about a
  second and needs no install; then a look-first install path, and who it is and is not for. `docs/FOR-AGENTS.md`
  gives an agent asked to recommend it the table, the limits and the risks in one place.
- **Packages you can trace to their source.** Release packages now carry a GitHub build-provenance attestation:
  `gh attestation verify dsh-krouter-1.0.4.tgz --repo 398894496-arch/KRouter`. `SECURITY.md` explains each flag a
  static scanner raises.

**Details**
- Docs: the README opens with the 200-question numbers, a look-first install (clone, sample receipt, `--dry-run`,
  then install with the nightly job off), who it is and is not for, and a one-second way to rerun the numbers.
  `docs/FOR-AGENTS.md` carries the third-bench table and the risks in one place; `SECURITY.md` maps each flag a static
  scanner raises to its file.
- Release: packages get a GitHub build-provenance attestation (`gh attestation verify`), so a package can be tied to
  the tagged source and the workflow that built it, not only to a checksum in the same release.
- Benchmark: claude-mem 13.39.0 (latest) on the 200-question third bench, at its defaults: 64% wrong citations,
  0 of 80 neighbours refused, 72 of 120 right, against KRouter 1.0.3's 27%, 46 and 102 (every difference significant).
- Benchmark: basic-memory 0.23.2 (latest) on the 200-question third bench, at its defaults: 78% wrong citations,
  0 of 80 neighbour questions refused, 45 of 120 right, against KRouter 1.0.3's 27%, 46 and 102 (every difference
  significant). `floor.py` and both adapters now run on all three vaults; the container runs offline.
- Docs: the README's honest numbers now come from the third bench (200 held-out questions, 95% intervals): level
  with BM25 plus the two rules at equal coverage, not ahead. The fresh-traffic blind judge waits for 50 new queries
  instead of a fixed 2026-10-16 date.
- Benchmark: a third held-out set by the outside reviewer, `heldout3.jsonl.gz`: 200 questions (80 neighbours, half
  Chinese) on `vault3/`, 110 pages including 20 daily logs as distractors, with no dev set on that vault. `run.py`
  gains `--ci` (bootstrap intervals), `--vs` (paired intervals), `--vs-matched` (equal coverage) and `--curve`.
  Baseline: KRouter 1.0.3 is ahead of BM25 with the two rules at equal coverage on every measure, significant on
  none. The decision rule for "surpasses BM25" and for a new default is in HELDOUT.md, written before any candidate.
- Benchmark: a negative result recorded. Recall changes that were better on both dev sets were worse on held-out
  (38% / 31% wrong citations vs 25%), so they were not shipped (`docs/BENCHMARK.md`, "Tried and not shipped"). A
  second dev set, `questions_dev2.jsonl` (50 questions, written by the maintainer), is added for tuning.
- Benchmark: a second, bilingual bench written by the outside reviewer. `vault2/` (60 pages, half Chinese), 50 dev
  questions (`questions_dev3.jsonl`) and 50 held-out (`heldout2.jsonl.gz`, gzipped so it stays out of greps), each
  with 20 neighbour questions whose missing term CI checks is on no page. First run, before any change: KRouter 33%
  wrong citations on heldout2 (9 / 20 neighbours refused, 24 / 30 answerable right); BM25 with the two rules 23%
  (15 / 20, 17 / 30); plain BM25 61%. `run.py --set dev3|heldout2`; the vault2 BM25 baselines search Chinese by
  character pairs.

## 1.0.3 — 2026-10-12

**What you will notice**
- **The comparison no longer flatters KRouter.** An outside review showed that the "25% vs 60%" gap was mostly
  structural: at their defaults the other systems cannot refuse and do not know a page was replaced. With the same two
  rules given to them (superseded pages left out, a refusal floor picked on the dev set only), plain BM25 reaches 19%
  wrong citations on held-out and basic-memory 30%. At the same coverage as KRouter they cite slightly fewer wrong
  pages (2 vs 3 of 12). The README and `docs/BENCHMARK.md` now say so plainly: KRouter's advantage on this bench is
  those two rules on by default, plus receipts, not a better ranker. Reproduced, not taken on trust; KRouter was
  not changed in response, because the held-out set is not a tuning target.
- Release cadence written down as practised: minor releases at most weekly, patch releases when ready.

**Details**
- `run.py --adapter bm25-floor`; `bench/memory_honesty/floor.py` applies "skip superseded + dev-picked floor" to any
  adapter output that carries scores; the basic-memory adapter now records scores.
- Third-party systems run in a Linux container (`bench/memory_honesty/adapters/Dockerfile`): basic-memory was re-run
  there, with identical answers to the host run. A container does not share the host's keychain or launchd.
- HELDOUT.md log: the reviewer's and the maintainer's baseline runs (aggregates only; no `--reveal`; no KRouter
  change).

## 1.0.2 — 2026-10-12

**What you will notice**
- **A comparison, with the other systems actually run.** On the 25 held-out questions, KRouter cites the wrong page
  25% of the time. basic-memory 0.22.1 does 60%, claude-mem 13.35.0 60%, and plain full-text search 61%. Of 10
  neighbour questions, KRouter refuses 8; the others refuse 0, 0 and 1. The cost is stated next to it: KRouter got 9
  of 15 answerable held-out questions right, basic-memory and claude-mem 10, full-text search 9, because KRouter refuses some questions phrased in
  words the page does not use. Both sets, how each system was run, and every system's raw per-question output on the
  dev set are in `docs/BENCHMARK.md` and `bench/memory_honesty/results/`.
- **claude-mem import, checked on a live install (13.35.0), is no longer beta.** One fix came from the real data:
  claude-mem files most decisions as `change` (only the reversal of an earlier decision came out as `decision`), so
  the decisions page now takes `decision`, `change`, `feature`, `bugfix` and `refactor`. In the live run, the model
  pass sorted them correctly: "any branch, manual upload → tags on main, CI publishes" was marked as replaced, and the
  session-start hook brought exactly that correction into a new session in the same repository and nothing into the
  other one. The decisions page's `how` line is now a summary of the page; the line matching the question comes from
  recall.
- **The memory honesty bench has a held-out set.** The 25 questions the 1.0.1 headline number comes from are now in
  `bench/memory_honesty/heldout.jsonl`: 9 corrections, 6 current, 10 neighbour questions on the same vault, written
  by the outside reviewer and never used for tuning. `run.py --set heldout` prints aggregates only; `--reveal` prints
  the misses and, followed by a ranking change, burns the set. Rules, the baseline at freeze and a log of who has
  seen what: `bench/memory_honesty/HELDOUT.md`.

**Details**
- The held-out set from the outside review (#32): `bench/memory_honesty/heldout.jsonl`, 25 questions; `run.py
  --set heldout` prints aggregates only, `--reveal` shows misses and burns the set; rules and log in `HELDOUT.md`.
- `tests/test_memory_honesty_heldout.py` pins a SHA-256 of the questions and of the bench vault (line endings
  normalized), checks the set does not overlap the development questions, and checks only a sanity guard: fewer
  wrong citations and at least as many refusals as plain full-text search. No floor on the held-out score.
- Adapters for basic-memory and claude-mem (`bench/memory_honesty/adapters/`); `tests/test_memory_honesty_competitors.py`
  re-grades the stored raw output and re-runs KRouter and BM25 against the published dev rows.
- No ranking, refusal or card change. Held-out at freeze (1.0.1): 25% wrong citations (3 / 12), 8 / 10 refused,
  5 / 9 corrections, 4 / 6 current; BM25 61% (14 / 23), 1 / 10.

## 1.0.1 — 2026-10-12

Fixes from an outside review of 1.0.0.

**What you will notice**
- **Fixed: decisions brought into a new session leaked across repositories that share a folder name.** The session-start hook matched by folder name, so a session in `beta-corp/api` was given `alpha/api`'s decisions. Reproduced, then fixed. A repository is now its git top level (or its directory, outside git). The path is written into each imported page (`project_root:`), and only pages for this exact repository are brought in. claude-mem's memory is split the same way, using the `cwd` it records. Pages imported by 1.0.0 have no path and are no longer brought in; re-run `import_sessions.py --days 30` to backfill (existing digests are kept).
- **Only what you confirmed, plus corrections, is brought in by default.** That means every line of a page you confirmed (`status: active` or `confirmed: true`), and from unconfirmed pages only the "A → B" corrections, marked unconfirmed. `KROUTER_INJECT=all` restores the previous behaviour. The text is in English unless the decisions are in Chinese.
- **Honest headline number.** On 25 questions written by the reviewer and never used for tuning, KRouter cites the wrong page 25% of the time (3 of 12 answered), against 61% for plain full-text search. The README and `docs/BENCHMARK.md` now lead with this, not with the 0% on the bench's own questions, which is a development-set number.
- **The claude-mem importer is marked beta** until it has run against a live claude-mem install.
- README: the plugin needs Claude Code 2.1.275 (2.1.292 for the shell form), and third-party marketplaces do not auto-update (`claude plugin update krouter@krouter`, or Enable auto-update in `/plugin` → Marketplaces).

## 1.0.0 — 2026-10-12

**1.0 means the surface agents and vaults depend on is now stable**: the vault layout, the alias table, the receipt
fields, the routes, the MCP tools, the `KROUTER_*` variables and the importers' page markers change only in a major
release, with a migration. Scoring may still be retuned in minor releases, always with before / after numbers on
the public benches. Nothing breaks from 0.13.0: same vault, same table, same receipts; re-run the install line to
upgrade.

**What you will notice**
- **Coming from claude-mem.** The install finds claude-mem's memory and offers to import it. Its session summaries
  become log pages, and each project's decisions become one page you confirm (`status: candidate`). With distilling
  on, your model sorts each project's decisions into the ones still in force and the ones a later decision replaced
  ("原来 A → 改成 B"). In a real run it caught "manual tags from any branch → tags on main, CI publishes". claude-mem
  is opened read-only and never changed.
- **The two things that make claude-mem feel like memory, in the Claude Code plugin.** When a session ends, it is
  imported (in the background, local; distilled when you said yes to that). When a session starts, up to 8 of this
  project's decisions from the last 30 days come with it, corrections first, each naming its page. Both run only after
  you said yes to importing, and `KROUTER_INJECT=0` turns the second off. Tested end to end with Claude Code: a new
  session answered "what did we decide about releases" with no tool call and named the page, and the session was in
  the vault when it ended.

**Details**
- `import_claude_mem.py` reads both column generations of claude-mem's schema (`memory_session_id` and the older
  `sdk_session_id`; epoch milliseconds or seconds), as of claude-mem `b3e036fa13`. The tests build both from its
  schema; it has not been run against a live claude-mem install. Pages carry `source: krouter-claude-mem`, and a page
  without that marker is never touched.
- `session_hook.py start|end`, wired by `hooks/hooks.json` at the plugin root; `import_sessions.py --file` imports one
  transcript.
- `nightly.py` gains `import_claude_mem`. It stays `off` until consent, and is also `off` when claude-mem is not
  installed.

## 0.13.0 — 2026-10-12

**What you will notice**
- **Useful in five minutes, not after a night.** The install asks whether to import the Claude Code and Codex
  sessions already on the machine (the last 7 days). On a yes, each session becomes a page (your questions and
  each turn's closing answer, redacted first, written only on this machine). A second question asks whether your
  model should write "what was decided, what changed" at the top of the latest sessions' pages, and says how many
  characters that sends first. Then it suggests a question to ask your agent.
- **Claude Code and Codex find the vault on their own.** The install registers KRouter as an MCP server
  (`krouter_ask`, `krouter_status`) with each CLI it finds and records the vault path, so no one has to export
  `OBSIDIAN_VAULT` first. Claude Code can also install it as a plugin:
  `/plugin install krouter --marketplace 398894496-arch/KRouter`.
- **A new front page.** One sentence on what it does, a 30-second demo (real Claude Code output), one install line,
  and how it differs from typical agent memory. Everything else moved to [`docs/DETAILS.md`](docs/DETAILS.md); facts
  for an agent deciding whether to recommend it moved to [`docs/FOR-AGENTS.md`](docs/FOR-AGENTS.md), phrased as
  facts rather than instructions.
- **A public memory honesty bench** ([`docs/BENCHMARK.md`](docs/BENCHMARK.md)): wrong-citation rate, refusals on
  neighbour questions, corrections followed. Plain full-text search that always answers: 63% wrong citations.
  KRouter 0.12.1, first run: 22%. 0.13.0: 0%, all 10 neighbour questions refused, 8 of 10 corrections followed
  (a development-set number: the fix below was found on this bench).

**Details**
- `import_sessions.py`: Claude Code `~/.claude/projects`, Codex `~/.codex/sessions`; one page per session and day
  under `05 时间日志/会话摘录/`, named after the session title. Headless runs (`claude -p`, `codex exec`, the nightly
  job's own calls), tool output, thinking, injected context and subagents are left out. A page it did not write is
  never touched. A session that grows is re-rendered, keeping its digest until the session changes. `--dry-run`,
  `--consent` and `--revoke` are supported, and the nightly job imports yesterday only after `--consent`. Imported
  pages rank as logs: clues, not rules.
- `nightly.py` gains `import_sessions` as its first step. It is `off` until the host consents, and `off` is not
  reported as a problem.
- `mcp_server.py`: MCP over stdio, standard library only. `krouter_home.py`: the router, the shell router and the
  MCP server fall back to `~/.config/krouter/vault` when `OBSIDIAN_VAULT` is unset.
- **Recall: English function words no longer count as unknown words.** `what`, `which`, `does`, `should` and the
  like were in no stop list, so in a small vault they counted as words the vault had never seen. That refused real
  questions and let neighbour questions through on `what` and `do`. They are now dropped from ranking and refusal,
  and plural and singular forms match each other (`services` / `service`). The author's Chinese vault scores the same
  before and after.
- **Fix: re-installing no longer deletes lines from the keys file.** The key probe rewrote
  `~/.dsh-krouter-keys.env` from its own results, dropping the claude long-lived token, pending keys, keys that
  failed that day's probe, and comments. It now updates only the names it manages. Found while testing this release
  on the author's machine: the token was restored and nothing was sent.
- Removed from the docs: the claim that the claude writer runs with `--dangerously-skip-permissions` and that the
  Windows task was never run on a real host. Both stopped being true in 0.12.

## 0.12.1 — 2026-10-11

- **`claude` stops getting logged out.** A logged-in `claude` keeps a short-lived token and a single-use refresh token in the keychain. When another program holds the same login — on the author's machine a CLIProxyAPI / EasyCLI copy that refreshes every ~8 hours — whichever refreshes first spends the token and the other is logged out: the CLI went to `loggedIn: false` half an hour after the proxy's refresh, while the desktop app (a separate login) kept working. Concurrent `claude` processes refreshing at once race the same way. Now every KRouter call to `claude` — nightly steps, the writer, the login probe — uses `CLAUDE_CODE_OAUTH_TOKEN` from `~/.dsh-krouter-keys.env` when present (`claude setup-token` issues one that lasts a year and needs no refresh), and runs one `claude` at a time (file lock).
- **The claude writer's allow-list, tested end to end** (the CLI was logged out when 0.12.0 shipped): the router answers, a file outside the vault is denied through both the Read tool and the shell, writing inside the vault works. The runtime prompt now says to run the router exactly as written (a `VAR=` prefix does not match the allow-list), and the allow-list accepts `sh` / `bash` / `/bin/sh` forms.

## 0.12.0 — 2026-10-11

**Renamed: DSH-KRouter → KRouter.** It was never specific to DeepSeek Harness. Old links, the old clone URL, the old
one-line install and old release downloads all redirect (checked after the rename). The npm / DSH plugin package
keeps its name (`dsh-krouter`), and so do the skill directory, `KROUTER_*` variables and the timer labels, so
existing installs are untouched.

**The nightly writer is confined (seventh outside review).** The review said the claude and grok writers, run with
permission prompts skipped and no sandbox, could read and write the whole account — keys file, `~/.ssh` — not just
the vault, and that the docs claimed otherwise. Tested: under the old flags grok read a file outside the vault
through both its file tool and its shell. Now:
- **grok** runs in a kernel-enforced sandbox profile KRouter writes into `<vault>/.grok/sandbox.toml`: grok's
  `strict` (read the working directory and system paths, write the working directory) plus the router read-only and
  KRouter's cache and state writable. Tested: outside file denied through both tools, vault write works, the real
  router answers. The runtime prompt now lives in the vault (`.krouter/`, deleted after the run) because the
  sandbox cannot read outside it.
- **claude** runs with `--permission-mode dontAsk` and tools allow-listed: read and edit inside the vault, run the
  router, nothing else (no other shell command, no web fetch). This is a tool-level rule, not a kernel sandbox; it
  could not be tested end to end this round (the CLI's login had expired) and is covered by an argv test.
- **Codex** keeps its `workspace-write` sandbox (writes the vault only) and is now described truthfully: it can read
  the account. Other CLIs have no confinement KRouter can set, and the install prompt says so.
- The install prompt offers the API-key lane first ("no agent runs on this machine") and states, per CLI, what it
  can reach. `SECURITY.md` has a lane-by-lane table.

**Also from the review**
- Two keys pasted on one line are both kept (each named from the words before it); a line with something
  key-shaped left that cannot be taken apart is kept whole in the keys file's pending area — never dropped.
- Paths and URLs survive redaction: a path- or URL-shaped run, or one ending in a file extension, is kept unless it
  holds a known key shape (`/Users/…/2026Q3Report2026Final.csv`, `https://…/Install2026Guide`, `s3://…`). Keys in
  query parameters and known key shapes inside URLs are still masked.
- The one-line install never falls back to an unverified archive on its own: a release with a checksum file must
  download and match, and a release without one installs only with `KROUTER_ALLOW_UNVERIFIED=1`. `SECURITY.md` says
  what a same-release checksum does and does not prove.

## 0.11.3 — 2026-10-11

- **The Windows one-line install no longer closes the PowerShell window.** `bootstrap.ps1` ended with `exit $LASTEXITCODE`; under `irm … | iex` that exits the user's own session, so the window closed before the last line — the one saying what is left to do — could be read. Found by running the published one-liner on a real Windows host after 0.11.2. It now returns instead; a test keeps both PowerShell scripts ASCII-only and free of `exit`.
- The "no model yet" message no longer promises nightly runs when the nightly job was not turned on.

## 0.11.2 — 2026-10-11

What a stranger's agent checks before recommending it, plus the sixth outside review.

**Consent and integrity of the one-line install (sixth review)**
- The one-line install no longer installs the nightly job silently. It installs the read-only parts (vault, router, rules), then asks in one sentence: which CLI will run, with what permissions (`claude` / `grok` with permission prompts skipped inside the vault; Codex in a workspace-write sandbox; or a direct API call), and how many pages and tokens it will send — from a dry run on the new vault. Only `y` installs it; no terminal to ask on means not installed; `--timer` / `--no-timer` decide up front. `install.sh` (for terminal users) still installs it; `KROUTER_NO_TIMER=1` skips.
- Releases carry the installable package and its `SHA256SUMS` (new `release-assets` workflow); `bootstrap.sh` / `bootstrap.ps1` verify the checksum before unpacking and stop on a mismatch. `KROUTER_TAG` pins a release (now in the README).
- A key pasted on the key page moves out of the vault in every common shape — `NAME: value`, `- NAME=…`, `DeepSeek 密钥：sk-…`, a bare key — not only `NAME=value`. The provider comes from the name, the key's prefix or a provider word; when none tells, the key waits as `KROUTER_PENDING_KEY_n`, the page says how to name it, and the notification says that instead of "no model".
- The redaction backstop no longer masks git commits, SHA digests or SRI integrity strings (pure hex, `sha512-…`) unless a key label precedes them. Trade-off, stated in `SECURITY.md`: an unlabeled bare-hex key is left to the secret-page layer.
- The keys file is written atomically (temp file + rename, mode 600).

**Windows, now in CI**
- CI runs on Linux, macOS and Windows. Running the suite on a real Windows host found two real bugs: vault-relative paths came back with `\`, which broke tiering (rule pages ranked like any page: English bench 1/12 on Windows), and CRLF line endings hid the frontmatter, so `status: superseded` was ignored. Both fixed; Windows passes the suite (POSIX-only tests skip).

**For a stranger's agent**
- README first screen: what it is, the one-line install, what leaves the machine and what it costs (first night ~4k tokens on the template, ~160k on a ~100-page vault), evidence at a glance with the development-set caveat next to the real-traffic number, and a versions policy. Same in Chinese. "Timer on by default" is gone wherever it was no longer true.
- `SECURITY.md` (data flows, what a CLI writer can see, known filter limits, private reporting), `CODE_OF_CONDUCT.md`, issue and PR templates.
- The DSH plugin installs from the release package as well as from git (`dsh plugin --profile web add https://github.com/…/releases/download/vX/dsh-krouter-X.tgz`); the package now includes everything `install.sh` and the one-line install use.

## 0.11.1 — 2026-10-11

- **Answer cards no longer go stale on frontmatter edits.** Cards were keyed to the whole page, so any frontmatter edit — `verified_at`, `status`, or the `nightly` / `nightly_at` fields `nightly.py` writes onto the health page — staled every card on that page, and the nightly run paid to rewrite them only to stale them again minutes later. Found on the author's machine after 0.11.0: all five health-page cards stale, `日更每天几点跑` ranked by a different page. New cards are keyed to the page body; cards written earlier (whole-page hash) stay valid until the page changes, so nothing is regenerated in bulk.
- The health page (`90 系统文件/自动化/日更健康.md`) gets no cards: the system rewrites its body every day (seal dates), so a card on it could never stay valid; the rule pages answer its questions.

## 0.11.0 — 2026-10-11

For anyone, with nothing to know and nothing to maintain. Plus the fifth outside review's two secret findings.

**One line to install**
- `curl -fsSL …/scripts/bootstrap.sh | sh` (macOS / Linux) and `irm …/scripts/bootstrap.ps1 | iex` (Windows) fetch the latest release, make a vault in `Documents/第二大脑` (Chinese template when the system language is Chinese) or `Documents/Second Brain`, install the router, the agent rules and the daily timer, and open the vault in Obsidian. An existing vault only gains missing skeleton files; nothing is overwritten; re-running upgrades. Only Python 3 is required (the Windows script installs it with winget when missing). The last line says the one step left, if any, in plain words. Run end to end on a real Windows 11 host.
- **`template-zh/`**: the template in Chinese, with its own sample alias table.

**Chinese recall on a fresh (small) vault**
- A general two-character word list (jieba dictionary, freq ≥ 100, MIT; `lexicon_zh2.txt`) decides what is a word. Two or more real words the vault never contains, outnumbering those on the top page, mean the question is about something else (`纠错之后的房贷利率是多少`); below 300 pages only real or titled words count as matches (`天会` no longer does). Chinese template bench: half-off-topic refused 1/6 → 5/6, off-topic 5/6 → 6/6, gold page 9/12 unchanged — and unchanged with the alias table emptied. English template and author vault unchanged (+4 ms per query).

**Secrets (fifth review)**
- `redact()` missed 13 of 16 common shapes. It now covers labels in either language and any separator (`密钥：…`, `凭据 …`, `Key: …`), table cells, `?key=` / `&access_token=`, connection-string passwords, more provider prefixes, and a backstop for any unbroken piece of ≥ 16 characters mixing letters and digits (Mistral, Together, 智谱, Fireworks, Perplexity, NVIDIA, Cerebras …). All 16 shapes are regression tests, with 11 ordinary texts that must stay untouched.
- **Secret pages**: a page named 凭据 / 密钥 / 秘钥 / 钥匙 / 口令 / credential / secret / password, or with `secret: true`, is never sent to a model, never quoted (the router shows only its path), never read by the API writer — no declaration needed.
- **Keys never come from the vault.** A CLI writer runs inside the vault with full permissions, so a key there is visible to its model whatever KRouter filters. A key pasted on the key page now moves into `~/.dsh-krouter-keys.env` (chmod 600) on the next run, the page line becomes a note, and nothing reads keys from the vault. Pasting on the page still works for hosts who never open a terminal.
- Recall cache schema `recall-v13` (full rebuild + vacuum on upgrade).

**When the night's work did not happen**
- A desktop notification (macOS, Linux `notify-send`, Windows balloon) when the seal or the nightly upkeep was skipped for lack of a model, or failed; at most once a day; `KROUTER_NOTIFY=0` off.

**Docs**: README leads with the one-line install; an alias table is no longer a prerequisite for recommending it; what leaves the machine now names secret pages and says why keys never live in the vault.

The DSH bridge tests (`extras/dsh/test-*.mjs`) no longer write the host's query log either — the last test entry point that did.

Not changed: answer cards stay on by default until the scheduled real-traffic test on 2026-10-16 (the author's decision). Tests 172/172 on both router paths.

## 0.10.2 — 2026-10-11

Fourth outside review. Both new findings reproduced, both fixed with regression tests that fail on 0.10.1.

- **A key pasted into the vault could leave the machine.** The key page tells a host to uncomment a line and paste a key. `90 系统文件/自动化/` is a rule zone, so answer cards sent that page's full text to the model, and a query like `DEEPSEEK API key 怎么填` printed the key line into the agent's context. The author's own vault had a real key on another page (`90 系统文件/Agent记忆/…凭据.md`) that answer cards had been sending since 0.9.0. Now: the key page is never a card target, never topic evidence, never an alias-proposal input; and every text KRouter prints, indexes, logs or sends passes through `krouter_redact.redact()` — values of key-like assignments (`*_API_KEY=`, `token:`, `password =`), known key shapes (`sk-…`, `ghp_…`, `AKIA…`, `AIza…`, `xox…`, `hf_…`, …) and bearer tokens become `<redacted>`; placeholders and plain numbers stay. Wired into the recall index and `how`, best lines, literal search (py and sh), the query log, answer cards and their check, topic evidence, learning prompts, alias proposals, and the API writer's file reads. `tests/test_secrets.py`: a fake key on the key page and on another page appears in no prompt, no router output (both paths), no query log, no cache file.
- **Chinese questions refused on a small vault.** 0.10.0's out-of-vault rule counted characters the vault never contains; a fresh vault lacks even `知` `道` `已` `经`, so ordinary Chinese questions were refused. Characters among the 1,500 most frequent (from jieba 0.42.1's dictionary word frequencies, MIT) no longer count; `咖` `啡` `垢` still do. Recall bench gains the 12 gold-page questions in Chinese (same sample alias table): 0.9.3 9/12 with 3 of 6 half-off-topic answered, 0.10.1 5/12, 0.10.2 9/12 with every off-topic and half-off-topic question still refused (CI: ≥ 9/12). Author vault: synthetic, held-out and all 92 real queries unchanged.
- The key page and README say where keys belong when a vault syncs to a cloud: `~/.dsh-krouter-keys.env`.
- The recall cache schema moves to `recall-v12`: a cache built by an older version (raw page text) is rebuilt in full on upgrade and vacuumed, so no key survives in it or in its free pages.

## 0.10.1 — 2026-10-11

- **`first_run.sh` no longer writes the host's query log.** The demo routes run on the bundled template, not on the host's traffic, yet each run appended its queries (`home`, `correction`, `memory` …) to `~/.local/state/krouter/queries.jsonl`, which the nightly learning reads. 0.10.0 isolated pytest; the demo script, also run by `verify_clean.sh`, slipped past. It now sets `KROUTER_NO_QUERY_LOG=1`; a test runs it and checks that no log appears. Found while rolling 0.10.0 out on the author's machine.

## 0.10.0 — 2026-10-11

Third outside review (two parts: a re-review of 0.9.3, and "would a stranger's agent recommend this"). Every finding was reproduced first; one proposed fix was measured and replaced (below).

**Behaviour that did not match the docs**

- **One CLI lane.** With no key, the nightly steps only knew `claude` / `codex`, while the writer detects grok, Codex, claude, cursor-agent, opencode, kimi, pi, vibe, antigravity. A grok-only host got five `skipped` steps and no sign of it. `llm.py` now owns the CLI candidates and their login probes; `resolve.py` imports them, so both lanes pick the same CLI. Each harness has a text-only invocation (grok: single-turn `--prompt-file`, verified).
- **Pure-shell `status` stopped before `host_action`** whenever no day was pending (a trailing `[ … ] &&` returned 1 under `set -e`). Fixed; found while testing the nightly line.

**Answer cards**

- The review proposed requiring half of a card question's words to be on the page. Measured on the 447 real cards it would drop 152 (34%, including `日更每天几点跑`), and the reviewer's adversarial card (0.125) sits inside the real cards' range (0.09–0.17): no word-overlap threshold separates them. Instead: lexical checks gain "most of the answer's words come from the page" (real cards ≥ 0.38; threshold 0.3), and a **second model pass** checks each card once — is the question about this page, does the answer answer it, is anything flipped or added. On 160 adversarial cards (half-off-topic question, swapped answer, flipped meaning, copied answer; 40 each) lexical checks catch 39, the second pass 160, with no real card lost beyond the 11 the lexical check already drops. This also closes 0.9.3's admitted gap: a reworded sentence that flips the page is now caught. Verified cards carry `v: 1`; unverified ones are re-checked the next night; `checkup.py` counts them.
- **Ablations on the 92 real queries** (same judge): removing the answer line 1.46 → 1.47; removing cards entirely 1.49 → 1.47. Both inside the ±0.05 noise. Cards do not measurably help on this traffic; the 0.8 → 0.9 gain belongs to that release's ranking changes. Docs no longer credit cards. Cards stay (cheap at query time, now checked twice).
- Secret filter: a long id made of short `-`/`_` pieces (`20260811-090406-v4-flash-…`) is no longer taken for a key; a 24+ unbroken mixed run (keys, 40-hex tokens) still is.

**Recall**

- A question with ≥ 2 Chinese characters the vault never contains, matching one content word, is out of the vault (`咖啡机的定时器多久除垢一次` matched `定时` and came back `high`). Template bench 18/24 → 21/24; author vault synthetic, held-out and all 92 real queries unchanged.
- **Public recall bench in CI** (`tests/fixtures/recall_bench.jsonl`, template): 12 gold-page, 6 off-topic, 6 half-off-topic questions. Every off-topic and half-off-topic one must be refused; gold page first ≥ 9/12.

**The host's data**

- **The alias table lives in the vault** (`90 系统文件/canonical_sources.psv`): it syncs with the vault and is in its snapshots. `map_for()` resolves `KROUTER_MAP` > the vault's table > the shipped sample everywhere (router py and sh, recall, L0, checkup); receipts print `canonical_map:`.
- **`install.sh --upgrade`** (`--force` is the same) replaces code only and keeps the alias table, ledgers and symlinks; a table edited in the old location moves into the vault once (a symlinked one gets a `HOST ACTION` instead of being rewritten behind another tool). Fresh installs seed the vault with the sample once.
- **`scripts/uninstall.sh`**: removes the timer (launchd / systemd / crontab line), Cursor rules, hook and skill; saves an alias table that is not in the vault yet; leaves the vault alone; `--dry-run`, `--purge` (cache and query log). Keys file is never deleted.
- **Timers beyond macOS.** Linux: a systemd user timer, or one marked crontab line. Windows: `extras/host-daily-evolution/run.py` (a Python twin of `run.sh`) and `scripts/install_windows_task.ps1` (`-Uninstall`). The PowerShell script has not been run on a Windows host yet.
- **Configurable zone names.** `krouter-zones.psv` at the vault root maps the default layout (`90 系统文件|System`, `Agent第二大脑.md|Home.md`, …); longest prefix wins, files too. Wired through the router, recall, cards, topics, checkup, nightly, ask, the key page and both writers. The DSH bridge still assumes the default names.
- **Alias cold start.** `propose_aliases.py` drafts lock rows from the vault — unlocked rule / topic pages, ranked by how often real traffic reached them without a lock; `--model` adds model-proposed nouns — into `90 系统文件/自动化/别名候选.md`. The host ticks rows; `--apply` re-checks and appends only those. Nothing is written unticked.

**Visibility and disclosure**

- **`nightly.py`** runs the five steps and writes each outcome — state, reason, model lane, calls, characters sent (metadata only) — to `90 系统文件/自动化/夜间维护.md` and the health page (`nightly`, `nightly_at`). `status` prints it and raises `host_action` when steps are skipped, failing, or three days old. The launchd job now logs to `~/Library/Logs/dsh-krouter-daily.log`.
- **`run.sh --dry-run`** (and `nightly.py --dry-run`): what would be sent, estimated tokens, which files would be written; no model call, no write.
- README's "tell your host" facts now say what leaves the machine: queries never; the writer sends logs and sessions; the nightly steps send rule and topic pages in full, topic excerpts, and unanswered router queries.

**Evidence and process**

- `docs/VERIFY.md` says plainly that the 92 real queries are a development set, that the held-out synthetic set is flat from 0.6.0 (88% / 75% → 88% / 71% on today's vault), the ablations, the adversarial card results, and that no fresh held-out traffic exists yet.
- The host's query log held 518 lines, 514 of them the author's own evaluation runs and pytest fixtures — they would have become learned triggers tonight, and the held-out questions among them would have stopped being held out. Removed (backup kept). `tests/conftest.py` now isolates state and cache for the whole test session; evaluation scripts set `KROUTER_NO_QUERY_LOG=1`.
- `CONTRIBUTING.md`: scoring-constant and refusal changes ship with before / after numbers on the recall bench and a held-out set; hosts should pin a tag.

Tests 133/133 on both router paths.

## 0.9.3 — 2026-10-11

Fixes from a second outside review, of 0.9.2. Each finding was reproduced before it was fixed.

- **The faithfulness check matched substrings.** `保留 3 天`, `保留 0 天` passed against a page that says `30 天`; `端口 80` and `端口 808` passed against `8080`. A specific must now appear as a whole token: no digit or letter on either side, and a number is not part of a decimal (`3` is not in `1.3`; `0.9.2` still matches `v0.9.2`). Pieces of joined words are checked the same way. In the author vault 11 of 447 cards now fail (was 7); the four new ones all quote a truncated identifier (`sv-doma` for `sv-domain-001`).
- **"Verified" overstated it.** The check covers specifics, not meaning: a plain-prose answer has nothing to check, and a reworded sentence that flips the page passes. The docs now say "specifics checked", and `checkup.py` lists cards with nothing checkable (89 of 447 in the author vault) so a human can read them.
- **An off-page card could pull an unrelated page to `high`.** On the template vault, a card asking `咖啡机除垢周期是多少` on `经验与方法.md` made that page the confident answer. A card now counts only if its question shares at least one content word with its page (question words like `多少` do not count) — checked when the card is written, when the page is indexed (the question is not a trigger otherwise), and when it is read. All 447 real cards share one; the coffee card shares none. `checkup.py` lists off-page cards.
- **Two model lanes.** The nightly `llm.py` had its own short provider table — no Gemini, Groq, Fireworks, Mistral, … — and no flagship lock, while the writer (`api_writer.py`) had both. Now there is one table and one lock, in `llm.py`; `api_writer.py` imports them (by file path, so an unrelated `llm` package cannot stand in). The nightly steps try keys in the writer's order and lock the catalog's flagship, unless `KROUTER_LEARN_MODEL` names one. The lock ranks Opus 5 above Opus 4. The Gemini key goes in a header, not the URL.
- **Cost was not disclosed.** With a key, the nightly steps now call the same paid provider every night (mostly on the first run; later runs redo only changed pages). The README's "tell your host" facts say so, and how to turn it off (`KROUTER_NIGHTLY=0`). Two stale `answer:` labels on the front page now read `answer (generated):`.

Same-run checks (author vault, installed alias table): synthetic top-1 85%, held-out gold page found 88% / first 75%, wrong locks 0 — identical to 0.9.2. On the 92 real router queries the top hit and the answer line are identical to 0.9.2 for every query (40 carry an answer), so the front-page judge number stands. Tests 119/119 on both router paths.

## 0.9.2 — 2026-10-11

Fixes from an outside review of 0.9.0. Each finding was reproduced before it was fixed.

- **A stale card kept ranking its page.** 0.9.0 said "a card whose page changed is ignored"; that was true for `answer:` only. Card questions were merged into the page's triggers without checking the hash, so an unrelated card question kept pulling the page up after the page changed. Card questions now count as triggers only while the card's hash matches the page's current content. Test: the page leaves the hits once it changes, not just the answer.
- **`answer:` had no faithfulness check.** "Only from this page" was a prompt instruction, nothing more. Now every number, path, command and latin word in an answer must appear verbatim in the page — checked when the card is written and again when it is read — and the line is labeled `answer (generated):`. Words the answer joined with `/` or `+` may be checked piece by piece; number combinations (`1:3.3`) must appear whole, since they are often computed. In the author vault 7 of 447 cards now fail and are not shown. Secret-like text is dropped before a card is written. The README no longer says the agent "usually does not need to open" the page: the page is the record.
- **Model-written card questions bypass the refusal gate.** Not new, but 447 of them amplify it. `checkup.py` now lists stale, not-verbatim, and too-broad cards (fewer than two content words).
- **One model lane.** New `llm.py`: `*_API_KEY` first (model from `KROUTER_LEARN_MODEL`, else the provider default; a provider with no known model is skipped, not guessed), then a logged-in `claude` / `codex`; `--cli` / `KROUTER_LEARN_CLI` is the host's explicit pick and goes first. `reconsolidate.py`, `consolidate_topics.py` and `answer_cards.py` use it; no hard-coded CLI path. Pages that yield no cards are remembered by hash and not re-asked every night. Generation-side tests added.
- **The bundled timer now runs the nightly upkeep.** 0.7–0.9 added five nightly scripts but only the author's own scheduler called them, so a fresh install got none of it. `extras/host-daily-evolution/run.sh` now runs them after the seal (`KROUTER_NIGHTLY=0` turns them off); each step is independent and none changes the seal's exit code. Documented in README, ARCHITECTURE, and SKILL.md, whose workflow now covers `recall:`, `answer (generated):`, `scope_widened` and `recall: none`.
- **README** drops the instructions addressed to summarizing agents ("do not call it …") and keeps the facts; `docs/VERIFY.md` speaks for itself.

Synthetic sets after the fix: top-1 85%, held-out gold page found 88% (one question fewer than 0.9.0), wrong locks 0, off-topic unchanged. Tests 117/117 on both router paths.

## 0.9.1 — 2026-10-11

Docs only. The README had grown one appended section per release, each with its own numbers from a different run. Now: the front page states what the product does today (lock, then ranked recall with precomputed answers, refusing instead of guessing; topics and answer cards built overnight) and quotes **one** same-run number — 92 real router queries, blind-judged, ≤ 0.5.1 vs 0.9.0: mean usefulness 0.62 → 1.47 of 2, direct answers 14 → 55, useless 49 → 12. The four after-the-lock features are one section. Evidence is four layers: `docs/VERIFY.md` adds layer 4 (real traffic) with the method, every per-release run, the held-out synthetic set, the judge's noise (±0.05), and what still fails. `PROTOCOL.md` and `docs/ARCHITECTURE.md` now describe the miss path the code runs, and drop "a rejected page still locks", which stopped being true in 0.7.0.

## 0.9.0 — 2026-10-11

**Answer cards (sleep-time compute).** The router used to stop at "here is the right page": the one-line `how` was just the page's first sentence (`你的层（全局结构）`), so an agent still had to open the page. Real traffic is predictable — half the calls repeat an earlier question — so `answer_cards.py` precomputes, for every rule and topic page, 3–5 `question → one-line answer` cards taken only from that page (447 cards on 104 pages in the author vault). Cards live in `90 系统文件/自动化/下意识问答.jsonl` (no source page is edited), carry the page's content hash, and are rewritten only when the page changes; a card whose page changed is ignored until then. Card questions also act as recall triggers, and the best-matching card on each hit prints as `answer:`.

One-concept queries (`DSH`, `发版`, `grok-fixed`; not bare numbers) skip the two-content-word gate, and a query that is a page's name (title, file name, or `topic_terms`) doubles that page; a named dossier now outranks same-named scattered rule pages. Speed: the per-query freshness walk no longer builds a `pathlib` object per file — recall 112 → 30 ms in-process, router p50 ~105–111 ms.

Field self-report, author vault (not in clone): 92 real router queries, blind-judged 0.8.0 vs 0.9.0: mean 1.34 → 1.43 of 2, direct hits 46 → 52, useless 15 → 12; 40 of 92 now carry an `answer:` line. Synthetic: top-1 82% → 85%, held-out right page 88% → 92%, wrong locks 0, off-topic unchanged.

## 0.8.0 — 2026-10-10

**Topic dossiers: the missing middle layer.** Retrieval was near its ceiling (synthetic: right page top-1 83%, top-10 95%); what still failed on real traffic was knowledge that lived only in daily logs (`SyGJ` in 44 logs, zero pages). `consolidate_topics.py` merges each listed topic (`90 系统文件/自动化/主题档案清单.psv`) into `02 经验与方法/主题档案/主题｜…md`: one-line summary, current state as of the latest evidence, facts with a `[[source]]` each, user corrections, timeline, open conflicts, authority pages first. Evidence is the vault only (authority pages, other pages, logs newest first, capped); frontmatter is written by the script, not the model; every wikilink must resolve or is demoted to text; a page is regenerated only when its evidence hash changes. Status stays `provisional`.

Recall treats dossiers as their own tier and only boosts one when the question names its topic (title or `topic_terms`), so a 20 KB page cannot win on stray words. Refusal got stricter where dossiers made it looser: bigrams with function characters (`的了我你他她吗呢吧啊么什`) and words that only appear in model-written triggers no longer count as content; a latin term the vault has never seen (`Kubernetes`) refuses unless more than two real words match. Single CJK characters are dropped from the query.

Field self-report, author vault (not in clone): 92 real router queries, blind-judged old vs new: mean 0.66 → 1.41 of 2, direct hits 14 → 52, useless 45 → 14; 16 topic questions written before the dossiers existed: 0.62 → 1.31. Synthetic held-out unchanged (88% / top-1 75% / wrong locks 0 / 0 of 6 off-topic answered). p50 ~115 ms.

## 0.7.0 — 2026-10-10

Memory maintenance, measured on the router's own real traffic. 92 de-duplicated queries the author's agents actually sent in 30 days, blind-judged (old vs new shuffled, Opus scores 0/1/2): mean 0.74 → 1.26, direct hits 20 → 42, useless 44 → 18. Synthetic held-out set: right page 88% → 92%, top-1 75%, wrong locks 0, 0/6 off-topic answered; p50 ~113 ms.

- **Lock**: the whitespace token fallback only counts whole-alias hits, so `纠错` no longer locks `纠错优先级` for `Claude Code 纠错`. A source page whose `status` is superseded / retired / rejected / deprecated / archived is out of force: no lock, no L0 row.
- **Recall**: a one-keyword query (`DSH`, `SyGJ`) answers when its one content term matches; bare numbers are not content terms. Trigger text now feeds the word-likeness statistics, and a bigram that appears in any title or trigger counts as a real word when deciding whether to refuse (`别名` in `别名表谁能改`).
- **Scope widening**: `preference` / `correction` / `memory` / `project` widen to the whole vault (rule pages first) when their own scope has no page that covers the question, and print `scope_widened: vault`.
- **Query log**: one JSONL line per routed query under `~/.local/state/krouter/` (`KROUTER_NO_QUERY_LOG=1` turns it off). Half of real calls repeat an earlier question.
- **`reconsolidate.py`** (nightly, one model call): weak queries + their recall candidates → the model picks the page that answers, or none → `rel|original query` appended to `90 系统文件/**/下意识触发词-自学习.psv`. Recall-only, never a lock, no invented paraphrase. Replay on history: 8 learned, 20 none, 12/12 off-topic probes refused.
- **`checkup.py`** (nightly, no model): writes `90 系统文件/自动化/下意识体检.md` — locks and triggers pointing at missing / dead pages, `supersedes` pairs where recall still ranks the replaced page first, rule pages nobody read or recalled in 60 days. Lists only; never edits sources.

## 0.6.0 — 2026-10-10

A lock miss is now answered by **L1 recall** instead of a whole-sentence literal grep. `skill/krouter-obsidian/scripts/recall_index.py` keeps a rebuildable SQLite FTS5 cache under `~/.cache/krouter/` (stdlib only, no service, no vectors): CJK bigrams + latin words, title and triggers weighted, rule pages first, `superseded` pages sink, cross-word junk bigrams filtered. Each hit prints its `how` line and the best matching line; weak overlap prints `recall: none` and must not guess. Triggers come from the alias table plus any `90 系统文件/**/下意识触发词.psv` (`rel|phrase;phrase`) and never lock.

The lock got stricter: a short alias inside a longer question (`日更` in `日更能不能交给云端跑`) only ranks suggestions. `route_knowledge.sh` now execs the Python twin (one process instead of four); `KROUTER_SH_ONLY=1` keeps the shell path. Ships the L0 compiler `compile_subconscious.py` and the `status` seal lines (`daily_seal*`) from the health page.

Field self-report, author vault (not in clone): 30 held-out questions written before tuning, right page 21% → 88%, top-1 0% → 75%, wrong locks 0, 0/6 off-topic answered, p50 118 ms. Clone tests: `tests/test_recall_index.py`.

## 0.5.1 — 2026-09-05

Windows can run the same lock through `skill/krouter-obsidian/scripts/route_knowledge.py`; DSH on win32 prefers that file. Same-score miss across two pages prints `host_prompt` and must not guess. `sha256` falls back to Python when `shasum` is missing. One protocol, two launchers. Does not ship L0 / `下意识.md`.

## 0.5.0 — 2026-08-31

Ask-as-product matcher in `skill/krouter-obsidian/scripts/ask_product.py`. At most one provisional page per utterance. `record` never writes `active`; `promote` does, after adopt + this task accepted. Triggers live on the page (`triggers:`) or `90 系统文件/自动化/ask-triggers.json`. `install.sh` copies `extras/cursor/ask-product.mdc`. This clone does not ship an author’s trigger table. Codex / Claude still paste the snippet.

## 0.4.3 — 2026-08-28

Lock-vs-neighbor Claim C: multilingual MiniLM; CJK inversion gone; `H15` 发版 already ranks the seal page before any floor (precision, not a threshold miss). Claim D: BGE-M3 middleweight dense; hit 16/16; at 0.40 the leftover is neighbor `B03` (生产事故 → timer), not one of the 12 OOD negatives. Do not merge C and D into “neither matched the lock.” On this contract (refuse + no neighbor cite), featherweight beats that middleweight stack — the “better than mainstream embedding RAG” line. Heavyweight hybrid + rerank is out of scope. Pytest replays frozen JSON (no extra pip in CI). Hub snapshots are not in the clone. Ship `scripts/verify_clean.sh` so the upload gate named in CONTRIBUTING exists in the clone.

## 0.4.2 — 2026-08-27

Ship `in_force` / `live_rows` / `parse_frontmatter` on `canonical_lookup.py`. `verify_canonical_map.py` and the lock-vs-neighbor runner imported them since 0.4.1; the lookup module on GitHub did not. Clone `python3 scripts/verify_canonical_map.py` raised `ImportError`. Not L0.

## 0.4.1 — 2026-08-27

Docs and checkers. No new product lane.

- Evidence is three layers in `docs/VERIFY.md` and the README: implementation (`clone_25`), comparison (`lock_vs_neighbor`), field self-report (author vault, not in clone). `clone_25` 25/25 is not the LLM 25/25.
- Sealed-day gap checker: `scripts/verify_sealed_days.py`. Same trust model as `verify_canonical_map.py` — measures this vault’s `05 时间日志/`, does not replay the author’s 72 consecutive seals. Empty files and `待总结` / `to-summarize` are gaps; a real note on the same day beats a stub.

Already on `main` since 0.4.0, first tagged here: public lock-vs-neighbor fixture (N=36), `clone_25` analogue, host-facing listing, both rungs of the ladder, receipt SVGs, latin-fragment alias rule, API-key-first / CLI subscription writer.

## 0.4.0 — 2026-08-21

- Memory-system tools on the DSH mount: `preference`, `correction`, `memory`, `project` in addition to `status` / `search` / `suggest`.
- Claude Code mount: `extras/claude-code/CLAUDE.snippet.md`.
- Self-evolution extra is now files plus `check.sh`. Template lamp defaults to `unused`. `first_run.sh` proves the extra without starting a timer.
- README maps each listing word to a path in this repo.

## 0.3.1 — 2026-08-21

- Public listing: **DSH-KRouter**. Keyword subtitle: DeepSeek Harness memory system, Agent second brain, Obsidian knowledge base, optional self-evolution, Cursor / Codex / Claude Code.
- Daily evolution extra documents the host scheduler contract. `dsh plugin add` still does not create a cron.

## 0.3.0 — 2026-08-21

- DSH mount: `extras/dsh` registers read-only `krouter_status`, `krouter_search`, `krouter_suggest`.
- Bridge tests on the template vault. No write routes. Uninstall does not delete the vault.
- Same `OBSIDIAN_VAULT` and alias map as Cursor and Codex.

## 0.2.0 — 2026-08-21

- CI: pytest + `first_run.sh` on every push to `main`.
- `suggest` route: prefix/overlap alias hints on a miss. Hints are not hits.
- Miss receipts include `suggestions:` so an agent can retry one noun.
- Public unit tests for exact match, same-file ties, and ambiguous miss.

## 0.1.0 — 2026-08-21

- First public template: five zones, short-noun router, install, architecture docs.
