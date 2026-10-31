# Local embeddings as an opt-in tier: the evidence (2026-10-30)

Question asked: can KRouter's paraphrase recall ("semantic recall") be backed by comparable numbers if local
embeddings become an opt-in tier, and is that tier worth building? This page collects every measurement made for it.
Nothing in the product changed: the default stays lexical, nothing was installed into a real vault, and
`canonical_sources.psv` was not touched. Registrations: [`HELDOUT.md`](../bench/memory_honesty/HELDOUT.md), set 3 log
(2026-10-30) and set 10.

## Where dense stands

| Branch / file | What it is | State |
|---|---|---|
| `bench/memory_honesty/dense.py` (main, from `recall/dense`) | bench prototype: `dense`, `agree`, `rescue`, `gate`, `vote` | merged; on 2026-10-30 given the vault3 floor fix, BGE-M3, `--ci`, `--by-lang`, and a chunked scorer for long session pages |
| `feature/dense` (10 commits, last 2026-10-13) | product module `skill/…/dense.py`: its own venv, opt-in (`bootstrap.py --dense`), falls back to lexical and says so, jina-v2-base-zh (640 MB), up to 4 chunks a page, tiered decision; inert logistic-regression decider | **not merged, 84 commits behind main**; rebasing is real work (recall_index, route_knowledge and nightly have all changed on main since) |
| heldout3, 2026-10-13 (on `feature/dense` only) | candidate 1, jina, tiered rules: 14.7% wrong (16 / 109), 64 / 80 refused, 93 / 120 right; failed the default bar (right ≥ 97). Plain `agree` with jina at equal coverage tied it | logged on the branch, not on main |
| real-traffic set 5, 2026-10-16 | dense candidate met its line, then the line was withdrawn: refusing everything would score higher than every system | **not shipping evidence** (HELDOUT.md) |

Gaps before this round: no dense number on main's KRouter (1.2.x), no paired intervals against today's default, no
second model, no outside benchmark, no cost numbers.

## heldout3: 200 questions, vault never tuned on (aggregates only)

Floors picked on dev3 (vault2). KRouter default = main `e934696`. 95% bootstrap intervals; Δ = variant minus KRouter
default on the same resamples.

| System | Wrong citations | Neighbours refused (of 80) | Answerable right (of 120) | Δ wrong rate (points) | Δ right | Δ refused |
|---|---|---|---|---|---|---|
| KRouter default | 26.1% (36 / 138) [19.0, 33.1] | 47 [36, 59] | 102 [88, 116] | | | |
| `rescue`, MiniLM | 29.1% (44 / 151) [21.9, 36.6] | 39 [28, 50] | **107** [93, 121] | +0.3 to +6.1 | **+1 to +10** | −14 to −3 |
| `agree`, MiniLM | **15.6% (12 / 77)** [7.6, 24.3] | **69** [56, 82] | 65 [52, 78] | **−19.1 to −1.8** | −49 to −26 | +11 to +32 |
| `rescue`, BGE-M3 | 26.4% (37 / 140) [19.4, 33.6] | 46 [35, 58] | 103 [90, 117] | −0.5 to +1.6 | 0 to +3 | −3 to 0 |
| `agree`, BGE-M3 | **14.0% (14 / 100)** [7.7, 21.2] | 67 [54, 80] | 86 [73, 100] | **−19.2 to −5.3** | −26 to −6 | +10 to +30 |
| *for reference, frozen 2026-10-13:* BM25 + skip superseded + dev3 floor | 21% (18 / 85) [13, 30] | 64 [52, 78] | 67 [54, 80] | | | |
| *for reference, `feature/dense` 2026-10-13:* `agree`, jina-v2-base-zh | 5.5% (4 / 73) | 76 | 69 | | | |

dev3 (the tuning set, in-sample): KRouter 7 / 33 wrong, 14 / 20 refused, 26 / 30 right; `rescue` 7 / 36, 14, 29 with
either model; `agree` MiniLM 1 / 24, 19, 23; `agree` BGE-M3 2 / 30, 18, 28. By the rule fixed before the run (`rescue`,
the model with the higher right − wrong on dev3, the smaller on a tie) the candidate is **`rescue` with MiniLM**.

By language (same runs, aggregates; Δ intervals against KRouter on the same half):

| Half | KRouter default | `rescue` MiniLM | `rescue` BGE-M3 | `agree` MiniLM | `agree` BGE-M3 |
|---|---|---|---|---|---|
| Chinese (100) | 29 / 84 wrong, 13 / 40 refused, 55 right | 33 / 89, 9, 56 | 30 / 85, 12, 55 | 9 / 40, 32, 31 | 12 / 59, **29**, 47 |
| English (100) | 7 / 54 wrong, 34 / 40 refused, 47 right | 11 / 62, 30, 51 | 7 / 55, 34, 48 | 3 / 37, 37, 34 | 2 / 41, 38, 39 |

Δ right against KRouter on the same half: `rescue` MiniLM 0 to +3 (Chinese), +1 to +8 (English); `agree` BGE-M3 −14
to −3 and −15 to −1; `agree` BGE-M3 Δ neighbours refused +8 to +24 in Chinese, 0 to +9 in English.

