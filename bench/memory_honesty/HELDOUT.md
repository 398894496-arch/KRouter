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
| 2026-10-19 | Candidate 1 merged into `main` at the maintainer's call, before the real-traffic blind judge that rule 2 asks for. Any release that carries it says so; the blind judge is still run when the 50 fresh queries are in, and its result is logged here against 1.0.3. |
| 2026-10-30 | **Dense prototype measured for an opt-in tier, registered before the run** (not a default candidate: nothing in the product changes). Bench code only (`bench/memory_honesty/dense.py` on main plus the vault3 fixes from `feature/dense`: floors picked on dev3 / vault2, never on vault3). Four configurations, each run once: `agree` (BM25 over character pairs and dense must put the same live page first, each above its dev3 floor) and `rescue` (KRouter's default answers stand; a KRouter refusal is answered only when dense puts KRouter's own best page first above a dev3 floor), each with `paraphrase-multilingual-MiniLM-L12-v2` (fastembed, quantised ONNX) and `BAAI/bge-m3` (its own ONNX export, CLS pooling, run through fastembed). Embeddings run on this machine; no question leaves it. Baseline: KRouter default on main `e934696`. Aggregates only, `--ci` with paired intervals against the baseline; no `--reveal`. **Selection, fixed now:** the opt-in candidate is `rescue` (it never changes an answer KRouter gives, so it cannot lose one), with whichever model has the higher right-minus-wrong on dev3, the smaller on a tie; `agree` is reported as the other point on the trade-off. Because four configurations are looked at, a heldout3 number for the chosen one is a measurement, not shipping evidence; set 9 (written by people) and LoCoMo (set 10) are the checks that do not share this selection. Counts as candidate 1 of the cycle after 1.2.1. |
| 2026-10-30 | **Dense opt-in measurement, run as registered** (each configuration once, aggregates only, `--ci` and `--by-lang`, no `--reveal`). Baseline KRouter default (`e934696`): 26.1% wrong (36 / 138) [19.0, 33.1], 47 / 80 refused, 102 / 120 right. `rescue` MiniLM: 29.1% (44 / 151) [21.9, 36.6], 39, **107**; minus baseline, paired: wrong rate [+0.3, +6.1] points, right [+1, +10], refused [−14, −3]. `rescue` BGE-M3: 26.4% (37 / 140) [19.4, 33.6], 46, 103; [−0.5, +1.6], [0, +3], [−3, 0]. `agree` MiniLM: 15.6% (12 / 77) [7.6, 24.3], 69, 65; [−19.1, −1.8], [−49, −26], [+11, +32]. `agree` BGE-M3: **14.0% (14 / 100)** [7.7, 21.2], 67, 86; [−19.2, −5.3], [−26, −6], [+10, +30]. Selection as fixed before the run: on dev3 `rescue` scored right − wrong 29 − 7 with both models, a tie, so the candidate is `rescue` with MiniLM. It answers more questions right than the default, and cites wrong pages more often, both outside chance: it does not meet rule 2 (wrong ≤ 27%, refused ≥ 46). The two MiniLM runs were repeated once with `--by-lang` added (same configuration, deterministic, same aggregates) to split the halves. Not changed after this run. Write-up: `docs/DENSE-OPTIN.md`. |

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

## Set 10: LoCoMo, someone else's conversations and labels (registered 2026-10-30, before any dense run)

LoCoMo (Maharana et al., ACL 2024; `github.com/snap-research/locomo`, `data/locomo10.json`, CC BY-NC 4.0, SHA-256 `79fa87e9…a698ff4`): 10 conversations between two people, 19 to 32 dated sessions each (272 in all), 1 986 questions labelled by the authors with evidence turns (`D3:5`) and a category. Category 5 (446) is adversarial: the conversation does not say it, and the right answer is "not mentioned". English only.

**Vault per conversation.** One Markdown page per session, as KRouter's session import would place it (`05 时间日志/会话摘录/`), the date in the title and frontmatter, then the turns as written, a shared photo as its caption. Nothing else.

**Systems,** at their defaults, floors picked on dev3, nothing tuned on LoCoMo: `krouter` (main `e934696`, in-process recall, up to three pages), `bm25` (no floor), `bm25-floor`, and the dense prototype: `dense` (top three, no floor), `dense-floor`, `agree`, `rescue`, each with MiniLM and BGE-M3. Long session pages are cut into pieces of at most 600 characters at line ends; a page scores its best piece.

**Scored mechanically** (`bench/locomo/locomo.py score`): evidence first (categories 1–4: the first cited page is an evidence session), evidence cited (any of three), refused although answerable, category 5 refused, and the wrong-citation rate (answered questions whose first page is not an evidence session, every answered category-5 question included). Paired 95% intervals against `krouter` (bootstrap over questions, 10 000 resamples, seed 20261030).

**Order, said as it happened.** The adapter was shaken down by running `krouter`, `bm25` and `bm25-floor` once and reading their aggregates before this registration; nothing was changed after. The dense systems run after it.

### Log, set 10

| Date | Event |
|---|---|
| 2026-10-30 | Adapter shakedown before registration (as said above): `krouter` evidence first 991 / 1 540, in top 3 1 204, refused answerable 137, category 5 refused 37 / 446; `bm25` 968, 1 257, 0, 0; `bm25-floor` (dev3 floor) 46, 46, 1 494, 422. |
| 2026-10-30 | Registered, then the dense systems run once each. MiniLM: `dense` 703 / 1 053 / 0 / 0; `dense-floor` 396 / 525 / 860 / 289; `agree` 286 / 286 / 1 225 / 359; `rescue` 999 / 1 212 / 127 / 34 (minus `krouter`, evidence first [+0.2, +0.9] points). BGE-M3: `dense` 963 / **1 272** / 0 / 0 (evidence first [−4.7, +1.0], top 3 [+2.0, +6.9]); `dense-floor` 331 / 403 / 1 103 / 349; `agree` 371 / 371 / 1 148 / 317; `rescue` 991 / 1 204 / 136 / 37. Floors from dev3 do not transfer to session pages. Retrieval scores, not LLM-judged answers: not comparable with published LoCoMo accuracies. |

## Set 11: LongMemEval answer accuracy, scored the way other projects report it (registered 2026-11-09, before any run)

**Why.** Set 7 counts whether a cited page is an answer session. Other memory projects publish answer accuracy: a
model reads what the memory returned, answers, and a judge model grades the answer with the benchmark's own prompts.
This set gives KRouter that number, produced the same way, so it can be read next to theirs.

**Data.** `longmemeval_s_cleaned.json` (SHA-256 `d6f21ea9…c3a442`), all 500 questions (470 answerable, 30 `_abs`).
**Seen:** set 7's results were read question by question and the refusal gate was tuned on the 30 `_abs` (set 7
amendment), so every number from this set is marked as on a seen set.

**Retrieval.** KRouter at `main` `16d5ee5` (v1.3.0), `route_knowledge.py search <question>` on each question's own
vault, as in set 7: up to three cited session pages, or a refusal. Run once; KRouter is not changed between this
registration and the scoring.

**Reader.** Claude Sonnet, run as Claude Code subagents on the maintainer's Claude subscription (the model each agent
reports is logged), with the benchmark's own reader template (`src/generation/run_generation.py`, the step-by-step
variant: "I will give you several history chats between you and a user. Please answer the question based on the
relevant chat history. Answer the question step by step: …"), history in its `nl` format: the cited sessions' turns
from the dataset, sorted by date, each as `### Session i: / Session Date: / Session Content:`. A refused question
gets the same template with the history `(no chat history was retrieved)`. The reader is given the prompt only: no
answers, labels or other questions. It ran with file access and was told to read its batch file only; said here as
such.

**Judge.** Claude Sonnet, in separate subagents that see only the judge prompt, with the benchmark's own per-type
prompts (`src/evaluation/evaluate_qa.py`, `get_anscheck_prompt`, verbatim; the abstention prompt for `_abs`), the reply
parsed as the original does (`'yes' in reply.lower()`). The paper's judge is GPT-4o; this one is not, and every number
names its reader and judge.

**Reported,** whatever it shows: accuracy over the 500, over the 470 answerable, per question type, and on the 30
`_abs`, with 95% bootstrap intervals (10 000 resamples over questions, seed 20261109). `bench/longmemeval/qa.py`
(prepare, judge-prepare, score); the dataset is not committed.

**Result (2026-11-09).** **400 of 500 right, 80.0%** (95% interval 76.4–83.4); answerable 371 / 470, 78.9%
[75.1, 82.6]; `_abs` 29 / 30 identified as unanswerable. By type: single-session-user 61 / 64, single-session-assistant
55 / 56, knowledge-update 69 / 72, temporal-reasoning 97 / 127, single-session-preference 20 / 30, multi-session 69 /
121. Reader and judge: every agent reported `claude-sonnet-5-5` (Claude Sonnet 5.5); 108 reader agents and 20 judge
agents, none of which saw another's files by instruction (one judge wrote its output file with a short script and
said so; one reader listed the answers folder and said so). Retrieval: the v1.3.0 run, an answer session among the
cited pages for 437 / 470 answerable, 14 answerable and 9 `_abs` refused.
*Judge check:* four batches (100 verdicts: the two lowest-scoring, 6 / 25 and 9 / 25, another multi-session batch
at 19 / 25 and a knowledge-update batch at 25 / 25) were judged again by fresh judge agents; they agreed on 100 of 100. Same model twice, so this shows the
judge is stable, not that another judge would agree.
*Read with:* most published LongMemEval numbers use GPT-4o as reader and judge; this run uses a newer model for both,
so a difference from them is partly the model. LongMemEval has been public since 2024, so the reader may have seen
it in training. The weakest type is the one top-three retrieval limits: multi-session questions add up facts from
several sessions, and three pages often miss some (in the lowest batch the reader counted 2 of 4 film festivals, 2
of 3 weddings). Set 7's results were read before this run (see *Seen* above).
Files: `bench/longmemeval/results/2026-11-09-sonnet-qa.jsonl` (each question's cited sessions, reply and verdict;
`qa.py score --verdicts bench/longmemeval/results` recomputes the numbers) and `…score.json`.

## Set 12: the same reader, given different things (registered 2026-11-09, before any run)

**Why.** Set 11's 80.0% is one number from one reader (Claude Sonnet 5.5), and other projects' numbers come from other
readers, so nobody can tell how much of it is KRouter and how much is the model. This set holds the reader and the
judge fixed and changes only what the reader is given.

**Data, reader, judge.** As set 11, unchanged: the same 500 questions, the same reader template and judge prompts,
Claude Sonnet as Claude Code subagents with the same instructions to the agents (reader batches of up to 12 prompts
or 200 000 characters, judge batches of 25; the *nothing* row's prompts are a few hundred characters each and go 50
to a batch). Every agent's reported model is logged; a row is only compared with set 11 if its agents report the same
model, and any that does not is said.

**Rows** (what the reader is given for each question):

1. *Nothing*: the template with `(no chat history was retrieved)`. What the reader scores from the question alone
   (the 30 `_abs` questions are answered right by saying the information is not there).
2. *Plain BM25, top three sessions*: Okapi BM25 over the question's own haystack, one document per session (all turns,
   both speakers), lower-cased `[a-z0-9]+` tokens, no stemming, no stop list, k1 1.2, b 0.75, the three highest
   scores, never a refusal (`qa.py baseline --kind bm25`, written before this registration and not changed after).
3. *KRouter*: set 11's run as it stands (v1.3.0, up to three cited pages or a refusal). Not run again.
4. *Answer sessions*: the sessions the benchmark labels as holding the answer (`answer_session_ids`), the
   benchmark's own oracle setting. What this reader scores when retrieval is perfect.

**Not run again.** Where a row gives the reader a prompt identical, character for character, to one set 11 already
ran (the same sessions, or the same nothing), the reply and verdict from set 11 are copied, not produced again; the
results files mark each such question (`from_set_11`) and the counts are reported.

**Known before the run.** The whole set is seen (set 11's *Seen*), and set 11's replies were read. An exploratory
count on 2026-10-18 found that plain BM25 cites an answer session about as often as KRouter on these haystacks, so
rows 2 and 3 are expected to be close; that is the question this set puts a number on, not a result to steer.

**Reported,** whatever it shows: each row over the 500, the 470 answerable, the 30 `_abs` and per question type, with
95% bootstrap intervals; and, paired over the same questions, KRouter minus BM25 and answer-sessions minus KRouter
(10 000 resamples, seed 20261109), with how many questions only one of the two got right (`qa.py compare`).

**Not in this set.** The benchmark's full-history setting (all of a question's ~50 sessions, about 115 000 tokens per
question) is not run: 500 such prompts through subagents is beyond what this run can spend. No other memory project
is run here either; their published numbers use their own readers and are not put in the same table.

**Result (2026-11-09).** All four rows; the fourth was paused for cost and finished the same day (see *Deviations*).

