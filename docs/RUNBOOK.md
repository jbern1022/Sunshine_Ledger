# Sunshine Ledger — Operational Runbook

Practical reference for running, deploying, and debugging the live app.
Complements the [README](../README.md) (which covers setup/architecture) —
this covers what to do when something needs attention.

## Where things live

| Thing | Location |
|---|---|
| Docker host (Omen, Proxmox VM) | `192.168.4.20` — SSH alias `docker` |
| Ollama host (Powerstation) | `192.168.4.50:11434` at time of writing — **verify current IP first**, see "Powerstation IP drift" below |
| Compose project name | `sunshineledger` (containers: `sunshineledger-{db,backend,frontend,cloudflared}-1`) |
| Public frontend | https://sunshineledger.josephbernal.com |
| Public API | https://sunshineledger-api.josephbernal.com |
| Repos | GitHub `jbern1022/Sunshine_Ledger`, Gitea `gitea.josephbernal.com/joe/Sunshine_Ledger` (both kept in sync) |
| Local working copy | This Mac, `docker --context sunshine-vm compose ...` runs commands against the remote host without SSHing in manually |

## Deploy / redeploy

All commands run from the repo root on the local Mac, targeting the remote host via the `sunshine-vm` docker context:

```bash
docker context use sunshine-vm   # or prefix each command with --context sunshine-vm

# after changing backend code:
docker compose -f docker-compose.yml build backend
docker compose -f docker-compose.yml up -d backend

# after changing frontend code (NEXT_PUBLIC_* vars are baked in at build time):
docker compose -f docker-compose.yml build frontend
docker compose -f docker-compose.yml up -d frontend

# after adding/changing a model -- generate + apply a migration:
docker compose -f docker-compose.yml run --name sl_migrate --rm=false backend \
  alembic revision --autogenerate -m "description"
docker compose -f docker-compose.yml cp sl_migrate:/app/migrations/versions/<file>.py \
  backend/migrations/versions/<file>.py
docker compose -f docker-compose.yml rm -f sl_migrate
docker compose -f docker-compose.yml build backend   # bake the migration file in
docker compose -f docker-compose.yml run --rm backend alembic upgrade head
```

**Important**: `docker compose -f docker-compose.yml ...` (explicit `-f`) skips
`docker-compose.override.yml`, which is local-dev-only (bind mounts +
hot reload). Always use explicit `-f docker-compose.yml` against the remote
host — omitting it would try to bind-mount local Mac paths that don't exist
on the remote daemon.

**Container restarts wipe `/tmp`.** If you download something into a
container (e.g. a TIGER/Line shapefile) and then rebuild/restart that same
container before using the file, it's gone. Do the download and the work
that needs it in the same `docker compose exec` session, or write to a
mounted volume instead.

## Scheduled ingestion

`/home/joe/scripts/run-ingestion.sh` runs on Omen itself (not from the Mac)
via cron, operating directly on the live `sunshineledger-backend-1`
container with `docker exec` -- no repo checkout needed on that host.

```
0 4 * * *   /home/joe/scripts/run-ingestion.sh              # daily: LegiScan, Legistar, Miami iQM2, summarize
0 5 * * 0   /home/joe/scripts/run-ingestion.sh --with-gdelt # weekly (Sunday): adds GDELT headline refresh
```

GDELT is deliberately weekly, not daily -- it re-checks every bill in the
database against GDELT's free DOC API with an 8s/bill minimum throttle,
so a full pass takes multiple hours even before 429 retries. Daily would
hammer a free third-party API for no real benefit.

LegiScan ingestion skips bills whose `change_hash` hasn't changed since
the last pull (see `legiscan.py`), so daily reruns only spend API quota on
bills that actually changed -- important given the 30,000 query/month
free-tier cap. Legistar and Miami iQM2 don't have the same metering
concern and just upsert every run.

Logs land in `/home/joe/scripts/ingestion.log` on Omen (uncapped --
worth an eye on size over time, no rotation configured yet).

## Running pipeline jobs manually

For one-off/ad-hoc runs (backfills, testing changes) from the Mac against
the remote docker context, rather than the scheduled job above:

