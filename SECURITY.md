# Security

<!-- krouter-status:start (source: docs/STATUS.md; run scripts/sync_status.py) -->
> **Current status of `main` (latest release v2.1.0, 2026-11-11). Measured, and what is not.** One-line installs get
> the latest release; anything under "Unreleased" in CHANGELOG.md is on `main` only. Every fact an evaluating agent
> needs, with sources: [`docs/FOR-AGENTS.md`](https://github.com/398894496-arch/KRouter/blob/main/docs/FOR-AGENTS.md).
> - **Held-out bench** (200 questions on a synthetic 110-page vault, never tuned on; *not* real traffic): KRouter 26%
>   wrong citations, 47 of 80 unanswerable questions refused, 102 of 120 answerable right. At their defaults claude-mem
>   64% and basic-memory 78%, 72 and 45 right; neither can refuse. BM25 given KRouter's two rules (skip replaced
>   pages, refuse a weak match) is level with KRouter: the lead is those rules being on by default, not the ranker.
> - **Answer accuracy** (LongMemEval S, the number other projects publish; measured on 1.3.0, which gave three pages):
>   400 of 500 right, 80.0% [76.4, 83.4], with KRouter's top three pages as the only context; reader and judge Claude Sonnet 5.5 with the benchmark's own
>   prompts, not the GPT-4o most projects use. Weakest on questions that add up several sessions (69 of 121).
>   The same reader given plain BM25's top three sessions gets 405 right (81.0%): no difference shown (paired −1.0
>   points [−2.8, +0.8]); given nothing it gets 0 of the 470 answerable. On this benchmark the lookup is level with
>   BM25, not ahead. Given the benchmark's own answer sessions (perfect retrieval) the reader gets 492 (98.4%), so
>   the missing 18 points [15.0, 21.8] are lost in retrieval, not by the reader. 2.0 gives five pages, two of them
>   ones the vault connects to the hits: every answer session among them for 210 of 235 held-out questions (BM25's
>   top five 198), multi-session 40 of 47 (31) ([set 18](https://github.com/398894496-arch/KRouter/blob/main/bench/memory_honesty/HELDOUT.md)).
>   Answer accuracy at five pages is not measured yet (set 22, registered).
> - **Someone else's benchmarks** (scored from the authors' labels, no model judge): LongMemEval S, an answer session
>   cited for 439 of 470 answerable questions (1.x, three pages); 9 of 30 unanswerable refused by the gate (set 14; the
>   "3 of 30" quoted before was 1.1.1; with a reader model on top, 29 of 30 are answered "not mentioned", but the same
>   reader given nothing says so for all 30, so that layer is mostly the model's: [`NUMBERS.md`](https://github.com/398894496-arch/KRouter/blob/main/docs/NUMBERS.md)); LoCoMo, evidence first for 991 of 1,540,
>   37 of 446 adversarial refused. Page found, not answer accuracy; plain BM25 finds about as many.
> - **Real-traffic blind test on fresh queries** ([VERIFY.md](https://github.com/398894496-arch/KRouter/blob/main/docs/VERIFY.md)
>   layer 4): not run yet; it waits for 50 new queries (30 logged by 2026-11-09).
> - **Who wrote the held-out questions:** Claude Opus in separate claude.ai sessions, not a person. A person-written
>   set is planned.
> - **Lessons across tasks** (held-out; the host model judges from a digest of the cards): the right lesson offered on
>   14 / 14 (Sonnet 5.5) and 11 / 14 (Haiku 5.5) Chinese tasks with a new subject, 14 / 14 and 13 / 14 in English,
>   none of the 14 quiet tasks disturbed; cards the agent writes itself passed on set 23 (13 / 16, faithful 92%).
> - **Releases:** 2.1.0 (2026-11-11, the bullet after this one); 2.0.0 (2026-11-10): mention something and the agent recalls what was settled about it; lessons carry
>   over between tasks and grow into skills; five pages with the ones the vault connects; a change of mind holds
>   with no key; a lighter install that is English end to end; the router moved to `skill/krouter` (an older
>   install's path is left as a link on upgrade). Minor releases at most once a week, patches when ready;
>   `KROUTER_TAG` pins one.
> - **New in 2.1.0 (2026-11-11):** a knowledge-base layer: folders declared in `krouter-kb.txt` (and clippings,
>   as before) are reference material, listed apart under `knowledge_base:` and never setting the confidence; when only
>   they match, the receipt starts `memory: none` (tests, and set 37's synthetic set). `krouter kb add / suggest /
>   import` (PDF, Word, HTML with a converter already on the machine). A rule to refuse more near misses was studied
>   on development data (set 37) and **not shipped**: none of 216 candidates refused 10 more within a 1-point loss
>   (the best: 3), so the refusal numbers above are unchanged. Instead the receipt's first line says `memory: direct`,
>   `related` (only related pages) or `none` (LongMemEval's 30: 0 / 21 / 9); an optional strict mode treats `related`
>   as `none` and on session-only memories answers almost nothing (set 38). Also: the README's team section and two-layer refusal
>   numbers, and a `recall_note:` naming question words the top page never uses (its effect **not measured**).
> - **Team server** (self-hosted; no KRouter cloud): several isolated memories per server, a token each, Prometheus
>   `/metrics`; Docker, Compose, Kubernetes and systemd files. Over HTTP on one M2 laptop: 10,000 pages 13 ms a lookup
>   and 301 answers/s with 32 callers, 50,000 pages 54 ms and 75/s (synthetic vaults, `bench/scale/serve_load.py`).
>   The Kubernetes manifest and systemd unit are checked by tests, not yet run on a cluster or host.
> - **Install and capture:** the one-line install asks nothing, connects every app it finds (Claude Code with its
>   plugin, Codex, Cursor, Claude Desktop, VS Code, Copilot CLI, Gemini CLI, Kiro, Zed, Cline CLI), lists every settings
>   file it changed (a copy of each kept), and imports nothing from the past (`--all` imports the last 7 days, locally,
>   no model call; `--minimal` is lookup only and connects only the apps you name). From then on, Claude Code, Codex and Cursor each
>   record every turn as it ends through their session hooks (local, no model call; Codex runs them once you trust them
>   in `/hooks`; Cursor's run in its agent CLI, where a typed correction is not noted). Distilling with a model and the nightly job
>   ask first (`--ask`). The manual `install.sh` installs the job (`KROUTER_NO_TIMER=1` skips). Queries never leave the machine.
> - **Nightly writer lanes:** an API key runs nothing locally; grok (kernel sandbox) and claude (tool allow-list) are
>   limited to the vault; Codex can read the whole account and writes only the vault, so it is used only when you name
>   it or set `KROUTER_ALLOW_CODEX=1`; other CLIs are unconfined and are never picked unless you set
>   `KROUTER_ALLOW_UNCONFINED=1`.
>   [SECURITY.md](https://github.com/398894496-arch/KRouter/blob/main/SECURITY.md) has the table.
<!-- krouter-status:end -->

KRouter reads and writes a personal knowledge vault and can hold model API keys, so this page says exactly
where data goes and how to report a problem.

## Where your data goes

| Data | Where it goes | When |
|---|---|---|
| Router queries and answers | Nowhere: a local SQLite cache under `~/.cache/krouter/` and a local query log under `~/.local/state/krouter/` | Every query |
| Yesterday's logs and sessions | The model lane you chose (a logged-in AI coding CLI, or an API key) | The nightly job, only if you turned it on |
| Your past Claude Code / Codex / Cursor agent sessions (questions and closing answers, redacted) | Pages in your vault, on this machine | At install and nightly, only after you said yes to the import (`import_sessions.py --consent`; `--revoke` stops it) |
| The same session excerpts | The model lane, to write "what was decided" | Only if you also said yes to distilling; the install says how many characters first |
| claude-mem's memory (`~/.claude-mem/claude-mem.db`, opened read-only) | Pages in your vault, on this machine | Only after you said yes (`import_claude_mem.py --consent`); nightly after that |
| One project's claude-mem decisions | The model lane, to sort what is still in force | Only with distilling on |
| This repository's recent distilled decisions, corrections first | The new Claude Code session's context (plugin `SessionStart` hook): up to 8 lines, each with its page. Only pages whose recorded repository path is this one; a folder name never matches | Only with the plugin, and after you said yes to importing; `KROUTER_INJECT=0` turns it off |
| Rule and topic pages, topic excerpts, unanswered queries (with, for each, up to 4 candidate pages' first 600 characters, redacted; never secret pages or `03 资料与证据`) | The same model lane | The nightly job, only if you turned it on |
| The whole vault, `.git` included, encrypted (AES-256, HMAC, test-restored) | The backup folders you named (`KROUTER_BACKUP_DIR`), and from there wherever their sync client takes it. The passphrase stays in the keys file and is never inside an archive | Nightly, only after `backup.py init --dir` |
| API keys | `~/.dsh-krouter-keys.env` (mode 600). Never the vault, never a prompt, never printed | — |
| Pages named or marked as secret (凭据 / 密钥 / 钥匙 / credential / secret / password, or `secret: true`) | Nowhere: never sent, never quoted | — |

`extras/host-daily-evolution/run.sh --dry-run` lists what the next nightly run would send, with token estimates,
and sends nothing. The one-line install asks before it installs the nightly job; without a yes it is not installed.

**What the nightly writer can see.** It depends on the lane, and the install prompt says which one you are choosing:

| Lane | Runs on this machine | Can read | Can write |
|---|---|---|---|
| **API key (recommended)** | Nothing: a direct API call | — (KRouter sends only what `--dry-run` lists) | — |
| `grok` | grok, in a kernel-enforced sandbox profile (`strict` + the router) | The vault, the router, system paths | The vault, KRouter's cache and state |
| `claude` | Claude Code, with tools allow-listed (`dontAsk`): read / edit / glob / grep inside the vault, run the router, nothing else | The vault (tool-level rule, no kernel sandbox). Up to 1.2.0 Glob and Grep were allowed without a path, and Grep could print lines from any file in the account, keys file included | The vault |
| Codex | Codex in its `workspace-write` sandbox. **Not picked on its own**: only when you name it (`KROUTER_WRITER`, `KROUTER_LEARN_CLI`) or set `KROUTER_ALLOW_CODEX=1` | **Your whole account**, keys file included | The vault |
| Others (opencode, kimi, pi, vibe, antigravity, cursor-agent) | The CLI with no confinement KRouter can set. **Never picked on its own**: only with `KROUTER_ALLOW_UNCONFINED=1` in the environment or the keys file | **Your whole account** | **Your whole account** |

The vault is where untrusted text arrives (clipped web pages, pasted chats), so a writer that can do more than
read and write the vault is one prompt injection away from acting as you. Prefer the API-key lane; if you use a CLI,
prefer grok or claude. A logged-in CLI KRouter cannot confine is skipped (a confined one further down the list is
used instead) and reported as `<kind>:unconfined` until you opt in; Codex the same way, as `codex:reads-account`. Before 0.12.0 the claude and grok writers ran with permission prompts skipped and no
sandbox — able to read and write anything in the account; an outside review pointed this out and a test confirmed
it (grok read a file outside the vault through both its file tool and its shell; under the new profile it cannot).

Text filters (`krouter_redact.py`) protect what KRouter itself prints and sends; they cannot filter what an agent
reads on its own — that is what the sandbox and the allow-list are for.

**Known limits of the text filter.** An unlabeled key that is pure hexadecimal is not masked (that is how notes record
commits and digests), nor a key split into short hyphenated groups. Put keys in `~/.dsh-krouter-keys.env`, or keep them
on a page whose name says what it is.

**Long-lived CLI token.** For the claude lane, `claude setup-token` issues a token for unattended use; put it in
`~/.dsh-krouter-keys.env` as `CLAUDE_CODE_OAUTH_TOKEN=…` (the file is mode 600, never in the vault). KRouter passes it
only to the `claude` process. It avoids the logout that happens when another program (a proxy, another machine) holds
the same keychain login and spends its single-use refresh token.

## What the install changes outside the vault

- `~/.agents/skills/krouter/` (the router), Cursor rules under `~/.cursor/rules/`.
- `~/.config/krouter/vault`: one line, the vault path, so agents and the MCP server find it.
- An MCP server named `krouter` registered with `claude` (user scope) and `codex` when they are installed:
  read-only, it runs the router and nothing else (`KROUTER_NO_MCP=1` skips it; `claude mcp remove krouter` and
  `codex mcp remove krouter` undo it).
- `~/.dsh-krouter-keys.env`: names the probe manages are updated in place; every other line is kept.
- The nightly job (launchd / systemd / cron / Windows task), only on your yes.

## Integrity of what you install

The one-line install downloads a tagged release, never `main`, and checks the package's SHA-256 against the release's
`SHA256SUMS` before unpacking (releases from v0.11.2 on; older tags fall back to the source archive and say so).
`KROUTER_TAG=vX.Y.Z` pins one release. If the release has a checksum file, a failed download or a mismatch stops the
install; a release without one installs only with `KROUTER_ALLOW_UNVERIFIED=1`.

What the checksum does and does not prove: it is published in the same release as the package, so it catches a
corrupted or truncated download, not a compromised repository or release. Releases after v1.0.3 also carry a GitHub
build-provenance attestation, signed by GitHub's workflow identity rather than stored next to the package: it says
which commit and which workflow built the file.

```bash
gh attestation verify dsh-krouter-X.Y.Z.tgz --repo 398894496-arch/KRouter
```

Or compare the package with the tagged source yourself (`npm pack` on a checkout of the tag gives the same files).

## What static scanners flag

Capability scanners read the shipped code and list what it could do. dsh-xray rates the DeepSeek Harness plugin C3
("powerful capability combined with sensitive behavior"; its own page says levels are capability, not malice). All
three flags are in `extras/dsh/`, the optional DeepSeek Harness plugin; the core router, the MCP server and the
Claude Code plugin are not part of it.

| Flag | What it is | File |
|---|---|---|
| patches the dsh runtime | The plugin manifest DeepSeek Harness reads to register a plugin's tools: it inserts a `krouter` entry with read-only routes. It does not change DeepSeek Harness's own code | `extras/dsh/cordis.patch.yml` |
| command execution | The plugin spawns KRouter's router (`route_knowledge.sh`) with one of seven read-only routes; anything else is rejected before spawning | `extras/dsh/lib/route.js` |
| reads credential-class env vars | `keyPresent()` checks whether any usable key exists, in `*_API_KEY` variables or in the keys file whose *path* `KROUTER_KEYS_ENV` names, and returns yes or no; no value is printed, stored or sent | `extras/dsh/lib/index.js` |

## Reporting a vulnerability

Please do not open a public issue for a vulnerability. Use GitHub's private report:
**Security → Report a vulnerability** on this repository. Include what you ran, what you expected, and what happened.
You will get an answer within a week; fixes ship as a patch release with the finding credited in `CHANGELOG.md`.
