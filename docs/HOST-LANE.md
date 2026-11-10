# The host lane: KRouter's model steps on the agent you already use, with no key

Some KRouter steps need a model: distilling sessions, writing experience cards from them, topic dossiers, answer
cards, trigger proposals. The aim is that none of them needs a key of their own: the agent the user already works in
(Claude Code, Codex, Cursor, …) comes with a model. Code: `skill/krouter-obsidian/scripts/llm.py` (`plan`,
`complete`, `channel_report`), `mcp_server.py` (`krouter_learn`, `krouter_note`), `experience.py learn`. Checked on
2026-11-09.

## The four levels, in the order they are tried

| Level | What it is | When it applies |
|---|---|---|
| 1. In session | The agent does the work in its own turn: `krouter_correct` makes a correction hold at once (a correction page that supersedes the old one; the old page marked `superseded`, or its line annotated when the page says other things too), `krouter_learn` writes an experience card, `krouter_note` a note (MCP); `corrections.py apply` and `experience.py learn` are the same for a host without MCP. No call from KRouter at all. | While a session is open. The MCP server's instructions ask the agent to call `krouter_correct` in the turn the user corrects something, and to record a lesson before the session ends. |
| 2. MCP sampling | The MCP server asks the client's model to answer. | Not used: the 2026-07-28 MCP specification deprecates it, and Claude Code does not support it ([anthropics/claude-code#1785](https://github.com/anthropics/claude-code/issues/1785), open). `mcp_server.py` records whether a client declares it, and `krouter_status` says so. |
| 3. The host's own CLI | No session around (the nightly run, a session-end import): the agent's official command line in non-interactive mode, on the login the user already has: `claude --print`, `codex exec`, `cursor-agent`, and the others `llm.py` lists. Found automatically (`detect_writer`); `KROUTER_LEARN_CLI` pins one. | Spends the user's **subscription**. At most **30 calls a day** by default (`KROUTER_HOST_CLI_MAX`); every call, failed ones included, is one line in `90 系统文件/自动化/订阅调用记录.md` and in the state directory's `host-calls.jsonl` (time, which CLI, which step, characters in and out; never the prompt); `KROUTER_HOST_CLI=0` turns this level off. Past the cap, the step is skipped as if there were no model. |
| 4. A key the user set | `*_API_KEY` in the environment or the keys file, as before. | Tried **before** an auto-detected CLI: a key is something the user set up on purpose. A CLI pinned with `KROUTER_LEARN_CLI` still goes first. |

**What KRouter never does:** read, copy or forward any app's login token, keychain item or credential file, or call
a provider's API with a subscription token. Level 3 runs the vendor's own CLI the way its documentation describes;
the CLI handles its login. (A user can put a `claude setup-token` token in the keys file for the CLI to use, as
`llm.cli_env` documents; KRouter only passes it to the CLI.)

**With no level available**, nothing needs a model and nothing breaks: recall, correction capture, the experience
digest, and the agent writing its own cards and notes all work. The nightly report (`90 系统文件/自动化/夜间维护.md`)
says which steps are off: session distilling, model-lane card extraction, topic dossiers, answer cards, trigger
proposals, and claude-mem distilling.

**A choice that differs from the brief.** The brief listed the levels as in session → sampling → CLI → key. KRouter
keeps a key the user set before an auto-detected CLI, so a user who pays for an API key is not switched to their
subscription without asking. It also keeps the CLI's flagship model (`--model opus` for Claude), as the user asked
for the "flagship" of the agent's model; set `KROUTER_LEARN_MODEL` to change it.

## Measured state, by app

| Level | Claude Code | Codex | Cursor | Claude Desktop |
|---|---|---|---|---|
| 1. In session (`krouter_correct`, `krouter_learn` over MCP) | **Connected for real** (Claude Code 2.1.295, isolated `CLAUDE_CONFIG_DIR`: `claude mcp list` → ✔ Connected, tools listed). The model calling the tools **not run**: the isolated config is not logged in, and KRouter does not log in for the user. Protocol and effect tested over stdio (`tests/test_correct_now.py`, `tests/test_experience.py`) | Not tested | Not tested | Not tested |
| 2. MCP sampling | **Not available, measured:** Claude Code 2.1.295's `initialize` declares `roots` and `elicitation`, not `sampling` (also open issue #1785) | Not tested; no evidence of support found | Not tested; no evidence of support found | Not tested; not supported by Anthropic's account, not verified here |
| 3. Official CLI | **Ran once for real, failed:** `/opt/homebrew/bin/claude --print` answered "OAuth session expired and could not be refreshed" on the author's machine (that binary's login had lapsed; the author's own `claude` is a wrapper alias). The call was recorded and the cap stopped a second one, as designed | Not tested (`codex exec`; used only when named or with `KROUTER_ALLOW_CODEX=1`, since it can read the whole account) | Not tested (`cursor-agent`; used only with `KROUTER_ALLOW_UNCONFINED=1`, since KRouter cannot confine it) | Not available (no CLI) |
| 4. API key | Not run this round (no key used, by rule); covered by the existing tests with stand-ins | same | same | same |

Every test of levels 3 and 4 uses a shell-script stand-in (`tests/test_host_lane.py`); none spends a subscription.

**What the smoke run showed.** It pinned the CLI (`KROUTER_LEARN_CLI=/opt/homebrew/bin/claude`), and a pinned CLI is
not probed, so the call went out and failed on the lapsed login. Detection on its own (`claude auth status`) reports
that binary as `claude:unauth` and would not have used it. So a lapsed login on an auto-detected CLI means "no lane";
on a pinned one it is a failed step in the nightly report, recorded and counted against the day's cap, so it cannot
loop. The fix is the user's: log that CLI in again (`claude` then `/login`), which KRouter does not do for them.