Read plainly:
- `rescue` does what an opt-in for paraphrase recall should do: it answers more answerable questions than KRouter,
  significantly, and never changes an answer KRouter gives. It pays for it: of the 13 refusals it turns into answers,
  5 are right and 8 are neighbour questions it should have refused, so the wrong-citation rate rises, also
  significantly. Embeddings are good at "this question is about that page" and that is exactly what a neighbour
  question looks like.
- BGE-M3's `rescue` floor (picked on dev3) is high enough that it rescues almost nothing: +1 right on the point
  estimate. A bigger model does not make `rescue` better; it makes it quieter.
- `agree` is the honesty tier, not the recall tier. With BGE-M3 it is the best honesty point measured on heldout3 that
  still answers most questions: 14% wrong (half of KRouter's 26%), 67 of 80 neighbours refused, 86 of 120 right, and on
  all three point estimates ahead of BM25 with the two rules (21%, 64, 67; frozen baseline, not paired). Its gain is
  largest in Chinese, where KRouter's own refusal is weakest (13 / 40 neighbours refused; `agree` BGE-M3 29 / 40). It
  costs 16 right answers against the default, and four configurations were looked at, so treat it as a measurement.
- Neither is "better than KRouter" on every axis. They are other points on the same trade-off, as the 2026-10-13
  jina runs found.

## LoCoMo (set 10): someone else's conversations and labels

1 986 questions over 10 conversations, 272 session pages; categories 1–4 answerable (1 540), category 5 adversarial
(446). Mechanical scoring from the authors' evidence labels; paired 95% intervals against KRouter, 10 000
resamples. English only.

| System | Evidence session first (of 1 540) | Evidence in top 3 | Refused answerable | Category 5 refused (of 446) | Wrong citations |
|---|---|---|---|---|---|
| KRouter default | 991 (64.4%) | 1 204 | 137 | 37 | 821 / 1 812 |
| BM25, no floor | 968 | 1 257 | 0 | 0 | 1 018 / 1 986 |
| BM25 + dev3 floor | 46 | 46 | 1 494 | 422 | 24 / 70 |
| dense MiniLM, no floor | 703 | 1 053 | 0 | 0 | 1 283 / 1 986 |
| `rescue`, MiniLM | 999 (Δ +0.2 to +0.9 pts) | 1 212 | 127 | 34 | 826 / 1 825 |
| `agree`, MiniLM | 286 | 286 | 1 225 | 359 | 116 / 402 |
| dense BGE-M3, no floor | 963 (Δ −4.7 to +1.0 pts) | **1 272** (Δ **+2.0 to +6.9 pts**) | 0 | 0 | 1 023 / 1 986 |
| `rescue`, BGE-M3 | 991 (no change) | 1 204 | 136 | 37 | 822 / 1 813 |
| `agree`, BGE-M3 | 371 | 371 | 1 148 | 317 | 150 / 521 |

By category, evidence first (KRouter → dense BGE-M3): 1: 130 → 143 of 282; 2: 197 → 195 of 321; 3: 27 → 41 of 96;
4: 637 → 584 of 841.

Read plainly: on long chat sessions MiniLM ranks worse than plain BM25 (703 vs 968 first), so it rescues almost
nothing (+8). BGE-M3 alone ranks about as well as KRouter first-hit (963 vs 991, interval spans zero) and puts an
evidence session in its top three more often than any other system (1 272 vs 1 204), better on categories 1 and 3 and
worse on 4: the two rankings fail on different questions, which is what a fused ranking would use. Neither prototype
rule uses that: `rescue`'s dev3 floor lets nothing through here, and `agree` with dev3 floors refuses three quarters of
the answerable questions. Floors picked on dev3's short rule pages do not transfer to session pages (BM25-floor and `agree`
refuse most answerable questions); this is the same finding as LongMemEval set 7. KRouter refuses only 37 of 446
adversarial questions: the LoCoMo version of its known abstention gap.

## LongMemEval S, 20 seed-drawn answerable questions (seen set, marked as such)

KRouter in-process 19 / 20 evidence cited, dense MiniLM 20 / 20, `rescue` 19 / 20, `agree` 9 / 20. Too small to
separate anything and at the ceiling: LongMemEval S questions share words with their answer sessions, so lexical
recall already finds them (set 7: KRouter 439 / 470, plain BM25 447 / 470). It costs about a minute a question to
embed a 500 KB haystack with MiniLM on this machine, so the full 470 was not run; BGE-M3 was about 40 times
slower on LoCoMo, so it was not run on LongMemEval at all.

## Cost

Measured on the maintainer's Mac (Apple silicon, **8.6 GB RAM**, 7 GB of swap already in use by other work), fastembed
0.9.1 on CPU, in a throwaway Python 3.12 venv.

