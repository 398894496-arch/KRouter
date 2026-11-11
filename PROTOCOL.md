# Protocol

<!-- krouter-status:start (source: docs/STATUS.md; run scripts/sync_status.py) -->
> **Current status of `main` (latest release v2.0.0, 2026-11-10). Measured, and what is not.** One-line installs get
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
> - **Releases:** 2.0.0 (2026-11-10): mention something and the agent recalls what was settled about it; lessons carry
>   over between tasks and grow into skills; five pages with the ones the vault connects; a change of mind holds
>   with no key; a lighter install that is English end to end; the router moved to `skill/krouter` (an older
>   install's path is left as a link on upgrade). Minor releases at most once a week, patches when ready;
>   `KROUTER_TAG` pins one.
> - **On `main`, unreleased (2.1.0):** a knowledge-base layer: folders declared in `krouter-kb.txt` (and clippings,
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

This is an **Agent knowledge OS**, not a search plugin.

- **Self-evolution** is the product (seal → distill → two-step promotion). Timer: the one-line install **asks before installing it** (no terminal, no timer); the manual `install.sh` from a clone installs it (`KROUTER_NO_TIMER=1` skips). **API key first:** lock that provider's flagship model and run distill + promotion. **No key:** the user's own Claudian-class CLI subscription (`grok` / official Codex / `claude` / …) does the same work. `lamp: unused` = you turned the timer off.
- **Promotion is two-step:** five gates pass → write `provisional` the **same day**, no ask. Next similar task → **ask** (matcher in `skill/krouter/scripts/ask_product.py`; at most one). Host adopts → `record`. This task accepted → `promote` writes `active`. Do not write `active` on `record`.
- **Correction-first:** current instruction and latest `supersedes` beat old logs.
- **Retrieval refuses rather than guesses:** ranked lexical recall over every page (words and Chinese character pairs, rule pages first), with an optional alias lock in front for fixed short nouns; a dual SHA-256 receipt; `recall: none` when nothing covers the question. No vector store by default. Citing a neighbour page as the answer is a protocol violation.

Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

1. Five zones: `01 项目` in progress; `02 经验与方法` verified reusable methods; `03 资料与证据` inputs and evidence; `04 已完成与复盘` finished results; `05 时间日志` what happened that day.
2. Four maturity layers: full logs → distillation → promotion → retrieval. Formal `02` requires the two-step gates above. Candidates stay in projects or materials until the five gates pass.
3. On conflict: the current user instruction and the latest `supersedes` beat old logs.
4. Clippings originals are copied only. Do not move them.
5. Routing, optional fast path: match the alias table (`90 系统文件/canonical_sources.psv` in the vault; the skill's copy is only a sample) with a short noun (exact > alias in query > query in alias; same score and same file → lowest id; otherwise no hit). Open that page. On a miss, print alias suggestions (hints only) and answer with ranked L1 recall over the route’s scope (rebuildable FTS5 cache, rule pages first, a precomputed `answer (generated):` card when one fits); weak overlap prints `recall: none` and only then literal-searches. A single-page route with no answer widens to the vault and says `scope_widened`. A source whose status is superseded / retired / rejected / deprecated / archived never locks. Same-score miss across two files: print `host_prompt` and do not guess. Windows may run `route_knowledge.py` (same contract as the POSIX script). No vector store. Evidence is four layers — implementation, comparison, self-report, real-traffic blind judge: [`docs/VERIFY.md`](docs/VERIFY.md). Neighbor cite is a failure: [`docs/LOCK_VS_NEIGHBOR.md`](docs/LOCK_VS_NEIGHBOR.md). On a miss, which is most questions, ranked recall answers; the alias table needs no upkeep (a sample ships; add a row only to pin a short noun to a page).
6. Every route prints a receipt: time, source path, source SHA-256, map SHA-256.
7. Two lanes, same job (distill + two-step promotion). **API key first:** keys live in `~/.dsh-krouter-keys.env`, never in the vault (a key pasted on `90 系统文件/自动化/自进化钥匙.md` is moved there on the next run); lock the provider's flagship model (`/models` catalog; skip mini/haiku), run `api_writer.py`. **No key:** spawn a logged-in Claudian-class CLI (`grok`, official Codex, `claude`, cursor-agent, opencode, kimi, pi, vibe, antigravity) with that harness's flagship. The nightly steps use the same lane: same provider table, same flagship lock, same CLI list (`llm.py`). Do not use a PATH-level `agent`. Chat/IDE login is not a spawnable harness. No extra env file. Mounted agents must run `status` and tell the host if `host_action` is present. Do not print secrets. Do not commit a live key.
8. **One product: KRouter.** Cursor, Codex, Claude Code, and DeepSeek Harness are sockets on one vault. Sharing is the vault and the alias map, not a second protocol. `extras/dsh` is the DSH socket (read-only tools). `extras/host-daily-evolution` is the writer. They are not two projects. Uninstalling the DSH socket does not delete notes. `dsh plugin add` does not start the timer.
