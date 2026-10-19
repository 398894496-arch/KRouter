# Held-out set: rules and log

`heldout.jsonl` holds 25 questions on the same 30-page vault as the development questions (`questions.jsonl`):
9 `correction`, 6 `current`, 10 `refuse` (neighbour questions). Same schema, ids prefixed `H-`.

The development questions are what KRouter is tuned on. These are not. Their only job is to say how KRouter does on
questions nobody shaped it for, so the number is worth something only as long as nobody tunes toward it.

## Where the questions come from

**Who the "outside reviewer" is.** Every held-out set here, and the outside reviews in `CHANGELOG.md`, come from
Claude Opus in claude.ai chat sessions that the maintainer starts and relays: not a human, and not the Claude Code
sessions that change KRouter, but the same model family. "Outside" means a separate session that did not write the
code it reviews; it does not mean independent of Anthropic's models, so question wording may share that family's
habits. A set written by a person is planned and will be logged here before it is run.

- Written on 2026-10-11 (Pacific) by Claude, an AI reviewer working for the maintainer in an outside review session,
  against the bench vault as of KRouter 1.0.0 (`c555de1`).
- Before writing them the reviewer had read the vault pages and the 30 development questions (to avoid duplicates).
  KRouter had not been run on any of them.
- Not edited after the first run. `H-R6` ("How should release tags be named?") is arguably borderline: the release
  page says to ship "from a tag on main" but says nothing about naming. It is kept as written, because editing a
  question after seeing results is exactly what this file forbids.

## Rules

1. **Frozen.** Questions, golds, kinds and the bench vault do not change. `tests/test_memory_honesty_heldout.py` pins
   a SHA-256 of `heldout.jsonl` and of the vault. A question found to be wrong is not fixed: the set is retired and
   a new one is added (rule 5).
2. **Not a tuning target.** A change to ranking, refusal or card checks justifies itself on the development benches
   (`questions.jsonl`, `tests/fixtures/recall_bench*.jsonl`), as `CONTRIBUTING.md` says. A PR may report the
   held-out aggregates; it may not use them as the reason for the change. CI has no floor on the held-out score, only
   a sanity guard far from any target: fewer wrong citations, and at least as many refusals, as plain full-text
   search that always answers.
3. **Aggregates only.** `python3 bench/memory_honesty/run.py --set heldout` prints totals, not which question was
   missed. `--reveal` prints the misses; use it only to audit a release, never while developing, and add a line to
   the log below when you do.
4. **Burned.** The set is burned if a ranking, refusal or vault change lands after a reveal by the same person, or if
   a change is shaped by known held-out misses. Then: add a line to the log, stop calling its numbers held-out, and
   rule 5 applies.
5. **Replacing it.** A new set (`heldout-2.jsonl`, same format, new pins) is written by someone who has not seen the
   ranker changes since the last set, before KRouter is run on it.
6. **Reporting.** Release notes and the README quote the held-out aggregates next to the development-set number,
   never the development number alone.

These rules make tuning toward the set visible; they cannot make it impossible. The pins and this log are the
guarantee: any edit to the questions, the vault or the pins shows up in a diff that a reviewer can ask about.

## Baseline at freeze

Frozen on 2026-10-12 at KRouter 1.0.1 (`8c2e0cb`). 1.0.0 scored the same.

| System | Wrong-citation rate | Refused | Correction hit | Current hit |
|---|---|---|---|---|
| Plain full-text search (SQLite FTS5 BM25), always answers | 61% (14 / 23) | 1 / 10 | 4 / 9 | 5 / 6 |
| KRouter 1.0.1 | 25% (3 / 12) | 8 / 10 | 5 / 9 | 4 / 6 |

## Log

What has been seen, by whom. Append; never rewrite.

| Date | Event |
|---|---|
| 2026-10-11 | Written by the reviewer; first run on KRouter 1.0.0. The reviewer saw the per-question results. |
| 2026-10-12 | **Partial exposure.** The three wrong citations were described publicly in `docs/BENCHMARK.md` and the 1.0.1 changelog: `H-A4` (branch-name format → the date-format page), `H-R6` (release-tag naming → the release page), `H-R7` (checkout load budget → the performance-budget page). Which answerable questions were refused was not published. Treat a change aimed at shared words like "format", at release-tag naming or at page-load budgets as aimed at this set. |
| 2026-10-12 | Added to the repository and frozen at 1.0.1 (`8c2e0cb`). Baseline above. |
| 2026-10-12 | Applied to the repository by the maintainer's Claude Code session (the one that changes the ranker). It checked the file's format, counts and that it holds no secrets, and ran aggregates only (25%, 8 / 10, 5 / 9, 4 / 6, matching the baseline). It did not read the questions or run `--reveal`. |
| 2026-10-12 | Maintainer's Claude Code session ran held-out **aggregates** for basic-memory 0.22.1 and claude-mem 13.35.0 through their adapters (`adapters/`), for docs/BENCHMARK.md. No `--reveal`; their per-question held-out output is kept out of the repository. |
| 2026-10-12 | Outside reviewer ran held-out **aggregates** for a baseline (BM25 + skip superseded + score floor) at several floors, reporting only the dev-picked one. Baseline only, no KRouter change. |
| 2026-10-12 | Maintainer's session ran held-out **aggregates** for the matched baselines (BM25 and basic-memory, skip superseded + dev-picked floor) and a coverage sweep of those two baselines to find their point at KRouter's coverage. Baselines only; no `--reveal`; no KRouter change. |
| 2026-10-12 | **Used for one go / no-go decision.** Maintainer's session tried a set of recall changes on branch `recall/paraphrase` (English stemming, following `superseded_by` to the newer page, a relaxed unknown-word refusal, a missing-topic refusal, English answer cards), tuned on `questions.jsonl` and a new maintainer-written `questions_dev2.jsonl`. One held-out run, aggregates only: worse than 1.0.3 (38% wrong citations without cards, 31% with, vs 25%; neighbours refused 5 / 10 vs 8 / 10). Not shipped. No `--reveal`. A further change chosen by held-out aggregates would be tuning on this set; the next claim of a ranking gain needs `heldout-2.jsonl` from someone who has not seen these changes. |

