# Protocol

<!-- krouter-status:start (source: docs/STATUS.md; run scripts/sync_status.py) -->
> **Current status of `main` (latest release v1.2.1, 2026-10-20). Measured, and what is not.** One-line installs get
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
> - **Releases:** 1.2.0 (2026-10-19) came ahead of the planned 2026-11-12, at the maintainer's call. From here, minor
>   releases at most once a week and patches when ready; `KROUTER_TAG` pins one.
> - **Nightly job:** the one-line install is lookup only and asks nothing; `--ask` asks about importing sessions and
>   the nightly job. The manual `install.sh` installs the job (`KROUTER_NO_TIMER=1` skips). Queries never leave the machine.
> - **Nightly writer lanes:** an API key runs nothing locally; grok (kernel sandbox) and claude (tool allow-list) are
>   limited to the vault; Codex can read the whole account and writes only the vault, so it is used only when you name
>   it or set `KROUTER_ALLOW_CODEX=1`; other CLIs are unconfined and are never picked unless you set
>   `KROUTER_ALLOW_UNCONFINED=1`.
>   [SECURITY.md](https://github.com/398894496-arch/KRouter/blob/main/SECURITY.md) has the table.
<!-- krouter-status:end -->

This is an **Agent knowledge OS**, not a search plugin.

- **Self-evolution** is the product (seal → distill → two-step promotion). Timer: the one-line install **asks before installing it** (no terminal, no timer); the manual `install.sh` from a clone installs it (`KROUTER_NO_TIMER=1` skips). **API key first:** lock that provider's flagship model and run distill + promotion. **No key:** the user's own Claudian-class CLI subscription (`grok` / official Codex / `claude` / …) does the same work. `lamp: unused` = you turned the timer off.
- **Promotion is two-step:** five gates pass → write `provisional` the **same day**, no ask. Next similar task → **ask** (matcher in `skill/krouter-obsidian/scripts/ask_product.py`; at most one). Host adopts → `record`. This task accepted → `promote` writes `active`. Do not write `active` on `record`.
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