```bash
# Real FL state bills (needs LEGISCAN_API_KEY in .env)
docker compose -f docker-compose.yml exec -T backend python -c "
from app.db import SessionLocal
from app.pipeline.legiscan import ingest_state_bills
db = SessionLocal()
ingest_state_bills(db, limit=1897)  # omit limit for whatever the current session size is
"

# Real Jacksonville bills (client token: jaxcityc)
docker compose -f docker-compose.yml exec -T backend python -c "
from app.db import SessionLocal
from app.pipeline.legistar import ingest_local_bills
db = SessionLocal()
ingest_local_bills(db, client_name='jaxcityc', limit=200)
"

# Real Miami bills (scraped from iQM2, not Legistar -- see gotcha below)
docker compose -f docker-compose.yml exec -T backend python -m app.pipeline.miami_iqm2

# Summarize bills whose summaries are missing or stale. Safe and cheap to
# re-run: each claim stores a hash of what generated it (source text +
# model + prompt version), so unchanged bills are skipped without a model
# call, and amended bills are refreshed. The run logs how many it skipped.
docker compose -f docker-compose.yml exec -T backend python -m app.pipeline.summarize_batch

# Re-summarize everything regardless of hash (after a prompt change, say).
# Expensive at full corpus size -- normally the hash check is what you want.
docker compose -f docker-compose.yml exec -T backend python -m app.pipeline.summarize_batch --force

# One-off: mark pre-existing claims as current instead of re-summarizing
# them. Read the docstring first -- it asserts each stored summary came
# from the description now in the DB, which is false for any bill amended
# since it was last summarized.
docker compose -f docker-compose.yml exec -T backend python -m app.pipeline.summarize_batch --mark-current

# GDELT headlines (slow -- ~8s/bill minimum due to rate limiting, see gotcha below)
docker compose -f docker-compose.yml exec -T backend python -m app.pipeline.gdelt
```

## Secrets / rotation

All secrets live in `.env` on the local Mac (gitignored), read by `docker
compose` at deploy time -- **the file itself is never copied to the remote
host**, only the resolved container env vars are sent over the Docker API.

| Secret | Where to get a new one |
|---|---|
| `LEGISCAN_API_KEY` | legiscan.com account |
| `CLOUDFLARE_TUNNEL_TOKEN` | Zero Trust → Networks → Tunnels → sunshine-ledger. Rotating requires updating the tunnel in Cloudflare's dashboard, then `docker compose up -d cloudflared` |
| `POSTGRES_PASSWORD` | Change in `.env`, then `docker compose up -d db backend` -- existing data isn't affected, just the connection credential |
| `OLLAMA_HOST` | See "Powerstation IP drift" below |

## Known gotchas (learned the hard way during the build)

- **Powerstation IP drift — real cause found.** Not simple DHCP lease
  renewal as first assumed: the Powerstation has **two network interfaces
  live on the same LAN at once** -- wired Ethernet via a Hyper-V virtual
  switch ("LabSwitch", MAC `34-5A-60-C5-B5-3D`) and Wi-Fi (MAC
  `AC-F2-3C-CB-BC-B7`) -- each with its own DHCP-assigned IP (`.50` and
  `.48` respectively at time of writing). Ollama binds `0.0.0.0` so it's
  reachable on whichever is current; `OLLAMA_HOST` breaks silently
  whenever the "live" one isn't the one it's pointed at. If summarization
  stops working, check the Powerstation's current IP (`ipconfig` over
  SSH: `ssh powerstation "ipconfig | findstr IPv4"`) before assuming
  Ollama itself is down. Real fix: DHCP-reserve the wired MAC, or just
  disable Wi-Fi on a machine that's always plugged in anyway (see Todoist
  ticket).
- **Miami's iQM2 attachments are not bill text, and some contain personal
  data.** iQM2 legislation pages link documents via
  `FileOpen.aspx?Type=N&ID=NNNNN`. At least one of those is a scan of
  **public comment cards carrying residents' full names and home street
  addresses**. Do not add iQM2 attachment ingestion without a verified way
  to tell the legislation document apart from comment cards, minutes and
  videos — feeding one of these to the summarizer would republish private
  addresses on a public site and contradict the privacy page. Miami bills
  summarize from their descriptions instead, which is a deliberate choice,
  not an unfinished one (see the Todoist ticket for the full reasoning).
