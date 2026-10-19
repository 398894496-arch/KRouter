# Changelog

**Release pace.** 1.1.x was held to fixes from 2026-10-15; 1.2.0 shipped on 2026-10-19, ahead of the planned
2026-11-12, at the maintainer's call. The early weeks shipped many versions a day; that pace was development, not a
support promise.

Minor releases (new features) at most once a week; patch releases (fixes, docs, benchmark updates) when ready. 1.0.0 to
1.0.2 went out on one day: 1.0.0 at the maintainer's call, 1.0.1 and 1.0.2 as fixes from outside reviews. From 1.0.0 the version follows
semantic versioning; what counts as the stable surface is listed in [`docs/DETAILS.md`](docs/DETAILS.md#stability-and-versions). Each entry starts with what you will
notice, then the details.

## Unreleased

Nothing yet.

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
