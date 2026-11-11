# KRouter

<!-- mcp-name: io.github.398894496-arch/krouter -->

**Give your agent a subconscious: mention it and it comes to mind, with what is connected to it, and the lessons carry over.**

KRouter is a local Markdown memory for coding agents such as Claude Code, Codex and Cursor. When something you
mention was settled before, the agent recalls it, with what is connected to it; a lesson from one task is offered on
another; a change of mind replaces the old answer; every answer names the page it came from. No API key, no server.

> **You:** Going to move the clippings originals into the archive folder this afternoon.
>
> **Agent:** That note says not to move the Clippings originals (from your "User preferences" page under 02 Methods/Agent), so I'd hold off on moving them to the archive this afternoon. If you meant a copy or a different set of files, tell me and we can sort out a safe way to do it.
>
> **You:** The coffee machine on our floor is broken again.
>
> **Agent:** Sorry to hear that, it's annoying when it keeps happening. I can't fix it from here, but I can help you draft a quick message to facilities if you'd like.

You only mentioned it in passing; KRouter recognised something already settled in what you said and handed it to the
agent with the page it came from. The second remark touches nothing in the memory, so nothing was added and the
agent answered as usual. Both agent replies are real: Claude Sonnet 5.5 (a Claude Code subagent, no tools),
2026-11-10, given exactly what the collapsed block below shows, copied as it answered; with another agent, the reply
is up to that agent. "Subconscious" is a figure of speech for recall that happens without being asked: a lookup on
your machine, no model, nothing sent.