## Held-out set 2 (`heldout2.jsonl.gz`)

50 questions on a second vault, `vault2/` (60 pages: 30 English under `Engineering/`, 30 Chinese under `工程规范/`;
20 decisions that were replaced, each with its old page, and 20 that were not). A development set of 50 on the same
vault comes with it, `questions_dev3.jsonl`, to tune on. All rules above apply to set 2 unchanged.

**Why a second vault.** By 2026-10-12 the first vault carried 105 questions on 30 pages, its wording had been studied
closely, and a round of changes that improved both dev sets made held-out worse (log above). Questions on a vault
nobody has tuned against are the cleaner test, and half of it is Chinese, which most KRouter users write in.

**Where the questions come from.**
- Written on 2026-10-12 (Pacific) by the same outside reviewer as set 1, together with the vault and `questions_dev3.jsonl`,
  for the maintainer's request that an independent writer produce the neighbour questions.
- 100 questions in six strata (English / Chinese × correction / current / neighbour), split 50 / 50 between dev3 and
  heldout2 with a fixed seed (20261012), stratified, so the two sets are the same kind of question: each has 15
  corrections, 15 current, 20 neighbours, 25 English and 25 Chinese.
- Every answerable question carries the sentence from its gold page that answers it (`evidence`); every neighbour
  question names the page it borrows from (`neighbor`) and a term that appears on no page of the vault (`absent`),
  so a neighbour question cannot be answered by accident. Both are checked by `tests/test_memory_honesty_v2.py`.
- Checked by script before KRouter was run on any of them; one held-out question repeated a maintainer dev2 question
  word for word and was replaced before the first run. Not edited after the first run.
- What the reviewer knew when writing: the vault-1 questions (all three sets), and the one-paragraph description of
  the not-shipped recall changes in `docs/BENCHMARK.md` ("Tried and not shipped"). Not their code, and not their
  per-question effects.
- **Exposure.** The questions were written in the reviewer's session, which the maintainer can read. The file is
  gzipped so that the maintainer's Claude Code session does not meet a question in a grep or a diff; it should apply
  the patch without decompressing the file.

**Baseline at freeze** (KRouter at `main` `f9d0be9`, i.e. 1.0.3 plus docs; first run of any system on these questions).
On vault2 the BM25 baselines split Chinese into character pairs; `bm25-floor` picks its floor on dev3.

| System | heldout2: wrong citations | neighbours refused | answerable right | dev3: wrong citations | refused | answerable right |
|---|---|---|---|---|---|---|
| Plain BM25, always answers | 61% (30 / 49) | 1 / 20 | 19 / 30 | 55% (27 / 49) | 1 / 20 | 22 / 30 |
| BM25 + skip superseded + dev3-picked floor | 23% (5 / 22) | 15 / 20 | 17 / 30 | 4% (1 / 22) | 19 / 20 | 21 / 30 |
| KRouter 1.0.3 | 33% (12 / 36) | 9 / 20 | 24 / 30 | 24% (8 / 34) | 13 / 20 | 26 / 30 |

### Log, set 2

| Date | Event |
|---|---|
| 2026-10-12 | Vault, dev3 and heldout2 written by the reviewer; integrity checked by script; one duplicate of a dev2 question replaced; frozen; first run, **aggregates only** for KRouter, BM25 and BM25-floor (table above). The reviewer has not looked at per-question held-out results. |
| 2026-10-12 | Applied by the maintainer's Claude Code session (the one that changes the ranker). The file was decompressed only by code: a count of rows and a scan for key-shaped text, nothing printed; the session did not read the questions. Aggregates only, matching the baseline (KRouter 33%, 9 / 20, 24 / 30). |
| 2026-10-12 | Maintainer's session: dense-retrieval prototype (`dense.py`, local multilingual MiniLM via fastembed) tuned on dev3 only. Candidate pre-registered on dev3 before the run: `agree` (BM25 over character pairs and dense must agree on the top page, both skipping superseded pages, floors picked on dev3). One heldout2 run, aggregates only: `agree` 18% wrong citations (5 / 28), 15 / 20 refused, 23 / 30 right. Also reported, not used to choose: `dense` 23% (7 / 30), 13 / 20, 23; `vote` 27% (10 / 37), 10 / 20, 27; KRouter 1.0.3 33% (12 / 36), 9 / 20, 24; bm25-floor 19% (4 / 21), 16 / 20, 17 (the freeze table says 5 / 22, 15 / 20; the one-question difference is under investigation). No `--reveal`. |

## Held-out set 3 (`heldout3.jsonl.gz`)

