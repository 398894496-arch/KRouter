# KRouter

<!-- mcp-name: io.github.398894496-arch/krouter -->

**Your AI remembers what you decided — and what you changed your mind about.**

Works with the AI you already use, and one is enough. Your memory is a folder of plain Markdown pages you can open,
read and edit, in [Obsidian](https://obsidian.md) or any editor. Ask "what did we decide about the cover title?" and
the answer comes with the page it came from. A correction replaces the old answer instead of competing with it. When
the memory does not know, your AI is told so, rather than handed something close. Code, writing, video, study or
work: anything you decide and later change.

[![ci](https://github.com/398894496-arch/KRouter/actions/workflows/ci.yml/badge.svg)](https://github.com/398894496-arch/KRouter/actions/workflows/ci.yml) [![release](https://img.shields.io/github/v/release/398894496-arch/KRouter)](https://github.com/398894496-arch/KRouter/releases/latest) [![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE) · 中文：[`README.zh.md`](README.zh.md)

Tests run on Linux, macOS and Windows on every push. The one-line install downloads the latest release (a tag, never
`main`) and checks its SHA-256 before running anything; each release also carries a GitHub build-provenance
attestation (`gh attestation verify <package> --repo 398894496-arch/KRouter`). What you ask never leaves your machine.

![Monday we decide A, Wednesday we change it to B, Thursday the agent answers B and cites the correction; a question the vault cannot answer is refused](docs/img/demo.gif)

**See it for yourself in a few seconds, with nothing installed and no key:** the same story on a throwaway memory,
deleted afterwards.

```bash
uvx --from git+https://github.com/398894496-arch/KRouter krouter demo      # or, in a clone: PYTHONPATH=sdk python3 -m krouter.cli demo
```

| I want to… | Start here |
|---|---|
| see it answer, correct itself and refuse, before installing anything | `krouter demo` (above) |
| give the AI apps I already use a memory | [Install](#install): one line, asks nothing, wires every app it finds |
| check which apps it connects to | [Works with](#works-with) |
| call it from my own code | [From your own code](#from-your-own-code) |
| share a memory with my team, or run several | [`docs/TEAM.md`](docs/TEAM.md) |
| check the numbers myself | [Check it yourself](#check-it-yourself) |
| know exactly what leaves my machine | [What leaves your machine](#what-leaves-your-machine) |

## Measured, not claimed

**Answer accuracy, the number other projects publish:** on LongMemEval (ICLR 2025; 500 questions, each over about 50
chat sessions), a model given only the pages KRouter cites answered **400 of 500 right (80.0%, 95% interval
76.4–83.4)**: 371 of 470 answerable, and 29 of 30 unanswerable ones recognised as such. Reader and judge are Claude
Sonnet 5.5 with the benchmark's own prompts; most published numbers use GPT-4o, so set them side by side with that in
mind. Weakest: questions that add up several sessions, 69 of 121, because three pages often miss one
([set 11](bench/memory_honesty/HELDOUT.md#set-11-longmemeval-answer-accuracy-scored-the-way-other-projects-report-it-registered-2026-11-09-before-any-run),
every reply and verdict in [`bench/longmemeval/results/`](bench/longmemeval/results/)).

**On other people's benchmarks**, scored from their authors' own labels, no model judge:
- **LongMemEval** (ICLR 2025; 500 questions, each over about 50 chat sessions): for 439 of 470 answerable questions an
  answer session is among the pages KRouter cites; for 70 of 72 questions whose fact changed later, it cites the
  newest one.
- **LoCoMo** (ACL 2024; 1,986 questions over 10 long conversations): the first page cited holds the evidence for 991
  of 1,540 answerable questions, and one of the top three does for 1,204.

These two count whether the right page was found, not whether a model then answered correctly; the answer accuracy is
the paragraph above. Plain BM25 finds about as many pages (447 / 470, 968 / 1,540).

**Where it is weak:** a question about a near neighbour of something the memory does mention still gets an answer. It
refuses 3 of 30 LongMemEval questions that have no answer, and 37 of 446 LoCoMo trick questions.

**On our own 200 held-out questions** (English and Chinese, never tuned on, written by Claude Opus in separate
sessions): KRouter cites a wrong page 26% of the time; claude-mem 64%, basic-memory 78%. Of 80 questions the memory
cannot answer, it refuses 47; the other two refuse none. Of 60 questions about a decision that was later changed, it
gets 50 right; they get 34 and 16. Part of that gap is by construction: plain full-text search given KRouter's two
rules is level with it. What KRouter adds is having those rules on by default, plus receipts (a few lines with each
answer: the page it came from, why that page, how sure) and a memory you can edit.
[Every number and its method](#honest-numbers) · [rerun them](#check-it-yourself)

## Install

```bash
curl -fsSL https://github.com/398894496-arch/KRouter/releases/latest/download/bootstrap.sh | sh
```

Both the short script this line downloads and the package it then installs come from the latest release (a tag,
never `main`), and the package is checked against the release's SHA-256 before anything runs; both carry a
build-provenance attestation.

Windows (PowerShell): `irm https://github.com/398894496-arch/KRouter/releases/latest/download/bootstrap.ps1 | iex` · Claude Code plugin: `/plugin install krouter --marketplace 398894496-arch/KRouter` (Claude Code 2.1.275 or later; from a shell, `claude plugin install krouter --marketplace 398894496-arch/KRouter` needs 2.1.292). Third-party marketplaces do not auto-update: run `claude plugin update krouter@krouter`, or turn it on in `/plugin` → Marketplaces → krouter → Enable auto-update.

Rather look first? Nothing below changes your machine until the last line:

```bash
git clone https://github.com/398894496-arch/KRouter.git && cd KRouter
./scripts/first_run.sh                      # a receipt on the bundled sample vault
python3 scripts/bootstrap.py --dry-run      # every change the install would make, made nowhere
python3 scripts/bootstrap.py --vault ~/notes --no-timer   # install against your vault, nightly job off
```

Python 3 is the only requirement, and the installer asks nothing. It makes a memory folder (or uses yours with
`--vault`, overwriting nothing), connects every app on [the list below](#works-with) that it finds on the machine,
adds the Claude Code plugin from the same checksummed release, and imports the last 7 days of agent sessions as
pages: locally, redacted, with no model call, each page listed in the change ledger and undoable. From then on it
remembers by itself, turn by turn, in Claude Code, Codex and Cursor (it adds their session hooks), and nothing leaves
the machine. `--no-import` installs lookup only; `--ask` asks first, and is
how you turn on distilling with your model and the nightly job, the two steps that send text out.

## Works with

One install wires every app it finds. It writes each app's own MCP settings in the format that app documents, keeps
everything else in the file and a copy of it, never touches a file it cannot parse or a `krouter` entry it did not
write, and `uninstall.sh` takes out only its own entries.

| App | How it connects | Status |
|---|---|---|
| Claude Code | plugin (session hooks) and MCP, both added by the installer | tested |
| Codex | MCP, and session hooks in `~/.codex/hooks.json` (trust them once with `/hooks`; Codex runs no hook you have not trusted) | MCP tested; hooks tested in codex-cli 0.155 |
| Cursor | rule and skill, MCP (`~/.cursor/mcp.json`), and session hooks (`~/.cursor/hooks.json`) | rule and skill tested; MCP settings and hooks checked by tests against Cursor's documented format, not yet inside Cursor |
| DeepSeek Harness | plugin (`dsh plugin --profile web add github:398894496-arch/KRouter`) | tested |
| Claude Desktop · VS Code (Copilot) · GitHub Copilot CLI · Gemini CLI · Kiro · Zed · Cline CLI | MCP: the installer writes each app's settings file when the app is installed; restart the app once | settings checked by tests against each app's documented format; not yet tested inside the apps |
| Agent frameworks: LlamaIndex, LangChain / LangGraph, OpenAI Agents SDK, Pydantic AI, Google ADK, CrewAI, Vercel AI SDK | a LlamaIndex retriever in the Python package; the others load the MCP server through their own MCP client: [`docs/FRAMEWORKS.md`](docs/FRAMEWORKS.md) | all tested against the server, each in its own environment and in CI; LangChain, Pydantic AI and the Vercel AI SDK through their whole agent loop with their own stand-in models |
| Any other app that runs a local MCP server: Devin Desktop (Windsurf), opencode, Continue, Roo Code, Cline in VS Code, … | add the server below to the app's MCP settings | should work, not yet tested by us: [tell us](https://github.com/398894496-arch/KRouter/issues) |
| A team: shared memories for several people | a self-hosted HTTP server: [Running it for a team](#running-it-for-a-team) | tested with Claude Code, the MCP Python SDK and the JS client over HTTP |
| Apps that only take a remote MCP server | the same HTTP server, behind HTTPS | should work, not yet tested by us |
| Your own code | a Python package and a `krouter` command; a JavaScript / TypeScript client with no dependencies (below) | tested |

```json
{ "mcpServers": { "krouter": { "command": "python3",
    "args": ["/Users/you/.agents/skills/krouter-obsidian/scripts/mcp_server.py"] } } }
```

Use the full path to your home folder (on Windows, `C:\\Users\\you\\.agents\\…` and often `python` instead of
`python3`). After the one-line install the server finds your memory by itself. It is standard-library Python over
stdio with three tools: `krouter_ask` and `krouter_status` read; `krouter_note` lets your AI write one line down (a
decision, a correction, a fact), which lands on that day's notes page as a clue, never on a rule page, and is listed
in the change ledger as one git commit you can revert. The HTTP team server leaves `krouter_note` off unless started
with `--allow-write`. A plain MCP client gets through `initialize`, `tools/list`, a cited answer and `recall: none`.

### From your own code

Python 3.9+, the same lookups, receipts and notes:

```bash
pipx install "git+https://github.com/398894496-arch/KRouter"      # or: uvx --from git+https://github.com/398894496-arch/KRouter krouter ask "…"
krouter ask "how do we ship a release?"
```

```python
import krouter
a = krouter.ask("how do we ship a release?")
print(a.page, a.how, a.refused)          # the page it came from, the one-line answer, True when the memory does not know
krouter.note("Releases are tagged from main only.", kind="decision")
```

JavaScript / TypeScript (Node 18+), local or a team server ([`sdk/js`](sdk/js); not on npm yet):

```js
import { KRouter } from "./sdk/js/index.js";
const a = await KRouter.local().ask("how do we ship a release?");   // or KRouter.remote(url, { token })
console.log(a.page, a.how, a.refused);
```

## Running it for a team

One server holds the memories of a team, each one a folder of Markdown in its own git repository; everyone's agent
asks it over MCP. It is self-hosted: there is no KRouter cloud.

| | |
|---|---|
| **Deploy** | `mcp_server.py --http` (standard-library Python, no packages), the Docker image `ghcr.io/398894496-arch/krouter`, [Compose](deploy/docker-compose.yml) (two memories and a git-pull sidecar), a [Kubernetes manifest](deploy/kubernetes/krouter.yaml), a hardened [systemd unit](deploy/systemd/krouter.service) |
| **Isolation** | several memories ("banks") on one server, each at `/mcp/NAME` with its own index, its own label on every answer and its own token; one bank's lookups never read another's folder |
| **Auth** | bearer tokens, one per memory; the server refuses to listen beyond this machine while any memory has none; browser Origins allow-listed; the access log keeps a hash of each question, never the text |
| **Speed** | below, measured; 4 resident lookup processes per memory (`--workers`), so a lookup does not start Python |
| **Freshness** | files re-checked at most every 2 s (`--refresh-every`); a note written through the server is found by the very next lookup; Compose and Kubernetes pull each repository every 5 minutes |
| **Monitoring** | `GET /healthz`; Prometheus `GET /metrics`: calls by memory, tool and outcome, refusals, a latency histogram, index build time, lookup processes |
| **Writes** | read-only by default; `--allow-write` offers `krouter_note`: one line, one git commit, listed in the change ledger |
| **Backup, rollback** | the memory is the git repository: back it up like code, take a change back with `git revert`; the index is a cache rebuilt from the folder |

Measured with [`bench/scale/serve_load.py`](bench/scale/serve_load.py) on synthetic memories, one Apple M2 laptop
(8 GB), the server and its callers on the same machine, 300 calls per row, none failed:

| Pages | One caller: median, answers/s | 8 callers: answers/s | 32 callers: median, p95, answers/s | Resident memory | Index build at start |
|---|---|---|---|---|---|
| 1,000 | 5 ms, 195/s | 646/s | 42 ms, 77 ms, 742/s | 203 MB | 0.5 s |
| 10,000 | 13 ms, 77/s | 267/s | 104 ms, 112 ms, 301/s | 216 MB | 3.5 s |
| 50,000 | 54 ms, 17/s | 72/s | 377 ms, 651 ms, 75/s | 267 MB | 24 s |

The same machine with 1.3.0's server (one process per lookup, every file re-checked each time): 210 ms and 15
answers/s at 10,000 pages, 980 ms and 3 answers/s at 50,000. Rerun: `python3 bench/scale/gen.py 10000 /tmp/v10000`,
then `python3 bench/scale/serve_load.py /tmp/v10000`. Setup, tokens and TLS: [`docs/TEAM.md`](docs/TEAM.md).

## Five minutes later

1. Ask your AI: *"what did we decide about X last week?"* It answers from the memory, names the page, and says plainly when the memory has nothing on it.
2. Open the memory folder: the last 7 days of Claude Code, Codex and Cursor sessions are already there, one page per session with your questions and each turn's closing answer, key-shaped text redacted. Nothing left the machine. (`--ask` asks before importing.)
3. **"Have your model pull out what was decided?"** On a yes, the model you already use (a logged-in CLI or an API key) writes "what was decided, what changed" at the top of each recent session's page. The installer tells you how many characters that sends before it sends anything.

## It keeps up on its own

Nothing needs maintaining, and nothing waits for a yes except the two steps that send text to a model:
- **Every night** (the job asks first) yesterday's sessions are imported and distilled, and the memory is tidied.
- **After every turn**, in Claude Code, Codex and Cursor, the session so far is written to its page the moment the
  agent finishes answering (locally, no model call, under a second in the background), so another window's agent
  can already find it. When the session ends it is distilled, if you said yes to that.
- **When you correct your AI**, in the same three, a line that reads like a correction ("from now on…", "改成…") is
  written down the moment you send it, locally and without a model call; the next distill settles it. A new session
  starts with this repository's recorded decisions, corrections first, each with its page.
- **During the day**, an optional timer catches today's sessions at two set times
  (`extras/host-daily-evolution/intraday_capture.py`, a macOS launchd example included).
- **Nothing waits for your approval, and nothing is hidden.** Every run writes what it added and what it replaced to
  `90 系统文件/自动化/记忆变更记录.md` (the change ledger; the default folders have Chinese names, and a
  `krouter-zones.psv` at the vault root maps them to yours). When the memory folder is a git repository (`git init` it once), each run is
  also one commit, and `import_sessions.py --undo <run>` takes it back.
- **Keep a session out** by putting `#nocapture` (or `#不记`) in any question of it.

**What it did on the maintainer's own machine**, 2026-10-30 → 11-09, every number from its own change ledger
([method and tables](docs/AUTO_CAPTURE.md#5-back-test-on-the-maintainers-machine-2026-10-30--11-09)):

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/capture-days-dark.svg">
  <img alt="Lines written to memory per day, 2026-10-30 to 11-09: 714 in all, 407 of them a change of mind" src="docs/img/capture-days-light.svg" width="760">
</picture>

- **30 runs wrote 714 lines**, 407 of them a change of mind ("was A → now B"), each naming the session it came from.
  None had to be undone.
- **Of 8 corrections the maintainer also wrote down by hand, 5 were in the memory by the next run.** 2 were missed by
  the distill; 1 was about the agent's own tool use, which import does not see. A correction typed in Claude Code is
  now kept even when the distill misses it: it is written in in your own words.
- **From correction to memory: median 15 hours** (0.5 to 17.7): the Mac slept through daytime runs. A correction typed
  in Claude Code is on record the moment you send it.
- **On the public decision-capture bench** (14 written sessions with 14 labelled decisions, 3 of them changes of mind,
  and 4 sessions where nothing was decided; scored by rule): all 14 found, all 3 changes, no false line, nothing
  written for the 4 empty sessions (Claude lane, 2026-11-09; rerun with `python3 bench/decision_capture/run.py --replay
  bench/decision_capture/results/2026-11-09-claude.jsonl`, or `--cli <your CLI>` to distill afresh). A small set: it shows
  the distill does not invent decisions, not that it never misses one; the 2 misses above are real.

## Is it for you?

**Yes**, if you use an AI assistant, any one, and keep telling it the same decision again, or it keeps answering with
something you changed weeks ago. No notes yet? The installer makes the folder. Using several assistants is a bonus,
not a requirement: they then share one memory. **No**, if you want semantic search over embeddings, the last chat
replayed into the next one, a hosted memory service run for you (a self-hosted team server is fine:
[`docs/TEAM.md`](docs/TEAM.md)), or a brain that is full on install.

**Not only for code:** the same story for short-video work, recorded the same way (Claude Code with the plugin, a
demo vault, real output):

![Monday the cover-title rule is A, Wednesday it changes to B, Thursday the agent answers B and cites the page; a question the vault has no page on is refused](docs/img/demo-content.gif)

**Not needed:** Obsidian (it is an optional viewer), an alias table to maintain, an environment variable to set.
Already have a vault? `--vault` changes none of its files. The default sends nothing anywhere: local session import,
no nightly job, no model call (`--no-import` for lookup only).

## How it is different

| | KRouter | Typical agent memory |
|---|---|---|
| Where memory lives | Markdown pages you can open, edit, diff and sync | A database or vector store |
| After a correction | The new page replaces the old one, which is marked superseded | Old and new chunks both match; you hope the right one wins |
| When nothing matches | `recall: none` — your AI says the memory does not know | The nearest chunk, presented with confidence |
| Every answer | Carries its source page and a receipt | Usually unsourced |
| Who shares it | Every AI app on the machine reads the same folder (MCP, skill, rules) | Usually one tool |

**Coming from [claude-mem](https://github.com/thedotmack/claude-mem)?** Keep it. The importer has been run end to end against a live claude-mem 13.35.0 install. The installer finds its memory and offers to import it: session summaries become pages, and each project's decisions become one page you confirm. Your model can then sort those decisions into the ones still in force and the ones a later decision replaced, which claude-mem itself does not do. The Claude Code plugin also does what makes claude-mem feel like memory, in plain Markdown: when a session ends it is recorded, and when a new one starts, this repository's recent decisions come with it, corrections first, each naming its page. Repositories are told apart by their path, never by folder name. Both happen only after you said yes to importing.

## What leaves your machine

Queries never do: lookup is a local SQLite full-text index, about 110 ms. Session import is local. Text goes to a model only for the steps you said yes to: distilling sessions and nightly upkeep. It goes to the CLI or API key you already use, and `--dry-run` shows the size first. Keys and pages marked secret are never sent or quoted. For the nightly writer, the API-key lane runs nothing on
your machine; CLI lanes differ in what they can read, and the install says which one you are choosing. Details:
[`SECURITY.md`](SECURITY.md).

**Backups.** `backup.py init --dir <a folder that syncs elsewhere>` turns on a nightly encrypted archive of the whole
vault, history included, opened again each night before it counts. Point it at iCloud Drive, OneDrive, Dropbox, a
Netdisk sync folder or a USB disk (or two of them); KRouter talks to no cloud. Why this and not syncing or pushing the
vault: [`DETAILS.md` → Backing up your vault](docs/DETAILS.md#backing-up-your-vault).

## Honest numbers

| Measured | Result |
|---|---|
| LongMemEval S, someone else's questions and labels ([set 7](bench/memory_honesty/HELDOUT.md#set-7-longmemeval-someone-elses-questions-and-labels-registered-2026-10-18-before-any-download-or-run); KRouter 1.1.1; scored mechanically from the authors' labels, registered before the run) | An answer session among the cited pages for 439 / 470 answerable questions; the newest fact cited for 70 / 72 knowledge updates (stale only: 1); 12 of 470 answerable questions refused; **3 of 30 unanswerable refused**. Plain BM25 with no floor, top three pages: 447 / 470 and 69 / 72, level |
| LongMemEval S answer accuracy ([set 11](bench/memory_honesty/HELDOUT.md#set-11-longmemeval-answer-accuracy-scored-the-way-other-projects-report-it-registered-2026-11-09-before-any-run); KRouter 1.3.0's top three pages as the only context; reader and judge Claude Sonnet 5.5 with the benchmark's own prompts; registered before the run; a seen set) | **400 / 500 right, 80.0% [76.4, 83.4]**; answerable 371 / 470, 78.9%; unanswerable recognised 29 / 30. By type: single-session 61 / 64 (user) and 55 / 56 (assistant), knowledge update 69 / 72, temporal 97 / 127, preference 20 / 30, multi-session 69 / 121. A second judge agreed on 100 of 100 re-judged verdicts. Not the same reader as the GPT-4o numbers most projects publish |
| LoCoMo, someone else's conversations and labels ([set 10](docs/DENSE-OPTIN.md#locomo-set-10-someone-elses-conversations-and-labels); KRouter at `main`, 2026-10-30; English only) | Evidence session cited first for 991 / 1,540 answerable questions, among the top three for 1,204; **37 of 446 adversarial questions refused**. Plain BM25: 968 first, 1,257 in the top three |
| Refuses instead of guessing (public benches, CI) | Off-topic questions refused 12/12 (English) and 6/6 (Chinese) |
| Wrong citations on a vault nobody tuned on ([third bench](docs/BENCHMARK.md#third-bench-200-held-out-questions-on-a-vault-nobody-tunes-on-2026-10-13), 200 held-out questions, English and Chinese, with daily-log distractors; 95% intervals) | At its default: KRouter 26% [19, 33] wrong, 47 / 80 neighbour questions refused, 102 / 120 answerable right; plain full-text search 58% [52, 65]. **Against a careful baseline it is level, not ahead:** plain search with the same two rules (leave replaced pages out, refuse below a floor: a minimum match score) at the same coverage cites 42 wrong pages to KRouter's 36 and gets 96 right to 102, but neither difference is significant (paired intervals: wrong rate [-10.2, +1.3] points, right [-2, +14]). On the same 200 questions at their defaults, claude-mem 13.39 cites a wrong page 64% of the time [58, 71] and basic-memory 0.23 78% [72, 84]; neither refuses any of the 80 neighbour questions; of 60 questions about a changed decision they get 34 and 16 right, KRouter 50 |
| Scale ([`BENCHMARK.md` → Scale](docs/BENCHMARK.md#scale-how-big-a-vault-can-get-2026-11-09); synthetic vaults, Apple M2 laptop) | The team server over HTTP: 10,000 pages 13 ms per lookup (median), 301 answers/s with 32 callers; 50,000 pages 54 ms, 75/s; 16 callers right after 200 pages changed: no errors, 0.14 s median. One lookup in its own process: 0.13 s at 10,000 pages, 0.35 s at 50,000 |
| Exact match vs embeddings on a supersede / neighbor set (CI) | Exact match refuses where TF-IDF, MiniLM and BGE-M3 cite a neighbor. Local embeddings as an opt-in tier: measured, not shipped ([`DENSE-OPTIN.md`](docs/DENSE-OPTIN.md)) |
| Real traffic, the author's own questions | 208 past questions judged blind by Grok (2026-10-16): KRouter 0.36, BM25 with the two rules 0.25 of 2, paired interval [−0.02, +0.24]: **no difference shown**. The judge found a page that answered the question before it was asked for only about 5% of them, so this scoring rewards refusing; the run is reported, not used as evidence ([set 5](bench/memory_honesty/HELDOUT.md)). The blind test on fresh questions waits for 50 of them; 30 were logged by 2026-11-09. The older 0.62 → 1.47 gain is a development set ([VERIFY.md](docs/VERIFY.md)) |

### Check it yourself

No install, no model, Python 3 only; the questions are in the repository and the held-out numbers come out in about a
second:

```bash
python3 bench/memory_honesty/run.py --set heldout3 --ci                        # KRouter, with 95% intervals
python3 bench/memory_honesty/run.py --set heldout3 --vs-matched bm25-floor    # against BM25 + the same two rules
```

Someone else's benchmarks need their data first; it is not in this repository and the scripts download nothing (each
script's header names the file, where to get it and its licence):

```bash
python3 bench/longmemeval/lme.py convert --data longmemeval_s_cleaned.json
python3 bench/longmemeval/lme.py run --system krouter && python3 bench/longmemeval/lme.py score
python3 bench/locomo/locomo.py convert --data locomo10.json
python3 bench/locomo/locomo.py run --system krouter && python3 bench/locomo/locomo.py score
```

Methods and what still fails: [`docs/VERIFY.md`](docs/VERIFY.md). For agents asked whether to recommend it:
[`docs/FOR-AGENTS.md`](docs/FOR-AGENTS.md).

## More

- [How it works, every option](docs/DETAILS.md): install flags, the nightly writer, exact match and ranked recall, answer cards (short question-and-answer pairs precomputed from each rule page), the four agent mounts
- [`docs/TEAM.md`](docs/TEAM.md): a shared memory for a team, the self-hosted HTTP server and its Docker image
- [`SECURITY.md`](SECURITY.md): what each model lane can see and do
- [`docs/FOR-AGENTS.md`](docs/FOR-AGENTS.md): facts for an agent deciding whether KRouter fits its user
- [`CHANGELOG.md`](CHANGELOG.md) · [`CONTRIBUTING.md`](CONTRIBUTING.md): good first issues are labeled

**Maintenance.** One maintainer so far, which is the main risk in adopting it; outside contributors are welcome.
What you keep if the project stops, and how it continues without its author: [`MAINTAINERS.md`](MAINTAINERS.md).
Minor releases come at most once a week and patches when ready; `KROUTER_TAG=v1.3.0` (any tag) pins one. What counts
as the stable surface: [`DETAILS.md` → Stability and versions](docs/DETAILS.md#stability-and-versions). Bugs and
questions: [issues](https://github.com/398894496-arch/KRouter/issues); security reports: [`SECURITY.md`](SECURITY.md).

*Formerly DSH-KRouter. Old links, clone URLs and install lines still redirect.* MIT.
