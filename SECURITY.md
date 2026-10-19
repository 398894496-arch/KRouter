# Security

<!-- krouter-status:start (source: docs/STATUS.md; run scripts/sync_status.py) -->
> **Current status of `main` (latest release v1.1.1, 2026-10-15). Measured, and what is not.** One-line installs get
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
> - **Stable line:** 1.1.x takes fixes only until 2026-11-12, at most one patch a week. Smallest install, nothing in the
>   background: `bootstrap.py --vault <vault> --no-timer --no-import`.
> - **Nightly job:** the one-line install asks before installing it; the manual `install.sh` installs it
>   (`KROUTER_NO_TIMER=1` skips). Queries never leave the machine.
> - **Nightly writer lanes:** an API key runs nothing locally; grok (kernel sandbox) and claude (tool allow-list) are
>   limited to the vault; Codex can read the whole account and writes only the vault; other CLIs are unconfined and
>   are never picked unless you set `KROUTER_ALLOW_UNCONFINED=1`.
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
| This repository's confirmed decisions and recent corrections | The new Claude Code session's context (plugin `SessionStart` hook): up to 8 lines, each with its page. Only pages whose recorded repository path is this one; a folder name never matches | Only with the plugin, and after you said yes to importing; `KROUTER_INJECT=0` turns it off |
| Rule and topic pages, topic excerpts, unanswered queries (with, for each, up to 4 candidate pages' first 600 characters, redacted; never secret pages or `03 资料与证据`) | The same model lane | The nightly job, only if you turned it on |
| API keys | `~/.dsh-krouter-keys.env` (mode 600). Never the vault, never a prompt, never printed | — |
| Pages named or marked as secret (凭据 / 密钥 / 钥匙 / credential / secret / password, or `secret: true`) | Nowhere: never sent, never quoted | — |

`extras/host-daily-evolution/run.sh --dry-run` lists what the next nightly run would send, with token estimates,
and sends nothing. The one-line install asks before it installs the nightly job; without a yes it is not installed.

**What the nightly writer can see.** It depends on the lane, and the install prompt says which one you are choosing:

| Lane | Runs on this machine | Can read | Can write |
|---|---|---|---|
| **API key (recommended)** | Nothing: a direct API call | — (KRouter sends only what `--dry-run` lists) | — |
| `grok` | grok, in a kernel-enforced sandbox profile (`strict` + the router) | The vault, the router, system paths | The vault, KRouter's cache and state |
| `claude` | Claude Code, with tools allow-listed (`dontAsk`): read / edit inside the vault, run the router, nothing else | The vault (tool-level rule, no kernel sandbox) | The vault |
| Codex | Codex in its `workspace-write` sandbox | **Your whole account**, keys file included | The vault |
| Others (opencode, kimi, pi, vibe, antigravity, cursor-agent) | The CLI with no confinement KRouter can set. **Never picked on its own**: only with `KROUTER_ALLOW_UNCONFINED=1` in the environment or the keys file | **Your whole account** | **Your whole account** |

The vault is where untrusted text arrives (clipped web pages, pasted chats), so a writer that can do more than
read and write the vault is one prompt injection away from acting as you. Prefer the API-key lane; if you use a CLI,
prefer grok or claude. A logged-in CLI KRouter cannot confine is skipped (a confined one further down the list is
used instead) and reported as `<kind>:unconfined` until you opt in. Before 0.12.0 the claude and grok writers ran with permission prompts skipped and no
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

- `~/.agents/skills/krouter-obsidian/` (the router), Cursor rules under `~/.cursor/rules/`.
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