200 questions on a third vault, `vault3/`, and **no development set on that vault**: nobody tunes on vault3, so it
measures what a vault KRouter has never seen gets, which is every new user's vault. All rules above apply.

**The vault.** 110 pages: 30 English rule pages under `Handbook/` and 30 Chinese under `团队手册/` (15 of each were
replaced, and their 30 old pages say `status: superseded`), plus 20 daily logs (`Daily log/`, `工作日志/`) that
mention old decisions and open discussions in passing. The logs are distractors: they are never a gold page, and
citing one first counts as a wrong citation. Real vaults are full of such pages; vault1 and vault2 had none. The logs
sit in plain folders, not in KRouter's `05 时间日志/`, so no system gets a head start from the layout.

**The questions.** 100 English and 100 Chinese: 60 corrections, 60 current, 80 neighbours (40%). Two answerable
questions per rule page, on different facts or in different words. Same checks as set 2, run by script before any
system was run: every answerable question's `evidence` sentence is on its gold page; every neighbour question's
`absent` term is in the question and on no page of vault3, logs included, English plurals counted. Before the first
run the checker was tightened (plurals) and two Chinese neighbour questions had their `absent` term set to the
question's own wording; no question text changed. Written on 2026-10-13 (Pacific) by the same outside reviewer, who
had not read the code of `feature/dense` or the logistic-regression work, and knew of them only from the maintainer's
summary (method names and dev3 / real-vault aggregates). Stored gzipped, as set 2.

**What it is for.** Enough questions to tell systems apart: with 50 questions the 95% intervals of a wrong-citation
rate are about ±15 points wide, here about ±7. `run.py` gives bootstrap intervals (`--ci`), paired intervals against
another system (`--vs`), a comparison at the same coverage (`--vs-matched`), and the coverage curve (`--curve`).
All four are aggregates and may be run on this set.

**Baseline at freeze** (main `792c74e`, KRouter 1.0.3; `bm25-floor` uses the floor picked on dev3, since vault3 has no
dev set). 95% bootstrap intervals in brackets.

| System | wrong citations | neighbours refused (of 80) | answerable right (of 120) |
|---|---|---|---|
| Plain BM25, always answers | 58% (116 / 199) [52, 65] | 1 [0, 3] | 83 [69, 96] |
| BM25 + skip superseded + floor from dev3 | 21% (18 / 85) [13, 30] | 64 [52, 78] | 67 [54, 80] |
| KRouter 1.0.3 | 27% (37 / 139) [19, 34] | 46 [35, 58] | 102 [88, 116] |
| BM25 + skip superseded, **same coverage as KRouter** (top 139) | 31% (43 / 139) | 44 | 96 |

KRouter 1.0.3 minus BM25 at the same coverage, paired 95% intervals: wrong-citation rate [-10.2, +1.4] points,
answerable right [-2, +14], neighbours refused [-7, +11]. Better on every point estimate, and not yet significant on
any. Along the whole coverage curve KRouter cites fewer wrong pages than BM25 at each coverage measured (for
example 19 vs 23 wrong at about 100 answered); its default threshold sits at the permissive end of its curve.

**Pre-registered decision rule** (written before any candidate is run on this set; amend only before a run, and log it).
A candidate is run on heldout3 once, at the default it would ship with.
1. **"Surpasses BM25"** may be claimed only if `run.py --set heldout3 --vs-matched bm25-floor` gives a paired 95%
   interval for the wrong-citation-rate difference entirely below zero, and an interval for the answerable-right
   difference that is not entirely below zero.
2. **Ships as the new default** only if, on heldout3, its wrong-citation rate is at most 27%, it refuses at least 46 of
   80 neighbours and gets at least 97 of 120 answerable questions right (1.0.3 minus 5), **and** the time-split blind
   judge on real traffic does not fall more than 0.05 below 1.0.3. Rule 2 does not need rule 1.
3. At most two candidates per release cycle are run on heldout3; each run is a line in the log below.

### Log, set 3