| The reader is given | All 500 | 470 answerable | 30 `_abs` |
|---|---|---|---|
| Nothing | 30, 6.0% [4.0, 8.2] | 0 | 30 |
| Plain BM25, top three sessions | 405, 81.0% [77.4, 84.4] | 376, 80.0% [76.4, 83.6] | 29 |
| KRouter (set 11) | 400, 80.0% [76.4, 83.4] | 371, 78.9% [75.1, 82.6] | 29 |
| Answer sessions (perfect retrieval) | 492, 98.4% [97.2, 99.4] | 462, 98.3% [97.0, 99.4] | 30 |

| By type (right / of) | knowledge-update | multi-session | single-session-assistant | single-session-preference | single-session-user | temporal-reasoning |
|---|---|---|---|---|---|---|
| Nothing | 0 / 72 | 0 / 121 | 0 / 56 | 0 / 30 | 0 / 64 | 0 / 127 |
| Plain BM25 | 68 / 72 | 69 / 121 | 56 / 56 | 21 / 30 | 62 / 64 | 100 / 127 |
| KRouter | 69 / 72 | 69 / 121 | 55 / 56 | 20 / 30 | 61 / 64 | 97 / 127 |
| Answer sessions | 71 / 72 | 117 / 121 | 55 / 56 | 30 / 30 | 64 / 64 | 125 / 127 |
| KRouter − BM25, points [95%] | +1.4 [0.0, 4.2] | 0.0 [−5.0, 4.1] | −1.8 [−5.4, 0.0] | −3.3 [−13.3, 6.7] | −1.6 [−7.8, 3.1] | −2.4 [−6.3, 0.8] |
| Answer sessions − KRouter, points [95%] | +2.8 [−2.8, 8.3] | +39.7 [31.4, 48.8] | 0.0 [0.0, 0.0] | +33.3 [16.7, 50.0] | +4.7 [0.0, 10.9] | +22.0 [15.0, 29.1] |

*Paired, KRouter minus BM25:* −1.0 points [−2.8, +0.8] over the 500 (−1.1 [−3.0, +0.9] over the 470 answerable);
only KRouter right on 8 questions, only BM25 on 13. **No difference shown, and the point estimate is on BM25's side.**
For 262 of the 500 questions the two gave the reader the same sessions, so those replies and verdicts are set 11's
(`from_set_11`); the *nothing* row copies 23 (the questions KRouter refused).

*Paired, answer sessions minus KRouter:* +18.4 points [15.0, 21.8] over the 500 (+19.4 [15.7, 23.0] over the 470
answerable); only the answer-sessions row right on 93 questions, only KRouter on 1. Answer sessions minus BM25:
+17.4 [14.0, 20.8]. For 17 questions KRouter had cited exactly the answer sessions, so those are set 11's replies.

*What it says.* The reader knows none of the answers by itself (0 of 470), so set 11's 80% comes from the retrieved
pages, not from the model's own knowledge. But plain BM25 with no floor and no supersede rule gets the same reader
just as far: on this benchmark KRouter's lookup adds nothing over keyword search. The floor does not help here
either: given BM25's three sessions for an unanswerable question, the reader itself says the answer is not there
(29 of 30), as often as when KRouter has a chance to refuse first. LongMemEval's raw sessions carry no `superseded`
marks, so this set says nothing about corrections (sets 1–3 and 9 are about those).

*Where the other 18 points are.* Given the answer sessions, the same reader gets 492 of 500, so the reader is not
what limits set 11: retrieval is. Of the 93 questions it then gets right and KRouter's row gets wrong (48
multi-session, 28 temporal), KRouter had cited every answer session for 3, some but not all for 58 and none for 32;
24 of them need more than three sessions, which three cited pages cannot hold (33 of the 500 questions do). BM25's
top three lose the same way (89 questions: 3, 61 and 25). Counted after the run from the results files, not
registered. The limit is how few pages are handed over and whether all of a question's sessions are among them.

*Agents.* *Nothing*: 10 reader agents, 6 judge agents. *BM25*: 54 reader agents, 10 judge agents. *Answer sessions*: 75 reader agents (26 before the pause, 49 after), 7 judge
agents. All reported
`claude-sonnet-5-5`, the model set 11's agents reported. Results: `bench/longmemeval/results/2026-11-09-sonnet-qa.none.jsonl`,
`…-sonnet-qa.bm25.jsonl` and `…-sonnet-qa.oracle.jsonl`; `qa.py compare` reproduces the tables from them.

*Deviations from the registration.* (1) **The *answer sessions* row was paused for cost** after 26 of 75 reader
batches (166 questions answered, none judged) and an earlier version of this page said the row was not reported. It
was resumed the same day at the maintainer's request: the other 49 batches went to the same reader with the same
instructions, and nothing was judged or scored before all 500 replies existed, so no result was seen in between.
(2) The *nothing* and *answer sessions* rows were judged in batches of up to 80 instead of 25 (the prompts
unchanged), to use fewer agents. (3) One *nothing* judge agent wrote its verdict file with a short script, and one
*answer sessions* judge agent ran a shell command that did nothing; both said so, and each read only its input file.
(4) The *answer sessions* verdicts were not judged a second time. Eight multi-session and temporal ones drawn at
random (7 yes, 1 no) were read against the benchmark's answers afterwards and all eight stood: a spot check, not a
second judge.

## Set 18: does following the vault's own connections bring the whole answer? (registered 2026-11-10, before the associative path was written or any held-out question was run)

**Why.** Set 12 put KRouter level with plain BM25 on LongMemEval (80.0% and 81.0% with the same reader), and 98.4%
when the reader gets the labelled answer sessions. The points lost are mostly multi-session and temporal questions,
whose answer is spread over several sessions. Counted offline over all 500 (not a test: every question was seen in
sets 7, 11 and 12), BM25's top 3 holds every answer session for 384 of 500, multi-session 73 of 133, temporal 91 of
133. This set asks whether a second, associative path (spreading from the pages the question hits, along links,
supersedes, same session or day, shared rare words, and later co-citation) brings more of the whole answer in the
same number of pages. Retrieval only: no reader and no judge, no model is called.

**Data.** `longmemeval_s_cleaned.json`, as set 7. The 470 answerable questions are split as set 14 split them
(`lme.split_of` on branch `claude/wp2-refusal-396930`: seed 20261110, `random.Random.sample` of the sorted ids, half to
*dev*): 235 dev (74 multi-session, 54 temporal), 235 held out (47 multi-session, 73 temporal). Set 14 counted only
refusals of the unchanged gate on held-out ablated vaults; no ranking on the held-out half was looked at for this
set. The 30 `_abs` questions are left out (no answer to bring). Every design choice and constant of the associative
path is chosen on the dev half and on the development benches of this directory (`dev`, `dev2`, `dev3`).

**Metric.** For k = 3, 5, 8: the number of questions whose k returned pages include *every* labelled answer session,
overall and per question type. Systems, each giving exactly k pages, no refusal gate (the gate is unchanged by this
set and reported separately): `bm25` (the offline count above: FTS5 BM25 over character pairs and words, superseded
pages skipped), `krouter` (in-process `recall`, `gate=False`, at `9d73bd5`'s ranking), `krouter+assoc` (the same
direct hits, the associative pages filling the k slots as the shipped code fills them). Paired 95% bootstrap intervals
for `krouter+assoc` minus `bm25` (10 000 resamples over questions, seed 20261110).

**Pass bar, fixed now.** On the held-out half: (1) multi-session: `krouter+assoc` above `bm25` with the paired 95%
interval above zero at k = 3 and at k = 5, and not below `bm25` at k = 8; (2) all 235: `krouter+assoc` not below
`bm25` at any k; (3) the memory honesty sets (`dev`, `dev2`, `dev3`, `heldout`, `heldout2`, `heldout3`, aggregates
only): with the associative path on, no more wrong citations, no fewer refusals, no fewer correction or current hits
than with it off. If any part fails, the associative path ships off by default and the numbers are reported as they
are. The held-out half is run once, for the one configuration chosen on dev. LoCoMo (set 10's vaults and scoring of
"evidence cited", top 3) is a second outside check if time allows; it decides nothing.

**Separately (not part of the pass bar):** the deterministic tie-break for "the vault changed its mind" (a newer page
on the same thing ranked first and the conflict named, with no model and no distillation), judged by its own tests
(the audit's PostgreSQL-then-SQLite scenario among them).

### Log, set 18

| Date | Event |
|---|---|
| 2026-11-10 | Registered. |
| 2026-11-10 | Dev half, said as it happened. A prototype over dumped dev rankings tried seeds 1–5, 40–400 key words per page, query boost 0–10, a same-day weight 0 or 0.5 and three slot splits; same-day edges lowered the count (about ten sessions share a day here), so their weight is 0. Shipped code, first run: k = 3 fell (41 → 39 multi-session) because the third direct hit, given up for the associative slot, could not come back as an associated page; fixed. A quiet gate for pages joined only by shared words (at least 6 shared rare words and an associative score of at least 0.2) was chosen on the memory-honesty dev benches (pages offered on 56 of 61 answered dev questions before, 7 after), and changed no dev count by more than one. Final configuration (`associate.py`): 3 seeds, 64 key words, query boost 3, words in more than 30% of pages ignored, slots (k + 1) // 3. Dev half, multi-session at k = 3 / 5 / 8: bm25 42 / 47 / 56, krouter 41 / 49 / 57, krouter+assoc **48 / 63 / 67**; all 235: 181 / 193 / 208, 182 / 195 / 209, **192 / 213 / 224**. Memory honesty, six sets: identical with the path on and off, and identical to `9d73bd5`. The held-out half is run next, once. |
| 2026-11-10 | **Held-out half, run once at `6dedefd`.** Multi-session (47) at k = 3 / 5 / 8: bm25 24 / 31 / 35, krouter 28 / 32 / 36, krouter+assoc **29 / 40 / 42**; paired, krouter+assoc minus bm25: k = 3 [0, +10], k = 5 [+4, +15], k = 8 [+3, +12]. Temporal (73): 51 / 54 / 59, 50 / 53 / 59, 50 / 58 / 63. All 235: 184 / 198 / 208, 187 / 198 / 209, **190 / 210 / 218** (k = 3 [−1, +13]). Memory honesty, six sets: no change. **Bar (1) fails at k = 3**: the interval's lower end is 0, not above it (most of the four-question lead over BM25 at k = 3 is the direct path's: krouter alone is 28); (2) and (3) pass. So the associative path ships **off by default** (`KROUTER_ASSOC=1` turns it on). |
| 2026-11-10 | After the held-out run, the conflict tie-break (not part of this bar) was narrowed: a newer page whose change line does not name the question's subject is no longer flagged (the dev half had 57 such "possible" flags in 235 questions, long chats being full of "instead of" and "replace"; 13 after). The held-out fire counts had been seen once before this change (they were counted next to dev's), not the coverage counts. The held-out half was then run a second time with the final code to report the shipped configuration: **every count identical** to the run above. |
| 2026-11-10 | LoCoMo, a second outside check that decides nothing (set 10's conversion, categories 1–4 with evidence, 1 536 questions, all sessions of a conversation in one vault): all at k = 3 / 5 / 8: bm25 1 079 / 1 181 / 1 269, krouter 1 104 / 1 204 / 1 273, krouter+assoc 1 078 / 1 183 / 1 271; category 1 (282, the multi-evidence category): 47 / 73 / 105, 51 / 78 / 110, 50 / 78 / 106. On LoCoMo's short sessions the associative path takes slots from direct hits that were right: **no gain, a small loss against krouter**. |
| 2026-11-10 | **The maintainer's decision after these numbers** (relayed by the planning session): the associative path goes in built in, no switch, as five pages, the first three always direct hits and the associated pages in places four and five (earlier only when there are fewer than three direct hits), a place they do not need going to the next direct hit. This is the k = 5 configuration measured above, decided by the maintainer, not by bar (1), which stays failed at k = 3. One fix with it: when one associated page was found, the fifth place could repeat it as a direct hit; now it goes to the next direct hit not already listed. Rerun of both halves and LoCoMo with that code: held-out k = 5 **unchanged** (multi-session 40, temporal 58, all 210; krouter's five direct hits 32 / 53 / 198; bm25 31 / 54 / 198); dev k = 5 unchanged (63 / 46 / 213). k = 3 is now krouter's three direct hits (no associated place), and k = 8 three direct + five associated (held-out 42 / 61 / 215). LoCoMo at five pages: 1 185 (bm25 1 181, five direct hits 1 204, the earlier three pages 1 104); at three pages now equal to krouter (1 104). Memory honesty, six sets, at five pages: unchanged. |
| 2026-11-10 | **A guard for short sessions, tried and not added.** On LoCoMo's short sessions the associated pages took places four and five from direct hits that were right. Two rules fixed before any count, each keeping a fourth or fifth direct hit in its place (so the path gets fewer places) when its score is high: at least half the top score, or at least 0.9 of the third hit's score. Counted on development data only: the LongMemEval dev half and five of LoCoMo's ten conversations (`random.Random(20261110).sample` of the sorted conversation vaults: conv-41, 43, 44, 47, 48; 794 questions), five pages, no gate. No guard: LongMemEval 213 (multi-session 63), LoCoMo 630. Half the top score: 203 (55), 634. 0.9 of the third: 211 (61), 632. Neither is a clear gain (the first costs ten LongMemEval questions for four LoCoMo ones, the second trades two for two), so **neither is added** and the held-out halves were not run for them. The other five LoCoMo conversations stay unused for this. |