<details>
<summary>What the agent was actually handed (the prompt hook's raw output on the English sample memory)</summary>

```text
you  > Going to move the clippings originals into the archive folder this afternoon.
hook > KRouter memory note (recalled from the user's vault, not typed by the user; it may not bear on this message):
       - "clippings originals" → Do not move Clippings originals [02 Methods/Agent/User preferences.md, alias]
       If you use it, cite the page.
you  > The coffee machine on our floor is broken again.
hook > (nothing)
```

</details>

### Mention it and it comes to mind

Every message is looked up locally, and the session starts with an index of what has been settled, so the agent also
catches a thing said in other words. Held out, 24 mentions (two thirds without the page's names): **Sonnet 5.5 24 / 24,
Haiku 5.5 23 / 24**; messages that should change nothing moved it 1 / 24 and 2 / 24
([set 35](bench/memory_honesty/HELDOUT.md#set-35-the-subconscious-as-a-whole--the-prompt-hook-then-the-host-reading-a-standing-index-registered-2026-11-10-before-any-case-existed)).

### With what is connected to it

A lookup gives five pages: three that match, then up to two the memory connects to them (a link, a replacement, the
same session, rare words they share, being cited together). Held-out half of LongMemEval, five pages each: every
session the answer needs for **210 of 235 questions, keyword search 198; multi-session 40 against 31**
([set 18](bench/memory_honesty/HELDOUT.md#set-18-does-following-the-vaults-own-connections-bring-the-whole-answer-registered-2026-11-10-before-the-associative-path-was-written-or-any-held-out-question-was-run)).

### The lessons carry over

A lesson from one task is offered on another in the same situation, and lessons that keep coming back grow into
skills the agent fetches when they fit. Held out: the right lesson for **14 / 14 (Sonnet 5.5) and 11 / 14 (Haiku
5.5)** tasks with a new subject, **14 / 14 and 13 / 14** in English (sets 15, 16); skills drafted right 16 / 16 and
fetched and followed 12 / 12 (sets 24, 25; [`bench/memory_honesty/HELDOUT.md`](bench/memory_honesty/HELDOUT.md)).

### Underneath, what you can check

Every answer comes with the page it came from; when the memory does not know, the agent is told so instead of
handed something close; a correction replaces the old answer instead of competing with it; and you can see all of
it: the memory is a folder of plain Markdown you can open and edit, in [Obsidian](https://obsidian.md) or any editor,
and `krouter view` / `krouter why` show what it holds and why it answered. It works with the AI you already use, and
one is enough.

### What it does not do

- The samples are small: a few dozen cases per set.
- In these evaluations the host wrote down which page it would fetch; it did not call the tools for real.
- In real sessions hosts almost never write a lesson card on their own (0 of 4 on both hosts, sets 30 and 31):
  learning comes from the hooks and the nightly run.
- On Cursor the per-message layer is not available (its hook cannot add context); it gets the session-start index.
- Answer accuracy has not been rerun for the five-page version (set 22 is registered, not run).
- Windows was not tested for 2.0.
- In a vault with many long pages someone else wrote (web clippings, research material) that are not marked as
  clippings, a question the vault has no answer to, English ones especially, can get an unrelated hit with `medium`
  confidence instead of `recall: none`. Seen on the maintainer's own vault; a better test for it is for a later
  version. Marking such pages as clippings caps them at `low`
  ([`DETAILS.md`](docs/DETAILS.md#clipped-pages-and-other-peoples-writing)).

[![ci](https://github.com/398894496-arch/KRouter/actions/workflows/ci.yml/badge.svg)](https://github.com/398894496-arch/KRouter/actions/workflows/ci.yml) [![release](https://img.shields.io/github/v/release/398894496-arch/KRouter)](https://github.com/398894496-arch/KRouter/releases/latest) [![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE) · 中文：[`README.zh.md`](README.zh.md)

Tests run on Linux, macOS and Windows on every push. The one-line install downloads the latest release (a tag, never
`main`) and checks its SHA-256 before running anything; each release also carries a GitHub build-provenance
attestation (`gh attestation verify <package> --repo 398894496-arch/KRouter`). What you ask never leaves your machine.

![Monday we decide A, Wednesday we change it to B, Thursday the agent answers B and cites the correction; a question the vault cannot answer is refused](docs/img/demo.gif)

No key is needed to start: lookup, sources and refusals run with no model, and a change of mind still wins: the
newer page is listed first and flagged, and your agent can make a correction hold in the same turn
([what works without a model](docs/INSTALL.md#without-an-api-key)).

**See it for yourself in a few seconds, with nothing installed and no key:** the same story on a throwaway memory,
deleted afterwards.

```bash
uvx --from git+https://github.com/398894496-arch/KRouter krouter demo      # or, in a clone: PYTHONPATH=sdk python3 -m krouter.cli demo
```

| I want to… | Start here |
|---|---|
| see it answer, correct itself and refuse, before installing anything | `krouter demo` (above) |
| see what it remembers, and why it answered the way it did | [`krouter view`, `krouter why`](#see-what-it-remembers) |
| give the AI apps I already use a memory | [Install](#install): one line, asks nothing, wires every app it finds (`--minimal`: lookup only, the apps you name) |
| check which apps it connects to | [Works with](#works-with) |
| call it from my own code | [From your own code](#from-your-own-code) |
| check the numbers myself | [Check it yourself](#check-it-yourself) |
| know exactly what leaves my machine | [What leaves your machine](#what-leaves-your-machine) |

## Install

```bash
curl -fsSL https://github.com/398894496-arch/KRouter/releases/latest/download/bootstrap.sh -o /tmp/krouter-install.sh && sh /tmp/krouter-install.sh
~/.dsh-krouter/current/scripts/krouter doctor                                  # OK, or what is missing and how to fix it
~/.dsh-krouter/current/scripts/krouter search "what did we decide about X?"    # your first question
```

It asks nothing and connects the AI apps it finds. To keep the memory in a folder you already have, your Obsidian
vault for instance: `sh /tmp/krouter-install.sh --vault ~/MyVault`. An existing folder keeps every file; only missing
ones are added, and uninstalling never touches your memory. Windows, the Claude Code plugin, `--minimal`, every file it
changes, what works without a key, and uninstalling: [`docs/INSTALL.md`](docs/INSTALL.md).

Then, once, let your agent bring in your past sessions, so on day one it knows what you settled before. The first two
steps never call a model and nothing leaves the machine; the third uses your agent's subscription (at least one call
per session, the newest 40 by default, not your whole history in one go): [`docs/INSTALL.md`](docs/INSTALL.md#bring-in-your-past-sessions).

```bash
python3 ~/.agents/skills/krouter/scripts/import_sessions.py --days 3650 --dry-run --distill        # how many; writes nothing
python3 ~/.agents/skills/krouter/scripts/import_sessions.py --days 3650 --local                    # import all, no model
python3 ~/.agents/skills/krouter/scripts/import_sessions.py --days 3650 --distill --distill-max 40  # distill the newest 40
```

### From your own code

`pipx install "git+https://github.com/398894496-arch/KRouter"`, then in Python `krouter.ask("how do we ship a
release?")` gives the page, the one-line answer and whether the memory refused, and `krouter.note(…)` writes a line.
LangGraph can keep its long-term memory in the folder (`krouter.integrations.langgraph.KRouterStore`); JavaScript,
LlamaIndex and the MCP clients of other frameworks: [`docs/INSTALL.md`](docs/INSTALL.md#from-your-own-code) and
[`docs/FRAMEWORKS.md`](docs/FRAMEWORKS.md).

## Measured, not claimed

**Finding the whole answer, five pages per question.** A lookup now gives five pages: three that match the question,
then up to two the memory connects to them (a link, a replacement, the same session, rare words they share, being
cited together). On LongMemEval (ICLR 2025; 500 questions, each over about 50 chat sessions), scored from the
benchmark authors' own labels with no model, on the 235 questions held out while those connections were tuned on the
other half, **KRouter's five pages hold every session the answer needs for 210 questions; plain keyword search (BM25)
given five sessions, for 198** (12 more, paired 95% interval +3 to +21). On questions whose answer is spread over
several sessions: **40 of 47 against 31**. These are retrieval numbers: what the pages hold, not what a model answers
from them ([set 18](bench/memory_honesty/HELDOUT.md#set-18-does-following-the-vaults-own-connections-bring-the-whole-answer-registered-2026-11-10-before-the-associative-path-was-written-or-any-held-out-question-was-run)).

**Answer accuracy for the five-page version has not been measured.** The run with a reader and a judge is registered
([set 22](bench/memory_honesty/HELDOUT.md#set-22-the-same-reader-five-pages-each--keyword-search-against-krouter-with-its-associative-path-registered-2026-11-10-before-any-reader-or-judge-call)) and was not run. The answer accuracy that was measured is the previous version's, which gave three
pages (KRouter 1.3.0: 400 of 500 right with Claude Sonnet 5.5 as reader and judge, level with BM25's three); that
table, with its version and page count, is in [`docs/NUMBERS.md`](docs/NUMBERS.md#the-same-reader-three-pages-krouter-130).

**Finding the page** (earlier three-page versions), scored the same way. LongMemEval (KRouter 1.1.1): an answer
session is among the cited pages for 439 of 470 answerable questions (BM25: 447), and for 70 of 72 questions whose
fact changed later the newest one is cited. LoCoMo (ACL 2024; 1,986 questions over 10 long conversations): the first
page cited holds the evidence for 991 of 1,540 answerable questions (BM25: 968).

**Where it is weak:** a question about a near neighbour of something the memory does mention still gets an answer.
Its refusal gate turns down 9 of 30 LongMemEval questions that have no answer (set 14; the "3 of 30" quoted
before was 1.1.1), and 37 of 446 LoCoMo trick questions. On LoCoMo's
short conversations the two connected pages cost more than they bring: the five pages hold every evidence session for
1,185 of 1,536 questions, five pages of direct matches would for 1,204.

**On our own 200 held-out questions** (English and Chinese, never tuned on, written by Claude Opus in separate
sessions): KRouter cites a wrong page 26% of the time; claude-mem 64%, basic-memory 78%. Of 80 questions the memory
cannot answer, it refuses 47; the other two refuse none. Of 60 about a decision that was later changed, it gets 50
right; they get 34 and 16. Part of that gap is by construction: plain full-text search given KRouter's two rules
(leave replaced pages out, refuse a weak match) is level with it.

**So what KRouter adds** is a lookup that follows the memory's own connections (the lead above, at five pages; on
the first page cited it is level with plain search given the two rules), those two rules on by default, a receipt with
each answer (the page it came from, why that page, how sure), and a memory you can open and edit.
[Every number and its method](#honest-numbers) · [rerun them](#check-it-yourself) · [words used here](#words-used-here)

## Works with

One install wires every app it finds, writing each app's own MCP settings in the format that app documents. It keeps
the rest of the file and a copy of it, never touches a file it cannot parse or a `krouter` entry it did not write,
and `uninstall.sh` takes out only its own entries.

| App | How it connects | Status |
|---|---|---|
| Claude Code | plugin (session hooks) and MCP, both added by the installer | tested; in real sessions a Claude Sonnet 5.5 subagent given the same tool descriptions through a shell helper (not the MCP server) called `krouter_correct` on 3 of 4 decision changes and `krouter_learn` on 0 of 4 solved problems ([`VERIFY.md`](docs/VERIFY.md#platforms-and-real-sessions-200-candidate-2026-11-10)) |
| Codex | MCP, and session hooks in `~/.codex/hooks.json` (trust them once with `/hooks`) | tested (command line, codex-cli 0.155.0-alpha.9.2, 2026-11-09): the MCP tools found, an answer with its page, a refusal; the hooks noted a typed correction and ran the turn-end and session-end imports. The CLI and the IDE extension share one configuration (Codex docs) Real sessions, 20 small tasks (2026-11-10, [`VERIFY.md`](docs/VERIFY.md#platforms-and-real-sessions-200-candidate-2026-11-10)): it mentioned the digest's lesson when the situation matched (2 of 4) and never when it did not (0 of 12); it did not call `krouter_learn` or `krouter_correct` by itself (0 of 4 each), because this Codex version shows the model no krouter tool. The session hook now names both tools; that change could not be checked on Codex (its usage limit ran out) |
| Cursor | rule and skill, MCP (`~/.cursor/mcp.json`), and session hooks (`~/.cursor/hooks.json`) | rule and skill tested; the rest tested in the Cursor agent CLI 2026.11.05-86047df (2026-11-09): the MCP entry found, its tools listed, an answer with its page, a refusal; the turn-end and session-end hooks wrote the session pages. The CLI and the editor read the same MCP configuration (Cursor docs). A difference seen: the CLI's non-interactive mode did not run `beforeSubmitPrompt`, so a typed correction is not noted there Three real tasks in the agent CLI (free account, `auto`, 2026-11-10): it looked the tools up itself and called `krouter_correct` on a decision change; it did not call `krouter_learn` after fixing a Makefile |
| DeepSeek Harness | plugin (`dsh plugin --profile web add github:398894496-arch/KRouter`) | tested |
| Claude Desktop | an extension: double-click [`KRouter.mcpb`](https://github.com/398894496-arch/KRouter/releases/latest/download/KRouter.mcpb) and press Install once (no settings file, no restart; the app checks the extension online for a few seconds before anything shows). Or the installer writes its settings file, but only while the app is closed: Claude Desktop keeps its settings in memory and writes the whole file back when it quits, so an entry written while it is open is gone after a restart. Found running, the installer leaves the file alone and builds the extension for your memory folder instead | **extension tested inside the app** (Claude Desktop 4.23118.1, macOS, 2026-11-10): installed with one press, no restart; its 3 tools connected; in an ordinary chat a question was answered with its source page and an unknown one refused (`recall: none`). Tested with a build that names the full Python path, as the installer's does; the release file's plain `python3` takes another launch path in the app, not yet tested. The settings file is checked by tests |
| VS Code (Copilot) · GitHub Copilot CLI · Gemini CLI · Kiro · Zed · Cline CLI | MCP: the installer writes each app's settings file; restart the app once | settings checked by tests against each app's documented format; not yet tested inside the apps |
| LangGraph long-term memory (no MCP) | `krouter.integrations.langgraph.KRouterStore`, a `BaseStore`: per-user and per-thread namespaces as folders of Markdown pages, cited and refusing: [`docs/FRAMEWORKS.md`](docs/FRAMEWORKS.md#langgraph-store-long-term-memory) | tested in real graphs (langgraph 1.0 and 1.2), in CI; not on PyPI yet |
| Agent frameworks: LlamaIndex, LangChain / LangGraph, OpenAI Agents SDK, Pydantic AI, Google ADK, CrewAI, Vercel AI SDK | a LlamaIndex retriever; the others through their own MCP client: [`docs/FRAMEWORKS.md`](docs/FRAMEWORKS.md) | all tested against the server, in CI; three of them through their whole agent loop |
| Any other app that runs a local MCP server (Windsurf, opencode, Continue, Roo Code, …) | add the server below to the app's MCP settings | should work, not yet tested by us: [tell us](https://github.com/398894496-arch/KRouter/issues) |
| Your own code | a Python package and `krouter` command; a dependency-free JavaScript / TypeScript client (below) | tested |

```json
{ "mcpServers": { "krouter": { "command": "python3",
    "args": ["/Users/you/.agents/skills/krouter/scripts/mcp_server.py"] } } }
```

Use the full path to your home folder (on Windows, `C:\\Users\\you\\.agents\\…` and often `python`). The server is
standard-library Python over stdio with three tools: `krouter_ask` and `krouter_status` read; `krouter_note` lets
your AI write one line down (a decision, a correction, a fact). A note lands on that day's notes page as a clue,
never on a rule page, as one git commit you can revert.

## Five minutes later

1. Ask your AI: *"what did we decide about X last week?"* It answers from the memory, names the page, and says plainly when the memory has nothing on it.
2. Open the memory folder: each session since the install is there, one page each, with your questions and each turn's closing answer (the install's last lines give the one command that brings in the last 7 days too).
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

## See what it remembers

Nothing is hidden, and there is a page to look at it with. Both commands only read.

```bash
krouter why "when do we ship releases"    # how that lookup came out, in words
krouter view                              # a page on this machine only: prints http://127.0.0.1:<port>/, opens nothing
krouter view --demo                       # the same page on a throwaway sample memory (add --open to open it in your browser)
```

![krouter view, "Try a sentence": two pages say different things about the billing database; the newer one is moved first and the conflict is named, with each page's matched words, score and tier](docs/img/view-why.png)

`why` says which alias or words matched, why each page sits where it does, why the confidence is that one, which pages came along a connection and from which page, which page replaced which, and, when the memory does not know, which word it could not find. `view` adds the pages with search (it pages through tens of thousands), the connections around a page with why each one exists, the experience cards with how often each was offered and taken, what the last nights did, and a box that runs `why`. It listens on 127.0.0.1 only, answers GET only so nothing in it can change the memory, loads nothing from the internet, and works in English and Chinese, light and dark, on a phone-width screen. [How to read it](docs/DETAILS.md#see-what-it-remembers-krouter-why-and-krouter-view).

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
| Answer accuracy by question type, KRouter 1.3.0 at three pages ([set 11](bench/memory_honesty/HELDOUT.md#set-11-longmemeval-answer-accuracy-scored-the-way-other-projects-report-it-registered-2026-11-09-before-any-run)) | single-session 61 / 64 (user) and 55 / 56 (assistant), knowledge update 69 / 72, temporal 97 / 127, preference 20 / 30, multi-session 69 / 121. A second judge agreed on 100 of 100 re-judged verdicts |
| Where the 93 questions lost to perfect retrieval went, three pages ([set 12](bench/memory_honesty/HELDOUT.md#set-12-the-same-reader-given-different-things-registered-2026-11-09-before-any-run)) | KRouter had cited some but not all of the answer sessions for 58, none for 32, all for 3; 24 need more than three sessions |
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
Minor releases come at most once a week and patches when ready; `KROUTER_TAG=v2.0.0` (any tag) pins one. What counts
as the stable surface: [`DETAILS.md` → Stability and versions](docs/DETAILS.md#stability-and-versions). Bugs and
questions: [issues](https://github.com/398894496-arch/KRouter/issues); security reports: [`SECURITY.md`](SECURITY.md).

*Formerly DSH-KRouter. Old links, clone URLs and install lines still redirect.* MIT.
