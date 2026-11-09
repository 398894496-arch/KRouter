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

## Measured, not claimed

**On other people's benchmarks**, scored from their authors' own labels, no model judge:
- **LongMemEval** (ICLR 2025; 500 questions, each over about 50 chat sessions): for 439 of 470 answerable questions an
  answer session is among the pages KRouter cites; for 70 of 72 questions whose fact changed later, it cites the
  newest one.
- **LoCoMo** (ACL 2024; 1,986 questions over 10 long conversations): the first page cited holds the evidence for 991
  of 1,540 answerable questions, and one of the top three does for 1,204.

These count whether the right page was found, not whether a model then answered correctly, so they do not line up with
the answer-accuracy percentages other projects publish. Plain BM25 finds about as many pages (447 / 470, 968 / 1,540).

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
curl -fsSL https://raw.githubusercontent.com/398894496-arch/KRouter/main/scripts/bootstrap.sh | sh
```

The line downloads a short script; the script installs the latest release (a tag, never `main`) after checking its
SHA-256, so what runs is a published, checksummed version.

Windows (PowerShell): `irm https://raw.githubusercontent.com/398894496-arch/KRouter/main/scripts/bootstrap.ps1 | iex` · Claude Code plugin: `/plugin install krouter --marketplace 398894496-arch/KRouter` (Claude Code 2.1.275 or later; from a shell, `claude plugin install krouter --marketplace 398894496-arch/KRouter` needs 2.1.292). Third-party marketplaces do not auto-update: run `claude plugin update krouter@krouter`, or turn it on in `/plugin` → Marketplaces → krouter → Enable auto-update.

Rather look first? Nothing below changes your machine until the last line:

```bash
git clone https://github.com/398894496-arch/KRouter.git && cd KRouter
./scripts/first_run.sh                      # a receipt on the bundled sample vault
python3 scripts/bootstrap.py --dry-run      # every change the install would make, made nowhere
python3 scripts/bootstrap.py --vault ~/notes --no-timer   # install against your vault, nightly job off
```

Python 3 is the only requirement. The installer makes a memory folder (or uses yours with `--vault`, overwriting
nothing), connects Claude Code and Codex to it through MCP when they are installed, and stops there: lookup only, no
questions, nothing leaves the machine. Another app? See [Works with](#works-with). When you want it to start
remembering, run the line it prints last (`bootstrap.py --ask`), which asks two questions.

## Works with

| App | How it connects | Status |
|---|---|---|
| Claude Code | plugin, or MCP (the installer registers it) | tested |
| Codex | MCP (the installer registers it) | tested |
| Cursor | rule and skill (the installer adds them) | tested |
| DeepSeek Harness | plugin (`dsh plugin --profile web add github:398894496-arch/KRouter`) | tested |
| A team: one shared memory for several people | a self-hosted server over HTTP (`mcp_server.py --http`, or the Docker image `ghcr.io/398894496-arch/krouter`), token required: [`docs/TEAM.md`](docs/TEAM.md) | tested with Claude Code over HTTP |
| Apps that only take a remote MCP server | the same HTTP server, behind HTTPS | should work, not yet tested by us |
| Claude Desktop | MCP: the installer adds KRouter to its MCP settings when the app is installed (restart the app once) | settings written and checked by tests; not yet tested inside the app |
| Any other app that runs a local MCP server: VS Code, Windsurf, Zed, Gemini CLI, … | add the server below to the app's MCP settings | should work, not yet tested by us: [tell us](https://github.com/398894496-arch/KRouter/issues) |

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

**From your own code** (Python 3.9+), the same lookups, receipts and notes:

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

## Five minutes later

1. Ask your AI: *"what did we decide about X last week?"* It answers from the memory, names the page, and says plainly when the memory has nothing on it.
2. **"Import the agent sessions already on this machine?"** (with `--ask`, for Claude Code, Codex and Cursor) On a yes, the last 7 days of sessions become pages, one per session: your questions and each turn's closing answer. Key-shaped text is redacted first, and nothing leaves the machine.
3. **"Have your model pull out what was decided?"** On a yes, the model you already use (a logged-in CLI or an API key) writes "what was decided, what changed" at the top of each recent session's page. The installer tells you how many characters that sends before it sends anything.

## It keeps up on its own

Once you said yes to importing, nothing needs maintaining:
- **Every night** (the job asks first) yesterday's sessions are imported and distilled, and the memory is tidied.
- **When you correct your AI**, with the Claude Code plugin, a line that reads like a correction ("from now on…",
  "改成…") is written down the moment you send it, locally and without a model call; the next distill settles it.
  A long conversation is also recorded before it is compacted, and again when it ends.
- **During the day**, an optional timer catches today's sessions at two set times
  (`extras/host-daily-evolution/intraday_capture.py`, a macOS launchd example included).
- **Nothing waits for your approval, and nothing is hidden.** Every run writes what it added and what it replaced to
  `90 系统文件/自动化/记忆变更记录.md` (the change ledger; the default folders have Chinese names, and a
  `krouter-zones.psv` at the vault root maps them to yours). When the memory folder is a git repository (`git init` it once), each run is
  also one commit, and `import_sessions.py --undo <run>` takes it back.
- **Keep a session out** by putting `#nocapture` (or `#不记`) in any question of it.

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
Already have a vault? `--vault` changes none of its files. The default is lookup only: no nightly job, no session
import.

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
| LoCoMo, someone else's conversations and labels ([set 10](docs/DENSE-OPTIN.md#locomo-set-10-someone-elses-conversations-and-labels); KRouter at `main`, 2026-10-30; English only) | Evidence session cited first for 991 / 1,540 answerable questions, among the top three for 1,204; **37 of 446 adversarial questions refused**. Plain BM25: 968 first, 1,257 in the top three |
| Refuses instead of guessing (public benches, CI) | Off-topic questions refused 12/12 (English) and 6/6 (Chinese) |
| Wrong citations on a vault nobody tuned on ([third bench](docs/BENCHMARK.md#third-bench-200-held-out-questions-on-a-vault-nobody-tunes-on-2026-10-13), 200 held-out questions, English and Chinese, with daily-log distractors; 95% intervals) | At its default: KRouter 26% [19, 33] wrong, 47 / 80 neighbour questions refused, 102 / 120 answerable right; plain full-text search 58% [52, 65]. **Against a careful baseline it is level, not ahead:** plain search with the same two rules (leave replaced pages out, refuse below a floor: a minimum match score) at the same coverage cites 42 wrong pages to KRouter's 36 and gets 96 right to 102, but neither difference is significant (paired intervals: wrong rate [-10.2, +1.3] points, right [-2, +14]). On the same 200 questions at their defaults, claude-mem 13.39 cites a wrong page 64% of the time [58, 71] and basic-memory 0.23 78% [72, 84]; neither refuses any of the 80 neighbour questions; of 60 questions about a changed decision they get 34 and 16 right, KRouter 50 |
| Scale ([`BENCHMARK.md` → Scale](docs/BENCHMARK.md#scale-how-big-a-vault-can-get-2026-11-09); synthetic vaults, Apple M2 laptop, one process per lookup) | 1,000 pages: 0.08 s per lookup (p50), first lookup with index build 0.4 s. 10,000: 0.12 s, 4.8 s. 50,000: 0.53 s (p95 1.1 s), 24 s, 76 MB peak memory. Over HTTP, 16 parallel callers on 10,000 pages: no errors, 0.96 s median |
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