- **Legistar client tokens aren't guessable from the city name.** Miami's
  is `miamifl`, Jacksonville's is `jaxcityc`, Fort Lauderdale's is
  `fortlauderdale`. Wrong guesses 500 with `LegistarConnectionString
  setting is not set up in InSite for client: X` -- confirm via
  `https://webapi.legistar.com/v1/{token}/Matters?$top=1` before wiring
  up a new city.
- **`MatterName` is null on every Legistar client tested so far** (Miami,
  Jacksonville, Fort Lauderdale) -- the real title lives in `MatterTitle`.
  `legistar.py` already handles this; if a new city's ingestion produces
  bills with empty titles, this is the first thing to check.
- **Miami's Legistar client (`miamifl`) is not the city's real active
  data source.** It only has ~6 legacy records, no sponsor data. Miami's
  actual current legislation lives on a completely different platform
  (Granicus iQM2, `miamifl.iqm2.com`), scraped by `miami_iqm2.py` instead.
  If you're investigating a new city and its Legistar client returns very
  few records, check whether it's actually the city's primary system
  before concluding "not much data" -- it might be the wrong system
  entirely (Orlando: eSCRIBE. Tampa: Municode, and Municode is a codified-law
  repository, not a bill-tracker, so it's the wrong shape even if scraped).
- **Cloudflare's free Universal SSL only covers one level of wildcard
  subdomain.** A hostname like `api.sunshineledger.example.com` (two
  labels before the root domain) fails the TLS handshake outright --
  `curl` reports `TLS alert, handshake failure`, which looks like a
  connectivity problem but is actually a missing certificate. Keep every
  public hostname to a single label (`sunshineledger-api.example.com`,
  not `api.sunshineledger.example.com`).
- **GDELT's free DOC API rate-limits harder than documented.** Even an
  8-second-minimum throttle with 30s/2-retry backoff can still get
  bursts of 429s if run right after other GDELT activity. The batch
  script (`gdelt.py`) skips a bill that fails rather than aborting the
  whole run -- if a run comes back with low success numbers, it's likely
  rate limiting, not a code bug. Re-running later picks up where it left
  off (dedup by URL).
- **New `Entity` rows have `None`, not `{}`, for `external_ids`/
  `attributes` until the first `db.flush()`.** These columns use a
  DB-level `default=dict` that only applies at INSERT time. Spreading
  `{**entity.external_ids, ...}` on a freshly-constructed (unflushed)
  entity raises `TypeError: 'NoneType' object is not a mapping`. Always
  pass `external_ids={}` explicitly in the constructor, or flush first.
- **Watch DB column length limits when ingesting free-text fields from
  external sources.** `entity.name` is capped at 500 chars, `bill.chamber`
  at 50 -- both have been hit by real data (a Legistar `MatterTitle` or a
  `department` field longer than the column). Truncate before storing IDs
  that don't have a controlled max length.

## Running tests

```bash
./scripts/run-tests.sh
```

Spins up an ephemeral Postgres/PostGIS container (tmpfs data, distinct db
name, port never exposed to the host) on the **local Docker Desktop
context**, runs the backend pytest suite against it, then tears the whole
stack down -- pass or fail. It never touches the `sunshine-vm` remote
context or any real data; that's why the script hardcodes
`--context desktop-linux` rather than using whatever context happens to be
active.

Coverage so far: pure-function pipeline parsing/mapping (`legiscan.py`,
`gdelt.py`) and the bills/flags API routes (including the admin auth
gate), using FastAPI's `TestClient` with a real DB per test rolled back
via a savepoint.

Frontend tests run separately (Vitest + React Testing Library, no
container needed -- everything's mocked at the `lib/api` boundary):

```bash
cd frontend && npm test
```

Covers `BillCard` (expand-to-fetch-sources, flag submission success/error)
and the browse page (`geo`-filter passthrough to the API, pagination).
No component/integration tests for the map view yet (Leaflet + jsdom is
more friction than it's worth right now).

## Reviewing flags

`GET /flags/admin` (HTTP Basic Auth, credentials in `.env` as
`ADMIN_USERNAME`/`ADMIN_PASSWORD`) lists submitted "flag this" reports,
newest first, defaulting to `status=pending`. Each includes the bill
number/name, the reporter's text, and their email if they gave one.

```bash
curl -u admin:<password> "https://sunshineledger-api.josephbernal.com/flags/admin"

# after acting on one:
curl -X PATCH -u admin:<password> -H "Content-Type: application/json" \
  -d '{"status": "reviewed"}' \
  "https://sunshineledger-api.josephbernal.com/flags/admin/<flag-id>"
```

Valid statuses: `pending` (default filter), `reviewed`, `dismissed`, or
pass `?status=all` to see everything. If `ADMIN_PASSWORD` isn't set, these
endpoints reject every request rather than falling back to a guessable
default.

## Monitoring

None yet — see the "add uptime monitoring" ticket. In the meantime, a
manual health check:

```bash
curl -s https://sunshineledger-api.josephbernal.com/health
curl -s -o /dev/null -w "%{http_code}\n" https://sunshineledger.josephbernal.com/
```

## Backups

Automated, off-box, and restore-tested as of 2026-08-04.

- **What**: `pg_dump -F c` (custom format, compressed) of the full
  database, run against the live `sunshineledger-db-1` container.
- **Where**: `/home/joe/scripts/backup-db.sh` on the Omen host, cron'd
  daily at 03:00 (`crontab -l` on Omen to confirm). Local copies land in
  `/home/joe/sunshineledger-backups/` on Omen.
- **Off-box destination**: rsynced to the Pi (`192.168.4.2`,
  `/home/joe/backups/sunshineledger/`) — a separate physical device, so an
  Omen disk failure doesn't take the backups with it. The rsync uses a
  dedicated key (`~/.ssh/sunshineledger_backup_key` on Omen) restricted via
  `rrsync -wo` in the Pi's `authorized_keys` — that key can only write into
  that one directory, nothing else on the Pi is reachable with it.
- **Retention**: 14 days, pruned automatically both on Omen (by the backup
  script itself) and on the Pi (separate cron job there, since the
  restricted key can't run arbitrary prune commands remotely). On Omen the
  prune runs *before* the dump, deliberately — see below.
- **Failure handling**: the script fails loudly (`BACKUP FAILED: <reason>`
  on stderr) and deletes its own partial dump, so the backup directory
  never contains a file that isn't a real backup. It checks free space up
  front, runs `pg_restore --list` against the dump to confirm the archive
  is actually restorable, and enforces a minimum size as a backstop.

  **A backup that "exists" is not a backup that works.** On 2026-08-21 a
  full disk produced a 0-byte dump that looked like a success until the
  log was read by hand. The failure was also self-reinforcing: retention
  pruning used to run at the *end*, so an aborted run never pruned, and
  the next run had no more space than the last. If you touch the ordering
  in this script, keep the prune first.

  Cron still swallows the non-zero exit, so nothing actively alerts yet —
  check `/home/joe/scripts/backup.log`, or grep it for `BACKUP FAILED`.

### Restoring

```bash
# Get a dump onto the box you're restoring to (from Omen or the Pi copy),
# then, against a target Postgres/PostGIS instance:
docker cp sunshineledger-<timestamp>.dump <target-container>:/tmp/restore.dump
docker exec <target-container> pg_restore -U sunshine -d sunshine_ledger --no-owner /tmp/restore.dump
```

Expect three harmless `schema "tiger"/"tiger_data"/"topology" already
exists` errors if restoring into a fresh `postgis/postgis` image (it
creates those schemas itself on init; pg_dump also captures them since the
extension owns them). Everything else should restore cleanly.

**This was verified end-to-end on 2026-08-04**: restored a real production
dump into a disposable throwaway container and confirmed `entities` (bill
count) and `claims` counts matched production exactly (2,311 bills, 4,240
claims), with real bill numbers present. The disposable container was
removed after verification — this wasn't left running.
