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

**Answer accuracy, the number other projects publish.** On LongMemEval (ICLR 2025; 500 questions, each over about 50
chat sessions), a model given only the pages KRouter cites answered **400 of 500 right (80.0%, 95% interval
76.4–83.4)**. Reader and judge are Claude Sonnet 5.5 with the benchmark's own prompts; most published numbers use
GPT-4o, so they cannot be set side by side. What can be compared is the same reader given something else:

| The reader is given | Right, of 500 | Of the 470 answerable |
|---|---|---|
| nothing | 30 (6.0%) | 0 |
| plain keyword search (BM25), its top three sessions | 405 (81.0%, 77.4–84.4) | 376 |
| the pages KRouter cites, three at most | 400 (80.0%, 76.4–83.4) | 371 |
| the benchmark's own answer sessions: perfect retrieval | 492 (98.4%, 97.2–99.4) | 462 |

Three things follow. The reader knows none of the answers by itself, so the 80% comes from what was retrieved.
**KRouter's lookup is level with plain keyword search, not ahead**: −1.0 points (paired interval −2.8 to +0.8). And
**the 18 points still missing are lost in retrieval, not by the reader** (+18.4 with perfect retrieval, 15.0 to
21.8), mostly on questions that add up several sessions (69 → 117 of 121) or reason about dates (97 → 125 of 127),
where three pages miss a session ([set 11](bench/memory_honesty/HELDOUT.md#set-11-longmemeval-answer-accuracy-scored-the-way-other-projects-report-it-registered-2026-11-09-before-any-run), [set 12](bench/memory_honesty/HELDOUT.md#set-12-the-same-reader-given-different-things-registered-2026-11-09-before-any-run); every reply and verdict in
[`bench/longmemeval/results/`](bench/longmemeval/results/)).

**Finding the page**, scored from the benchmark authors' own labels with no model judge. LongMemEval: an answer
session is among the cited pages for 439 of 470 answerable questions (BM25: 447), and for 70 of 72 questions whose
fact changed later the newest one is cited. LoCoMo (ACL 2024; 1,986 questions over 10 long conversations): the first
page cited holds the evidence for 991 of 1,540 answerable questions (BM25: 968).

**Where it is weak:** a question about a near neighbour of something the memory does mention still gets an answer.
It refuses 3 of 30 LongMemEval questions that have no answer, and 37 of 446 LoCoMo trick questions.

**On our own 200 held-out questions** (English and Chinese, never tuned on, written by Claude Opus in separate
sessions): KRouter cites a wrong page 26% of the time; claude-mem 64%, basic-memory 78%. Of 80 questions the memory
cannot answer, it refuses 47; the other two refuse none. Of 60 about a decision that was later changed, it gets 50
right; they get 34 and 16. Part of that gap is by construction: plain full-text search given KRouter's two rules
(leave replaced pages out, refuse a weak match) is level with it.

**So what KRouter adds is not a better ranker.** It is those two rules on by default, a receipt with each answer (the
page it came from, why that page, how sure), and a memory you can open and edit.
[Every number and its method](#honest-numbers) · [rerun them](#check-it-yourself) · [words used here](#words-used-here)

## Install

```bash
curl -fsSL https://github.com/398894496-arch/KRouter/releases/latest/download/bootstrap.sh | sh
```

Windows (PowerShell): `irm https://github.com/398894496-arch/KRouter/releases/latest/download/bootstrap.ps1 | iex` · Claude Code plugin: `/plugin install krouter --marketplace 398894496-arch/KRouter` ([versions, updating](docs/DETAILS.md#the-claude-code-plugin)).

Rather look first? Nothing below changes your machine until the last line:

```bash
git clone https://github.com/398894496-arch/KRouter.git && cd KRouter
./scripts/first_run.sh                      # a receipt on the bundled sample vault
python3 scripts/bootstrap.py --dry-run      # every change the install would make, made nowhere
python3 scripts/bootstrap.py --vault ~/notes --no-timer   # install against your vault, nightly job off
```

Python 3 is the only requirement, and the installer asks nothing. It makes a memory folder (or uses yours with
`--vault`, overwriting nothing), connects every app on [the list below](#works-with) that it finds, and imports the
last 7 days of agent sessions as pages: locally, redacted, with no model call, each one listed in the change ledger
and undoable. From then on it remembers by itself, turn by turn, in Claude Code, Codex and Cursor, and nothing leaves
the machine. `--no-import` installs lookup only; `--ask` asks first, and is how you turn on the two steps that send
text out: distilling with your model, and the nightly job.

## Works with

One install wires every app it finds, writing each app's own MCP settings in the format that app documents. It keeps
the rest of the file and a copy of it, never touches a file it cannot parse or a `krouter` entry it did not write,
and `uninstall.sh` takes out only its own entries.

| App | How it connects | Status |
|---|---|---|
| Claude Code | plugin (session hooks) and MCP, both added by the installer | tested |
| Codex | MCP, and session hooks in `~/.codex/hooks.json` (trust them once with `/hooks`) | MCP tested through the command line agent (`codex exec`, codex-cli 0.155.0-alpha.9.2, 2026-11-09): tools found, an answer with its page, a refusal; hooks tested in the same version (the correction typed in a prompt was noted, the turn-end and session-end imports ran). The desktop Codex app: not tested |
| Cursor | rule and skill, MCP (`~/.cursor/mcp.json`), and session hooks (`~/.cursor/hooks.json`) | rule and skill tested; through the Cursor agent CLI (2026.11.05-86047df, 2026-11-09) the project-level MCP entry was found, approved and its three tools listed; answering, refusing and the hooks: not tested (no usable account); the desktop app: not tested |
| DeepSeek Harness | plugin (`dsh plugin --profile web add github:398894496-arch/KRouter`) | tested |
| Claude Desktop 4.23118.1 | MCP: the installer writes `claude_desktop_config.json`; restart the app once | the entry was written and the server started from that very entry, listing its three tools, outside the app (2026-11-09); not yet asked inside the app: Claude Desktop reads its settings only at launch |
| VS Code (Copilot) · GitHub Copilot CLI · Gemini CLI · Kiro · Zed · Cline CLI | MCP: the installer writes each app's settings file; restart the app once | settings checked by tests against each app's documented format; not yet tested inside the apps |
| Agent frameworks: LlamaIndex, LangChain / LangGraph, OpenAI Agents SDK, Pydantic AI, Google ADK, CrewAI, Vercel AI SDK | a LlamaIndex retriever; the others through their own MCP client: [`docs/FRAMEWORKS.md`](docs/FRAMEWORKS.md) | all tested against the server, in CI; three of them through their whole agent loop |
| Any other app that runs a local MCP server (Windsurf, opencode, Continue, Roo Code, …) | add the server below to the app's MCP settings | should work, not yet tested by us: [tell us](https://github.com/398894496-arch/KRouter/issues) |
| A team | a self-hosted HTTP server: [Running it for a team](#running-it-for-a-team) | tested with Claude Code, the MCP Python SDK and the JS client over HTTP |
| Apps that only take a remote MCP server | the same HTTP server, behind HTTPS | should work, not yet tested by us |
| Your own code | a Python package and `krouter` command; a dependency-free JavaScript / TypeScript client (below) | tested |

```json
{ "mcpServers": { "krouter": { "command": "python3",
    "args": ["/Users/you/.agents/skills/krouter-obsidian/scripts/mcp_server.py"] } } }
```

Use the full path to your home folder (on Windows, `C:\\Users\\you\\.agents\\…` and often `python`). The server is
standard-library Python over stdio with three tools: `krouter_ask` and `krouter_status` read; `krouter_note` lets
your AI write one line down (a decision, a correction, a fact). A note lands on that day's notes page as a clue,
never on a rule page, as one git commit you can revert.

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

Rerun it, and setup, tokens and TLS: [`docs/TEAM.md`](docs/TEAM.md).

## Five minutes later

1. Ask your AI: *"what did we decide about X last week?"* It answers from the memory, names the page, and says plainly when the memory has nothing on it.
2. Open the memory folder: the imported sessions are already there, one page each, with your questions and each turn's closing answer.
3. **"Have your model pull out what was decided?"** On a yes, the model you already use (a logged-in CLI or an API key) writes "what was decided, what changed" at the top of each recent session's page. The installer tells you how many characters that sends before it sends anything.

## It keeps up on its own

Nothing needs maintaining, and nothing waits for a yes except the two steps that send text to a model:
- **After every turn**, in Claude Code, Codex and Cursor, the session so far is written to its page when the agent
  finishes answering (locally, no model call, under a second), so another window's agent can already find it.
- **When you correct your AI**, a line that reads like a correction ("from now on…", "改成…") is written down the
  moment you send it. A new session starts with this repository's recorded decisions, corrections first, each with
  its page.
- **Every night** (the job asks first) yesterday's sessions are distilled and the memory is tidied; an optional timer
  also catches up during the day.
- **Nothing is hidden.** Every run writes what it added and replaced to the [change ledger](#words-used-here); in a
  git repository each run is one commit, and `import_sessions.py --undo <run>` takes it back.
- **Keep a session out** by putting `#nocapture` (or `#不记`) in any question of it.

**On the maintainer's own machine**, 2026-10-30 → 11-09, every number from its own change ledger
([method and tables](docs/AUTO_CAPTURE.md#5-back-test-on-the-maintainers-machine-2026-10-30--11-09)):

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/capture-days-dark.svg">
  <img alt="Lines written to memory per day, 2026-10-30 to 11-09: 714 in all, 407 of them a change of mind" src="docs/img/capture-days-light.svg" width="760">
</picture>

30 runs wrote 714 lines, 407 of them a change of mind ("was A → now B"), each naming its session; none had to be
undone. Of 8 corrections the maintainer also wrote down by hand, 5 were in the memory by the next run: the distill
missed 2, and 1 was about the agent's own tool use, which import does not see. On the public decision-capture bench
(14 labelled decisions across 18 sessions, 4 of them with nothing decided; scored by rule) it found all 14 and wrote
no false line. A small set: it shows the distill does not invent decisions, not that it never misses one.

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

## How it is different

| | KRouter | Typical agent memory |
|---|---|---|
| Where memory lives | Markdown pages you can open, edit, diff and sync | A database or vector store |
| After a correction | The new page replaces the old one, which is marked superseded | Old and new chunks both match; you hope the right one wins |
| When nothing matches | `recall: none` — your AI says the memory does not know | The nearest chunk, presented with confidence |
| Every answer | Carries its source page and a receipt | Usually unsourced |
| Who shares it | Every AI app on the machine reads the same folder (MCP, skill, rules) | Usually one tool |

**Coming from [claude-mem](https://github.com/thedotmack/claude-mem)?** Keep it. The installer finds its memory and
offers to import it (run end to end against claude-mem 13.35.0): session summaries become pages, each project's
decisions become one page, and your model can sort those into the ones still in force and the ones a later decision
replaced. Nothing is imported until you say yes ([details](docs/DETAILS.md#importing-what-you-already-have)).

## What leaves your machine

Queries never do: lookup is a local SQLite full-text index, about 110 ms. Session import is local. Text goes to a
model only for the two steps you said yes to (distilling sessions, nightly upkeep), to the CLI or API key you already
use, and `--dry-run` shows the size first. Keys and pages marked secret are never sent or quoted. What each model
lane can read: [`SECURITY.md`](SECURITY.md).

**Backups.** `backup.py init --dir <a folder that syncs elsewhere>` turns on a nightly encrypted archive of the whole
vault, history included; KRouter itself talks to no cloud ([details](docs/DETAILS.md#backing-up-your-vault)).

## Words used here

| Word | What it means here |
|---|---|
| memory, vault | The folder of Markdown pages ("vault" is Obsidian's word for it) |
| page | One Markdown file. A *rule page* states a standing decision and is answered from first; a day's *notes page* is only a clue |
| receipt | The lines that come with each answer: the page it came from, why that page, how sure |
| `recall: none` | The reply when nothing matches well enough; your AI is told to say it does not know |
| floor | The minimum match score, below which KRouter refuses instead of citing the nearest page |
| superseded | Replaced by a later correction: kept, marked, and left out of answers |
| distill | A model writes "what was decided, what changed" at the top of a session's page. It sends text out, so it asks first |
| change ledger | The page in the memory that lists what every run added and replaced. Default folder names are Chinese; a `krouter-zones.psv` at the vault root maps them to yours |
| bank | One memory on a team server, with its own address, index and token |
| session hook | A command an app runs when a session starts or a turn ends; this is how turns get recorded |
| MCP | Model Context Protocol, the standard way AI apps load outside tools |
| BM25 | The standard keyword-search ranking, used here as the plain baseline |
| held-out | Questions never used to tune anything |

## Honest numbers

Every number on this page, with its set, version, baseline and the result that did not go our way, is one table in
[`docs/NUMBERS.md`](docs/NUMBERS.md); the sets were registered in
[`HELDOUT.md`](bench/memory_honesty/HELDOUT.md) before their runs. What the sections above leave out:

| Measured | Result |
|---|---|
| Answer accuracy by question type ([set 11](bench/memory_honesty/HELDOUT.md#set-11-longmemeval-answer-accuracy-scored-the-way-other-projects-report-it-registered-2026-11-09-before-any-run)) | single-session 61 / 64 (user) and 55 / 56 (assistant), knowledge update 69 / 72, temporal 97 / 127, preference 20 / 30, multi-session 69 / 121. A second judge agreed on 100 of 100 re-judged verdicts |
| Where the 93 questions lost to perfect retrieval went ([set 12](bench/memory_honesty/HELDOUT.md#set-12-the-same-reader-given-different-things-registered-2026-11-09-before-any-run)) | KRouter had cited some but not all of the answer sessions for 58, none for 32, all for 3; 24 need more than three sessions |
| Off-topic questions (public benches, CI) | refused 12 / 12 (English) and 6 / 6 (Chinese) |
| Against a careful baseline ([200 held-out questions](docs/BENCHMARK.md#third-bench-200-held-out-questions-on-a-vault-nobody-tunes-on-2026-10-13)) | plain search given the same two rules cites 42 wrong pages to KRouter's 36 and gets 96 right to 102; neither difference is significant |
| One lookup in its own process ([scale](docs/BENCHMARK.md#scale-how-big-a-vault-can-get-2026-11-09)) | 0.13 s at 10,000 pages, 0.35 s at 50,000 |
| Exact match vs embeddings (CI) | exact match refuses where TF-IDF, MiniLM and BGE-M3 cite a neighbour; local embeddings are measured, not shipped ([`DENSE-OPTIN.md`](docs/DENSE-OPTIN.md)) |
| The author's own 208 past questions, judged blind | KRouter 0.36, BM25 with the two rules 0.25 of 2, paired interval [−0.02, +0.24]: no difference shown |

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

- [How it works, every option](docs/DETAILS.md): install flags, the nightly writer, exact match and ranked recall, the four agent mounts
- [`docs/NUMBERS.md`](docs/NUMBERS.md): every number with its method
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
