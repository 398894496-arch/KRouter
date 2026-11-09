# Auto-capture: what is written down, when, and what it costs

How KRouter turns sessions into "what was decided" lines, how it lives next to another collector, and what moving the
work from the nightly run to the end of each session costs. Code: `import_sessions.py`, `session_hook.py`,
`answer_cards.py`. Measured on the author's machine on 2026-10-30 unless said otherwise.

## 1. Answer cards the checkup lists as unfaithful or too broad

The 2026-10-28 checkup listed 8 cards whose answers held a number or path not found in the page, and 18 questions
too broad to tell which page they were about. All 8 were written on 2026-10-10, the day the whole-token check
(`4d02772`) went in, and all 8 had passed the model check (`v: 1`). Two causes:

- **Cards on file were never re-checked.** `answer_cards.py` rewrote a page's cards only when the page changed; a card
  that a later, stricter check would refuse stayed in the file, blocked at read time, for good. Now every run holds
  kept cards to the current checks and asks a page again once when one fails (new cards pass the same checks, so the
  page is not asked again the next night).
- **The check read layout as content.** 6 of the 8 answers copied the page exactly but without its spaces
  (`1 : 3.3` → `1:3.3`, `6230 / N70 / N73` → `6230/N70/N73`, `1.2MB / 498 行` → `1.2MB/498`, `2026-08-23 / 24`), or
  quoted `session_item_`, which the token pattern cut to `session_item`. `faithful()` now also reads the page with
  spaces around `/` and `:` removed, and a trailing `_` is part of a token. The other 2 rewrote a date
  (`08-16` → `8/16`) and are still refused; the prompt now says to copy values as written.
- **Too broad** was only counted by the checkup, never refused at write time. `recall_index.broad_question()` is now
  the one test both use: a new card with fewer than two content words is dropped, and the prompt asks for the page's
  own subject in the question ("Roadster 那期音效比人声低多少？", not "音效该比人声低多少？").

Dry run on the author's vault after the change: 16 pages re-asked once (about 35 000 characters), the 2 remaining
unfaithful cards and the broad ones among them. Tests: `tests/test_recall_index.py`.

## 2. Living next to another collector (`collect_day.py`)

The host's daily job (`collect_day.py` + `distill_llm.py`) writes one `type: daily-log` page per day under
`05 时间日志/YYYY-MM/`: a stub that lists every session as `` `claude:<id>` ``, then a distilled day summary that
cites sessions by an 8-character prefix. It reads session metadata (first question, turn count), not the turns:
its distilled logs say "索引未提供" where the content would be. KRouter's pages are the turn-by-turn record of one
session-day. They are not the same content, so the plan is to link them and remove true duplicates, not to pick one.

- **Matching a session to a daily log**, in the vault only (no import of the host's code): a `type: daily-log` page
  covers a session it names (`` `agent:id` ``, or a bare 8+ hex prefix) **on that page's own date** (a session that
  ran past midnight is not covered for the next day), and covers its whole date when a collector wrote it
  (`source_kind` in its frontmatter). On the author's last 7 days: 41 session-day pages, 38 matched by id, 3 by day.
- **`--overlap link`** (default): write the page, add `covered_by: "[[the log]]"` and a line pointing to it.
  **`--overlap skip`**: write nothing for a covered session-day. Saved with `--consent`.