| Date | Event |
|---|---|
| 2026-10-13 | Vault3 and heldout3 written by the reviewer; checked by script; frozen; first run, **aggregates only** (KRouter 1.0.3, BM25, BM25-floor, with intervals, the matched comparison and both coverage curves; table above). No `--reveal`. Not a candidate run. |
| 2026-10-13 | Applied by the maintainer's Claude Code session. heldout3 was decompressed only by code (row count, key-shaped-text scan, nothing printed); the questions were not read. Not a candidate run. |
| 2026-10-14 | **Other memory systems on heldout3, registered before the run** (not candidates; the two-candidate limit does not apply). basic-memory 0.23.2 (latest on PyPI), in the container (`adapters/Dockerfile`), its default search, top 3 (in 0.23 that is hybrid: full text plus semantic search with fastembed `BAAI/bge-small-en-v1.5`, min similarity 0.55, reranker off; the container runs offline, so the model is downloaded on the host and mounted; added before any heldout3 output was scored); a question counts as refused only when the search returns nothing. Scored twice: at its default, and with the two rules from `floor.py` (superseded pages skipped, floor picked on dev3 on vault2, applied unchanged). Aggregates only, `--ci`; no `--reveal`, and the adapter's per-question output is not read. mem0 and Zep / Graphiti are not run: both need a hosted model for extraction and none was configured for this run. claude-mem pending. |
| 2026-10-14 | **basic-memory 0.23.2 on heldout3** (as registered above; one run, aggregates only, no `--reveal`; a mechanical check found every cited path is a vault3 file). Default: 77.5% wrong citations (155 / 200) [71.5, 83.5], 0 / 80 neighbours refused, 45 / 120 right (16 corrections, 29 current). With the two rules (floor 1.225 picked on dev3): 18.5% (5 / 27) [4.2, 33.3], 76 / 80 refused, 22 / 120 right. KRouter 1.0.3 minus basic-memory default, paired: wrong rate [−58.5, −43.4] points, right [+43, +72], refused [+35, +58]. On dev (vault1) 0.23.2 scored 18 / 29 wrong against 0.22.1's 11 / 28. |
| 2026-10-14 | **claude-mem on heldout3, registered before the run** (not a candidate). The latest claude-mem from its marketplace, at its defaults (observer `claude-haiku-4-5`), in an isolated HOME with `CLAUDE_MEM_CLAUDE_CONFIG_DIR` set so it cannot reach the host's keychain login (C50). It learns vault3 as in the first bench: Claude Code sessions (model haiku) in a copy of vault3 read every page, one Read per page, one session per top folder, with a neutral prompt (read and list each page's rule or entry); then each question goes to its `/api/search`, top 3, mapped to pages through `files_read`. A question counts as refused only when nothing maps to a page. Default only (it gives no score, so no floor). Aggregates only, `--ci`; no `--reveal`, and the adapter's per-question output is not read. |
| 2026-10-14 | **claude-mem 13.39.0 on heldout3** (as registered above; one run, aggregates only, no `--reveal`). Four haiku sessions read all 110 pages (45 + 45 + 10 + 10 Read calls, no errors); its observer, signed in through the environment token only (the keychain lookup went to the isolated service name and found nothing), stored 85 observations covering 85 of the 110 pages and skipped 18 reads as noise; queue drained before any question. Every cited path is a vault3 file. Default: 64.0% wrong citations (128 / 200) [57.5, 71.0], 0 / 80 neighbours refused, 72 / 120 right (34 corrections, 38 current). KRouter 1.0.3 minus claude-mem, paired: wrong rate [−45.0, −29.9] points, right [+17, +44], refused [+35, +58]. The isolated directory was deleted afterwards. |
| 2026-10-18 | **Candidate 1 of this release cycle** (`fix/named-absent`: refuse when the question names, mid-sentence and capitalised, something no page mentions; tuned on LongMemEval S `_abs` and dev3, never on heldout3). One run, aggregates only, no `--reveal`: wrong citations 36 of 138 answered (26.1%, 95% [19.0, 33.1]), neighbours refused 47 of 80, answerable right 102 of 120 (50 + 52). Shipped 1.0.3 default on the same day: 37 of 139 (26.6%), 46, 102. Against bm25-floor at matched coverage: wrong rate difference [-10.2, +1.3] points, right [-2, +14]: still level, not ahead. Rule 2's heldout3 conditions are met; its real-traffic blind-judge condition cannot be checked yet (the 50 fresh queries are not in), so the candidate waits. |

## Held-out set 5: real questions from the maintainer's own agents (registered 2026-10-16, before any run)

