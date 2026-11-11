# Installing KRouter

The README keeps the shortest path (one line, then `krouter doctor` and a first question). Everything else about installing is here: Windows, the Claude Code plugin, `--minimal`, every file the install creates or changes, what works without a key, trying it before installing, uninstalling, and calling it from your own code.

```bash
curl -fsSL https://github.com/398894496-arch/KRouter/releases/latest/download/bootstrap.sh -o /tmp/krouter-install.sh && sh /tmp/krouter-install.sh
```

The script is saved to a file first, so a failed download stops right there with a non-zero exit (`curl … | sh`
would run an empty script and report success). Windows (PowerShell): `irm https://github.com/398894496-arch/KRouter/releases/latest/download/bootstrap.ps1 | iex`
· Claude Code plugin only: `/plugin install krouter --marketplace 398894496-arch/KRouter` ([versions, updating](DETAILS.md#the-claude-code-plugin)).

Python 3 is the only requirement; ripgrep, when present, only makes literal search faster on a big vault. Neither way
asks anything. Pick one (options go after the script: `sh /tmp/krouter-install.sh --minimal --apps claude`):

| | Default | `--minimal` |
|---|---|---|
| Lookup with the source page, "not in the memory" instead of a guess | yes | yes |
| Apps connected | every app on [the list below](../README.md#works-with) that it finds | only the ones you name with `--apps claude,codex,cursor,…` (none when you name none) |
| Claude Code plugin (session hooks) | installed when `claude` is found | no |
| Codex and Cursor session hooks | added when the app is found | no |
| Cursor rules (`~/.cursor/rules/`) | yes | only with `--apps cursor` |
| Records sessions | from now on: each turn as it ends, on this machine, redacted, no model call | no |
| Imports past sessions (the last 7 days) | no: one command at the end of the install does it, or `--all` up front | no |
| Nightly job, distilling with your model (the steps that send text out) | no: `--ask` asks, `--timer` turns the job on | no |
| Opens the new memory in Obsidian | only when you run it from a terminal (`--open` always, `--no-open` never); run by an agent, no | same |

`--all` does everything the install can do without a model, as the default used to: it also imports the last 7 days
of sessions and claude-mem's memory, if you have one.

Every file the default install creates or changes (`--dry-run` lists them for your machine first, changing nothing;
the install itself lists each settings file it changed, and keeps a copy of it first):

| Where | What |
|---|---|
| `~/Documents/Second Brain/` (or your folder, `--vault`) | the memory: plain Markdown. An existing folder keeps every file; only missing ones are added |
| `~/.dsh-krouter/<version>/`, `~/.dsh-krouter/current` | the downloaded release (installing from a clone uses the clone) |
| `~/.agents/skills/krouter/` | the router |
| `~/.config/krouter/vault` | where the memory is, for hooks and the MCP server |
| `~/.claude.json` (`claude mcp add`), `~/.claude/settings.json` (plugin and its marketplace) | Claude Code |
| `~/.codex/config.toml` (`codex mcp add`), `~/.codex/hooks.json` | Codex |
| `~/.cursor/mcp.json`, `~/.cursor/hooks.json`, `~/.cursor/rules/` | Cursor |
| each other app's MCP settings file, [listed below](../README.md#works-with) | only for apps it finds; a copy of each changed file is kept as `*.krouter-bak` |
| Claude Desktop's `claude_desktop_config.json` | only when the app is closed (with the extension instead: after you press Install the app checks it online for a few seconds with nothing on screen; press once and wait, a second press can remove it again); while it runs, nothing: you get `~/.config/krouter/KRouter.mcpb` to double-click, or quit the app and run the `--connect claude-desktop` command the install prints |
| `~/.cache/krouter/`, `~/.local/state/krouter/` | the search cache (rebuildable) and what the import has seen |

Tested for 2.0: macOS (the install, the upgrade, the uninstall, inside the apps); Linux in a clean `python:3.12-slim` container (install, upgrade from the pre-2.0 folder, lookup, refusal, `doctor`, uninstall; a container has no scheduler, and `--timer` there now says the job was **not** installed). **Windows was not tested for 2.0**: no Windows machine was reachable; the 2026-10-11 check is in [`docs/VERIFY.md`](VERIFY.md), and only the logic of the folder move is pinned by a test.

Nothing leaves the machine during the install except the download itself. When it is done:

```bash
~/.dsh-krouter/current/scripts/krouter doctor     # OK, or what is missing and the command that fixes it
~/.dsh-krouter/current/scripts/krouter search "what did we decide about X?"
```

(From a clone, `./scripts/krouter`; with the Python package on your PATH, just `krouter`.) The memory folder is plain
Markdown: open it in any editor, or in Obsidian if you like. Tools find it through `KROUTER_VAULT`, else
`OBSIDIAN_VAULT` (the older name, still read; `KROUTER_VAULT` wins when both are set), else the folder the install
recorded in `~/.config/krouter/vault`.

### Without an API key

Lookup, answers with their source page, refusals, the local session import and noting what
reads like a correction all work, and a change of mind is handled three ways:

1. **The newer page first.** When two imported pages answer the question about as well and the newer one says it
   changed the subject (`switched … to`, `instead of`, `改成`, …), the newer page is listed first and the receipt
   says `recall_conflict: an earlier page says otherwise`. No model; it does not catch a change worded any other way.
2. **The agent, in the same turn.** When you correct it, it calls `krouter_correct`: the old page is marked
   superseded and the next lookup gives the new answer. This needs the agent to make the call (the MCP instructions
   ask it to).
3. **The nightly job, on an agent you are logged in to.** With the nightly job on and no key, distilling and settling
   correction candidates borrow an AI coding CLI's subscription (`claude --print`, …; Codex only with
   `KROUTER_ALLOW_CODEX=1`), at most 30 calls a day, each listed in the vault; `KROUTER_HOST_CLI=0` turns it off.
   Run for real once, with Codex: it distilled the sessions and the old page was marked superseded.

With no key and no logged-in CLI, distilling (each page's "what was decided, what changed"), the rest of the nightly
upkeep and settling correction candidates do not run, so a change the first two miss can leave the older page first.
Checked with no key in a throwaway home (2026-11-10): PostgreSQL on Monday, SQLite on Wednesday, imported, never
distilled: SQLite's page first with the conflict line; after `krouter_correct`, the old page superseded and the
correction first. The installer and `krouter doctor` both say which state you are in.

Rather look first? Nothing below changes your machine until the last line:

```bash
git clone https://github.com/398894496-arch/KRouter.git && cd KRouter
./scripts/first_run.sh                      # a receipt on a throwaway copy of the sample memory
python3 scripts/bootstrap.py --dry-run      # every file and app setting the install would change, changed nowhere
python3 scripts/bootstrap.py --minimal --apps claude --vault ~/notes   # lookup only, Claude Code only, your folder
```

**Uninstall:**

```bash
sh ~/.dsh-krouter/current/scripts/uninstall.sh     # from a clone: sh scripts/uninstall.sh; --dry-run lists first
```

It stops and removes the nightly job, the router, the rules, KRouter's MCP entries and hooks, the Claude Code plugin
(and its marketplace when it points at a folder on this machine) and the recorded path. It never touches your
memory folder or your keys file. `--purge` also removes the cache, the state and `~/.dsh-krouter`.


## Bring in your past sessions

Recommended once, right after installing: let your agent bring in the sessions already on this machine (Claude Code,
Codex, Cursor), so on day one it knows what you settled before. Three steps; the first two never call a model.

```bash
python3 ~/.agents/skills/krouter/scripts/import_sessions.py --days 3650 --dry-run --distill       # 1. how many, writes nothing
python3 ~/.agents/skills/krouter/scripts/import_sessions.py --days 3650 --local                   # 2. all of them, no model
python3 ~/.agents/skills/krouter/scripts/import_sessions.py --days 3650 --distill --distill-max 40 # 3. distill the newest 40
```

1. **Preview.** Writes nothing and sends nothing. Its last line says how many sessions (`sessions`), how many pages it
   would write (`pages`), how many sessions step 3 would send to a model (`distilled`) and how many characters
   (`chars`). Tell the user these numbers before step 3.
2. **Import.** One page per session in `05 Journal/Sessions/` (`05 时间日志/会话摘录/` in a vault with the default
   names): your questions and each turn's last answer, redacted. No model is called and nothing leaves the machine.
   Lookups use these pages at once; a question you asked before with no answer recorded is not taken as its own
   answer.
3. **Distill.** Each session is sent to the model lane to write "what was decided, what changed" on its page: a key you
   set, else an AI coding CLI you are logged in to, on its subscription (`claude --print`, …; Codex only with
   `KROUTER_ALLOW_CODEX=1`). At least one call per session, more for a long one. `--distill-max` (default 40) takes
   the newest that many sessions; a session already distilled is not sent again. Through a logged-in CLI there is also
   a cap of 30 calls a day (`KROUTER_HOST_CLI_MAX`), each listed on the vault's subscription-calls page. **2.0 does not
   work through the whole history by itself**: to go further back, run step 3 again on another day with a larger
   number (80, 120, …). With no key and no logged-in CLI it says `distill skipped` once, writes the excerpts, and exits
   normally.

Taking it back: each distill run gets an id in the change ledger (`90 System/Automation/Memory changes.md`); when the
memory folder is a git repository (`git init` in it once), `import_sessions.py --undo <id>` reverts that run. The
pages step 2 wrote are new files, one per session in `05 Journal/Sessions/`: delete them to take them back. On
Windows, use `python` and `%USERPROFILE%\.agents\skills\krouter\scripts\import_sessions.py`.

Checked in a throwaway home with five synthetic sessions and no model (2026-11-10): the preview reported 5 sessions,
5 to distill, 7,800 characters, and wrote nothing; the import wrote 5 pages and sent nothing; step 3 said
`distill skipped: no model lane …` and exited 0.

## From your own code

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

JavaScript / TypeScript (Node 18+), local or a team server ([`sdk/js`](../sdk/js); not on npm yet):

```js
import { KRouter } from "./sdk/js/index.js";
const a = await KRouter.local().ask("how do we ship a release?");   // or KRouter.remote(url, { token })
console.log(a.page, a.how, a.refused);
```
