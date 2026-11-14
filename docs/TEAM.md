# A memory for a team

> **Experimental.** Tested on one machine only; no real team has used it over weeks; the Kubernetes manifest and the systemd unit are checked by tests and have never been run on a cluster or a host.

One person's memory stays on their machine. A team shares a second memory: a folder of Markdown in its own git
repository, served read-only over HTTP by one small server everyone's AI apps connect to. There is no hosted
service; you run the server.

```
  each person                          the team
  ───────────                          ────────
  personal vault ── stdio MCP ──┐      team repo (private git remote)
  (never leaves the machine)    │          │  git pull every few minutes
                                ├── AI app ── HTTP MCP ──► team server (read-only, token)
                                │                         --label team
```

Every answer from the team server starts with `vault_label: team`, and the personal server can say
`vault_label: personal` (`--label personal`), so an answer always says which memory it came from.

## 1. The team vault

A git repository with the same layout as a personal vault (copy `template/` or `template-zh/` to start). Decisions
get into it the way code does: someone writes or edits a page and commits, or opens a pull request. The server never
writes to it. A page that replaces another marks the old one `status: superseded`, as in a personal vault, and the
server stops citing the old one on the next question.

What does not go in: anything a person would not show the whole team. Each person's session capture
(`import_sessions.py`, the hooks) writes to their personal vault only.

## 2. The server

On any machine the team can reach (a small VM is plenty; see the numbers below):

```bash
git clone git@github.com:your-org/team-vault.git /srv/team-vault
openssl rand -hex 24 > /etc/krouter/token && chmod 600 /etc/krouter/token
python3 skill/krouter/scripts/mcp_server.py --http 0.0.0.0:8787 \
  --vault /srv/team-vault --label team --token-file /etc/krouter/token
```

or with Docker (the image is built and smoke-tested on every release, with a build-provenance attestation). The
container runs as user 10001, so give it the token file (`chown 10001 /etc/krouter/token`):

```bash
docker run -d --name krouter-team --restart unless-stopped -p 8787:8787 \
  -v /srv/team-vault:/vault:ro -v /etc/krouter/token:/run/secrets/krouter_token:ro \
  ghcr.io/398894496-arch/krouter:v2.1.2
```

Keep the vault current with a pull every few minutes (cron, a systemd timer, or a CI job):

```bash
*/5 * * * *  git -C /srv/team-vault pull --ff-only --quiet
```

The full-text index catches up on the next question; nothing needs restarting.

**Put HTTPS in front of it** (Caddy, nginx, a cloud load balancer) before it leaves a private network: the server
itself speaks plain HTTP. What the server does on its own:

- binds to `127.0.0.1` unless you name another address, and refuses to start on another address without
  `--token-file`; every `POST /mcp` must carry `Authorization: Bearer <token>` (compared in constant time);
- rejects browser origins other than localhost unless you list them with `--allow-origin` (DNS-rebinding guard);
- serves only the two read-only tools, `krouter_ask` and `krouter_status` (`--allow-write` adds `krouter_note`);
  bodies over 1 MB are refused;
- logs one JSON line per request to stderr with a SHA-256 prefix of the question, never the question; it does not
  write questions to the query log either (`--log-queries` turns that on, for a team that wants nightly learning);
- `GET /healthz` answers `{"ok": true, "version": …, "label": …}` for a load balancer or the Docker health check,
  without the vault's path.

To change the token, write a new one to the file and restart the server.

## 2b. Several memories on one server, monitoring, Compose

**Banks.** One server can hold several memories that never see each other: a vault per team, per project or per
customer, each at its own URL and, if you like, with its own token.

```bash
python3 skill/krouter/scripts/mcp_server.py --http 0.0.0.0:8787 \
  --bank team=/srv/team-vault --bank-token team=/etc/krouter/team.token \
  --bank ops=/srv/ops-vault   --bank-token ops=/etc/krouter/ops.token
# → https://krouter.your-team.example/mcp/team and …/mcp/ops
```

