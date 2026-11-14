# Reproduce the numbers

[中文](REPRODUCE.zh.md) · every number with its method: [`docs/NUMBERS.md`](../docs/NUMBERS.md) · registrations and logs:
[`HELDOUT.md`](memory_honesty/HELDOUT.md)

## In about ten seconds, no model, no key, no download

```bash
git clone https://github.com/398894496-arch/KRouter && cd KRouter
python3 bench/reproduce.py
```

It recomputes 18 registered numbers (the honesty bench on three vaults with BM25 and the two-rules baseline next to KRouter,
claude-mem's and basic-memory's stored raw answers graded again, the reference-material recognition of set 40, and the prompt
hook by itself on set 45's development half and sets 32 and 35's held-out halves) and prints each beside the value written down
when it was registered, with `match` or `MISMATCH` and where it is registered. The exit code is 0 only if every row matches.
`--zh` prints 一致 / 不一致. Nothing leaves the machine, the query log is off, no file outside a temporary folder is written.
A `MISMATCH` means do not trust either side yet: open the named source, and open an issue with both numbers.

`python3 bench/reproduce.py --timing` adds this machine's hook latency on the small benchmark vault, apart from the table: a
timing depends on the machine and its load, so it is never compared with anything (the front page's latencies were measured on a
laptop shared with other work).

Tested on one machine (macOS, Python 3.14) from a clean clone; Linux and Windows have not been run.

## Not in that table

| What | Why it is not in the table | How to run it yourself |
|---|---|---|
| LongMemEval counts of answer sessions found (set 7) and the refusal rules over its 500 questions (sets 14, 37–39) | no model, but the dataset is not in this repository and the scripts download nothing | fetch `longmemeval_s_cleaned.json` yourself (licence in the script header), then `python3 bench/longmemeval/lme.py convert --data …`, `run --system krouter`, `score` |
| LoCoMo (sets 10, 18) | the same | `python3 bench/locomo/locomo.py convert --data locomo10.json`, `run --system krouter`, `score` |
| LongMemEval **answer accuracy** (sets 11, 12, 22) | a reader model and a judge model | `bench/longmemeval/qa.py prepare / judge-prepare / score`: the script writes prompt files, you run them through your own reader and judge and write the replies back. The registered runs used Claude Sonnet 5.5 as both, as Claude Code subagents; set 22's log gives about 410 subagent runs and about 15 M tokens. Another reader or judge gives other numbers; the log says what was read and by whom |
| The whole chain's refusal (set 41) | a reader model | `bench/memory_honesty/endtoend.py` (its header lists the steps); the log of set 41 has the size |
| The subconscious's **host layer** (sets 33, 35's host half, set 45's addendum: Sonnet 44 / 48, Haiku 42 / 48) | a host model that goes and looks | `bench/subconscious/both.py prepare set45dev --work DIR`, answer the batches with your model, `score`; the four registered runs read and wrote 478,381 tokens |
| Lessons and skills (sets 15–26), real sessions (30, 31) | host models, and real sessions of Codex or Claude Code | each set's section in `HELDOUT.md` names the scripts and what ran |
| Ten people at once (set 27), 30 minutes of mixed load (set 28), the scale table, set 34's speed | minutes to hours of machine time and a timing | `bench/team/load.py`, `bench/scale/run.py`, `bench/subconscious/speed.py` (commands in [`docs/TEAM.md`](../docs/TEAM.md) and [`docs/BENCHMARK.md`](../docs/BENCHMARK.md)) |
| Automatic reference recognition on a real vault (set 42) | the vault is the maintainer's own and is not published | nothing to run; the method is in `HELDOUT.md` |
| The held-out half of set 45 | sealed on purpose | the maintainer opens it once, to confirm a result found on the development half |

We have not priced these runs in money: it depends on the model you choose. The registered logs say how many tokens each one used
where they were counted.

## Other systems on the subconscious benchmark

[`bench/subconscious/public/`](subconscious/public/README.md): a small adapter interface (a message and the pages in; the pages
handed over, or none, out), a scorer with the registered counting, the KRouter hook and a plain BM25 baseline as adapters, and a
note on writing your own in about a dozen lines. Nothing in it installs or calls another project's software.