**Where the questions come from.** Everything the maintainer typed to seven agents between 2026-06-09 and 2026-10-16,
read from each agent's local store by `bench/real_questions/extract_asks.py`: Claude Code (session files and the
prompt history), Codex (current and restored archives), Cursor agent transcripts, DeepSeek Harness (personal and
company), Grok and Hermes. Human messages only (no injected context, tool output, subagents, headless or automation
runs), redacted, de-duplicated: 11 853. A rule prefilter kept 5 369 question-like ones. Grok 4.7 (high reasoning,
through the maintainer's CLIProxyAPI) labelled each: 393 ask about something the maintainer or their agents had
decided, set up or done (`classify_asks.py`). One more Grok 4.7 call over all 393 marked 332 as understandable without
their conversation and grouped them by intent into 208 things (`group_asks.py`). The frozen set is the earliest ask of
each group: **208 questions**, all Chinese (74 from June, 15 July, 63 August, 44 September, 12 October), SHA-256
`ed2efd001e9a32d6a522fbb0d9a8cf39e769917f3e67b8651de981f22152c61f`. Groups asked on two or more days give **38 pairs**
(earliest and latest ask) for the learning bench, SHA-256 `e2a8cb06c727d7a7161ab2460a58a79ac113b823d70bb44b8a20e121bdb0b84f`.
The questions are the maintainer's private messages: they stay on the machine and are never committed; only
aggregates are published. They were never used to tune KRouter (the 92 router queries of VERIFY.md layer 4 are a
different source). One known overlap: the alias table's 26 seed rows (2026-08-21) were written from 25 of the
maintainer's earlier questions, so some questions may hit an alias; hit modes are reported separately (below).

**Snapshot.** The maintainer's vault at its own git commit `57b6019` (2026-10-15), exported with `git archive`
(uncommitted edits are not used). 531 pages.

**Systems.** (a) KRouter on main `bf476ae` as an agent calls it: `route_knowledge.py search <question>` (alias lock,
then ranked recall), cited pages read off the receipt (`run_real.py`). (b) BM25 over character pairs and words,
superseded pages skipped, refusal floor picked on dev3. (c) Dense candidate 1 (`feature/dense` at `4412acd`, local
embeddings on, balanced tier). The SessionStart fix in #52 does not touch retrieval.

**Two configurations.** *As used*: the snapshot unchanged. *Without learning*: the snapshot minus
`90 系统文件/自动化/下意识触发词-自学习.psv` (6 learned lines); the alias table is kept, because all of its 167 aliases are
the 2026-08-21 seed (checked against the alias ledger: none added since). **The pass lines below use only *without
learning*.**

**Hit mode,** recorded per question and system: `canonical_match` (the alias lock), `learned trigger` (KRouter's
cited pages differ between the two configurations), `recall`, or `none` (refused). Reported separately.

**Valid citations.** A cited page counts only if it existed before the question was asked and does not come from the
question's own session or a later one. Evidence that a page existed: it is in the newest vault backup taken before the
ask (backups exist for 2026-08-18, 08-19 and 08-22), or its own date (frontmatter `created` / `date`, or a dated file
name) is earlier than the ask's day. Session excerpts and time logs dated on the ask's day or later never count. A
page with no such evidence counts as not having existed (score 0): 288 of the 531 pages carry no date, which weighs
most on asks before 2026-08-18; scores are also reported by month.

**Judging.** Grok 4.7, high reasoning (not a Claude model: KRouter was built and tuned with Claude). Per question the
judge sees the question, its date, and each system's output rendered the same way (each valid cited page's path,
date, status and first 400 characters; or "refused"). First it decides, from a candidate pool (all systems' cited
pages plus each system's top 5 without its refusal gate, each with date and status), whether the snapshot holds a
page that answered the question before it was asked. If it does, a refusal scores 0. If it does not, a refusal scores
2 and any citation 0. Otherwise each output scores 0 (useless), 1 (relevant, the agent still has to dig) or 2 (answers
it). Pairs are judged twice, the second time with X and Y swapped; a question's score is the mean.

**Agreement.** The maintainer labels 40 to 50 of the questions (a random sample, seed 20261016) without seeing the
systems' names; the report gives Grok's agreement with them (same score, and within one point).

**Pass lines** (*without learning*). "KRouter answers real questions better than BM25 with the two rules" may be said
only if the paired bootstrap 95% interval (10 000 resamples, seed 0) of KRouter minus BM25's mean score is entirely
above zero. For the dense candidate, this counts as the second piece of evidence for shipping it as an opt-in (with the
real-traffic blind judge registered above) if its mean is at most 0.05 below KRouter's.

**What any claim says.** One person's questions, on one vault, over four months and seven agents; that person is the
maintainer.

**Not in this run.** The cross-system injection comparison (step 3) waits until #52's two regressions are fixed and
reviewed.

### Log, set 5

| Date | Event |
|---|---|
| 2026-10-16 | Registered (commit on `bench/real-questions`, before any run). |
| 2026-10-16 | **Run, as registered.** Snapshot `57b6019`. KRouter (main `bf476ae`) answered 173 of 208 and refused 35; *as used* and *without learning* gave identical results (the 6 learned triggers changed no answer; no question hit the alias lock). BM25 + two rules answered 186, refused 22. Dense candidate 1 (`4412acd`, 1 216 page vectors) answered 81, refused 127. Valid-citation rule: of KRouter's 173 answers, 82 cite at least one page that provably existed before the ask (June 1 of 59, July 0 of 13, August 41 of 53, September 30 of 38, October 10 of 10); BM25 99 of 186. |
| 2026-10-16 | **Judged** (Grok 4.7 high, 26 batches × 2 passes per pair, X/Y swapped, no failed batch). KRouter minus BM25 + two rules: 0.363 vs 0.252, paired 95% interval [−0.019, +0.243]: **the "better on real questions" line is not met.** Dense candidate minus KRouter: 1.231 vs 0.370, [+0.726, +0.995]: **its registered line (at most 0.05 below KRouter) is met**. How to read both: the judge found a pre-ask answer page for only about 5% of the questions (11 of 208 in pair 1, 10 in pair 2), so scores are dominated by the refusal rule (refusing scores 2 when nothing answered the question yet); the dense candidate refuses most. On the 8 questions where both passes found an existing answer: KRouter 0.75, BM25 1.12; dense 1.0, KRouter 1.0 (too few to tell apart). The main finding is not about ranking: when the maintainer asked about past decisions, the vault mostly did not hold the answer yet. Maintainer agreement sample (45, seed 20261016): pending. |
| 2026-10-16 | **Re-read after an outside review (no new judge calls).** A system that refuses everything would score 1.909 on all 208 (1.838 on the 117 asked from 2026-08-19, when vault backups start): higher than every system. Under this scoring the judged results are not evidence of retrieval quality, and the dense candidate's met line is **not** shipping evidence. On the 117 questions from 2026-08-19 the judge found a pre-ask answer for 7–8%; KRouter 0.338, BM25 + two rules 0.329, KRouter minus BM25 [−0.179, +0.197]. Why the share is low cannot be told apart from why it cannot be shown: pages without a date that were created between the 2026-08-22 backup and the start of the vault's git history (2026-10-10) count as not having existed, and the vault's git history cannot date older pages (every page's first commit is the 2026-10-10 baseline). No complete vault copy older than 2026-08-18 exists (cold storage holds only governance extracts). The earlier reading "decisions were not written down in time" is **withdrawn**: session import shipped on 2026-10-12 (0.13.0), and only 4 frozen questions were asked after that, too few to test timeliness. |
| 2026-10-16 | **Agreement sample: not labelled by the maintainer.** At the maintainer's request the 45 sampled questions (seed 20261016) were judged a second time by Claude Opus (the `claude` CLI, no tools, the same prompt, X/Y swapped) in place of the registered human labels, so this is a cross-model check, **not** the registered human check, which stays undone. Grok and Claude agree on "a pre-ask answer existed" for 41 of 45 (Grok yes on 4, Claude on 2), and on scores for 84 of 90 question × system pairs (87 of 90 within one point). Both judges saw the same candidate pool, already narrowed by the valid-citation rule, so the agreement says the judging is stable, not that undated pages did not exist. |

