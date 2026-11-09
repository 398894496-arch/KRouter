> **Current status of `main` (latest release v1.3.0, 2026-11-09). Measured, and what is not.** One-line installs get
> the latest release; anything under "Unreleased" in CHANGELOG.md is on `main` only. Every fact an evaluating agent
> needs, with sources: [`docs/FOR-AGENTS.md`](https://github.com/398894496-arch/KRouter/blob/main/docs/FOR-AGENTS.md).
> - **Held-out bench** (200 questions on a synthetic 110-page vault, never tuned on; *not* real traffic): KRouter 26%
>   wrong citations, 47 of 80 unanswerable questions refused, 102 of 120 answerable right. At their defaults claude-mem
>   64% and basic-memory 78%, 72 and 45 right; neither can refuse. BM25 given KRouter's two rules (skip replaced
>   pages, refuse a weak match) is level with KRouter: the lead is those rules being on by default, not the ranker.
> - **Answer accuracy** (LongMemEval S, the number other projects publish): 400 of 500 right, 80.0% [76.4, 83.4],
>   with KRouter's top three pages as the only context; reader and judge Claude Sonnet 5.5 with the benchmark's own
>   prompts, not the GPT-4o most projects use. Weakest on questions that add up several sessions (69 of 121).
> - **Someone else's benchmarks** (scored from the authors' labels, no model judge): LongMemEval S, an answer session
>   cited for 439 of 470 answerable questions, 3 of 30 unanswerable refused; LoCoMo, evidence first for 991 of 1,540,
>   37 of 446 adversarial refused. Page found, not answer accuracy; plain BM25 finds about as many.
> - **Real-traffic blind test on fresh queries** ([VERIFY.md](https://github.com/398894496-arch/KRouter/blob/main/docs/VERIFY.md)
>   layer 4): not run yet; it waits for 50 new queries (30 logged by 2026-11-09).
> - **Who wrote the held-out questions:** Claude Opus in separate claude.ai sessions, not a person. A person-written
>   set is planned.
> - **Releases:** 1.3.0 (2026-11-09): capture keeps the memory current without a confirmation step, and every run is
>   logged and can be undone. Minor releases at most once a week, patches when ready; `KROUTER_TAG` pins one.
> - **Install and capture:** the one-line install asks nothing, connects every app it finds (Claude Code with its
>   plugin, Codex, Cursor, Claude Desktop, VS Code, Copilot CLI, Gemini CLI, Kiro, Zed) and imports the last 7 days of
>   sessions locally, with no model call; `--no-import` is lookup only. After that, Claude Code, Codex and Cursor each
>   record every turn as it ends through their session hooks (local, no model call; Codex runs them once you trust them
>   in `/hooks`; Cursor's checked against its docs, not yet inside Cursor). Distilling with a model and the nightly job
>   ask first (`--ask`). The manual `install.sh` installs the job (`KROUTER_NO_TIMER=1` skips). Queries never leave the machine.
> - **Nightly writer lanes:** an API key runs nothing locally; grok (kernel sandbox) and claude (tool allow-list) are
>   limited to the vault; Codex can read the whole account and writes only the vault, so it is used only when you name
>   it or set `KROUTER_ALLOW_CODEX=1`; other CLIs are unconfined and are never picked unless you set
>   `KROUTER_ALLOW_UNCONFINED=1`.
>   [SECURITY.md](https://github.com/398894496-arch/KRouter/blob/main/SECURITY.md) has the table.