| | MiniLM-L12 multilingual | BGE-M3 | jina-v2-base-zh (`feature/dense`) |
|---|---|---|---|
| Runtime (fastembed + onnxruntime + numpy + tokenizers, own venv) | 145 MB | same | same |
| Model on disk | 246 MB | 2.2 GB (ONNX weights 2.1 GB) | 640 MB |
| Download here (through the local proxy) | ~3 min | ~1 h, one stall; fastembed deleted a 1.3 GB partial file on the failed attempt, `hf_hub_download` resumes | — |
| Model load | 1.2–1.5 s | 7.7 s | — |
| One query | 3 ms | 46 ms | — |
| 110 short rule pages (vault3) | 1.5 s | 21 s | — |
| Long session text (600-character pieces) | ~40 pieces/s; a 500 KB LongMemEval haystack ≈ 1 min | LoCoMo's 272 sessions (1.3 MB) took 38.5 min (MiniLM: under a minute); a 193-piece haystack sample did not finish in 10 min while other work held memory, because the 2.1 GB weights paged in and out of swap | author's 1 206-file vault: 17 min first build at 4 pieces a page |
| Peak resident memory | 1.3 GB | 1.1 GB counted, plus 2.1 GB of mapped weights | — |

On an 8 GB machine BGE-M3 is usable only for small vaults of short pages; MiniLM fits anywhere but is the weaker
model.

## Verdict

**Is an opt-in tier worth building now? Not as either prototype rule stands.** What the numbers support:

1. **Paraphrase recall, the thing the opt-in was meant to buy, is small in the two rules measured.** The pre-registered
   candidate (`rescue`, MiniLM) answers 5 more of 120 heldout3 questions right (+1 to +10) and 8 more neighbour
   questions wrongly; on LoCoMo +8 of 1 540; on LongMemEval no change. Rule 2's honesty bars (≤ 27% wrong, ≥ 46
   refused) are not met. BGE-M3 `rescue` changes almost nothing. A score for "semantic recall" cannot be raised on this
   evidence.
2. **Where embeddings clearly help is honesty, not recall:** `agree` with BGE-M3 halves wrong citations on heldout3
   (14% vs 26%, interval entirely below zero), mostly through Chinese neighbour refusals, for 16 fewer right answers.
   That is an opt-in "strict" tier, and the 2026-10-13 jina runs found the same shape.
3. **The ranking signal is there on long sessions** (BGE-M3 top three on LoCoMo +2 to +7 points over KRouter), but
   neither rule uses it, because **floors picked on short rule pages do not transfer to session pages**. This, not
   the model, is the blocker for any product version: a floor has to be set per page kind or calibrated without a dev
   set of the user's own vault.
4. **Cost on an 8 GB machine:** MiniLM (0.4 GB with its runtime) is cheap but weak on conversational text; BGE-M3
   (2.3 GB) is the useful model and is slow to build on long pages here (38 min for 1.3 MB) and fragile to download.

**Recommended next step, if the maintainer wants to pursue it** (it needs the infrastructure gate's explicit yes before
anything is installed into a real vault): an opt-in *strict* tier (`agree` style, BGE-M3 or jina) for vaults of short
rule pages, with page-kind floors, measured on set 9 when it closes; and, separately, a fused ranking (KRouter +
dense, reciprocal rank) tuned on LoCoMo conversations 1–5 and measured once on 6–10, registered before it runs.
`feature/dense` holds the product scaffolding (own venv, opt-in switch, lexical fallback) but is 84 commits behind
main.

**Risks.** Four configurations were looked at on heldout3, so the chosen one's number is optimistic; LoCoMo and set 9
are the checks that do not share that selection. heldout3 and the dev3 floors were written by Claude Opus, not a
person. LoCoMo results here are retrieval (is an evidence session cited), **not** the LLM-judged answer accuracy that
Mem0, Zep and others publish for LoCoMo, so they are not comparable with those leaderboard figures. LoCoMo is
CC BY-NC.

## Running LongMemEval and LoCoMo with KRouter (both are in the repo now)

- **LongMemEval** (`bench/longmemeval/lme.py`, set 7): converter, KRouter and BM25 runner, mechanical scorer from the
  authors' labels already existed; now also the dense systems on a seed-drawn sample (`--sample N`). The 30 `_abs`
  questions are a development set and S and M share questions, so no fresh abstention number can come from it.
- **LoCoMo** (`bench/locomo/locomo.py`, set 10): new. One vault per conversation, one page per session, evidence turns
  mapped to sessions, category 5 as abstention. All systems run in minutes (the dataset is 1.3 MB of text).
- **Chinese.** Neither benchmark has a Chinese release (DuLeMon, Baidu 2022, is Chinese long-term dialogue but labels
  personas, not evidence turns, so it cannot be scored the same way). The Chinese evidence today is heldout3's
  Chinese half (100 questions) and, when it closes, set 9. Minimal adapter for a Chinese LoCoMo: translate two or
  three conversations (about 60 sessions, ~90 k English tokens) and their ~500 questions with a model, keep `D`-turn
  ids unchanged so the labels carry over, register before the run, and say a model translated it. Cost: one model
  pass of ~100 k tokens in and ~130 k out (a few dollars at most on a mid-size model), plus one pass of a second model
  to spot-check that answers stayed in the turns they were labelled to. The translated text is public data; no
  maintainer question leaves the machine. Not run this round.
