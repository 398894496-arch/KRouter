# Contributing

This repo stays a deterministic router. Do not add a vector index, embedding daemon, or retrieval subprocess as the default path. The lock-vs-neighbor MiniLM and BGE-M3 rows are frozen cosine replays (`dense_vectors.json`, `dense_m3_vectors.json`), not a product retriever.

1. `python3 -m pip install -r requirements.txt -r requirements-dev.txt`
2. `python3 -m pytest -q`
3. `./scripts/first_run.sh`

Before **upload** (`git push` / a release): commit, then `./scripts/verify_clean.sh`. That script unpacks `git archive HEAD` into a temp dir — uncommitted and untracked files are not there. A green pytest in a dirty worktree is not this check. v0.4.1 shipped `verify_canonical_map.py` against helpers that only existed uncommitted.

A miss may print alias **suggestions**. Those are hints to add or retry a noun. They are not `canonical_match: true`.

## Changes to ranking, refusal or card checks

A change to a scoring constant (`SCORE_MIN`, `TITLE_HIT`, `TOPIC_*`, `CARD_MIN`, `ALIEN_MIN`, `ANSWER_SUPPORT_MIN`, …) or to a refusal / card check ships with numbers, in the PR description, before and after, on the same run:

- `tests/test_recall_bench.py` on the template (in CI): every off-topic and half-off-topic question refused; the gold-page count may rise, never fall. Raise `POS_TOP1_MIN` when it rises; never lower it to make a change pass.
- If you have a vault of your own: your held-out questions — written before you tuned, never used to tune — not the questions you tuned on.
- The memory honesty bench's held-out set (`bench/memory_honesty/heldout.jsonl`) is not a tuning target. You may report its aggregates (`run.py --set heldout`); do not look at which questions it misses while developing, and do not cite it as the reason for a change. The same holds for the second held-out set, `heldout2.jsonl.gz` on `vault2/`: tune on `questions_dev3.jsonl`, report `--set heldout2` aggregates, and do not decompress the file to read it. `heldout3.jsonl.gz` on `vault3/` has no dev set at all; a candidate runs on it once, under the decision rule written in HELDOUT.md before any candidate ran. Rules and log: [`bench/memory_honesty/HELDOUT.md`](bench/memory_honesty/HELDOUT.md).

Tests and evaluation runs must not write the host's query log (`~/.local/state/krouter/queries.jsonl`): it is what the nightly learning reads, so test questions in it become learned triggers, and held-out questions in it stop being held out. `tests/conftest.py` points `KROUTER_STATE_DIR` and `KROUTER_CACHE_DIR` at a temp dir; evaluation scripts set `KROUTER_NO_QUERY_LOG=1`.

`main` takes reviewed changes; hosts should pin a release tag. Release cadence: a minor release (new features) at most once a week; a patch release (fixes, docs, benchmark updates) at most once a week, security fixes excepted. **Until 2026-11-12, 1.1.x takes fixes only**; feature PRs stay open for 1.2.0. Each changelog entry starts with a "what you will notice" summary.

## The quickest way to help: try it in your app and say so

Several rows of the README's "Works with" table and of [`docs/FRAMEWORKS.md`](docs/FRAMEWORKS.md) say "not yet
tested inside the app" or "not yet run by us". One report from someone who ran it moves a row to "tested by a user":
open a [Works in my app](https://github.com/398894496-arch/KRouter/issues/new?template=works-with.yml) issue with
the app or framework, its version, your OS, and what `krouter_ask` answered (a question your memory knows, and one it
does not). It worked and it did not are both worth reporting. Open right now:

| Where | What to try |
|---|---|
| Claude Desktop, VS Code (Copilot), Copilot CLI, Gemini CLI, Kiro, Zed, Cline CLI | after the one-line install, restart the app and ask it something your memory holds |
| Cursor | the session hooks: a new chat starts with this repository's decisions; a turn shows up in `05 时间日志/会话摘录/` |
| An agent framework not in `docs/FRAMEWORKS.md` (Agno, Mastra, AutoGen, Haystack, …) | load the MCP server the way that framework loads one, and say what it took |
| The LangGraph store (`KRouterStore`) | on Windows; in a LangGraph Platform deployment (`langgraph.json` store config); with langmem's memory tools |
| The Kubernetes manifest, the systemd unit | `deploy/kubernetes/krouter.yaml`, `deploy/systemd/krouter.service` on a real cluster or host |
| Any benchmark | rerun it on your machine (`bench/scale/serve_load.py`, `bench/memory_honesty/run.py`, `bench/longmemeval/`) and post your numbers next to ours |

## Good first issues

Issues labeled [`good first issue`](https://github.com/398894496-arch/KRouter/labels/good%20first%20issue) are small and self-contained. Typical ones: import sessions from another agent (Cursor, Gemini CLI, OpenCode) in `import_sessions.py`; a vault template for another field; an adapter for the memory honesty bench ([`docs/BENCHMARK.md`](docs/BENCHMARK.md)) that runs another memory system on the same 30 questions.
