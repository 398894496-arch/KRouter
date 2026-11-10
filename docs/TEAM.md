# A memory for a team

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
  ghcr.io/398894496-arch/krouter:v1.3.0
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
| Access | bearer token per bank or per server, constant-time compare; loopback only without one; origin check |
| Monitoring | `/metrics` (Prometheus), `/healthz`, one JSON access-log line per request with a hash of the question |
| Deployment | `python3 mcp_server.py --http`, the Docker image (non-root, read-only vault, provenance attestation), Compose, Kubernetes, systemd |
| Scale | over HTTP, 10,000 pages: 13 ms per lookup (median), 301 answers/s with 32 callers; 50,000: 54 ms, 75/s ([§4](#4-how-big-it-can-get)) |
| Backups | the git remote, and `backup.py` for an encrypted nightly copy of a personal vault |
| Not offered | a hosted service, SSO, per-user permissions inside one bank: give each group its own bank |

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
