# Memory honesty bench

<!-- krouter-status:start (source: docs/STATUS.md; run scripts/sync_status.py) -->
> **Current status of `main` (latest release v1.2.0, 2026-10-19). Measured, and what is not.** One-line installs get
> the latest release; anything under "Unreleased" in CHANGELOG.md is on `main` only. Every fact an evaluating agent
> needs, with sources: [`docs/FOR-AGENTS.md`](https://github.com/398894496-arch/KRouter/blob/main/docs/FOR-AGENTS.md).
> - **Held-out bench** (200 questions on a synthetic 110-page vault, never tuned on; *not* real traffic): KRouter 26%
>   wrong citations, 47 of 80 unanswerable questions refused, 102 of 120 answerable right. At their defaults claude-mem
>   64% and basic-memory 78%, 72 and 45 right; neither can refuse. BM25 given KRouter's two rules (skip replaced
>   pages, refuse a weak match) is level with KRouter: the lead is those rules being on by default, not the ranker.
> - **Real-traffic blind test on fresh queries** ([VERIFY.md](https://github.com/398894496-arch/KRouter/blob/main/docs/VERIFY.md)
>   layer 4): not run yet; it waits for 50 new queries.
> - **Who wrote the held-out questions:** Claude Opus in separate claude.ai sessions, not a person. A person-written
>   set is planned.
> - **Releases:** 1.2.0 (2026-10-19) came ahead of the planned 2026-11-12, at the maintainer's call. From here, minor
>   releases at most once a week and patches when ready; `KROUTER_TAG` pins one.
> - **Nightly job:** the one-line install is lookup only and asks nothing; `--ask` asks about importing sessions and
>   the nightly job. The manual `install.sh` installs the job (`KROUTER_NO_TIMER=1` skips). Queries never leave the machine.
> - **Nightly writer lanes:** an API key runs nothing locally; grok (kernel sandbox) and claude (tool allow-list) are
>   limited to the vault; Codex can read the whole account and writes only the vault, so it is used only when you name
>   it or set `KROUTER_ALLOW_CODEX=1`; other CLIs are unconfined and are never picked unless you set
>   `KROUTER_ALLOW_UNCONFINED=1`.
>   [SECURITY.md](https://github.com/398894496-arch/KRouter/blob/main/SECURITY.md) has the table.
<!-- krouter-status:end -->

Does an agent memory cite the right page, follow a correction, and refuse what it does not hold? Retrieval benches
usually score how often the right page shows up. This one scores the opposite failure, the one users actually get
burned by: a confident answer from the wrong page.

Everything is in [`bench/memory_honesty/`](../bench/memory_honesty/): a 30-page vault of plain Markdown, 30
questions, a runner, and a scorer that grades any system's output.

## The questions

| Kind | n | What the vault holds | Right behaviour |
|---|---|---|---|
| `correction` | 10 | an old page (`status: superseded`) and the newer page that replaces it, which also says so in its text | cite the new page first |
| `current` | 10 | one page that answers it | cite that page first |
| `refuse` | 10 | nothing that answers it, but a page that answers a *neighbouring* question: the search API timeout when the vault has the payments API timeout; file storage backups when it has database backups | refuse; citing the neighbour is a wrong citation |

## Metrics

- **Wrong-citation rate**: of the questions a system answered, the share whose first citation is not the gold page.
  Every answered `refuse` question counts as wrong.
- **Refusal**: `refuse` questions refused, of 10.
- **Correction hit**: `correction` questions whose first citation is the new page, of 10.
- **Current hit**: `current` questions whose first citation is the gold page, of 10.

## Results

Four systems, both question sets, run on 2026-10-12. Held-out means the 25 questions in `heldout.jsonl` that KRouter was
never tuned on ([`HELDOUT.md`](../bench/memory_honesty/HELDOUT.md)); dev means the 30 bench questions, on which KRouter
was fixed once (see below). Each cell gives the wrong-citation rate, refusals out of 10 neighbour questions, and right
answers on correction and current questions.

| System | Held-out: wrong citations | refused | corrections | current | Dev: wrong citations | refused | corrections | current |
|---|---|---|---|---|---|---|---|---|
| Plain full-text search (SQLite FTS5 BM25), always answers | 61% (14 / 23) | 1 / 10 | 4 / 9 | 5 / 6 | 63% (19 / 30) | 0 / 10 | 1 / 10 | 10 / 10 |
| basic-memory 0.22.1, default search (vector) | 60% (15 / 25) | 0 / 10 | 4 / 9 | 6 / 6 | 39% (11 / 28) | 2 / 10 | 7 / 10 | 10 / 10 |
| claude-mem 13.35.0, its search over what it observed | 60% (15 / 25) | 0 / 10 | 5 / 9 | 5 / 6 | 43% (13 / 30) | 0 / 10 | 7 / 10 | 10 / 10 |
| **KRouter 1.0.1** | **25% (3 / 12)** | **8 / 10** | 5 / 9 | 4 / 6 | 0% (0 / 17) | 10 / 10 | 8 / 10 | 9 / 10 |

That table compares systems at their defaults, and at their defaults the other three have no way to refuse and no
notion of a replaced page, so "neighbours refused 0 / 10" is settled before the first question. An outside review
(2026-10-12) pointed this out. The fair question is what an ordinary search does once it gets the same two things
KRouter has: replaced pages left out (`status: superseded`), and a score floor below which it refuses.

### Matched baselines: the same two things, for everyone

Each system that reports a score gets superseded pages removed from its results and a floor picked **on the dev set
only**, by one fixed rule (most right answers minus wrong citations; on a tie, the lower floor), then applied
unchanged to held-out. `run.py --adapter bm25-floor` is the BM25 version; `floor.py` does it for any scored adapter
output. claude-mem's search returns no score, so it has no row here.

| Held-out, 25 questions | Wrong citations | Neighbours refused | Answerable right (of 15) |
|---|---|---|---|
| BM25 + skip superseded + dev floor | 19% (3 / 16) | 7 / 10 | 13 |
| basic-memory 0.22.1 + skip superseded + dev floor | 30% (6 / 20) | 4 / 10 | 14 |
| KRouter 1.0.1 (as shipped) | 25% (3 / 12) | 8 / 10 | 9 |

Systems that answer more questions also cite more wrong pages, so the fair comparison is at the **same coverage**:
each baseline's floor set so that it answers as many questions as KRouter does (12 on held-out, 17 on dev). Choosing
an operating point on held-out is done here for baselines only, never for KRouter.

| Same coverage | Held-out: wrong / right | Dev: wrong / right |
|---|---|---|
| BM25 + skip superseded | 2 / 10 | 1 / 16 |
| basic-memory + skip superseded | 2 / 10 | 1 / 16 |
| KRouter 1.0.1 | 3 / 9 | 0 / 17 (tuned on dev) |

**What this says.** On this bench, KRouter's retrieval is not better than plain full-text search or basic-memory's
embedding search once they are given the same two rules; at the same coverage it is slightly worse on held-out. Almost
all of the gap in the first table, 61% → 25% wrong citations, comes from those two rules: a replaced page that is
marked and left out, and an answer withheld when the match is weak. KRouter's real difference is that it does both
by default and says so with a receipt, in plain Markdown that several agents share. That is a design choice
anyone can copy, not a better ranker. The bench is small (30 pages, English, 55 questions): a fair reading is "no
measurable ranking advantage", not "worse".

What the default-settings table still shows, because it is how people run these tools:
- **Neighbour questions are where the defaults differ.** basic-memory, claude-mem and plain search answer nearly every
  question that sounds like something in the vault, so a question about the search API timeout gets the payments API
  timeout page. KRouter refuses 8 of 10 on held-out.
- **KRouter pays for that in answerable questions:** 9 of 15 on held-out against 10 for basic-memory and claude-mem.
  Five of its six misses there are refusals of a question phrased in words the page does not use.
- **Corrections are hard at defaults.** All four put the replaced page first on some correction questions; with
  replaced pages left out, BM25 and basic-memory get 8 and 9 of 9.

### Tried and not shipped (2026-10-12)

After the matched baselines showed no ranking advantage, a round of changes aimed at beating BM25: English stemming
(`locally` = `local`), following `superseded_by` from a replaced page to its replacement, refusing on unknown words
only when they outnumber the matched ones, refusing when the question names another page's topic that the top page
never mentions, and answer cards that work on English pages (they had been written in Chinese and filtered out). On
the two dev sets (the bench's 30 and 50 more written by the maintainer, `questions_dev2.jsonl`) the change matched
BM25+rules on coverage and beat it on refusals and wrong citations. **On held-out it was worse than what is
shipped:** 38% wrong citations (31% with cards) against 1.0.3's 25%, and 5 of 10 neighbour questions refused instead
of 8. The maintainer's own neighbour questions were easier than an independent writer's. It is not shipped, and the
held-out set was used once for this go / no-go (see `HELDOUT.md`). Generated questions also hurt BM25 on held-out
(19% → 29%): expanding pages with paraphrases lets neighbour questions match too.

How each system was run (adapters in [`bench/memory_honesty/adapters/`](../bench/memory_honesty/adapters/), each
system's defaults, isolated HOME):
- **basic-memory 0.22.1** indexes the vault folder as a project (`basic-memory reindex`, 30 notes embedded) and
  answers with `basic-memory tool search-notes`. Its `--hybrid` and `--vector` modes gave identical results to the
  default. It refuses only when the search returns nothing.
- **claude-mem 13.35.0** (Claude Code plugin from its marketplace, observer `claude-haiku-4-5`) does not index a
  folder; it remembers sessions. It learned the vault the way it learns a user's docs: one Claude Code session read
  all 30 pages, one Read per page, and claude-mem recorded 30 observations (10 decision, 8 change, 12 discovery). Each
  question goes to its own search (`/api/search`, what its MCP search tool calls); results map to pages through each
  observation's `files_read`. It has no refusal: it always returned something. Running it isolated takes one extra
  setting: even with its own HOME, claude-mem looks for Claude Code's login in the macOS keychain, which is shared
  across HOMEs; `CLAUDE_MEM_CLAUDE_CONFIG_DIR` set to a fresh folder keeps it off your real login, and the worker then
  needs `CLAUDE_CODE_OAUTH_TOKEN` in its own environment.
- **KRouter** runs in-process (`run.py`); BM25 is `run.py --adapter bm25`, and `--adapter bm25-floor` is BM25 with
  superseded pages removed before indexing and the dev-picked floor.
- **basic-memory was re-run in a Linux container** (`bench/memory_honesty/adapters/Dockerfile`) for the matched
  baseline, recording its scores; its answers were identical to the first run on the host.

Raw per-question output on the dev set, for every system, is in
[`bench/memory_honesty/results/2026-10-12/`](../bench/memory_honesty/results/2026-10-12/); grade any of them with
`run.py --answers`. Per-question held-out output is not published, to keep the held-out set usable (HELDOUT.md rule 3);
only the aggregates above are.

Not run: Obsidian Smart Connections (it runs inside the Obsidian app, with no headless search to call) and Mem0 (it
needs an LLM and a vector store configured, and has no default to compare against). Adapters are welcome.

### History on the dev set

| System | Wrong-citation rate | Refused | Correction hit | Current hit |
|---|---|---|---|---|
| KRouter 0.12.1 (first run, before any change) | 22% (4 / 18) | 7 / 10 | 5 / 10 | 9 / 10 |
| KRouter 0.13.0 to 1.0.1 | 0% (0 / 17) | 10 / 10 | 8 / 10 | 9 / 10 |

**Who the "outside reviewer" is.** Every held-out set here, and the outside reviews in `CHANGELOG.md`, come from
Claude Opus in claude.ai chat sessions that the maintainer starts and relays: not a human, and not the Claude Code
sessions that change KRouter, but the same model family. "Outside" means a separate session that did not write the
code it reviews; it does not mean independent of Anthropic's models, so question wording may share that family's
habits. A set written by a person is planned and will be logged here before it is run.

**Held-out, on questions KRouter was never tuned on.** An outside reviewer wrote 25 new questions for the same 30-page vault: 15 answerable ones phrased differently, and 10 neighbour questions. They were written independently of any tuning. KRouter 1.0: 25% wrong citations (3 / 12), 8 / 10 neighbours refused, 9 / 15 answerable right. Plain BM25 that always answers: 61%, 1 / 10. The questions are in [`bench/memory_honesty/heldout.jsonl`](../bench/memory_honesty/heldout.jsonl), frozen at 1.0.1; the rules for using them (aggregates only, no tuning toward them, what burns the set) and a log of who has seen what are in [`bench/memory_honesty/HELDOUT.md`](../bench/memory_honesty/HELDOUT.md). CI pins the questions and the vault and checks only a sanity guard against plain full-text search, never a floor. Quote this figure, or the 0.12.1 row (22%), as KRouter's wrong-citation rate, not the 0% above. The three wrong citations: a git branch-name format question cited the date-format page (both say "format"); a release-tag naming question and a checkout-page load-budget question each cited a neighbouring page.

**Read the 0.13.0 row as a development-set number.** The bench was written for 0.13.0, and its first run found a bug:
English function words (`what`, `which`, `does`, `should`) were counted as words "the vault has never seen", so a
plain English question about a page that was there got refused, while a neighbour question that happened to share
`what` and `do` with a page got answered. 0.13.0 drops those words from ranking and refusal and lets `services` match
`service`. The fix is general, not shaped to these 30 questions: on the author's Chinese vault the recall eval is
identical before and after. Still, KRouter was changed after seeing the bench, so the honest held-out figure is the
0.12.1 row.

The 0.13.0 misses are all refusals, never wrong answers. Each one asks with a word the page does not use: a pull
request "needs approvals" where the page says "merge"; an on-call "shift" where the page says "rotates"; "locally"
where the page says "local development". Lexical recall cannot bridge those. An embedding system would answer them,
and it would answer the neighbour questions too.

## Second bench: a bilingual vault nobody has tuned on (2026-10-12)

The first vault now carries 105 questions on 30 pages, and a round of changes that helped both of its dev sets made
its held-out set worse ("Tried and not shipped" above). So the outside reviewer wrote a second one: `vault2/`, 60
pages (30 English, 30 Chinese; 20 replaced decisions with their old pages, 20 that were not replaced), with 100
questions split 50 / 50 by a fixed seed into `questions_dev3.jsonl` (tune on it) and `heldout2.jsonl.gz` (never; stored
gzipped so it does not turn up in a grep). Each set: 15 corrections, 15 current, 20 neighbour questions, half of each
in Chinese. Every neighbour question names a term no page contains, checked in CI, so it cannot be answered by
accident. Provenance, rules and log: [`HELDOUT.md`](../bench/memory_honesty/HELDOUT.md), "Held-out set 2".

On vault2 the BM25 baselines split Chinese into character pairs (otherwise every Chinese question would be "refused"
for having no Latin words, which flatters the baseline), and `bm25-floor` picks its floor on dev3.

| System | heldout2: wrong citations | neighbours refused | answerable right | dev3: wrong citations | refused | answerable right |
|---|---|---|---|---|---|---|
| Plain BM25, always answers | 61% (30 / 49) | 1 / 20 | 19 / 30 | 55% (27 / 49) | 1 / 20 | 22 / 30 |
| BM25 + skip superseded + dev3-picked floor | 23% (5 / 22) | 15 / 20 | 17 / 30 | 4% (1 / 22) | 19 / 20 | 21 / 30 |
| KRouter 1.0.3 | 33% (12 / 36) | 9 / 20 | 24 / 30 | 24% (8 / 34) | 13 / 20 | 26 / 30 |

Read plainly: on questions written by someone else, on a vault nobody tuned for, KRouter answers more questions right
than the careful BM25 baseline (24 vs 17 of 30) but cites a wrong page more often (33% vs 23%) and refuses fewer
neighbour questions (9 vs 15 of 20). It sits at a different point on the same trade-off, not above it. basic-memory and
claude-mem have not been run on vault2 yet; their adapters take the vault1 sets only.

### Dense prototype on vault2 (2026-10-12, bench only, not in the product)

`bench/memory_honesty/dense.py` adds a local embedding model (`paraphrase-multilingual-MiniLM-L12-v2` through
fastembed; questions never leave the machine) and combines it with lexical search. Tuned on dev3 only; the candidate
was fixed on dev3 before one heldout2 run: **`agree`**, which answers only when BM25 (Chinese by character pairs) and
the dense model put the same page first, both with superseded pages left out and each above a floor picked on dev3.

| heldout2, 50 questions | Wrong citations | Neighbours refused | Answerable right |
|---|---|---|---|
| KRouter 1.0.3 (shipped) | 33% (12 / 36) | 9 / 20 | 24 / 30 |
| BM25 + skip superseded + dev3 floor | 19% (4 / 21) | 16 / 20 | 17 / 30 |
| **`agree`: BM25 and dense must agree** | **18% (5 / 28)** | **15 / 20** | **23 / 30** |
| dense + skip superseded + dev3 floor | 23% (7 / 30) | 13 / 20 | 23 / 30 |

Read plainly: on questions written by someone else, on a vault nobody tuned for, the agreement of two different
retrievers keeps the careful baseline's precision and refusals while answering six more questions, and against what
KRouter ships it cites fewer than half as many wrong pages for one fewer right answer. It is a prototype on a 60-page
bench, not yet a feature: it needs an embedding model on the user's machine and floors that do not depend on a dev
set of their own vault.

## Third bench: 200 held-out questions on a vault nobody tunes on (2026-10-13)

Fifty questions cannot separate two systems: a 5 / 28 against a 5 / 22 wrong-citation rate is noise. `vault3/` has
110 pages (English and Chinese rule pages, their replaced versions, and 20 daily logs as distractors) and 200
held-out questions, 80 of them neighbours, with **no dev set**: it stands for a vault KRouter has never seen. `run.py`
now gives 95% bootstrap intervals (`--ci`), paired intervals against another system (`--vs`), a comparison at equal
coverage (`--vs-matched`) and the coverage curve (`--curve`). Baseline at freeze, KRouter 1.0.3 minus BM25 with the two
rules at KRouter's coverage: wrong-citation rate −4.3 points [−10.2, +1.4], answerable right +6 [−2, +14]. Ahead
on every point estimate, significant on none. The rule for claiming "surpasses BM25", and for shipping a new default,
was written down before any candidate ran: [`HELDOUT.md`](../bench/memory_honesty/HELDOUT.md), "Held-out set 3".

**Other memory systems on the same 200 questions (2026-10-14).** basic-memory 0.23.2 and claude-mem 13.39.0, the
latest releases, at their defaults (basic-memory 0.23: full text plus semantic search, in a container; claude-mem:
four Claude Code sessions read every page, its haiku observer took notes, in an isolated home), registered in
HELDOUT.md before each run.
95% intervals in brackets.

| System | wrong citations | neighbours refused (of 80) | corrections right (of 60) | current right (of 60) |
|---|---|---|---|---|
| KRouter 1.0.3, default | 27% (37 / 139) [19, 34] | 46 | 50 | 52 |
| claude-mem 13.39.0, default | 64% (128 / 200) [58, 71] | 0 | 34 | 38 |
| basic-memory 0.23.2, default | 78% (155 / 200) [72, 84] | 0 | 16 | 29 |
| basic-memory + the two rules (floor from dev3) | 19% (5 / 27) [4, 33] | 76 | 3 | 19 |

KRouter minus each at their defaults, paired 95% intervals: against claude-mem, wrong-citation rate −30 to −45 points,
answerable right +17 to +44; against basic-memory, −43 to −59 points and +43 to +72; neighbours refused +35 to +58
against both. Neither has a way to refuse, and neither knows a page was replaced. With the two rules basic-memory cites few wrong pages but answers 27
of 200 questions: its scores do not separate right from wrong well enough for one floor to keep the right answers.
Neither tool can refuse (an empty search is the only refusal the adapters can see), so their 0 / 80 neighbour
refusals are structural, and the answerable-right columns are the comparison that does not depend on refusing.
Their raw per-question output is stored in `bench/memory_honesty/results/2026-10-14/` and regraded in CI
(`tests/test_memory_honesty_competitors.py`). claude-mem gives no score, so it has no floor variant. mem0 and Zep were not run: both need a hosted model to
extract memories, and none was configured.

## Learning from use (2026-10-15, dev sets)

KRouter's nightly learner (`reconsolidate.py`) reads the questions the router did not answer well and, when a model
confirms a page answers one, adds that question to the page's recall triggers. `learn_bench.py` measures what one
night of that does: week-1 wordings go through the router into a private query log, the learner runs once, and week-2
wordings are scored before and after. On the dev sets, the learner as shipped through 1.1.0 made recall **worse**:
it picked neighbour pages that only share the subject (a question about SSH keys learned onto "where secrets live",
a question about screen readers onto "Accessibility").

| One night, dev pairs | learned | of them wrong | week-2 wrong citations | neighbours refused |
|---|---|---|---|---|
| vault1, learner ≤ 1.1.0 | 5 | 2 | 2 → 5 | 33 → 30 of 35 |
| vault1, learner with proof | 3 | 0 | 2 → 2 | 33 → 33 |
| vault2, learner ≤ 1.1.0 | 2 | 2 | 7 → 9 | 13 → 11 of 20 |
| vault2, learner with proof | 0 | 0 | 7 → 7 | 13 → 13 |

The fix: the learner now sees the start of each candidate page and must copy the sentence that answers the question.
A pick is learned only if the quote is on the page, is a sentence (at least four words) and shares a content word with
the question. That check stops made-up, fragmentary and unrelated quotes; it does not by itself tell a neighbour page
from the answer (a neighbour can hold a sentence that shares a word), which is left to the model's judgement as the
prompt asks. Inputs pages (`03 资料与证据`, clipped and pasted text) are never candidates.

Read the result for what it is: **it no longer learns wrong triggers, and it learns few** (3 on vault1, 0 on vault2).
Right answers did not change in either version, because the dev pairs are two different questions about one page,
not one question asked twice. Whether learning *helps* needs one intent in two wordings, written by a person:
`bench/memory_honesty/human_set/`.

## Run it

```bash
python3 bench/memory_honesty/run.py                  # KRouter, in-process
python3 bench/memory_honesty/run.py --adapter bm25   # the plain full-text baseline
python3 bench/memory_honesty/run.py --answers mine.jsonl
python3 bench/memory_honesty/run.py --set heldout     # held-out set: aggregates only (HELDOUT.md)
python3 bench/memory_honesty/run.py --set dev3        # second vault (vault2/), dev set
python3 bench/memory_honesty/run.py --set heldout2    # second vault, held-out: aggregates only
python3 bench/memory_honesty/run.py --set heldout3 --vs-matched bm25-floor   # third vault, equal coverage, intervals
python3 bench/memory_honesty/run.py --set heldout3 --curve --adapter krouter  # coverage curve
```

To grade another system, index `bench/memory_honesty/vault/` with it, ask each question in
`bench/memory_honesty/questions.jsonl` (`q`), and write one JSON line per question:

```json
{"id": "C-release", "cited": ["Engineering/Release process.md"], "refused": false}
```

`cited` is in rank order and uses vault-relative paths. A system that returns chunks maps each chunk to its file.
`refused: true` means it said it had nothing; an empty `cited` with `refused: false` counts as a refusal too. CI runs
the KRouter row on every push (`tests/test_memory_honesty.py`), and its floors only go up.