- **Forks and resumes** copy earlier turns verbatim. A turn is keyed by its time and question; sessions of one day
  whose first turn is the same turn are one conversation. The longest keeps the shared turns, each other keeps only
  its own (`forked_from`), and one wholly inside another gets no page (and its old page, if ours, is removed; in hook
  mode the earlier session's transcript is found by id and read back). Same words asked at another time are not a
  fork. On the author's last 7 days: 1 such duplicate.

Not done here, on purpose: turning on `--consent` on the author's machine. Suggested line, once the model lane works:
`import_sessions.py --consent --distill --cli /opt/homebrew/bin/claude --overlap link --days 1`.
Tests: `tests/test_import_sessions.py`.

## 3. Distilling at session end instead of at night

`session_hook.py end` already imports the session that ended, in a detached process, and distills it when consent
included `--distill`. So "real time" needed no new hook; it needed three fixes before it is reasonable to leave on:

| | Before | Now |
|---|---|---|
| A session that ends several times (window closed, `/clear`, resumed and ended again) | the whole excerpt re-sent each time its turn count changed | only the turns since the last digest, plus 2 turns of context and the earlier lines for the change-of-mind pass |
| Two imports at once (two windows, hook and nightly) | both send the same session | one at a time (`flock`); the second finds the first one's digest |
| Model lane | whatever the session's shell held: `llm.plan` tries `*_API_KEY` first, so a DeepSeek key in the shell sent the excerpt to DeepSeek while the nightly job used `claude` | the CLI named at `--consent --cli` goes first |

**Cost.** Last 7 days (2026-10-24 to 30): 27 sessions, 41 session-days, 316 turns, median 4 turns and 3 400
characters per page. Distilling the 32 session-days with at least 2 turns sends **444 000 characters** (about 14 000
per session-day, 63 000 a day; for comparison the 2026-10-28 nightly sent 138 000 for topic dossiers and 54 000 for
answer cards). With the incremental digest, moving this to session end costs about the same as doing it at night:
the extra per additional end is the prompt templates, 2 context turns (at most about 1 500 characters each) and the
earlier lines, so a few thousand characters at most, instead of the whole excerpt again. Each end runs one
python process and, for a session that grew, 2 or more model calls in the background; nothing waits on it.

**Privacy.** What is sent does not change: redacted questions (up to 600 characters) and closing answers (up to 900),
no tool output, no thinking. What changes:
- **No window to take a session back.** At night there is a day to `--revoke` or delete a transcript; at session end
  it is sent within a minute. `redact()` removes key-shaped strings, not personal data: on 2026-10-29 the author's
  sessions held a third person's name and date of birth, which either path would send.
- **More sends, each smaller**, to the lane named at consent. With no lane named, the hook would follow the shell's
  keys (now avoided by `--cli`).
- **Headless runs** (`claude -p` used by the distill itself) end too; their transcripts have no human turns and are
  skipped, after waiting for the lock.

Keeping a session out, built since: `#不记` (or `#nocapture`) in any question of a session keeps it out of import
and distill, and removes a page already written for it; `--exclude-root <dir>` (repeatable, saved with `--consent`)
does the same for every session under that project root.

## 3a. When a session "ends" is not a schedule

A desktop window often stays open for days and is archived long after the work in it is done, so `SessionEnd` fires
late or not at all; it is a top-up, not the trigger. What runs the work on a schedule instead:

- **Daytime slots.** `extras/host-daily-evolution/intraday_capture.py`, from an hourly timer
  (`launchd.intraday.example.plist`: `StartInterval` 3600), runs `import_sessions.py --intraday` when a slot is due.
  Slots are wall-clock times in one zone (`--slots 12:10,18:10 --tz Asia/Shanghai` by default), so the machine's
  daylight-saving change does not move them. A machine asleep at a slot runs it once on the first tick after it
  wakes (the latest missed slot only); a failed slot is tried once more on the next tick, then left to the nightly
  job. `--intraday` needs consent, uses the lane and distill choice recorded then, and covers today and yesterday,
  so a session that crossed midnight is seen; with the incremental digest a page that did not grow sends nothing.
  State and a one-line summary per run: `~/.local/state/krouter/intraday.json`, `intraday.log`.
- **Corrections on the spot.** `session_hook.py prompt` (UserPromptSubmit) appends a typed correction to
  `05 时间日志/会话摘录/YYYY-MM-DD｜纠正候选.md` (`status: provisional`, time, project, `claude:<id8>`, the cue word,
  "待下次蒸馏判定"). Pattern match only: correction cues (改成/改为/换成/以后都/一律/锁死/不要再/别再/记住/纠正/搞错/说错,
  `from now on`, `instead of`, `that's wrong`, …), minus a sentence that ends as a rhetorical question (不是吗/对不对/
  是不是/难道不是, `isn't it`). Skipped: no consent, a prompt over 1500 characters, a session marked `#不记`, and any
  prompt under a KRouter model call (`llm.cli_env()` sets `KROUTER_IN_DISTILL`, so the distill's own `claude -p`
  never records its excerpt as your correction). Redacted, cut to 300 characters, nothing sent, never fails the
  session, prints nothing into it. The page is a clue (time-log tier in recall); the next distill of that session
  settles each candidate on its own (`corrections.py`): a digest line sharing enough of its content words makes it
  成立 (the verdict names that line and page), none makes it 不成立. No extra model call.

## 3b. Observable, not approved

Capture writes memory without a yes: a yes/no gate on every digest line was one more chore that did not get done, so
nothing ever took effect. In its place every run that changes something is visible and reversible:

- **One commit per run** (when the vault is a git repository) with exactly the files that run wrote or deleted,
  tagged `[krouter-run <id>]`. Other changes in the vault are left out of it (`git commit --only`). Hook-written
  candidates are committed as they were just before they are settled, so undoing a run puts them back to pending.
- **One ledger entry per run** in `90 系统文件/自动化/记忆变更记录.md` (`status: generated`, so recall never cites
  it): each page that gained lines and its session, each added line (a change of mind shown as `取代：原来 A → 改成
  B`), each candidate's verdict, each page removed. The entry is committed separately, so undoing keeps the record.
- **One command back:** `import_sessions.py --undo <id>` reverts that run's commit and notes the undo in the ledger.
- The SessionStart hook brings every distilled line (corrections first), unmarked; `KROUTER_INJECT=confirmed`
  restores the earlier confirmed-pages-only default. A run that changes nothing writes no commit and no entry.

## 4. Decision-capture bench (`bench/decision_capture/`)

Set 6 (`bench/real_questions/capture_bench.py`) measures capture on the author's real sessions with model judges; it
is private and its numbers depend on the judge. This bench is the small public counterpart: 14 written sessions (10
Chinese, 4 English) with 14 labeled decisions, 3 of them changes of mind, and 4 sessions where nothing was decided
(discussion, a one-off, steps only, "I'll think about it"). Scored by rule: each decision lists the words a line must
hold; `forbid` lists steps and discussion. Reported: recall, change recall (a line with "→"), false-extraction rate,
steps-or-discussion lines, lines on the no-decision sessions.

```
python3 bench/decision_capture/run.py --oracle          # scorer check: recall 1.0, false 0.0
python3 bench/decision_capture/run.py --cli /opt/homebrew/bin/claude --save lines.jsonl --show
python3 bench/decision_capture/run.py --replay lines.jsonl
```

Baseline, 2026-11-09, `claude` lane: 14 of 14 decisions found, 3 of 3 changes, 20 lines with none false, nothing
written for the 4 sessions where nothing was decided. The lines are in `results/2026-11-09-claude.jsonl` (`--replay`
regrades them). (On 2026-10-30 the same run had failed: the CLI's login had expired.)
Lexical scoring undercounts a correct line worded with none of the listed alternatives; `--show` prints misses and
false lines to read. Tests: `tests/test_decision_capture_bench.py`.

## 5. Back-test on the maintainer's machine (2026-10-30 → 11-09)

Capture ran on the author's machine from 2026-10-30, so its own record can be checked against what actually happened.
Only counts are published here, never session content. Sources: the change ledger (`记忆变更记录.md`), the session
pages it wrote, the day's correction-candidate pages, and the corrections the author recorded by hand in the same
period (8 entries in the Claude Code correction log, each with the person's own words and date). Labels below were
assigned by Claude reading the pages, not by a person.

**What it wrote.** 30 runs on 11 days, 68 page writes over 27 sessions, 714 lines: 407 changes of mind ("was A → now B")
and 307 new decisions. Every line names its session; no run was undone. All sessions in the period were Claude Code
ones (the machine had no Codex or Cursor sessions after 2026-10-30), so this says nothing about the other importers.

**Against the 8 hand-recorded corrections.**

| | Count |
|---|---|
| In the memory as a "was A → now B" line by the next run | 5 |
| In the session page's turns, missed by the distill | 2 |
| About the agent's own tool use, which import does not see (it keeps questions and closing answers only) | 1 |

From the turn that made the correction to the run that wrote it down: 0.5 to 17.7 hours, median 15. The machine slept
through most daytime slots; the slot then runs once after wake.

**The correction catcher** (`session_hook.py prompt`) only worked from 2026-11-04 (a manual install had not recorded
the vault path; fixed in `install.sh`). On the 12 lines it kept from then to 11-09:

| | 1.3.0 | after this change |
|---|---|---|
| Lines kept | 12 | 6 |
| Of them, a correction or decision the person typed | 7 | 6 |
| Kept although not the person's words (an app-attached block, a pasted document) | 2 | 0 |
| Kept although a question or a suggestion ("…有 ECC 纠错吗", "要不要再去…查一下") | 3 | 0 |
| A real correction now dropped (a decision phrased as a question, "…对吗") | — | 1 |

Settling was the larger fault. Of 10 settled candidates, 7 were tied to the wrong digest line, because the shared
words counted included the correction wording itself (`改成` on both sides). Three of those were corrections the
distill had missed altogether (a price, a disk size, a cache size): the old rule tied each to an unrelated line and
reported it covered. Now correction wording and times are left out of the comparison; a match needs a shared
distinctive term (a model, a number, a name) or at least three shared Chinese terms; and a candidate no digest line
covers is written into the digest in the person's own words (`补记`) instead of being settled as not holding. Replayed
on the same pages, the three missed corrections are now written in, and no candidate is tied to an unrelated line.