## Set 6: does KRouter write down what was decided? (offline replay, registered 2026-10-16, before any run)

**Sessions.** 10 of the maintainer's recorded sessions, drawn at seed 20261016 from those with 8 to 60 turns, at least
70% of turns answered, and not KRouter's own development sessions: 4 Claude Code, 3 Cursor, 3 Codex (first days
2026-07-31 to 10-13). Cut by day as the importer pages them: 22 session-days, about 136 000 characters of excerpt
(the maintainer's questions and each turn's closing answer, redacted). Private; aggregates only.

**System.** KRouter's own import and distill (`import_sessions.render` then `import_sessions.distill`, main `bf476ae`),
on the maintainer's nightly lane (the `claude` CLI); up to 8 lines per session-day, as shipped.

**Reference.** Grok 4.7 (high reasoning) lists, from the same excerpt, what was decided and what changed. The
maintainer marks each listed item right or wrong and adds what was missed; the confirmed list is the reference. A
different model family proposes the reference than the one that distills.

**Scoring.** Grok 4.7 pairs reference items with distilled lines (same decision, same direction; for a change, both
before and after right; one-to-one). Reported: missed rate = 1 − matched / reference items; wrong rate = 1 − matched /
distilled lines; and of the reference's changes ("A → B"), how many were captured. No pass line: this measures where
KRouter stands, with the bias named (the same model family proposes the reference and pairs the lines; the
maintainer's corrections are the check on that).

`bench/real_questions/capture_bench.py` (pick, distill, propose, sheet, score).

**Amendment, 2026-10-16, before the reference was checked or anything scored.** The maintainer could not recall most
of the sessions and asked for the check to be done by a model. The reference is therefore verified by GPT-5.5 (high
reasoning, through the maintainer's CLIProxyAPI): for each session-day it reads the same excerpt, keeps or rejects
each Grok item (kept only if the excerpt shows the maintainer stating or accepting it), and adds what was missed. GPT
also does the pairing in place of Grok. A third model family on purpose: Claude distilled, Grok proposed, GPT checks
and pairs. Any claim says the reference was model-verified, not confirmed by the maintainer. Items the maintainer does
mark on the sheet are compared with GPT's verdicts and reported as a spot check.

### Log, set 6

| Date | Event |
|---|---|
| 2026-10-16 | Registered; amended (model-verified reference) before checking or scoring. |
| 2026-10-16 | **Run.** KRouter distilled 143 lines over 22 session-days (`claude` CLI). Grok proposed 94 items; GPT-5.5 kept 91 and added 32: a reference of 123. GPT-5.5 paired 60. **Missed rate 51%, wrong rate 58%; of 19 changes of mind, 12 captured.** Why: 5 session-days hold more than 8 reference decisions (27, 26, 19, 9, 9), so the 8-line cap alone forces at least 50 of the 63 misses; and KRouter fills its 8 lines whether or not much was decided (27 lines on the 4 session-days where the reference holds nothing; 7 or 8 lines where it holds 1 to 3). The maintainer did not confirm the reference (amendment above). These 22 session-days are a measurement set: changes to the distill step are tuned on other sessions and re-measured here. |
| 2026-10-16 | **Why lines did not match** (GPT-5.5, each of the 143 lines against the excerpt and the reference; 7 lines of one session-day unparsed): 62 match the reference (granularity differences included), 40 are decisions the agent proposed without an explicit yes, 30 are steps or discussion rather than decisions, 3 are real decisions the reference missed, 1 has no basis in the excerpt. **The maintainer's own check:** shown the source turns of 30 sampled items, the maintainer said most of them were things they had agreed to, and declined to label further; so "the agent proposed it and the maintainer went along" counts as a decision. Re-scored on that definition (not item-by-item human labels): wrong rate 23% (31 of 136: steps and discussion, plus 1 fabricated), missed about 37% (most of it the 8-line cap); changes of mind captured 12 of 19, unchanged and the measure to watch. |
| 2026-10-16 | **Re-measurement registered, before it runs.** Candidate: the distill on `feat/distill-capture` at `adfdc9b` (segments of about 6 000 characters, a change-of-mind pass over the whole excerpt, near-duplicates merged, changes first, up to 24 lines), tuned on ten other sessions (`tune_capture.py`, seed 20261017; these 22 session-days were not used). Baseline: the shipped distill's 143 lines already recorded above. Both scored the same way: a reference rebuilt under the maintainer's definition (Grok's same 94 proposals, re-checked by GPT-5.4 with "what the maintainer said, or went along with when the agent proposed it"; GPT-5.5 is out of quota), pairing by GPT-5.4, and each line classified by GPT-5.4 (steps or discussion, fabricated, and so on). The candidate is better if it captures at least as many changes of mind as the baseline, misses fewer reference decisions, and its steps-or-fabricated share is no more than 5 points above the baseline's; fabricated lines are reported on their own. |
| 2026-10-16 | **Amendment before scoring the re-measurement.** The reference was rebuilt as registered (GPT-5.4 kept 83 of Grok's 94 proposals and added 48: 131) and the candidate distilled the 22 session-days (252 lines), but every GPT model then returned HTTP 402 (the proxy's OpenAI quota ran out), so pairing and classification did not run. They are done by Grok 4.7 instead, for baseline and candidate alike. Grok also proposed the reference items, so absolute rates may read better than with GPT; the comparison between baseline and candidate, scored by the same judge on the same reference, is what the registered criteria use. |
| 2026-10-16 | **Re-measurement, scored** (Grok 4.7 pairing and classification, both versions, same 131-item reference under the maintainer's definition). Baseline (shipped): 143 lines, missed 51.9%, changes of mind 11 of 24, steps-or-fabricated 21.7% (30 steps, 1 fabricated). Candidate (`feat/distill-capture` `adfdc9b`): 252 lines, missed 40.5%, changes 15 of 24, steps-or-fabricated 17.1% (43 steps, 0 fabricated). **All three registered criteria met.** One-to-one "wrong rate" rises (55.9% → 69.0%) only because 252 lines are paired against 131 items; by category the share of steps and fabrications falls. The judge is the model that proposed the reference items (amendment above), so the absolute numbers are not quoted; the comparison is. |

## Set 7: LongMemEval, someone else's questions and labels (registered 2026-10-18, before any download or run)

Every earlier set was written by a model we chose (sets 1–3) or drawn from the maintainer's own traffic (sets 5–6).
Outside reviews named that as the weak point. This set uses a public benchmark nobody here wrote or labelled:
LongMemEval (Wu et al., ICLR 2025), the cleaned release `longmemeval_s_cleaned.json` (MIT,
`huggingface.co/datasets/xiaowu0162/longmemeval-cleaned`). 500 questions, each with its own haystack of about 50 chat
sessions, the session dates, and the authors' labels: which sessions hold the answer (`answer_session_ids`, and
`has_answer` on the turns), the question type, and `_abs` on the 30 questions that cannot be answered.

**Vault per question.** One Markdown page per haystack session: the date in the title and frontmatter, then the turns
as written. Nothing else: no distill, no `status: superseded`, no alias rows. This tests recall on raw imported
sessions, not the write side; KRouter's correction handling depends on the write side and is not exercised here.

**Systems,** each run once at the default it ships with, no tuning on this set:
- `krouter`: `route_knowledge.py search <question>` at the release current on the run day; up to three cited pages,
  or a refusal;
- `bm25-floor`: BM25 over Chinese character pairs and English words, floor picked on dev3 (as in set 3).

**Scored mechanically from the authors' labels** (no model in the loop):
1. *Evidence cited* (470 answerable questions): at least one cited page is an answer session.
2. *Knowledge update* (the `knowledge-update` type, answerable ones): the cited pages include the latest-dated answer
   session (the update); *stale only* = they cite an earlier answer session and not the latest.
3. *Abstention* (30 `_abs` questions): refused. Against it, the refusal rate on the 470 answerable questions.
Paired 95% intervals (bootstrap over questions, 10 000 resamples, seed 20261018) for KRouter minus BM25 on each.

**Secondary, model-judged, reported apart:** grok-4.7 reads the question, its date and the cited pages and answers or
says it does not know; grok-4.7 grades the answer with the benchmark's own per-type judge prompts (the paper used
GPT-4o; any number says which judge). Not a LongMemEval leaderboard score: the reader sees at most three pages.

**What may be claimed.** The mechanical numbers, all of them, whatever they are. "Better than BM25" on a metric only
if its paired interval is entirely on the right side of zero. No re-run after a fix: a fix is measured on a fresh
seed-drawn half of `longmemeval_m` instead, registered before it runs.

`bench/longmemeval/` (convert, run, score). The dataset is not committed; the scripts download nothing.

## Set 8: does an answer stay right as the vault grows? (registered 2026-10-18, before any run)

Rankings of memory systems can flip with tenure (Spencer 2026, "Ground Truth First": a system that leads at three
weeks fell from 96% to 72% at nine). The maintainer's vault has been a git repository since 2026-10-10, with a commit
a day, so the question can be asked of real history instead of a synthetic one.

**Events.** Every commit after the first (the 2026-10-10 import) that adds a change of mind (`原来 A → 改成 B` or the
same in English, in any page) or marks a page `status: superseded`. Extracted by script, none dropped by hand. On
2026-10-18 there are 9; the set is drawn when it is run.

**Questions.** For each event Grok 4.7 writes, from the diff alone, one question whose answer changed, with the old and
the new answer. The maintainer does not edit them. Frozen in a private file before any system runs.

**Snapshots.** For each event, the vault (`git archive`, read-only) at the commit that made the change, at three weeks
after it and at nine weeks after it (or the newest commit, if younger; the age is reported).

**Systems.** `krouter` at the release current on the run day; `bm25-floor` with and without skipping superseded pages.

**Scored.** A Grok 4.7 judge, blind to the system, sees the question, the old and the new answer, and the cited pages,
and labels the citation *new*, *old*, *both* or *neither*. Reported per snapshot age: share answered with the new value,
share stale (old only), refused.

**When.** First run on or after 2026-10-31 (three weeks of history), second on or after 2026-12-12 (nine weeks). Both
reported whatever they show.

**Amendment to set 7, 2026-10-18, after its run and before any change to KRouter.** The 30 `_abs` questions of
`longmemeval_s_cleaned.json` are now a development set: their results above have been read question by question and
the refusal gate may be tuned on them, so no abstention number from them is reported again. The plan to give the final
abstention number on a seed-drawn half of `longmemeval_m` does not work: LongMemEval's S and M files hold the same 500
questions (the README: 500 evaluation instances in each; they differ in the history around them), so every `_abs`
question in M has been seen. The final abstention numbers come instead from questions nobody here has read:
(1) the 80 neighbour questions of heldout3 (written by Claude Opus, never tuned on; at most two candidates a release
cycle, as registered), and (2) the neighbour questions of set 9, written by people. The answerable 470 of S stay a
check that a change does not start refusing what it should answer; any number from them is marked as seen.

## Set 9: written by people — corrections and their neighbours (registered 2026-10-18, before any item is written)

The correction handling is KRouter's main claim and has no outside evidence: every question about it so far was
written by a model (sets 1–3), drawn from the maintainer's traffic (set 5), or comes from LongMemEval, whose raw
sessions carry no `superseded` marks. This set is written by people.

**Items.** Each writer fills in, in their own words, one or more cases on a collection page: a topic; what was decided
first, with a date; what it was changed to later, with a date and why; a question whose answer is the new decision;
and a neighbour question on the same topic that the two notes do not answer. Writers do not see each other's cases or
any system's output. The page records whether a case came from the maintainer or someone else, nothing more.

**Vault.** All cases go into one vault built from the Chinese or English template, so cases are each other's
distractors. Each case becomes two pages: the first decision, and the change written as its own note. Two conditions:
*marked* (the first page gets `status: superseded`, as a KRouter user marks a correction) and *plain* (no mark; only
the dates and the wording say which is newer).

**Systems.** `krouter` at the release current on the run day; `bm25-floor` (floor from dev3); plain BM25 with no floor.

**Scored mechanically.** Current question: the change page cited first (right), the first-decision page cited first
(stale), or refused. Neighbour question: refused, or what was cited. Reported per condition and per writer group
(maintainer, others), with paired 95% intervals against each baseline (bootstrap over cases, 10 000 resamples, seed
20261018).

**Who reads what, when.** Nobody tuning KRouter (the maintainer's agents included) reads the cases before the run: the
build script reads them from the page's store, writes the vault and the questions to a private folder, and prints
counts only. Collection closes when at least 40 cases are in or on 2026-11-30, whichever comes first; the run follows
the close. Results are reported whatever they show; cases read after the run are spent, like a revealed held-out set.

### Log, sets 7 and 8

| Date | Event |
|---|---|
| 2026-10-18 | Both registered. Set 7 waits for the dataset; set 8 for history. Real-traffic blind judge (VERIFY layer 4): 18 router queries logged since the 2026-10-10 freeze plus 7 in agent sessions, of the 50 it waits for. |
| 2026-10-18 | **Set 7 run** (`longmemeval_s_cleaned.json`, SHA-256 `d6f21ea9…c3a442`; KRouter v1.1.1 from a worktree at the tag; scored mechanically from the authors' labels). Answerable questions with an answer session among the cited pages: **KRouter 439/470**, bm25-floor 264/470. Refused although answerable: KRouter 12/470, bm25-floor 204/470. Knowledge update, latest answer session cited: **KRouter 70/72**, bm25-floor 48/72; stale only: KRouter 1/72, bm25-floor 0/72. Unanswerable (`_abs`) refused: **KRouter 3/30**, bm25-floor 22/30. Paired 95% intervals, KRouter minus bm25-floor: evidence +37.2 points [+32.8, +41.7]; refused-answerable −40.9 [−45.5, −36.4]; knowledge update +30.6 [+19.4, +41.7]; abstention −63.3 [−80.0, −46.7]. |
| 2026-10-18 | **Reading it** (exploratory, not registered, said as such): plain BM25 with no floor, top three pages, cites an answer session for 447/470 and the latest update for 69/72, level with KRouter. The registered baseline's floor was picked on dev3, a 60-page Chinese vault, and on these 50-session English haystacks it refuses 43% of answerable questions; KRouter's lead over it comes from that floor, not from ranking, as on heldout3. What does hold: KRouter's refusal gate does not cost answerable questions here (12/470), and on raw sessions with no `superseded` marks it still cites the newest fact for 70 of 72 updates. What fails: it refuses 3 of 30 unanswerable questions. LongMemEval's abstention questions ask about a near neighbour of something the haystack does mention (a pet it never named, a trip it never took), the case KRouter's gate handles worst; it is the next thing to fix, measured on a seed-drawn half of `longmemeval_m` as registered. The model-judged secondary (reader and judge) has not been run. |
| 2026-10-18 | Set 7 amended (S `_abs` now development; final abstention numbers from heldout3 neighbours and set 9, since M repeats S's questions). Set 9 registered before any item was written. |
| 2026-10-18 | Development use of S (seen; not a reported score): candidate `fix/named-absent` (PR #61) refuses 9 of the 30 `_abs` questions (3 before) and 14 of 470 answerable (12 before); evidence cited 437 of 470 (439). Set 9 collection page published (owner reads all cases; each writer reads and writes only their own); a probe document was written, read back at owner and at `interact` level (not visible there), and deleted. |