## Set 22: the same reader, five pages each — keyword search against KRouter with its associative path (registered 2026-11-10, before any reader or judge call)

**Why.** Set 12 found KRouter's three pages level with plain BM25's three (400 and 405 of 500), and the README says so.
KRouter now hands over five pages, the last two from the associative path, and set 18 counted, without a reader, that
this brings every answer session for more multi-session and temporal questions. This set asks whether that turns
into answers, against keyword search given the same number of pages.

**Data, reader, judge.** As set 12, unchanged: the same 500 questions, the reader template and judge prompts in
`bench/longmemeval/qa.py`, Claude Sonnet 5.5 as Claude Code subagents with the same instructions, reader batches of up
to 12 prompts or 200 000 characters, judge batches of 25. Every agent's reported model is logged; a row is compared
with sets 11 and 12 only if its agents report `claude-sonnet-5-5`.

**Rows.** (1) *Plain BM25, top five sessions*: `qa.py baseline --kind bm25 --top 5` (set 12's Okapi BM25, unchanged
apart from five instead of three). (2) *KRouter, five pages*: `lme.py run --system krouter --pages 5` at the commit
that carries this registration: `route_knowledge.py search`, as an agent calls it, the receipt's pages in order (direct
hits, then `associated:`); a refusal gives the reader nothing.

**Not run again.** A prompt identical, character for character, to one sets 11 or 12 ran is copied with its reply and
verdict, not produced again; a prompt identical between the two rows of this set is run once and used for both. The
results files mark each such question and the counts are reported.

