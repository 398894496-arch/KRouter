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
>   The same reader given plain BM25's top three sessions gets 405 right (81.0%): no difference shown (paired −1.0
>   points [−2.8, +0.8]); given nothing it gets 0 of the 470 answerable. On this benchmark the lookup is level with
>   BM25, not ahead. Given the benchmark's own answer sessions (perfect retrieval) the reader gets 492 (98.4%), so
>   the missing 18 points [15.0, 21.8] are lost in retrieval, not by the reader.
> - **Someone else's benchmarks** (scored from the authors' labels, no model judge): LongMemEval S, an answer session
>   cited for 439 of 470 answerable questions, 3 of 30 unanswerable refused; LoCoMo, evidence first for 991 of 1,540,
>   37 of 446 adversarial refused. Page found, not answer accuracy; plain BM25 finds about as many.
> - **Real-traffic blind test on fresh queries** ([VERIFY.md](https://github.com/398894496-arch/KRouter/blob/main/docs/VERIFY.md)
>   layer 4): not run yet; it waits for 50 new queries (30 logged by 2026-11-09).
> - **Who wrote the held-out questions:** Claude Opus in separate claude.ai sessions, not a person. A person-written
>   set is planned.
> - **Releases:** 1.3.0 (2026-11-09): capture keeps the memory current without a confirmation step, and every run is
>   logged and can be undone. Minor releases at most once a week, patches when ready; `KROUTER_TAG` pins one.
> - **Team server** (self-hosted; no KRouter cloud): several isolated memories per server, a token each, Prometheus
>   `/metrics`; Docker, Compose, Kubernetes and systemd files. Over HTTP on one M2 laptop: 10,000 pages 13 ms a lookup
>   and 301 answers/s with 32 callers, 50,000 pages 54 ms and 75/s (synthetic vaults, `bench/scale/serve_load.py`).
>   The Kubernetes manifest and systemd unit are checked by tests, not yet run on a cluster or host.
> - **Install and capture:** the one-line install asks nothing, connects every app it finds (Claude Code with its
>   plugin, Codex, Cursor, Claude Desktop, VS Code, Copilot CLI, Gemini CLI, Kiro, Zed, Cline CLI), lists every settings
>   file it changed (a copy of each kept), and imports nothing from the past (`--all` imports the last 7 days, locally,
>   no model call; `--minimal` is lookup only and connects only the apps you name). From then on, Claude Code, Codex and Cursor each
>   record every turn as it ends through their session hooks (local, no model call; Codex runs them once you trust them
>   in `/hooks`; Cursor's checked against its docs, not yet inside Cursor). Distilling with a model and the nightly job
>   ask first (`--ask`). The manual `install.sh` installs the job (`KROUTER_NO_TIMER=1` skips). Queries never leave the machine.
> - **Nightly writer lanes:** an API key runs nothing locally; grok (kernel sandbox) and claude (tool allow-list) are
>   limited to the vault; Codex can read the whole account and writes only the vault, so it is used only when you name
>   it or set `KROUTER_ALLOW_CODEX=1`; other CLIs are unconfined and are never picked unless you set
>   `KROUTER_ALLOW_UNCONFINED=1`.
>   [SECURITY.md](https://github.com/398894496-arch/KRouter/blob/main/SECURITY.md) has the table.
