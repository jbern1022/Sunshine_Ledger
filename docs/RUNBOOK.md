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

## Running pipeline jobs manually

No scheduler exists yet (see the "scheduled ingestion pipeline" ticket) --
everything below is run by hand via `docker compose exec`:

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

# Summarize everything that doesn't have a summary yet (safe to re-run --
# only processes bills with zero existing claims)
docker compose -f docker-compose.yml exec -T backend python -m app.pipeline.summarize_batch

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

- **Powerstation IP drift.** The Ollama host's DHCP-leased IP has changed
  at least once (`192.168.4.48` → `192.168.4.50`) across a sleep/wake
  cycle, silently breaking `OLLAMA_HOST` with no clear error until you
  actually try to summarize something. If summarization suddenly stops
  working, check the Powerstation's *current* IP before assuming Ollama
  itself is down. A DHCP reservation would fix this permanently (see
  Todoist ticket).
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
  restricted key can't run arbitrary prune commands remotely).

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