**Known before the run.** The whole set is seen (sets 7, 11, 12), and so is set 18's retrieval count on both halves
(dev tuned, held-out run; FTS5 BM25 there, not this set's Okapi BM25). The configuration is set 18's five-page rule as
shipped; nothing in ranking, refusal or the page rule changes between this registration and the run. Expected from set
18: more answer sessions handed over on multi-session and temporal questions; whether the reader turns that into
answers, and whether two more pages of distractors cost elsewhere, is the question.

**Reported,** whatever it shows: each row over the 500, the 470 answerable, the 30 `_abs` and per type, with 95%
bootstrap intervals; paired, KRouter minus BM25 (10 000 resamples, seed 20261110), with how many questions only one
of the two got right; and each row next to set 12's three-page rows (same reader). **What may be said after it:** if
the paired interval over the 500 is above zero, that KRouter is ahead of keyword search at the same five pages, with
the numbers; if it holds zero, that they are level at five pages too; if it is below zero, that.

**Estimated cost, counted from the prompts before any call** (KRouter's pages taken in-process, so the run's own
count may differ by a few): BM25 row 500 prompts, 33.0 M characters, 205 reader batches; KRouter row 466 prompts after
34 are copied from sets 11 and 12, 420 after 46 identical to the BM25 row are shared, 27.3 M characters, 168 reader
batches; about 37 judge batches. In all **about 410 subagent runs and 60 M characters (about 15 M tokens) of reader
input**. Not started until the maintainer says so.

**Amendment (2026-11-10, before any reader or judge call; replaces *Rows*' scope, the batch size, *Reported*'s
claim and the cost above).** (1) **Held-out half only**: the 235 answerable questions of set 14's held-out half
(`lme.split_of`, seed 20261110). The associative path's settings were chosen on the dev half, so a reader result on it
would not be clean; the held-out half is the number to trust. The dev half and the 30 `_abs` questions are not run.
(2) The two rows are unchanged (BM25's top five, KRouter's five pages at the commit that carries this amendment);
where both rows hand over exactly the same sessions the prompt is identical and is run once for both; a prompt
identical to one sets 11 or 12 ran is still copied. Reader batches of up to 12 prompts or **400 000** characters
(set 12: 200 000), judge batches of 25. (3) **Bar, fixed now:** KRouter is called *ahead of keyword search at five
pages* only if the paired 95% interval of KRouter minus BM25 over the 235 has its lower end above zero; otherwise the
README's "level with keyword search" stays as written (with this set's numbers added). Reported per question type,
multi-session on its own line, with paired intervals per type; the type rows decide nothing. (4) KRouter's
configuration: unchanged by the short-session guard tried after set 18 (see set 18's log: not added). **Cost, counted
from the prompts** (KRouter's pages through `route_knowledge.py`, as the run takes them): 235 BM25 prompts; for
KRouter 23 shared with BM25 and 17 copied from sets 11 and 12, so 195 to run; **430 reader prompts, 28.3 M characters
(about 7 M tokens), 78 reader batches and 18 judge batches: about 96 subagent runs.** Waiting for the maintainer.

### Log, set 22

| Date | Event |
|---|---|
| 2026-11-10 | Registered. Not run (waiting for the maintainer, for cost). |
| 2026-11-10 | Amended as above, before any reader or judge call: held-out half only, batches of 400 000 characters, the bar for "ahead" fixed, cost recounted (about 96 subagent runs instead of about 410). Not run. |
| 2026-11-10 | **Registered, not run: the maintainer decided not to spend the quota on it.** No reader or judge call was made and there is no result at the answer level for five pages. The registration (as amended) stands; it can be run as written later. |
## Set 14: can the refusal gate refuse more, without losing answers? (registered 2026-11-09, after the development analysis below and before any held-out half was opened)

**Why.** The README's "refuses 3 of 30 LongMemEval questions that have no answer" is quoted as a gap. Two things in it
are stale or mixed up: 3 of 30 is KRouter 1.1.1 (set 7); the gate shipped since the absent-name rule (`fix/named-absent`)
refuses 9 of 30 (set 7's log), and set 11's retrieval was that 9. And it is a *retrieval* number (the cited-pages
list is empty); the benchmark's own question is whether the *answer* says the information is not there, which
set 11 and 12 measured: 29 of 30, for KRouter and for plain BM25 alike, and 30 of 30 when the reader is given nothing.
This set asks the narrower product question: can the gate itself be made to refuse more of them, without refusing
questions it can answer?

**Data.** `longmemeval_s_cleaned.json`, as set 7. The 30 `_abs` questions stay a development set (set 7 amendment: they
were read question by question and the gate was tuned on them once already, so no abstention number from them is a
test). The 470 answerable questions are split by `lme.split_of` (seed 20261110, `random.Random.sample` of the sorted
ids): 235 *dev*, 235 *held out*. Held-out unanswerable questions come from two places no rule is chosen on: (a) the
*held-out half with its answer sessions removed* (`lme.make_ablated`: every page the authors label as an answer session
is deleted from the question's vault, so nothing can answer it; labelled by the authors, no model; easier than the real
`_abs`, whose topical sessions stay in the vault), and (b) LoCoMo category 5 (set 10; KRouter's 37 of 446 there was an
aggregate seen once, nothing was tuned on it).

**Pass bar, fixed before any rule is chosen.** A candidate rule ("also refuse when ...") is kept only if, on the dev half,
it loses at most 1 point of the answerable questions' evidence-cited rate (at most 2 of 235) and refuses clearly more
of the real `_abs` than the 9 of 30 now (a gain of 5 or more of the 21 that are answered). Only then is the held-out
half run, once, for that one rule: held-out answerable evidence cited must not fall by more than 1 point (of 235) and
refusals on the held-out ablated vaults and on LoCoMo category 5 must rise. If no rule passes on dev, the held-out
half is not opened and the report says so. No model is called, as for the reader-free sets.

**Development analysis, said as it happened (before this registration, on dev data only).** Features per question for
the gate shipped at `9d73bd5`: top score, gap to the second page, strong-match count, the share of the question's idf
mass found on the best page, question words that no page contains, and a few more (`bench/longmemeval/gate_study.py`).
One- and two-signal rules over a threshold grid, scored on: the 30 `_abs`, the dev half's answers the gate now gets
right (225 of 235), and the dev half with answer sessions removed. The held-out half was not read; the unchanged
gate's refusal rate on all 470 ablated vaults was counted (the product is not changed by this set, so that count tunes
nothing). The same script reproduces the numbers below.

### Log, set 14

| Date | Event |
|---|---|
| 2026-11-09 | Gate at `9d73bd5`, unchanged: 9 of 30 `_abs` refused, 14 of 470 answerable refused, evidence cited 437 of 470 (reproduces set 11's retrieval). On the answer-sessions-removed vaults: **220 of 470 refused** (dev 103 of 235, held-out 117 of 235). For the 30 `_abs`, the labelled "answer" sessions are in the vault and the best page is one of them for 22 of 30: these questions ask for a detail a related session does not give. |
| 2026-11-09 | Dev search, 49 288 rules: **no rule passes.** Within the 1-point budget (at most 2 of 235 answers lost) the best rule refuses 2 more of the 21 real `_abs` that are answered (in-sample, so an upper bound); at 5 lost (2.1 points) it refuses 5 more. Share of the question's idf mass on the best page, refuse below 0.40: 11 of 30 `_abs`, 17 answers lost; below 0.55: 18 of 30, 53 lost. Signals that carry the near-miss (best-page coverage, missing words, gap to the second page) separate the real `_abs` from answerable questions no better than chance (AUC 0.46–0.54: coverage 0.54, missing words 0.53 and 0.46, among the 21 still answered and the 225 right); the ones that do separate them (top score 0.70, strong-match count 0.72, short questions 0.68; gap to the second page 0.62) are what the gate already uses. The held-out half and LoCoMo were not opened; nothing in the product changed. |

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

## Set 13: same situation, different subject — does an experience card come back as a suggestion? (registered 2026-11-09, before any matcher was written)

**Why.** Every set above asks whether KRouter finds the page that answers a question. This one asks something else:
whether a lesson learned on one task ("the stew tasted flat; a spoonful of sugar fixed it") comes back as a
*suggestion* on a task with a different subject in the same situation ("the poster's colours look dull"), and stays
quiet otherwise. Code: `skill/krouter/scripts/experience.py`; bench: `bench/transfer/`.

**Cards.** 14 experience cards written by hand in `bench/transfer/cards/` (situation, what was done, what came of it,
the lesson without the subject, the "when" triggers, a source line). Chinese only. Each comes from one subject (nginx,
CI, a stew, a production database…). The cards are frozen at registration with the cases: SHA-256 of the
concatenated card files in name order `df0cfe6a…5d6f191e`.

**Cases.** 56, Chinese, written in one sitting before the matcher existed: 28 *transfer* cases (two per card, each on
a subject different from the card's and from each other; the expected card is the one whose lesson a careful person
would offer) and 28 that should get no suggestion: 14 *topic traps* (the card's own subject, a different situation:
"does nginx's server_name take wildcards"), 6 *word traps* (a word from some card's triggers, a different situation:
"the drawer is stuck"), 8 *unrelated*. Split at seed 20261109: for each card one transfer case to development and one
to held-out; topic traps 7 / 7, word traps 3 / 3, unrelated 4 / 4. `bench/transfer/dev.jsonl` (28) is what the
matcher is tuned on; `bench/transfer/heldout.jsonl.gz` (28, SHA-256 of the uncompressed text `3a7f625c…3361f33`) is
run once.

**Who wrote what.** The cards, all 56 cases and the matcher are written by the same Claude Code session (Opus 5.5).
The cases were written before any matching code and are not edited after the split, but the author knew the cards'
trigger wording when writing them: the held-out number measures generalisation from the development cases to unseen
cases of the same author, not to other people's phrasing. This is the main limit of the set and is said with any
number from it.

**System.** The default suggestion path: lexical only (the recall index's tokenizer and word lists, the cards'
`when` triggers and lesson line; no embeddings, no model call), up to two suggestions, a quiet threshold picked on
development only. The optional dense tier (`docs/DENSE-OPTIN.md`) may be measured on development as a comparison; it
is not the default and is not run on held-out unless registered here first.

**Scored mechanically.** Recalled: on a transfer case, the expected card is among the suggestions. Wrong suggestion:
any suggestion on a case that should get none, and any card other than the expected one on a transfer case. Reported
for development and held-out: recalled / 28 transfer… per split, cases with a wrong suggestion, total wrong cards,
and by negative kind.

**Pass line (fixed now).** On held-out: recalled on at least 8 of 14 transfer cases (a majority), and at most 1 of the
14 should-be-quiet cases gets any suggestion, and at most 1 wrong card on the transfer cases. If it fails, the
suggestion path ships off by default, marked experimental, with the numbers as they are.

### Log, set 13

| Date | Event |
|---|---|
| 2026-11-09 | Registered (`e2b33e5`): cards, development cases and the sealed held-out file committed before `experience.py` existed. |
| 2026-11-09 | **Development (in-sample).** Two lexical rules tried: a card's best single `when` phrase covered (`phrase`), and all its phrases pooled (`bag`); for `phrase`, also counting bigrams outside the word list at half weight. Thresholds swept with `run.py dev --sweep`. Choice rule, fixed before the sweep was read: highest recalled − 2 × (quiet cases with a suggestion + wrong cards on transfer cases), ties to the stricter. Chosen: `phrase`, at least 2 words of the phrase, coverage ≥ 0.6: **recalled 3 / 14, quiet cases with a suggestion 0 / 14, wrong cards 1**. The loosest setting tried recalled 6 / 14 with 2 quiet cases suggested and 4 wrong cards; `bag` at best 3 / 14 with 3 wrong cards; the half-weight variant was worse at every setting and was dropped. Reading the misses: most transfer cases share no word with the card's triggers ("差点意思" against "缺点什么", "改过" against "改了"); lexical matching cannot bridge them. The dense tier was not measured: no embedding model is on this machine and downloading one (about 250 MB) was not approved in this session. Threshold frozen; held-out next. |
| 2026-11-09 | **Held-out, run once** (`run.py heldout`, threshold as frozen above). **Recalled 0 / 14 transfer cases. Quiet cases with a suggestion 2 / 14 (both word traps; topic traps 0 / 7, unrelated 0 / 4). Wrong cards on transfer cases 2.** Fails all three parts of the pass line (8 / 14, ≤ 1, ≤ 1). The development number (3 / 14) did not carry over at all: the three it recalled were cases whose wording happened to share two words with a trigger, and none of the held-out cases did. As registered, the suggestion path ships off by default, marked experimental (`KROUTER_EXPERIENCE=1` to try it). What it does show: a lexical matcher over subject-free triggers does stay quiet on questions about a card's own subject (0 of 14 topic traps over both splits); what it cannot do is recognise the same situation said in other words, which is the point of the feature. The held-out cases are now spent. |

## Set 15: the host model judges the situation itself, from a digest of every card (registered 2026-11-09, before any host was run or the usage wording was settled)

**Why.** Set 13 matched tasks to cards by shared words and recalled 0 of 14 held-out cases: one situation in other
words shares no words. Here nothing is matched. The session-start hook gives the host model the whole experience
digest (`experience.digest`: every card as one subject-free line "situation → what to do〔id〕", at most 30 lines,
then one line on how to use them), and the host decides whether this task's situation is one of them. Set 13 and its
spent held-out file stay as they are.

**Cards.** Set 13's 14 cards, unchanged. For the scale check, 40 distractor cards in `bench/transfer/distractors/`
(lessons about plants, cooking, travel, money…), written before any set 15 case was read; SHA-256 of the
concatenated files in name order `8860fc6d…25a48`.

**Cases.** 56, Chinese, written by Fable 5.2 (claude-fable-5-2) in a fresh Claude Code subagent, a different model
from the session that wrote the cards and the code (Opus 5.5) and from both hosts. The writer saw one input file:
the 14 lessons (`通用说法`) in shuffled order under neutral labels, each with a few words naming the card's original
subject (needed for the topic traps). It did not see the triggers, the situation/action fields, the digest, the
usage wording or any code, and was told to read nothing else. It wrote 28 *transfer* cases (two per lesson, subjects
other than the original), 14 *topic traps* (the original subject, another situation), 8 *word traps* (a word from
some lesson, another situation) and 6 *unrelated*. Not edited. Split at seed 20261115: one transfer case per card to
each side, traps 7 / 7, word traps 4 / 4, unrelated 3 / 3. `bench/transfer/set15_dev.jsonl` (28) is where the usage
wording may be revised; `bench/transfer/set15_heldout.jsonl.gz` (28; SHA-256 of the uncompressed text
`88bec167…e854b5`) is sealed and run once per host. The writer's raw file (with its notes) is kept out of the repository.

**Hosts.** Haiku 5.5 and Sonnet 5.5, run as set 12 ran its reader: `bench/transfer/host.py prepare` writes batches of
14 prompts (the injected digest, the user's message, and one bench line asking for only the first few sentences of
the reply and no tools); a Claude Code subagent on the named model (`model: haiku` / `sonnet`) answers each prompt in
a batch as if it were the only one and writes the replies back; each agent's reported model is logged. No API key
and no stored Claude login are used. About 250 short prompts in all.

**Scored mechanically** (`host.py score`): recalled = the expected card's id is cited; quiet case with a suggestion =
any id cited where none should be; wrong cards = any other id cited on a transfer case (distractor ids included).
Replies citing more than two ids are counted too.

**Pass line (fixed now), per host, on held-out:** recalled ≥ 8 / 14, quiet cases with a suggestion ≤ 1 / 14, wrong
cards ≤ 1. The digest passes when both hosts pass. Only then is a default-on proposal made.

**Scale check (development only).** The same development cases with the 40 distractors added (54 cards, all listed);
reported next to the 14-card development row for each host. Not a pass condition.

**Known limits, said with any number.** Each agent sees up to 14 cases in one batch, so it may compare them; the bench
line asks for short replies, which a real session does not; the writer saw each card's subject label; Chinese only;
the digest's token count is an estimate (no tokenizer is downloaded: one token per CJK character, one per three
other characters, an upper-end figure).

### Log, set 15

| Date | Event |
|---|---|
| 2026-11-09 | Registered (`dc985b4`). Before the first host run two harness faults were fixed, neither touching the digest or its wording: prompts were batched in case order (one batch all transfer cases, the other all quiet ones), and case ids such as `C01-x1` carried the expected card's id into the prompt. Prompts are now ordered and named by an opaque hash (`host.py opaque`). |
| 2026-11-09 | **Development, first and only wording** (the digest and usage line as committed with this log; 28 prompts per host, two batches of 14; agents reported `claude-haiku-5-5` and `claude-sonnet-5-5`). **Sonnet 5.5: recalled 14 / 14, quiet cases with a suggestion 0 / 14, wrong cards 0. Haiku 5.5: 13 / 14, 0 / 14, 1** (it added C05 to C11 on one case and missed C09 on another). No reply cited more than two ids. The wording was not revised: frozen as is. Digest: 14 lines, 842 characters, about 690 tokens by the registered estimate. |
| 2026-11-09 | **Held-out, run once per host** (wording as frozen in `a581b84`; agents reported `claude-haiku-5-5` and `claude-sonnet-5-5`). **Sonnet 5.5: recalled 14 / 14, quiet cases with a suggestion 0 / 14, wrong cards 0. Haiku 5.5: recalled 11 / 14, quiet cases with a suggestion 0 / 14, wrong cards 0.** No reply cited more than two ids. Both hosts pass the registered line (≥ 8, ≤ 1, ≤ 1). A mechanical check not in the registration, reported for what it is: no quiet-case reply on either split says 「可以试试」 or offers a lesson without an id (one development reply uses 经验 in its ordinary sense, "常见的经验是测试金字塔"); every transfer case that cited its card also used the 「别的任务里的经验」 wording. Limits as registered: up to 14 cases per agent, short replies asked for, writer saw the subject labels, Chinese only. |
| 2026-11-09 | **Scale check, development only** (14 cards + 40 distractors, all 54 listed; about 1 906 characters, about 1 518 tokens by the estimate). **Sonnet 5.5: 14 / 14, 0 / 14, 0. Haiku 5.5: 13 / 14, 0 / 14, 0** (against 13 / 14, 0, 1 with 14 cards): no distractor id was cited, quiet cases stayed quiet. Found while preparing it: with the shipped cap of 30 lines, all 14 real cards would have been left out, because nothing yet writes `adopted_at` and the bench cards share one date, so ties fall to file-name order (`D…` before `C…`). The cap's ordering is only as good as the dates and adoption marks on the cards. Totals for the set: 168 host prompts (56 per run: development, scale, held-out) in 12 agents, plus the case writer. |

## Set 16: set 15 in English (registered 2026-11-09, before any host was run on it or its usage wording was settled)

**Why.** Set 15 was Chinese only. This set asks the same question on an English vault with English sessions.

**Cards.** Set 13's 14 cards translated into English by the session that wrote the code (`bench/transfer/cards_en/`,
same ids; SHA-256 of the concatenated files in name order `b27d45a3…59f03bc`), on the public English template.

**Digest.** The English digest: each card's lesson as written ("When …, … [id]"), then an English usage line with the
same rules as set 15's (genuinely the same situation, not a shared word or subject; at most two, as "A lesson from
another task you could try: … [id]"; otherwise say nothing). Written once before this registration; it may be revised
on development only and is frozen before held-out.

**Cases.** 56, English, written by Sonnet 5.5 (claude-sonnet-5-5) in a fresh Claude Code subagent that saw only the
14 English lessons, shuffled under neutral labels, each with its original subject named in a few words, and was told
to read nothing else; same four kinds and counts as set 15 (28 transfer, 14 topic traps, 8 word traps, 6 unrelated).
Not edited. Split at seed 20261116 as set 15 was. `bench/transfer/set16_dev.jsonl` (28); `bench/transfer/set16_heldout.jsonl.gz`
(28; SHA-256 of the uncompressed text `d939c2ca…5b24ba8a`), run once per host.

**Hosts, scoring and pass line:** as set 15 (`host.py --set 16`): Haiku 5.5 and Sonnet 5.5, 14 prompts per agent,
ids cited; per host on held-out, recalled ≥ 8 / 14, quiet cases with a suggestion ≤ 1 / 14, wrong cards ≤ 1.

**Known limits,** beyond set 15's: **the case writer is also one of the two hosts** (Sonnet 5.5), so Sonnet's number
may read better than an outside writer's cases would give it; the cards are a translation.

## Set 17: are the cards a host agent writes itself any good? (registered 2026-11-09, before any host was run on it)

**Why.** The zero-key path has the agent that ran a session write the card (`krouter_learn` / `experience.py learn`);
no model lane, no key. Sets 15 and 16 used hand-written cards. This is a small check of what the hosts write.

**Sessions.** 12 synthetic sessions written for this check by the session that wrote the code, never a real one
(`bench/transfer/set17_sessions.jsonl`, SHA-256 `7ccda464…c4ba2de`): 7 with a lesson (5 Chinese, 2 English), 3 whose
lesson is already one of the 14 cards in another subject (2 Chinese, 1 English), 2 with no lesson (one each). Each
has gold: the subject's words, and terms the action and the result must hold.

**Run.** `bench/transfer/extract.py`: each host (Haiku 5.5, Sonnet 5.5; one agent each, 12 prompts) gets the
session-start digest of the vault in that language, the session, and the tool's own description, and says with what
arguments it would call `krouter_learn` at the end. Every proposed card goes through `experience.learn()` on a fresh
copy of the vault, as the tool would. Run once; no development split.

**Scored mechanically.** Lesson sessions with a card written; of cards written, subject-free (no subject word in
title, lesson or `when`) and faithful (action and result each hold a gold term); duplicate sessions with a card
written (and whether the host proposed one at all); cards written on sessions with no lesson.

**Bar (fixed now), both hosts together:** lesson sessions with a card ≥ 10 / 14; subject-free ≥ 90% and faithful ≥ 90%
of cards written; duplicates written ≤ 1 / 6; cards on no-lesson sessions ≤ 1 / 4.

**Known limits.** Twelve sessions, written by the code's author, short and clean; whether a host calls the tool on its
own at the end of a real session, unprompted, is not measured here.

### Log, sets 16 and 17

| Date | Event |
|---|---|
| 2026-11-09 | Registered (`361f906`). |
| 2026-11-09 | **Set 16, development, first and only wording** (English digest, 14 lines, 2 522 characters, about 846 tokens by the estimate; agents reported `claude-haiku-5-5`, `claude-sonnet-5-5`). **Haiku 5.5: recalled 14 / 14, quiet cases with a suggestion 0 / 14, wrong cards 0. Sonnet 5.5: 14 / 14, 0 / 14, 0.** Wording not revised; frozen. |
| 2026-11-09 | **Set 17, run once** (one agent per host, 12 sessions). Haiku 5.5: lesson sessions with a card 7 / 7; of 7 cards, subject-free 6, faithful 6; duplicate sessions: none proposed, none written (0 / 3); no-lesson sessions: none written (0 / 2). Sonnet 5.5: 7 / 7; of 7 cards, subject-free 6, faithful 4; duplicates 0 / 3; no-lesson 0 / 2. **Both hosts together: lesson sessions with a card 14 / 14 (bar ≥ 10); subject-free 12 / 14 = 86% (bar ≥ 90%); faithful 10 / 14 = 71% (bar ≥ 90%); duplicates written 0 / 6 (≤ 1); no-lesson written 0 / 4 (≤ 1). The bar is not met** on subject-free and faithful. Reading the five failing cards afterwards (not part of the registered score, said as such): the four "unfaithful" cards say what the session says in other words than the gold terms ("明显减少" for 少了, "唯一标识" for 请求 id, "planned 22 and finished 21" for close/within); the two subject leaks are real, each one `when` phrase naming the subject ("新人总来问", "no reply to my email"), while both cards' lessons, the only field the digest shows, are subject-free. The duplicates were all skipped by the hosts themselves (the digest showed the same lesson), not caught by the code's lexical same-lesson check. |
| 2026-11-09 | **Set 16, held-out, run once per host** (English wording as frozen in `f9597e6`). **Haiku 5.5: recalled 13 / 14, quiet cases with a suggestion 0 / 14, wrong cards 0. Sonnet 5.5: 14 / 14, 0 / 14, 0.** Both pass (≥ 8, ≤ 1, ≤ 1). Sonnet also wrote the cases (registered limit). 112 host prompts for set 16, 24 for set 17. |

## Set 19: set 17 again, on sessions that read like real ones, judged by a model (registered 2026-11-09, before any host was run on it)

(Set 18 is kept for another session's work.)

**Why.** Set 17 missed its bar, and its result has been read, so it is spent. Two changes were made before this
registration, on the strength of set 17's reading: cards no longer carry `when` phrases (nothing uses them since set
13; both of set 17's subject leaks were there), and faithfulness is judged by a model reading the session instead of
fixed gold terms.

**Sessions.** 16, written by Sonnet 5.5 (claude-sonnet-5-5) in a fresh subagent, not by the session that wrote the
code: 8 to 10 turns each, with drift and changes of course. 8 with a lesson (5 Chinese, 3 English), 4 whose lesson
is one of the 14 cards in another subject (2 each; the writer saw the 14 lessons for that), 4 with no lesson (2 each).
The writer also gave each session's subject words and the lesson's gist. Not read by the code's author before the
run (counts only). `bench/transfer/set19_sessions.jsonl`, SHA-256 `b137cc96…9a07c85caf`.

**Run.** As set 17 (`extract.py --set 19`): each host (Haiku 5.5, Sonnet 5.5; one agent each, 16 prompts) gets the
digest, the session and `krouter_learn`'s description, now without `when`, and proposes arguments; every proposed card
goes through `experience.learn()` on a fresh copy of the vault. Run once.

**Judged.** Every card written on a lesson session is judged by the *other* host model (Haiku's cards by Sonnet,
Sonnet's by Haiku; one agent each), reading the session and the card: faithful (situation, action and result say only
what the session shows, nothing invented or abandoned) and subject-free (lesson and title would read unchanged on
another subject), yes or no. The mechanical subject check against the writer's subject words is reported beside it.

**Bar (fixed now), both hosts together:** lesson sessions with a card ≥ 12 / 16; of cards written on lesson sessions,
judged faithful ≥ 90% and judged subject-free ≥ 90%; duplicate sessions with a card ≤ 1 / 8; no-lesson sessions with a
card ≤ 1 / 8. If it passes, the digest, the use records and `krouter_learn` become the default when the vault has
cards (`experience.DEFAULT_ON`); if not, they stay off.

**Known limits.** Sonnet wrote the sessions, is one of the two hosts, and judges Haiku's cards; Haiku is a weaker
judge of Sonnet's. Sixteen synthetic sessions. Whether a host calls the tool unprompted at the end of a real session
is still not measured.

### Log, set 19

| Date | Event |
|---|---|
| 2026-11-09 | Registered (`4fbb174`). |
| 2026-11-09 | **Run once.** Cards: Haiku 5.5 8, Sonnet 5.5 8; judges: Sonnet 5.5 for Haiku's, Haiku 5.5 for Sonnet's (agents reported `claude-sonnet-5-5`, `claude-haiku-5-5`). **Both hosts together: lesson sessions with a card 16 / 16 (bar ≥ 12); judged faithful 14 / 16 = 87.5% (bar ≥ 90%); judged subject-free 14 / 16 = 87.5% (bar ≥ 90%); duplicates written 0 / 8 (≤ 1); no-lesson sessions with a card 0 / 8 (≤ 1). Not passed**, by one card on each of the two counts. Haiku's cards: faithful 6 / 8, subject-free 8 / 8 (mechanical 7 / 8). Sonnet's: faithful 8 / 8, subject-free 6 / 8 (mechanical 8 / 8). The four judged failures: a result claiming two restructures where the session shows one; an action stating a step the session only suggested; two lessons keeping a subject term ("大件东西 / 运得进", "执行计划"). Set 19 is now development: the card instructions are revised on it, and a new set of held-out sessions is registered before the revised wording is checked on them. |
| 2026-11-09 | **Development iterations on set 19** (in-sample; each round: both hosts propose cards, the other host judges). Round 2: a host-named `subject` list, and the code refuses a lesson or title that uses one of its own subject words (`experience.names_subject`), returning the reason; action only for steps actually carried out; result only as the session shows. Hosts listed ordinary words as subject and 3 Sonnet calls were refused; since the MCP tool returns its reason to the agent, the bench now lets a refused call be rewritten once with that reason (`extract.py retry`). Faithful 13 / 16, subject-free 15 / 16. Round 3: one sentence each; a corrected figure or cause, the corrected one; reread before calling. Sonnet 9 / 9 and 9 / 9, but Haiku wrote cards on 2 no-lesson sessions. Round 4: record only when something did not work, a way out was tried and its outcome seen; drafting, polishing, formatting, comparing options do not count; when in doubt, do not. Faithful 15 / 15, subject-free 13 / 15 (one session, judged by both hosts as tied to its subject), duplicates 1 / 8. Round 5: a self-test, "would the lesson make sense word for word to someone fixing a bug, writing a report and cooking; if not, one level higher". **Both hosts: lesson sessions with a card 14 / 16, faithful 14 / 14, subject-free 14 / 14, duplicates 0 / 8, no-lesson 0 / 8: the bar met in-sample.** Wording frozen here, before set 20. |

## Set 20: set 19's check on new held-out sessions, with the wording revised on set 19 (registered 2026-11-09, before any host was run on it)

**Sessions.** 16, written by Sonnet 5.5 in a fresh subagent with set 19's instructions, plus "the assistant sometimes
suggests things the person does not end up doing"; same kinds and counts (8 lesson: 5 Chinese, 3 English; 4 duplicate;
4 none). Written while the wording was being revised, without seeing it; not read by the code's author (counts only).
`bench/transfer/set20_sessions.jsonl`, SHA-256 `56ad0b0c…8aabb780`.

**Run, judging and bar:** as set 19 (`extract.py --set 20`), with the frozen wording of set 19's round 5, and one
retry of a refused call with the tool's reason (`extract.py retry`), as an agent using the MCP tool would get. Bar,
both hosts together: lesson sessions with a card ≥ 12 / 16; judged faithful ≥ 90% and judged subject-free ≥ 90% of cards
on lesson sessions; duplicates ≤ 1 / 8; no-lesson ≤ 1 / 8. Run once. If it passes, `experience.DEFAULT_ON` is set.

**Known limits:** as set 19 (Sonnet wrote the sessions, is a host and judges Haiku's cards).

### Log, set 20

| Date | Event |
|---|---|
| 2026-11-09 | Registered (`79bafe3`). |
| 2026-11-09 | **Run once** (frozen wording; agents reported `claude-haiku-5-5`, `claude-sonnet-5-5`; 2 of Sonnet's calls refused for naming the subject and rewritten once with the tool's reason, none of Haiku's). **Both hosts together: lesson sessions with a card 16 / 16 (bar ≥ 12); of 18 cards on lesson sessions, judged faithful 16 = 88.9% (bar ≥ 90%), judged subject-free 17 = 94.4% (≥ 90%); duplicates written 1 / 8 (≤ 1); no-lesson sessions with a card 0 / 8 (≤ 1). Not passed**, by one card on faithfulness. Haiku's cards: faithful 7 / 9, subject-free 9 / 9, one duplicate written. Sonnet's: faithful 9 / 9, subject-free 8 / 9. Both unfaithful cards are Haiku's and misstate a figure (a result claimed for all batches where the session confirmed 20 of 24; a gap given as height where the session gave width); the subject leak is a Sonnet title naming "图纸". `experience.DEFAULT_ON` stays off. The sessions are now spent. |

## Set 21: set 20's check again, with numbers held to the session (registered 2026-11-10, before any host was run on it)

**Why.** Set 20 missed by one card on faithfulness, and both misses were figures. One change since, made without a
development run to save calls (said as such): every number left in a card must be in the session, mechanically
(`experience.unsupported_figures`); for a card the host writes, the session snippets it gives in `quotes`, since the
MCP server does not see the session; for the model lane, the excerpt. A card with an unquoted number is sent back with
the numbers named, and the instructions now say to leave numbers out of action and result unless the lesson needs
them. Offline, both of set 20's unfaithful cards would have been sent back.

**Sessions.** 16 new ones by Sonnet 5.5 in a fresh subagent with set 20's instructions, plus "numbers appear naturally,
and some are corrected later"; same kinds and counts. Counts only read. `bench/transfer/set21_sessions.jsonl`, SHA-256
`d1d77769…3d52744`.

**Run, judging and bar:** exactly as set 20 (one retry of a refused call with the tool's reason; the other host
judges; lesson sessions with a card ≥ 12 / 16, judged faithful ≥ 90%, judged subject-free ≥ 90%, duplicates ≤ 1 / 8,
no-lesson ≤ 1 / 8). Run once. If it passes, `experience.DEFAULT_ON` is set.

### Log, set 21

| Date | Event |
|---|---|
| 2026-11-10 | Registered (`0eea66c`). |
| 2026-11-10 | **Run once** (agents reported `claude-haiku-5-5`, `claude-sonnet-5-5`; 1 of Sonnet's calls refused and rewritten once, none of Haiku's). **Both hosts together: lesson sessions with a card 15 / 16 (bar ≥ 12); of 15 cards on lesson sessions, judged faithful 15 = 100% (≥ 90%), judged subject-free 15 = 100% (≥ 90%); no-lesson sessions with a card 0 / 8 (≤ 1); duplicates written 2 / 8 (bar ≤ 1). Not passed**, on duplicates. Both duplicate cards are on one session (N09), written as a duplicate of C06 ("before an action you cannot undo, keep a copy you can restore"); both hosts drew a different lesson from it ("delete what a tool keeps a record of through that tool, so the record and the files stay in step"), and the code's same-lesson check, lexical, did not match them to C06. Read afterwards, not part of the score: whether that session's lesson is C06's is arguable. `experience.DEFAULT_ON` stays off. |

## Set 23: a repeated lesson is recorded on the old card, not written again (registered 2026-11-10, before any host was run on it)

**Why.** Set 21 missed only on duplicates (2 of 8 sessions got a new card), both on one session whose duplicate label
was arguable. Changes since, made without a development run (calls are short): when the digest already has the lesson,
the host names that line's id (`same_as`) and the old card gets an `again` record, which counts in the digest's order
like an adoption; the code's lexical same-lesson check records `again` too, as a fallback; nightly lists near-duplicate
cards to merge by hand.

**Sessions.** 16 new ones by Sonnet 5.5 in a fresh subagent, same kinds and counts as set 21; for each duplicate the
writer also says which stored lesson it repeats and why (`dup_reason`), and was asked to make each duplicate teach that
lesson and nothing else worth recording. 7 to 8 turns each, shorter than the 8 to 14 asked for. Counts only read.
`bench/transfer/set23_sessions.jsonl`, SHA-256 `2d7d4c15…c65c2ef`.

**Duplicate labels reviewed, rule fixed now.** Haiku 5.5, not the writer, reads each duplicate session with the stored
lesson and the writer's reason and answers whether the session's lesson is the same (yes / no / unclear;
`extract.py review`). A duplicate session the reviewer does not answer "yes" for is reported on its own and left out of
the duplicates denominator; nothing else is left out.

**Run, judging and bar:** as set 21 (one retry of a refused call; the other host judges faithfulness and
subject-freedom; lesson sessions with a card ≥ 12 / 16, judged faithful ≥ 90%, judged subject-free ≥ 90%, no-lesson
sessions with a card ≤ 1 / 8), and duplicates: at most 1 new card over the confirmed duplicate sessions of both hosts.
Also reported: how many duplicates were linked to the right card with `same_as`. Run once. If it passes,
`experience.DEFAULT_ON` is set.

### Log, set 23

| Date | Event |
|---|---|
| 2026-11-10 | Registered (`8ea41c3`). |
| 2026-11-10 | **Review of the duplicate labels** (Haiku 5.5): all 4 confirmed ("yes"); none left out. |
| 2026-11-10 | **Run once** (agents reported `claude-haiku-5-5`, `claude-sonnet-5-5`; 2 of Haiku's calls refused, one for an unquoted number and one for naming the subject, and rewritten once). **Both hosts together: lesson sessions with a card 13 / 16 (bar ≥ 12); of 13 cards on lesson sessions, judged faithful 12 = 92.3% (≥ 90%), judged subject-free 12 = 92.3% (≥ 90%); new cards on confirmed duplicate sessions 0 of 8 (≤ 1), all 8 linked to the right card with `same_as`; no-lesson sessions with a card 0 / 8 (≤ 1). Passed.** Haiku: 6 / 8 lesson sessions, faithful 6 / 6, subject-free 5 / 6 (a lesson naming "font size"). Sonnet: 7 / 8, faithful 6 / 7 (one card counting one mismatch as two and generalising from one later round), subject-free 7 / 7. As registered, `experience.DEFAULT_ON` is set: the digest, use records and `krouter_learn` on by default when the vault has cards. |

## Set 24: does experience grow into a skill where it should, and only there? (registered 2026-11-10, before any scenario was written or any host was run)

**Why.** The nightly run now drafts skills from experience cards (`skills.py`): one card borne out repeatedly
(adopted + seen again ≥ `DRAFT_EVIDENCE` = 3), or two or more cards the drafting model judges to be the same kind of
situation. This set asks whether a draft appears where it should, says only what its cards say, and does not appear
where it should not.

**Scenarios.** 32, written by Sonnet 5.5 (claude-sonnet-5-5) in a fresh Claude Code subagent that sees neither the
drafting prompt nor any code, only a description of what a card holds and of the four kinds: 8 *single* (one card
borne out ≥ 3 times among unrelated ones), 8 *group* (two or three cards on the same kind of situation in different
subjects, low counts, among unrelated ones), 8 *none* (unrelated cards, counts ≤ 2), 8 *trap* (cards sharing a
subject, a tool or a word but not the situation, counts ≤ 2). Each kind 6 Chinese and 2 English, 5 to 7 cards each;
the writer names the group that should become a skill (none for *none* and *trap*). Not edited. Split by kind and
language at seed 2026112424 (`bench/skills/run.py split`): `bench/skills/set24_dev.jsonl` (16), where the drafting
wording may be revised, and `bench/skills/set24_heldout.jsonl.gz` (16), sealed, run once per host. Card ids in the
prompts are opaque hashes.

**Run.** `run.py prepare24`: the prompt is exactly what `skills.draft_step` sends through the host lane. Hosts Haiku
5.5 and Sonnet 5.5, Claude Code subagents on the named model, one agent per host and split, answer each prompt as if
it were the only one; the reply goes through `skills.parse`, the code's own checks, as the nightly run does. No key,
no stored Claude login.

**Scored.** Mechanically: on *single* and *group*, a *right draft* = a draft whose cards are within the named group
(and at least two of them when the group has two or more); *wrong-card drafts* = drafts that take a card outside the
named group; on *none* and *trap*, any draft that passes the code. Judged: every right draft is read by the other host
model (Haiku's by Sonnet, Sonnet's by Haiku) with the cards it rests on: faithful (every step supported by the cards'
actions, results and lessons) and subject-free (name and "when to use"), yes or no.

**Bar (fixed now), both hosts together on held-out:** right drafts on *single* + *group* ≥ 13 / 16; judged faithful
≥ 90% and judged subject-free ≥ 90% of right drafts; scenarios of *none* + *trap* with a draft ≤ 2 / 16; wrong-card
drafts ≤ 2.

**Known limits.** The writer writes cards directly (the cards a host writes were measured in sets 17–23); 32
scenarios; Sonnet writes them, is a host and judges Haiku's drafts; a real vault has more cards, written over months.

## Set 25: does the host fetch and follow a skill when it fits, and keep quiet when it does not? (registered 2026-11-10, before any skill or case was written or any host was run)

**Skills and cases.** Written by Sonnet 5.5 in a fresh subagent (another one than set 24's), which sees neither the
digest wording nor any code: 6 skills (name, "when to use", 3 to 5 steps; 4 active, 2 drafts), each on its own kind of
situation, and 24 user messages: 12 *applicable* (two per skill, a subject other than the one the skill's wording
suggests) and 12 *quiet* (6 sharing a word or a subject with a skill but not its situation, 6 unrelated). Chinese.
Skill ids are opaque. Split at seed 2026112425 by kind: `set25_dev.jsonl` (12) and `set25_heldout.jsonl.gz` (12).

**Run.** The vault is the Chinese template with set 13's 14 cards and the 6 skills. Phase 1: the host gets the
session-start context as the hook builds it (the experience digest, then `skills.digest`), `krouter_skill`'s
description as the MCP server builds it, and the message; it either writes `CALL krouter_skill {"id": …}` or starts
its reply. Phase 2, only where it called: the same context, the tool's answer (`skills.show`), and it replies. Hosts
Haiku 5.5 and Sonnet 5.5 as in set 24.

**Scored.** Mechanically: applicable cases where the right skill was fetched; where another was fetched; quiet cases
where any skill was fetched or a skill id cited. Judged: on each applicable case with the right skill fetched, the
other host model reads message, skill and reply: does the reply follow the skill's steps (yes / no)?

**Bar (fixed now), both hosts together on held-out:** right skill fetched ≥ 10 / 12; judged as following ≥ 90% of
those; wrong skill fetched ≤ 1; quiet cases with a skill fetched or cited ≤ 1 / 12.

**If sets 24 and 25 both pass,** `skills.DEFAULT_ON` is set (skills in the digest, `krouter_skill`, the nightly
step). If either fails, skills stay off by default (`KROUTER_SKILLS=1` turns them on) and the docs say so.

**Known limits.** One-shot prompts with a bench note, not a live session; the case writer saw the skills; Chinese
only; the tool call is simulated by a line the host writes, not a real MCP call.

## Set 26: is a skill recorded as adopted only when the user says so, and what do the promotion and withdrawal counts become? (registered 2026-11-10, before any item was written)

**Items.** 40, written by Sonnet 5.5 in set 25's writer subagent (after set 25's material): a user message, the
assistant's reply following a skill (with `{id}` where the reply cites it), and the user's next message: 10 *adopt*
(says it was followed or worked), 10 *reject*, 10 *ignore* (moves on), 10 *unclear* (neither). 30 Chinese, 10 English.
Split at seed 2026112426 by kind and language: `set26_dev.jsonl` (20), `set26_heldout.jsonl.gz` (20).

**Scored mechanically** (`run.py score26`) by `experience.uses_in`, the code that records card and skill use, not
tuned here: p_true = adopt items recorded `adopted`; p_false = other items recorded `adopted`.

**Thresholds, by a rule fixed now, on development only** (`run.py thresholds`): over W ∈ {4, 5, 6, 8, 10} and k ∈
{1, 2, 3}, the smallest W, then the smallest k, such that a draft that never fits is promoted before withdrawal with
probability ≤ 5% (Binomial(W, p_false) ≥ k, p_false taken as at least 2%) and one that always fits is promoted within W
offers with probability ≥ 90% (Binomial(W, p_true) ≥ k). k becomes `PROMOTE_ADOPTED`, W `WITHDRAW_OFFERED`;
`SINK_OFFERED` is half of W, rounded up; `WITHDRAW_DAYS` stays 45, a policy, not measured. **Held-out:** p_true and
p_false reported once; bar p_false ≤ 1 / 15. Set 26 does not gate the default.

**Known limits.** It assumes every offer of a fitting skill could be adopted, and treats offers as independent; real
users answer in their own ways.

### Log, sets 24–26

| Date | Event |
|---|---|
| 2026-11-10 | Registered (`643db15`). |
| 2026-11-10 | **Material written** by two fresh Sonnet 5.5 subagents (one for set 24, one for sets 25 and 26), counts checked mechanically, contents not read by the code's author except set 26's development half (below). Set 24: 32 scenarios, 8 per kind, 6 Chinese and 2 English each; split 16 / 16 (4 per kind each side); held-out text SHA-256 `f8d39268…bc20430`. Set 25: 6 skills (4 active, 2 drafts; `bench/skills/set25_skills.json`, SHA-256 `a093d11d…47905d2`, ids opaque) and 24 messages (12 applicable, 6 word traps, 6 unrelated); split 12 / 12; held-out SHA-256 `7625411f…e79406`. Set 26: 40 items as registered; **split 22 / 18, not 20 / 20**: the odd-sized groups (7 Chinese *ignore* and *unclear*, 3 English of those two kinds) are split by a coin in `run.py split`, which the registration did not foresee; held-out SHA-256 `ca1edc8c…f3fc49b`, 13 negatives, so the bar p_false ≤ 1 / 15 means none. |
| 2026-11-10 | **Set 26, development, and a deviation from the registration.** As registered, `experience.uses_in` unchanged: p_true 1 / 5, p_false 0 / 17. With p_true 0.2 the threshold rule has no feasible pair (W = 10, k = 1 promotes a fitting draft with probability 0.89). The four missed adoptions report the result in plain words ("已经把三个问题发给他了", "重新输了新密码就好了", "真的不闪了", "the fan is quiet again"). **Deviation, before any held-out half was opened:** the adoption cues were extended on the development half (`experience.ADOPT_MORE`: saying it was done or the problem is gone; `experience.UNSURE`: a partly done or unsure reply is not an adoption; four more refusal phrases). This is shared code: card adoption records use it too. In-sample: p_true 5 / 5, p_false 0 / 17. The rule then picks **W = 4, k = 2**: `PROMOTE_ADOPTED` = 2, `WITHDRAW_OFFERED` = 4, `SINK_OFFERED` = 2 (useless draft promoted ≤ 0.23% with p_false taken as 2%). Set 26's held-out half is now a check of the extended cues, run once. |
| 2026-11-10 | **Set 26, held-out, run once** (cues and thresholds as committed in `d7ccf16`): **p_true 4 / 5, p_false 0 / 13: passed** (bar: none of the 13). With p_true 0.8, W = 4, k = 2 still promotes a fitting draft with probability 0.97. |
| 2026-11-10 | **Set 25, development, first and only wording** (the digest's skills part and `krouter_skill`'s description as committed; agents reported `claude-haiku-5-5`, `claude-sonnet-5-5`). Both hosts: right skill fetched 6 / 6, judged as following 6 / 6 (by the other host), wrong skill 0, quiet cases with a skill 0 / 6, quiet cases citing a card 0. Wording not revised: frozen. |
| 2026-11-10 | **Set 24, development, round 1** (drafting wording as first committed). Right drafts: Haiku 8 / 8, Sonnet 8 / 8; wrong-card drafts 0; drafts on *none* / *trap*: Haiku 1 / 8, Sonnet 0 / 8. Judged (other host): faithful Haiku 7 / 8, Sonnet 8 / 8; **subject-free Haiku 4 / 8, Sonnet 6 / 8 (10 / 16, 62%)**: names and "when to use" taken from the card's situation ("合并数据", "恢复训练", "a connection with under 90 minutes"). **Round 2:** name and "when to use" from the lessons, not the situations, with general-word examples and the set 19 self-test (bug / report / cooking); steps in general words. Right drafts 8 / 8 and 8 / 8; drafts on *none* / *trap*: Haiku 2 / 8 (one merging "slow practice with a metronome" and "switch food over seven days" as "do big changes in stages"), Sonnet 0 / 8. Not judged. **Round 3:** lessons that only share broad advice ("go gradually", "keep a fallback", "ask first") are not to be merged; the problem must be of one kind and the step the same. |
| 2026-11-10 | **Set 24, development, round 3.** Right drafts Haiku 7 / 8, Sonnet 7 / 8 (both lost the same English *group* draft to the code's check that steps share words with the cards: both wrote it in Chinese, from English cards); drafts on *none* / *trap* Haiku 1 / 8, Sonnet 0 / 8; wrong-card drafts 0. Judged: faithful Haiku 5 / 7, Sonnet 7 / 7 (12 / 14, 86%); subject-free 7 / 7 and 7 / 7 (14 / 14). Haiku's two unfaithful drafts pad one-step lessons with steps the cards do not have ("find the source", "confirm it is off"). Changes after round 3: the prompt names the language to write in (made without its own development run, said as such; the subagents, like a host CLI on the author's machine, carry an instruction to answer in Chinese); 1 to 6 steps, each found in the cards, "if the cards give one step, write one step, do not pad" (the code now takes 1 to 7 steps). Round 4 runs that wording. |
| 2026-11-10 | **Set 25, held-out, phase 1, run once** (agents reported `claude-haiku-5-5`, `claude-sonnet-5-5`): right skill fetched Haiku 6 / 6, Sonnet 6 / 6; wrong skill 0; quiet cases with a skill fetched or cited 0 / 6 and 0 / 6. |
| 2026-11-10 | **Set 24, development, round 4** (wording of `ea3a565`). Right drafts Haiku 8 / 8, Sonnet 8 / 8; wrong-card drafts 0; drafts on *none* / *trap* Haiku 1 / 8, Sonnet 0 / 8. **Drafting wording frozen here**, before round 4's drafts are judged and before any held-out scenario is run; held-out drafting runs in the same agents as round 4's judging. |
| 2026-11-10 | **Set 24, development, round 4 judged** (after the freeze): faithful Haiku 8 / 8, Sonnet 8 / 8; subject-free 8 / 8 and 8 / 8. |
| 2026-11-10 | **Set 25, held-out, run once, complete** (phase 2 and judging; agents reported `claude-haiku-5-5`, `claude-sonnet-5-5`). **Both hosts together: right skill fetched 12 / 12 (bar ≥ 10); judged as following 12 / 12 = 100% (≥ 90%); wrong skill fetched 0 (≤ 1); quiet cases with a skill fetched or cited 0 / 12 (≤ 1). Passed.** No quiet case cited an experience card either. |
| 2026-11-10 | **Set 24, held-out, drafting run once** (frozen wording of `88e6f51`; agents reported `claude-haiku-5-5`, `claude-sonnet-5-5`). Mechanical, both hosts together: **right drafts 16 / 16 (bar ≥ 13); drafts on *none* / *trap* 0 / 16 (≤ 2); wrong-card drafts 2 (≤ 2)**, one per host, each a second draft beside a right one. Found while scoring, before any held-out verdict was read: the scorer sent every draft of a scenario with a right draft to the judge, where the registration says right drafts; fixed to count right drafts only (a wrong-card draft is still judged, not counted). |
| 2026-11-10 | **Set 24, held-out, judged** (Haiku's drafts by Sonnet, Sonnet's by Haiku; agents reported `claude-sonnet-5-5`, `claude-haiku-5-5`). **Both hosts together: right drafts 16 / 16 (bar ≥ 13); of 16 right drafts, judged faithful 16 = 100% (≥ 90%), judged subject-free 16 = 100% (≥ 90%); drafts on *none* / *trap* 0 / 16 (≤ 2); wrong-card drafts 2 (≤ 2). Passed.** With set 25 passed, as registered, `skills.DEFAULT_ON` is set. Model calls for sets 24–26: 3 writer agents, 20 host and judge agents (about 330 prompts). Limits as registered, and: the wording was revised three times on 16 development scenarios; Haiku is the weaker judge of Sonnet's drafts; the wrong-card bar was met exactly. |
## Set 32: mention it and it comes to mind — does the prompt hook bring the right page, and only then? (registered 2026-11-10, before any case was split or run)

**Why.** Until 2.0 the lock and the trigger words ran only when the agent chose to call `krouter_ask`: whether the
vault "came to mind" depended on the agent. `session_hook.py prompt` now looks every message up (`recollect.py`: no
model call) and hands the agent at most two pages, marked as memory. This set asks whether it brings the right page
when a message mentions something the vault knows, brings the newer page when the rule changed, and stays silent
otherwise. Silence matters most: this runs on every message.

**Vault.** `bench/memory_honesty/vault3` (frozen, 110 pages, English and Chinese, 18 old/new page pairs), copied to a
temporary folder at run time with `bench/subconscious/overlay/` laid into `90 系统文件/`: an alias table of 63 rows
(some rows still point at a page that was later superseded, as a table nobody updated would; three topics have a row
for both pages) and two trigger sidecars (20 generated lines, 7 learned questions). The overlay was written before any
case existed, by the session that writes the matcher.

**Cases.** 120, written by Sonnet 5.5 in a fresh Claude Code subagent that read one input file (every Handbook and
团队手册 page with its status and text, and the alias names of the pages that have them) and nothing else: not the
trigger sidecars, not the anchors, not any code. Told to write the way people write to a coding assistant mid-work
and neither to use nor to avoid the names. Per language (zh, en): 24 *recall* (a message that mentions something one
active page covers; the expected page), 24 *quiet* (6 each: unrelated; a name meant in another sense; a name or key
word as an everyday word in a longer sentence; a name only inside pasted code, a log, a diff or command output, at
least half unfenced), 12 *changed* (a topic with an old and a new page; the new page expected, the old one recorded).
Not edited. Split at seed 20261132, stratified by language, kind and subkind, half to each side:
`bench/subconscious/dev.jsonl` (60) is where the matcher, the paste filter and the routes may be tuned;
`bench/subconscious/heldout.jsonl.gz` (60) is sealed and run once. The writer's raw file stays out of the repository.

**System.** `recollect.recollect()` as the hook calls it, with the routes chosen on development. Choice rule, fixed
now: maximise recalled (recall + changed cases bringing the expected page) − 3 × (quiet cases bringing anything +
wrong pages brought on recall and changed cases), ties to fewer routes. Full-text recall (`recall`, `high` confidence
only) may enter the default only if on development it adds no quiet delivery and no wrong page.

**Scored mechanically** (`bench/subconscious/run.py`): *brought* = the pages handed over (at most two). Recall case:
right if the expected page is brought; any other page brought is a wrong page. Changed case: right if the new page is
brought; the old page brought as a page is a wrong page *and* an old-page delivery (naming the old page in the
"an earlier page said otherwise" note is expected, not a delivery). Quiet case: any page brought counts against it.

**Pass line (fixed now), held-out, both languages together:** quiet cases bringing anything ≤ 1 / 24; wrong pages on
recall and changed cases ≤ 1; old-page deliveries 0; changed cases bringing the new page ≥ 6 / 12; recall cases
bringing the right page ≥ 12 / 24, and ≥ 5 / 12 in each language. All five must hold for the hook to be on by
default (together with set 33's line below); otherwise it ships off (`KROUTER_RECALL_PROMPT=1` to try it) and the
numbers are reported as they are.

**Known limits, said with any number.** One writer model; the writer saw the alias names (it was told neither to use
nor to avoid them, so recall depends on how often people say a page's name); the matcher's author wrote the alias
table and triggers, knowing the pages; vault3 is small; the cases are single messages, not conversations.

### Log, set 32

| Date | Event |
|---|---|
| 2026-11-10 | Registered (`b5254b2`); split committed (`676e829`), held-out sealed (SHA-256 of the text `5ba6f5ed…fbe649c6`). |
| 2026-11-10 | **Development.** First run, alias and trigger routes only, before any tuning: recall 2 / 24, changed 4 / 12, **quiet cases bringing something 8 / 24** (other sense 2, everyday word 3, pasted 3), wrong pages 0. Full-text recall at `high` confidence added nothing: on vault3 no page is in the rule tier, so `high` never happens. Changes, each justified on development only: (1) the paste filter learned three formats it missed (docker compose log prefixes `name_1  \| …`, merge-conflict markers, indented or diffed YAML): pasted 3 → 0; (2) a second key for a name match: recall over the whole message must not refuse it, or its top page must match at least 4 of the message's content words (every loud name match had recall refusing with ≤ 3 matched words; every right one had recall answering or ≥ 4 words): quiet 5 → 0, no right hit lost; (3) a `recall` route at `medium` or `high` confidence with the top page at least 2.5 × the second, never a log page. Sweep of the second key (3, 4, 5 words) × margin (1.3–2.5) × confidence set: best choice score 10 at 4 words for every margin ≥ 1.75; ties went to the strictest (2.5, medium/high). **Frozen** (`b6cfb53`): routes alias, trigger, recall; development **recall 5 / 24 (zh 2, en 3), changed 5 / 12, quiet 0 / 24, wrong pages 0, old-page deliveries 0.** The trigger sidecars brought nothing right or wrong on development. Reading the misses: most recall cases share no word with their page ("Dana's prod DB login vanished" against "access unused for 60 days is removed"); a lexical lookup cannot bridge them. |
| 2026-11-10 | **Held-out, run once** (routes and thresholds as frozen; the first invocation stopped on a missing output folder while saving, before printing anything, and was re-run unchanged; the lookup is deterministic). **Quiet cases bringing something 1 / 24** (one name in another sense: 「iOS 里相机的权限申请弹窗」 brought 权限申请), **wrong pages 0, old-page deliveries 0, changed 4 / 12, recall 7 / 24 (zh 6 / 12, en 1 / 12).** Against the line: quiet ≤ 1 holds, wrong ≤ 1 holds, old 0 holds; changed ≥ 6 fails; recall ≥ 12 and ≥ 5 per language fails (English). **Fails. As registered, the prompt hook ships off by default** (`KROUTER_RECALL_PROMPT=1` turns it on). What it shows: on every message it stays quiet as required (1 of 24 over everything thrown at it, 0 of 12 pasted), and when it speaks it is right (11 pages brought on recall and changed cases, all the expected page, none old); what it cannot do is notice a mention said in other words, which is most mentions people make. |

## Set 33: does the host use what the hook brought, and ignore what does not fit? (registered 2026-11-10, before any host was run)

**Why.** Set 32 measures what the hook hands over. This set measures what the host model does with it: whether it
uses a page that was brought and says where it came from, and whether a page that does not fit the message pulls it
off course.

**Cases.** From set 32's held-out file, after its single run: up to 16 recall and changed cases (8 per language, the
first in file order) on which the hook brought the expected page. Each message is given to the host three ways, as
the prompt hook would give it: (A) with the hook's own memory note; (B) with the memory note the hook gave a
different case of the same language (the next one in the list, wrapping), so a page that does not fit; (C) with no
note. The wording of the note is the one shipped in `recollect.render` at registration; it is not revised on this set.

**Hosts.** Haiku 5.5 and Sonnet 5.5, run as sets 12 and 15 ran theirs: a Claude Code subagent on the named model
answers a batch of prompts, each as the only one, writing only the start of the reply (at most five sentences, no
tools). No API key and no stored login are used.

**Scored mechanically.** Each case lists one or two key terms of the expected page's rule (a number, a product name),
taken from the page before any host run. (A) *used* = the reply contains a key term; *cited* = it names the page
(its path or file name). (B) *pulled* = the reply contains a key term or the name of the page that was brought but
does not fit. (C) the same key-term check, reported to show what the host knows without the note.

**Pass line (fixed now), per host:** (A) used ≥ 12 / 16 and cited ≥ 8 / 16; (B) pulled ≤ 2 / 16. Both hosts must
pass for the hook to be on by default (with set 32). When nothing is brought the hook prints nothing, so the host's
input is byte for byte what it was before 2.0; that is checked by the hook tests, not by a host run.

### Log, set 33

| Date | Event |
|---|---|
| 2026-11-10 | **Run** (`bench/subconscious/host.py`; agents reported `claude-haiku-5-5` and `claude-sonnet-5-5`; 33 prompts each in one batch, opaque ids, shuffled). Only **11** of set 32's held-out recall and changed cases had the right page brought (8 zh, 3 en), so 11 cases, not the 16 the line was written for. **Haiku 5.5: (A) used 10 / 11, cited 11 / 11; (B) pulled 0 / 11; (C) key term without the note 3 / 11. Sonnet 5.5: (A) 10 / 11, 11 / 11; (B) 0 / 11; (C) 1 / 11.** In proportion both pass (10 / 11 ≥ 12 / 16, 11 / 11 ≥ 8 / 16, 0 ≤ 2); in the registered counts "used ≥ 12" cannot be met with 11 cases. Read after scoring: the one (A) miss per host is the same case (third-party scripts), and both replies state the page's rule in full, in Chinese (the batch was mostly Chinese and the agents answered this English message in Chinese), so the English key terms did not match: in substance 11 / 11. Replies in `bench/subconscious/results/set33/`. Limits: 11 cases, all ones the hook got right; one batch per host; short replies. |

## Set 34: does it reach the app, and is it fast enough to run on every message? (registered 2026-11-10, before any timing run)

**Delivery.** For each app, whether the memory note the hook prints reaches the model: Claude Code
(`UserPromptSubmit`, `hookSpecificOutput.additionalContext`), Codex (`UserPromptSubmit`, the same JSON, which Codex's
hooks documentation says is added as developer context) and Cursor (`beforeSubmitPrompt`, whose documented output is
only `continue` / `user_message`: no context can be added). Checked with the real Codex CLI in a throwaway
`CODEX_HOME`; where the login does not carry over, against a local mock of the Responses API, and the report says so.

**Speed.** The whole hook process (`python3 session_hook.py prompt`, from start to exit, as the app runs it) on a
message that matches and one that does not, 200 runs each, on vault3 with the overlay and on a 10,000-page vault
(`bench/scale/gen.py 10000`, with an alias table of 2,000 rows and 10,000 trigger lines added). Cold = the first run
after the page cache of the vault folder is not warmed by a previous run (a fresh copy of the vault); warm = the rest.
Reported: p50 and p95. **Line (fixed now):** warm p95 ≤ 250 ms on both vaults; if not, the lookup moves to a cached
index or a resident process before the default is decided.

### Log, set 34

| Date | Event |
|---|---|
| 2026-11-10 | **Delivery.** Codex: codex-cli 0.155.0-alpha.9.2 (the app's own binary, not the shell wrapper on this machine), throwaway `CODEX_HOME` and `HOME`, a local mock of the Responses API (no login carries over to a throwaway home, so no real model was called), hooks run with `--dangerously-bypass-hook-trust`: for 「新项目的仓库我就建在公司自己的 GitLab 上吧」 the hook ran and the memory note (代码托管.md, with the earlier page named) arrived in the request as a **developer message right after the user message**; for a message naming nothing, no note was sent. Claude Code: output format per its hooks documentation (`hookSpecificOutput.additionalContext` on `UserPromptSubmit`) and the hook tests; not run inside the Claude Code app here. Cursor: not available (`beforeSubmitPrompt` can only allow or block); the hook does not run the lookup there. |
| 2026-11-10 | **Speed** (`bench/subconscious/speed.py`, results in `bench/subconscious/results/set34-speed.txt`; Apple laptop shared with other sessions, load average 5–6). A first run set `PYTHONPYCACHEPREFIX` for cold starts, which turned out to add about 90 ms to every run (the same hook: 62 → 154 ms) and was discarded; cold now means the scripts' bytecode cache deleted and the phrase table not yet compiled. Whole hook process, routes as frozen (alias, trigger, recall), 200 warm and 20 cold runs each. **vault3 + overlay: warm p50 / p95 87 / 124 ms (a message that names a page) and 83 / 102 ms (one that names nothing); cold 91 / 126 and 94 / 121. 10,000 pages, 2,000 alias rows, 10,000 trigger lines: warm 126 / 144 and 116 / 139; cold 221 / 246 and 214 / 327.** Alias and trigger routes only: 10,000 pages warm 129 / 149 and 72 / 82. The hook with the lookup off: 62 / 73 ms on either vault. **Line (warm p95 ≤ 250 ms on both vaults): holds.** Two changes made before this run, on development timings only: the phrase table is compiled once and kept next to the recall index (`marshal`, 9 ms to load 26,000 phrases instead of re-reading the files: the JSON form took 38 ms), and related-page titles are resolved without walking the vault. Set 32's held-out pages brought were checked to be identical before and after each change (compared, not re-scored). |

## Set 35: the subconscious as a whole — the prompt hook, then the host reading a standing index (registered 2026-11-10, before any case existed)

**Why.** Set 32: the prompt hook alone stays quiet but brings the right page for only 7 of 24 mentions, because people
mostly mention a thing in other words. Set 15 met the same wall with experience cards (0 / 14 by words) and got past
it by putting the cards in front of the host (14 / 14). Here the session-start hook hands the host a standing index
(`compile_subconscious.standing_index`: one line per live topic of the alias table, name / one other name / what was
decided / page; replaced pages counted under the page that replaced them; rule pages first, then most recently used or
updated; at most 60 lines and 5,400 characters; then one usage line that says how to fetch a page with `krouter_ask`,
the route command or the file path, since some hosts show the model no tool list). A message then counts as
remembered when either layer brings the right page.

**Vault and hook.** Set 32's: vault3 with `bench/subconscious/overlay/`, the prompt hook exactly as frozen there
(`b6cfb53`, routes alias, trigger, recall). The index on it: 60 topics, all listed.

**Cases.** 120 new messages, written by Sonnet 5.5 in a fresh Claude Code subagent that reads the same one input file
as set 32's writer (pages, statuses, alias names) and nothing else; it has not seen set 32's cases, the index, its
wording or any code. Per language (zh, en): 24 *recall*, of which at least 16 must not use any of the page's listed
names (the writer marks each `named`); 24 *quiet* (6 each: unrelated; a name in another sense; a name or key word as
an everyday word; a name only inside pasted code or logs); 12 *changed* (the newer page expected). Not edited. Split
at seed 20261135, stratified by language, kind, subkind and `named`: `bench/subconscious/set35_dev.jsonl` (60), where
the index's usage line may be revised at most once; `bench/subconscious/set35_heldout.jsonl.gz` (60), run once per host.

**Hosts.** Haiku 5.5 and Sonnet 5.5, as Claude Code subagents (`model: haiku` / `sonnet`), one agent per host and
split. The batch file gives the session-start context once at the top (exactly the index the hook would print) and
then each message as a separate session, with the prompt hook's note above it when the hook brought something. The
host writes the start of its reply; a fetch it would make is written as a first line `CALL krouter_ask: …`,
`CALL shell: …` or `CALL read: …` instead of being run. No API key, no stored login.

**Scored mechanically** (`bench/subconscious/both.py`). A fetch is resolved by running it for real on the bench vault
(`route_knowledge.py search` with the question or the command's query: the lock's page, else recall's first page when
recall answers; a `read` path as written). The host *recalls* a page when it fetches it or names its path in the reply.
Recall or changed case **right** when the hook brought the expected page or the host recalled it; **wrong page** when
the hook brought, or the host fetched or named, any other page; **old-page delivery** when the superseded page was
brought, fetched or named. Quiet case **loud** when the hook brought anything or the host fetched anything or named any
page. Reported per host and language, with what each layer contributed (hook right; host right where the hook was not).

**Pass line (fixed now), held-out, each host:** recall cases right ≥ 18 / 24 and ≥ 8 / 12 in each language; changed
cases right ≥ 9 / 12; quiet cases loud ≤ 2 / 24; wrong pages ≤ 2; old-page deliveries 0. Both hosts must pass for the
prompt hook and the standing index to be on by default.

**Scale check (development only, not a pass condition).** (a) Crowded: the index with 240 distractor topics added
(synthetic pages with alias rows on subjects the cases never touch), all 300 lines listed regardless of the budget, to
see whether a long list makes the host fetch wrongly or speak on quiet cases; both hosts. (b) At the shipped budget
with the same 240 distractors dated newer than the real pages: how many real topics stay listed, and the hook-plus-host
numbers with Haiku 5.5.

**Known limits, said with any number.** One writer model, also one of the hosts; the writer saw the alias names;
batches show the host every case of a split at once; the host is told to write fetches instead of making them, so a
real session's tool use may differ; token counts are the registered estimate (one per CJK character, one per three
other characters).

### Log, set 35

| Date | Event |
|---|---|
| 2026-11-10 | Registered (`77aeb94`). Cases written (Sonnet 5.5): recall named / not named zh 7 / 17, en 6 / 18; changed named zh 1, en 3. Split: the first stratified split left odd-sized strata unbalanced (held-out 23 recall, 14 changed), so before any case was read it was redone with the odd case of each language-and-kind alternating between the sides: 60 / 60, each side 12 recall, 12 quiet and 6 changed per language. Held-out sealed, SHA-256 of the text `945ac5f6…f94a6b1`. |
| 2026-11-10 | **Development, first wording** (agents reported `claude-haiku-5-5`, `claude-sonnet-5-5`). Sonnet 5.5: recall 23 / 24, changed 12 / 12, quiet loud 2 / 24 (both by the frozen hook: 「笔记本（记事那种纸质的）」, and a pasted `FAIL test_sms.py … 验证码短信` line the hook's paste filter does not treat as pasted), wrong pages 3 (a neighbouring page fetched as well), old 0. Haiku 5.5, as first scored: recall 22 / 24, changed 12 / 12, quiet loud 6 / 24, wrong 5. **Scoring clarified before held-out:** of Haiku's 6, three were `CALL read: package.json`, `README.md` and a Java file the user mentioned: ordinary work, not a fetch from the memory. A quiet case is now loud on a *memory* fetch (`krouter_ask`, the route command, reading a file inside the vault) or a named vault page, which is what the registration meant by "fetched" (the same rule resolves fetches); Haiku's quiet loud is then 3 / 24 (one host fetch on a pasted merge conflict, the two hook cases). **The one allowed wording revision:** the usage line now says to fetch only the one page that bears on the message most, and that a word inside pasted code, logs or output is not a mention (`compile_subconscious.INDEX_TAIL`). Haiku re-run on development once with it; then frozen. |
| 2026-11-10 | **Development, revised wording, Haiku 5.5 re-run once** (`claude-haiku-5-5`): recall 22 / 24 (zh 11, en 11; hook 6, host 16), changed 12 / 12, quiet loud 3 / 24 (two by the frozen hook, one host fetch on a pasted merge conflict), wrong pages 1 (was 5), old 0. Sonnet's development run used the first wording and was not repeated. **Frozen** (`58f0437`); held-out next, once per host. |
| 2026-11-10 | **Held-out, run once per host** (wording as frozen; agents reported `claude-haiku-5-5` and `claude-sonnet-5-5`; replies in `bench/subconscious/results/set35/b35held/`). **Sonnet 5.5: recall 24 / 24 (zh 12 / 12, en 12 / 12; the hook 7, the host where the hook was silent 17; mentions without the page's names 17 / 17), changed 12 / 12 (hook 5, host 7), quiet loud 1 / 24 (by the hook: a pasted line), wrong pages 0, old 0. Haiku 5.5: recall 23 / 24 (zh 11 / 12, en 12 / 12; hook 7, host 16; without names 16 / 17), changed 12 / 12 (hook 5, host 7), quiet loud 2 / 24 (one by the hook, one host fetch on an everyday word), wrong pages 0, old 0.** Against the line (recall ≥ 18 / 24 and ≥ 8 per language, changed ≥ 9 / 12, quiet ≤ 2 / 24, wrong ≤ 2, old 0): **both hosts pass. As registered, the prompt hook and the standing index are on by default** (`recollect.DEFAULT_ON`; `KROUTER_RECALL_PROMPT=0`, `KROUTER_RECALL_INDEX=0`, `KROUTER_INJECT=0` turn them off). Index: 60 topics, all as full lines, 5,600 characters, about 2,630 tokens by the registered estimate. |
| 2026-11-10 | **Scale check, development only.** Before it ran, preparing (b) showed the index as first written would have listed **0 of the 60 real topics**: 240 newer distractors filled the line budget and the oldest, never-used real pages were cut. Changed then, on development only and without touching the 60-topic index (byte-identical on vault3): when the topics do not fit, every topic keeps its name in one "also known" line and the remaining budget goes to full lines for the first ones (`INDEX_FULL_MIN`); at 300 topics that is 16 full lines and all 300 names in 5,644 characters, about 2,510 tokens. (a) **Crowded, all 300 topics as full lines** (24,495 characters, about 10,690 tokens, over the shipped budget): Sonnet 5.5 recall 23 / 24, changed 12 / 12, quiet loud 1 / 24, wrong 2; Haiku 5.5 21 / 24, 11 / 12, 2 / 24, wrong 2 (development, against 23 / 24, 12 / 12, 2, 3 and 22 / 24, 12 / 12, 3, 1 with the 60 real topics). (b) **Shipped budget, distractors dated newer, real topics as names only**: Haiku 5.5 recall 19 / 24, changed 9 / 12, quiet loud 1 / 24, wrong 1. A long list did not make either host noisier; losing the one-line conclusion costs Haiku about 3 of 24 mentions. |
| 2026-11-10 | Defaults switched as registered (prompt hook and standing index on; learning off after set 36). Found while switching: with no alias table of its own a vault fell back to the sample table shipped with the code; the index now uses only the vault's own table (or `KROUTER_MAP`). Session-start hook with the index: 115 ms median on vault3 (101 without), 430 ms at 10,000 pages with 2,000 alias rows (109 without); it runs once per session. |

## Set 36: does it get better with use — learning a mention from what the host fetched (registered 2026-11-10, before any case existed)

**Why.** When the hook says nothing and the host fetches a page itself and uses it, the turn hook notes the message and
the page; the nightly `learn_mentions` step turns the message's most distinctive phrase into a provisional trigger word
for that page. The question: does the hook then bring that page by itself the next time the team says it that way,
without getting louder?

**Cases.** Written in the same sitting as set 35 by the same writer: per language 8 *pairs* (two messages on one
topic that share a team expression the pages and names do not contain, as teams have nicknames for their own rules;
the first is the learning message, the second the test message, written so it would not share the expression by
accident with any other page), and 4 *lookalike* quiet messages (the same team expression's ordinary words used about
something unrelated). `bench/subconscious/set36.jsonl`, not split (nothing is tuned on it).

**Procedure.** Learning: each first message goes through the hook (frozen) and Sonnet 5.5 with the index, as in set
35; where the hook brought nothing and the host fetched and named the right page, that is a learning event, exactly as
the turn hook would write it; `learn_mentions.run` then writes the trigger file. Test: the prompt hook alone, before
and after learning, on the 16 second messages, on the 8 lookalikes, and on set 35's 24 held-out quiet messages.

**Pass line (fixed now):** after learning, the hook alone brings the right page for at least half of the second
messages whose first message produced a learning event (before learning: counted and reported); quiet messages (the
lookalikes and set 35's held-out quiet ones) bringing something: no more than before learning; no wrong page brought
on a second message. If it fails, the nightly step stays in the code but is reported as not shown to work.

### Log, set 36

| Date | Event |
|---|---|
| 2026-11-10 | Registered (`77aeb94`); cases written with set 35's (`bench/subconscious/set36.jsonl`). **Run once** (learning messages answered by Sonnet 5.5, `claude-sonnet-5-5`; replies in `bench/subconscious/results/set36/`). On the 16 first messages the hook brought the right page 3 times (Chinese) and the host fetched it on the other 13: **13 learning events** (zh 5, en 8). `learn_mentions` learned one phrase per event. **Second messages, the hook alone: before learning 0 / 16; after, right on 6 of the 13 whose first message was learned (zh 1 / 5, en 5 / 8); wrong pages 0. Quiet (8 lookalikes + set 35's 24 held-out quiet messages) bringing something: 1 before, 1 after.** Against the line (≥ half of 13, i.e. 7; quiet no worse; no wrong page): **fails by one**; quiet holds. Reading the learned phrases: English ones were the team expressions or close to them ("dusty-keys sweep", "white-hat queue", "lunch-break reaper strikes"); Chinese ones mostly were not (「回家加班」「昨晚连上」, or the expression with a word attached, 「每日洗牌刷掉」): without real Chinese word segmentation the picker cuts in the wrong places. As registered, the nightly step stays in the code, reported as not shown to work; it is **off by default** (`KROUTER_RECALL_LEARN=1`), because it also keeps the latest message's words in the state folder. |
