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
python3 skill/krouter-obsidian/scripts/mcp_server.py --http 0.0.0.0:8787 \
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
python3 skill/krouter-obsidian/scripts/mcp_server.py --http 0.0.0.0:8787 \
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
`krouter_index_build_seconds{vault}` and `krouter_uptime_seconds`. It holds counts only, never a question; when the
server has tokens, it takes any of them (`authorization: {credentials_file: …}` in the Prometheus scrape config).

**Compose.** [`deploy/docker-compose.yml`](../deploy/docker-compose.yml) runs the server with two banks, read-only
and as user 10001, next to a small container that pulls each vault every five minutes. Checked with
`docker compose config`; the multi-bank server itself is tested in `tests/test_mcp_banks.py`.

| Running it | What KRouter does |
|---|---|
| Storage | Markdown files in a git repository you own; the index is a rebuildable SQLite cache |
| Isolation | one bank per memory: own URL, own token, own index, own label on every answer |
| Access | bearer token per bank or per server, constant-time compare; loopback only without one; origin check |
| Monitoring | `/metrics` (Prometheus), `/healthz`, one JSON access-log line per request with a hash of the question |
| Deployment | `python3 mcp_server.py --http`, the Docker image (non-root, read-only vault, provenance attestation), Compose |
| Scale | 10,000 pages: 0.12 s per lookup (p50); 50,000: 0.53 s ([§4](#4-how-big-it-can-get)) |
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

Measured with `bench/scale/` on synthetic vaults (the template plus N generated pages), on an Apple M2 laptop with
8 GB of memory, each lookup in its own process as the MCP server runs it:

| Pages | First lookup (builds the index) | Later lookups, p50 / p95 | Peak memory | Index on disk |
|---|---|---|---|---|
| 1,000 | 0.4 s | 0.08 s / 0.09 s | 37 MB | 3 MB |
| 10,000 | 4.8 s | 0.12 s / 0.19 s | 41 MB | 27 MB |
| 50,000 | 24 s | 0.53 s / 1.14 s | 76 MB | 139 MB |

Over HTTP on the 10,000-page vault, 16 parallel callers right after 200 pages changed got every answer (none
failed, slowest 2.2 s); 64 calls from 16 threads took 0.96 s at the median and 1.28 s at p95. The server builds the
index before it starts listening, so the first person to ask does not wait for it.

Past about 10,000 pages the time goes to checking every file's modification time on each lookup. A team vault of a
few thousand pages answers in about a tenth of a second.

Rerun on your machine:

```bash
python3 bench/scale/gen.py 10000 /tmp/v10000
python3 bench/scale/run.py /tmp/v10000 --queries 30
```