Each bank has its own index (the cache is keyed by the vault's path), answers only from its own pages, and stamps its
name on every receipt (`vault_label: ops`). A token opens only its own bank; a bank without its own token uses
`--token-file`, and the server refuses to start off loopback while any bank has neither. With banks there is no bare
`/mcp`. `GET /healthz` lists each bank and whether its folder is there.

**Monitoring.** `GET /metrics` is Prometheus text: `krouter_tool_calls_total{vault,tool,outcome}`,
`krouter_refusals_total{vault}` (answers that were `recall: none`), `krouter_request_seconds` (a histogram per vault),
`krouter_index_build_seconds{vault}`, `krouter_lookup_workers{vault}` (resident lookup processes) and
`krouter_uptime_seconds`. It holds counts only, never a question; when the
server has tokens, it takes any of them (`authorization: {credentials_file: …}` in the Prometheus scrape config).

**Resident lookups.** Each bank keeps up to 4 lookup processes (`--workers N`; started as callers arrive, so an
idle bank holds one), and each re-checks its vault's files at most every 2 seconds (`--refresh-every`). A note written
through the server makes the next lookup re-check at once. A lookup that hangs for 120 s is cut off and its process
replaced; a process that dies is replaced on the next call (that call runs the old way, one process). `--workers 0`
is the old way for every call.

**Compose, Kubernetes, systemd.** [`deploy/docker-compose.yml`](../deploy/docker-compose.yml) runs the server with
two banks, read-only and as user 10001, next to a small container that pulls each vault every five minutes.
[`deploy/kubernetes/krouter.yaml`](../deploy/kubernetes/krouter.yaml) is the same as a Deployment (an init container
clones each vault, a sidecar pulls it, tokens and the deploy key from Secrets, read-only root filesystem, `/healthz`
probes, Prometheus annotations) and a Service. [`deploy/systemd/krouter.service`](../deploy/systemd/krouter.service)
runs it on a Linux host with the vaults on disk, as its own user with `ProtectSystem=strict` and the vaults read-only.
The Compose file is checked with `docker compose config`; the Kubernetes manifest and the unit are checked by
`tests/test_deploy.py` (shape, probes, read-only mounts, and that every flag they pass exists), not yet applied to a
cluster or a systemd host by us. The multi-bank server itself is tested in `tests/test_mcp_banks.py`.

| Running it | What KRouter does |
|---|---|
| Storage | Markdown files in a git repository you own; the index is a rebuildable SQLite cache |
| Isolation | one bank per memory: own URL, own token, own index, own label on every answer |
| Access | a token per person or agent (`--users`: only hashes kept, `read` or `write`, which banks), or one shared token per bank or server; constant-time compare; loopback only without one; origin check |
| Attribution | every write names its person on the page, in the change ledger, in a journal (`krouter_changes`) and as the git author; two corrections of one thing: the later holds, the earlier is kept and named ([§2c](#2c-one-token-per-person-who-changed-what-and-conflicting-corrections)) |
| Monitoring | `/metrics` (Prometheus), `/healthz`, one JSON access-log line per request with a hash of the question |
| Deployment | `python3 mcp_server.py --http`, the Docker image (non-root, read-only vault, provenance attestation), Compose, Kubernetes, systemd |
| Scale | over HTTP, 10,000 pages: 13 ms per lookup (median), 301 answers/s with 32 callers; 50,000: 54 ms, 75/s ([§4](#4-how-big-it-can-get)); ten people reading and writing at once: [§5](#5-ten-people-at-once) |
| Backups | the git remote, and `backup.py` for an encrypted nightly copy of a personal vault |
| Not offered | a hosted service, SSO, per-page permissions inside one bank (a token is read or write for the whole bank: give each group its own bank), more than one server writing one vault |

## 2c. One token per person, who changed what, and conflicting corrections

**Personal tokens.** Give each person, or each agent, a token of their own. Only its SHA-256 goes in the users file;
the token goes to a new file (mode 600) for you to hand over:

```bash
python3 skill/krouter/scripts/team.py add-user --users /etc/krouter/users alice --token-out alice.token
python3 skill/krouter/scripts/team.py add-user --users /etc/krouter/users ci-bot --role read --banks team --token-out ci.token
python3 skill/krouter/scripts/mcp_server.py --http 0.0.0.0:8787 --vault /srv/team-vault --label team \
  --users /etc/krouter/users --allow-write
python3 skill/krouter/scripts/team.py remove-user --users /etc/krouter/users alice   # her token stops at once
```

In Docker, mount the file read-only too (`-v /etc/krouter/users:/run/secrets/krouter_users:ro`) and end the `docker
run` line with `--label team --users /run/secrets/krouter_users` (plus `--allow-write` and a read-write vault mount,
not `:ro`, for a server that writes). The image's entry point still reads the shared token at
`/run/secrets/krouter_token`, which keeps working beside the personal ones. (Personal tokens were tested with the
Python server; not yet inside the image.)

One line per person: `name|sha256:<hex>|write or read|* or bank names`. The server re-reads the file when it changes,
so adding or removing someone needs no restart. A `read` token is not offered the write tools and is refused if it
calls one; a token restricted to some banks gets 403 on the others. The shared tokens of §2 and §2b (`--token-file`,
`--bank-token`) keep working, alone or next to a users file; their writes are recorded as made with the shared token
(`共享令牌`), with no person. With a users file and no shared token, every request needs a personal token. The token
itself is never written anywhere by the server: the access log has `"who": "alice"`, the journal and git have the
name.

**What each write records** (notes, corrections and lessons, with `--allow-write`):

| Where | What |
|---|---|
| The page | a note ends `— 来自 alice（MCP，claude-code）`; a correction page has `author:` and `written_at:`; a page it replaces gets `superseded_by_author:` |
| The change ledger | `90 系统文件/自动化/记忆变更记录.md`: the person, their app, the pages, the undo command |
| The journal | `90 系统文件/自动化/团队变更.jsonl`, one JSON line per write: `seq` (arrival order), `at` (UTC, ms), `who`, `via` (app), `auth` (`user`, `shared-token`, `open`), `tool`, `run`, `pages`, `text` (redacted, 200 characters), `supersedes`, `conflicts` |
| git | the commit's author is the person (`alice <alice@krouter.invalid>`; the committer stays `krouter-capture`), tagged `[krouter-run <id>]` |

"Who changed this page, and when": the `krouter_changes` tool (by page, by person, or by words of the note; read-only,
offered on a team server that has a users file or allows writes), `team.py changes --vault /srv/team-vault --page
"01 项目/数据库选型.md"`, or `git log`.

**One writer at a time.** Writes to one memory run one after another, in the order they reach the server: a lock in
the server and a file lock in its state folder. Pages are replaced in one step, so a lookup reading a page meanwhile
sees the old page or the new one. Two writes in the same second get different run ids (`…-2`), so undoing one never
takes the other.

**Two corrections of the same thing.** The later one to arrive holds; the earlier one is kept, marked superseded, and
named in the later one's reply. Concretely, when a correction names a page:

- that page is already superseded (someone corrected it since you looked): the new correction replaces the correction
  now in force at the end of the page's `superseded_by` chain, so the chain reads old page → first correction →
  second correction, and only the last is in force;
- the old line, on a long page, already has a `⚠ 已改` note: the correction pages those notes point to are replaced,
  and the new note goes below the earlier ones (top to bottom in arrival order);
- the page is another person's correction still in force: it is replaced as usual, and the reply says whose it was.

The reply then has a line such as `conflict: 05 时间日志/会话摘录/…｜纠正｜数据库改用 Postgres.md by alice at
2026-11-10T09:12:03.120+08:00 said "数据库改用 Postgres"; stale: the page named was already superseded. Rule: the
later correction holds; that page is kept, marked superseded.` The journal row carries the same, and `/metrics`
counts `krouter_correction_conflicts_total`. Nothing is deleted: every correction stays on disk and in git, and one
run can be undone on its own. A page in force that is long and is not a correction page is never voided whole: the
reply says `still active (a long page): read both`. "Later" means arrival at the server, not when the person typed it;
the rule settles which correction is in force, not which one is right.

**The change ledger stays small.** Every write adds an entry to `记忆变更记录.md`, and every write re-indexes that
page; past 256 KB it moves whole to `90 系统文件/自动化/记忆变更记录/<time>.md` (linked from the top of the new
page, in the same commit), so a write costs the same after a month as on the first day. The corrections log
(`纠错与取代记录.md`, a page of yours) is appended to by each correction and is not moved: about 280 bytes a
correction.

**With `--allow-write`, the server is the vault's writer.** If people also push to the vault's git remote, the
server's `git pull --ff-only` stops once the two have diverged: push the server's commits from the same cron job
(`git push`), or keep the server read-only and change the team vault through pull requests.

## 3. Each person

Add the team server as a second MCP server, next to the personal one:

```bash
# Claude Code (tested end to end against this server)
claude mcp add --transport http krouter-team https://krouter.your-team.example/mcp \
  --header "Authorization: Bearer $KROUTER_TEAM_TOKEN"

# Codex
codex mcp add krouter-team --url https://krouter.your-team.example/mcp --bearer-token-env-var KROUTER_TEAM_TOKEN
```

Any app that takes a remote ("Streamable HTTP") MCP server with a header takes the same URL and token. Questions to
the personal memory still go to the local stdio server and never reach the team server; questions to the team server
go only to the server you run.

**Tested:** the HTTP transport with a plain client (`tests/test_mcp_http.py`: token, health, bad requests, parallel
calls during an index update, the access log), the Docker image (`scripts/docker_smoke.sh`), and Claude Code 2.1
calling `krouter_ask` through `--transport http` with a bearer header. **Not yet:** Codex end to end (our one run
timed out before the first call), and other remote-MCP apps.

## 4. How big it can get

Measured on synthetic vaults (the template plus N generated pages) on an Apple M2 laptop with 8 GB of memory, the
server and its callers on the same machine.

**The server**, as a team uses it (`bench/scale/serve_load.py`: `krouter_ask` over HTTP, 4 resident lookup processes,
300 calls per row, none failed):

| Pages | One caller: median, answers/s | 8 callers: answers/s | 32 callers: median, p95, answers/s | Resident memory | Ready after |
|---|---|---|---|---|---|
| 1,000 | 5 ms, 195/s | 646/s | 42 ms, 77 ms, 742/s | 203 MB | 0.5 s |
| 10,000 | 13 ms, 77/s | 267/s | 104 ms, 112 ms, 301/s | 216 MB | 3.5 s |
| 50,000 | 54 ms, 17/s | 72/s | 377 ms, 651 ms, 75/s | 267 MB | 24 s |

Up to and including 1.3.0 the server started one process per lookup and re-checked every file each time; on the same machine: 91 ms and
42 answers/s at most on 1,000 pages, 210 ms and 15/s on 10,000, 980 ms and 3/s on 50,000 (32 callers: p95 14.8 s);
it held 15–29 MB. The server builds each memory's index before it starts listening, so the first person to ask does
not wait for it ("Ready after"). Three changes made the difference: resident lookup processes, the file re-check at most every
2 seconds, and the literal fallback (what a question the vault cannot answer costs) reading only the pages that can
hold the question, found in the index, instead of every file; it prints the same lines as reading every file (checked
on 2,442 pieces of real page text and in `tests/test_resident_lookups.py`). A resident process also no longer keeps
every SQLite connection it opened (each was about 2.7 MB until the garbage collector ran).

**One lookup in its own process**, as an agent's skill rule or `krouter ask` runs it (`bench/scale/run.py`, 30
lookups):

| Pages | First lookup (builds the index) | Later lookups, p50 / p95 | Peak memory | Index on disk |
|---|---|---|---|---|
| 1,000 | 0.6 s | 0.07 s / 0.08 s | 37 MB | 3 MB |
| 10,000 | 4.9 s | 0.13 s / 0.17 s | 43 MB | 29 MB |
| 50,000 | 25 s | 0.35 s / 0.36 s | 84 MB | 150 MB |

Here the time goes to checking every file's modification time on each lookup, which is why the server re-checks at
most every 2 seconds.

Rerun on your machine:

```bash
python3 bench/scale/gen.py 10000 /tmp/v10000
python3 bench/scale/serve_load.py /tmp/v10000 --concurrency 1,8,32 --calls 300
python3 bench/scale/run.py /tmp/v10000 --queries 30
```

Re-measured on 2026-11-10, same machine but busy (load average 8 to 11 from other test runs), 32 callers, 100 calls,
50,000 pages: the server before resident lookups (`482e6f2`) p50 10.5 s, **p95 14.8 s**, 2.8/s, which reproduces the
1.3-era row; 2.0 with `--workers 0` (one process per lookup, every file re-checked, the narrowed literal fallback)
p95 6.1 s; 2.0 as shipped p95 1.3 to 1.6 s, 24 to 29/s. The 8.7 s between the first two runs is mostly the old literal fallback, which read
every file for a question the index could not answer (other changes between those versions are mixed in); the
6.1 s → 1.5 s after it is one process per lookup with a full file walk each time. Neither is left in 2.0. The
same busy machine is slower than the idle one of the table above (one caller: 137 ms against 54 ms), so compare rows
taken on one day only.

## 5. Ten people at once

**Measured** with [`bench/team/load.py`](../bench/team/load.py) ([set 27](../bench/memory_honesty/HELDOUT.md#set-27-ten-people-with-their-own-agents-on-one-team-server-at-three-sizes-registered-2026-11-10-before-the-10000--and-50000-page-rows-were-run)):
one server with `--allow-write` and a users file of 10 personal tokens, on a git copy of the vault; 10 clients, each
with its own token and app name. First four bursts in which all ten do the same thing at once (ask; write a note;
correct one shared line of a long page; correct one decision, all naming its original page, so every correction after
the first contradicts one already in force), then a seeded mix of 40 operations each (60 % asks, 20 % notes, 10 %
corrections of the client's own lines on the shared page, 5 % of the decision, 5 % of the shared line). Apple M2,
8 GB, server and clients on one machine, which was busy with other test runs (load average 5 to 14). Default server
settings (4 lookup processes). KRouter at `c255760`.

| Pages | Reads p50 / p95 / p99 | Writes p50 / p95 / p99 | Done per second (mix): all, reads, writes | Errors | Ready after |
|---|---|---|---|---|---|
| 136 (template) | 39 / 129 / 234 ms | 1.09 / 1.38 / 1.46 s | 18.4, 10.4, 8.0 | 0 of 440 | 0.3 s |
| 10,136 | 102 / 284 / 396 ms | 1.52 / 2.01 / 2.15 s | 12.7, 7.2, 5.5 | 0 of 440 | 6.4 s |
| 50,136 | 446 / 2,010 / 2,885 ms | 2.99 / 4.35 / 4.65 s | 5.8, 3.3, 2.5 | 0 of 440 | 40 s |

Each row: 204 writes acknowledged, 90 correction replies with a `conflict:` line, 236 answers. **Every property held
at every size:** every acknowledged write is in the journal, in order, with its own run; every note is on its page
exactly once with its author; the page, the journal and the git author name the token's person for all 204 writes;
no page is unreadable or half-written, nothing is left uncommitted, `git fsck` passes; for each of the 25 contested
things (115 corrections) exactly one correction is in force, the last to arrive, the others are superseded in arrival order and each
reply names the one it replaced; every answer names its vault and a page or says `recall: none`; no token appears in
the server's log. After the run, a lookup on the contested decision lists the correction in force as its first
correction page, with `how: 现在：…` (the corrections log, a rule page, comes first overall).

**What the numbers mean.** Writes are one at a time per memory, so a write's time is mostly its wait behind the
others: with ten agents writing 40 % of the time, the queue is several deep. What one write costs is about
1 / writes-per-second: 0.13 s on the template, 0.18 s at 10,000 pages, 0.40 s at 50,000, most of it the two git
commits (about 20 ms each on a small repository, 150 ms on a 50,000-file one, on this machine). So one memory takes
about 8, 5 and 2.5 writes a second. Reads run beside writes, not behind them, but share the CPU with git. Ten agents in a
real team write a few times an hour, not twice a second; this is a stress test, not a forecast.

**Thirty minutes** ([set 28](../bench/memory_honesty/HELDOUT.md#set-28-thirty-minutes-of-mixed-load-registered-2026-11-10-before-the-run);
10,136 pages, the same ten clients without pause, 80 % asks): 21,218 calls (16,956 reads, 4,262 writes), **0 errors**,
every property above held (2,132 corrections of 32 contested things, 544 of them of one decision, all converged;
2,100 conflict replies each naming the right page). Server memory (server and its lookup processes) 195 MB at 5
minutes, 205 MB at the end, highest 230 MB: no growth. Reads p50 / p95 / p99 717 ms / 2.7 s / 4.1 s (slowest 8.2 s),
writes 291 ms / 1.6 s / 1.9 s, 11.7 calls a second. Reads are slower than in the short run because the pages every
write touches had grown: at the end each correction re-indexed the corrections log (589 KB, 0.39 s) and the long
shared page (0.15 s), each note the day's notes page (0.12 s), with the index locked meanwhile. **The first two
30-minute runs failed** and are kept in the log: one let corrections stand side by side after the 100th correction of
one decision, and the change ledger re-indexed at 1.6 MB slowed every lookup; the other lost the correction in force
among 544 replaced ones. All three are fixed (§2c) and have tests.

**The CI test** (`tests/test_team_concurrency.py`) runs the same harness on the template vault with 8 mixed operations
per client and two seeds, and asserts every property above, on Linux, macOS and Windows. **Identity and the conflict
rule** are tested in `tests/test_team_identity.py` (hashes only, the shared token still working, read-only tokens,
bank limits, re-reading the users file, the journal, git authors, `krouter_changes`, both conflict cases).

Rerun:

```bash
python3 bench/team/load.py --ops 40                                   # the template vault
python3 bench/scale/gen.py 10000 /tmp/v10000 && python3 bench/team/load.py --vault /tmp/v10000 --ops 40
python3 bench/team/load.py --vault /tmp/v10000 --duration 1800 --write-share 0.2 --rss-every 30 --out run.json
python3 bench/team/load.py --vault /tmp/v10000 --duration 43200 --write-share 0.05 --rss-every 300 --out 12h.json  # 12 hours: not run yet
```

The report is JSON: latency by kind, the checks with any failure's details, memory samples. Exit status 1 if any
check fails. Tokens are generated into the work folder and never printed.

**Known limits.** One memory takes a few writes a second, bounded by git. The corrections log
(`纠错与取代记录.md`) grows by about 280 bytes a correction and every correction re-indexes it (0.39 s at 589 KB, here
after about 2,000 corrections); a long page with hundreds of `⚠ 已改` notes and a busy day's notes page cost the same
way. A question worded like the corrections themselves can miss once more than about 80 nearly identical corrections
of one thing exist, since a lookup starts from the 80 best full-text matches.

**Not tested:** more than one machine (server and clients were on one laptop, over loopback); more than one server
writing the same vault; a real team using it over weeks (nobody has run it in production that we know of); networks
with real latency or TLS in front; agents other than the scripted clients (the clients are threads speaking MCP over
HTTP, not Claude Code or Codex sessions); more than 10 clients at once with writes; the server's own commits meeting
pushes from people to the same git remote.

## The team server at a glance (moved from the README)

One server holds the memories of a team, each one a folder of Markdown in its own git repository; everyone's agent
asks it over MCP. It is self-hosted: there is no KRouter cloud.

| | |
|---|---|
| **Deploy** | `mcp_server.py --http` (standard-library Python, no packages), the Docker image `ghcr.io/398894496-arch/krouter`, [Compose](../deploy/docker-compose.yml) (two memories and a git-pull sidecar), a [Kubernetes manifest](../deploy/kubernetes/krouter.yaml), a hardened [systemd unit](../deploy/systemd/krouter.service) |
| **Isolation** | several memories ("banks") on one server, each at `/mcp/NAME` with its own index, its own label on every answer and its own token; one bank's lookups never read another's folder |
| **Auth** | a token per person or agent (`--users`: only hashes kept, read or write, limited to some memories if you like), or one shared token per memory, or both; the server refuses to listen beyond this machine while any memory has none; browser Origins allow-listed; the access log keeps a hash of each question and the person's name, never the text or a token |
| **Attribution** | every write names who made it: on the page, in the change ledger, in a journal (`krouter_changes`: who changed this, and when) and as the git author; two people correcting one thing in opposite ways: the later holds, the earlier is kept as superseded and named in the reply |
| **Speed** | below, measured; 4 resident lookup processes per memory (`--workers`), so a lookup does not start Python |
| **Freshness** | files re-checked at most every 2 s (`--refresh-every`); a note written through the server is found by the very next lookup; Compose and Kubernetes pull each repository every 5 minutes |
| **Monitoring** | `GET /healthz`; Prometheus `GET /metrics`: calls by memory, tool and outcome, refusals, a latency histogram, index build time, lookup processes |
| **Writes** | read-only by default; `--allow-write` offers `krouter_note` and `krouter_correct`: one write at a time, one git commit each, listed in the change ledger; a `read` token is not offered them |
| **Backup, rollback** | the memory is the git repository: back it up like code, take a change back with `git revert`; the index is a cache rebuilt from the folder |

Measured with [`bench/scale/serve_load.py`](../bench/scale/serve_load.py) on synthetic memories, one Apple M2 laptop
(8 GB), the server and its callers on the same machine, 300 calls per row, none failed:

| Pages | One caller: median, answers/s | 8 callers: answers/s | 32 callers: median, p95, answers/s | Resident memory | Index build at start |
|---|---|---|---|---|---|
| 1,000 | 5 ms, 195/s | 646/s | 42 ms, 77 ms, 742/s | 203 MB | 0.5 s |
| 10,000 | 13 ms, 77/s | 267/s | 104 ms, 112 ms, 301/s | 216 MB | 3.5 s |
| 50,000 | 54 ms, 17/s | 72/s | 377 ms, 651 ms, 75/s | 267 MB | 24 s |

Ten people with their own tokens and agents reading and writing at once ([`bench/team/load.py`](../bench/team/load.py);
asks, notes, concurrent corrections of one page and contradicting corrections of one decision; the same laptop, then
busy with other test runs): reads p50 / p95 39 / 129 ms on the template, 102 / 284 ms at 10,000 pages,
446 / 2,010 ms at 50,000; one memory takes about 8, 5 and 2.5 writes a second (one at a time; the git commits are most
of it); no errors. Every write was attributed to the right person, nothing acknowledged went missing, and each contested
decision ended with the last correction in force. Thirty minutes of it at 10,000 pages: 0 errors in 21,218 calls, no memory growth (on the third run; the first two
found three bugs, now fixed). A smaller run of it is a CI test. Not tested: several machines, or a
real team over weeks.

Rerun it, and setup, tokens and TLS: [`docs/TEAM.md`](TEAM.md).

Which apps connect to a team server (from the README's "Works with" table):

| App | How it connects | Status |
|---|---|---|
| A team | a self-hosted HTTP server: [the team server at a glance](#the-team-server-at-a-glance-moved-from-the-readme) | tested with Claude Code, the MCP Python SDK and the JS client over HTTP |
| Apps that only take a remote MCP server | the same HTTP server, behind HTTPS | should work, not yet tested by us |
