# AWS Migration Path

BRD 6 non-functional requirement: *"Architecture shall support a clean
migration path from local hosting to AWS (RDS, Lambda/ECS, S3) once traffic
or reliability needs exceed what home infrastructure can support -- favoring
containerization now so that transition does not require a rebuild."*

This documents what that migration actually looks like, verified against the
real codebase rather than assumed from the containerization alone -- and the
one piece that isn't as clean as "just deploy the images."

## Current architecture (home-lab)

Docker Compose on a single Proxmox VM ("Omen"): `db` (postgis/postgis),
`backend` (FastAPI), `frontend` (Next.js `next dev`), `cloudflared` x2
(tunnel, no inbound ports opened on the home network). No host-specific
bind mounts in the production compose invocation -- `docker-compose.yml`
alone (not `docker-compose.override.yml`, which is dev-only and only
auto-applies on a local Docker Desktop context) bakes code into images via
`COPY . .`, matching how ECS/Fargate expects to consume images.

## Audit: is it actually portable?

Grepped the codebase for hardcoded host references. Every one found is a
`localhost`/`http://localhost:*` **default** in `backend/app/config.py`,
`docker-compose.yml`, and `frontend/lib/api.ts` -- all overridable via env
var (`DATABASE_URL`, `CORS_ALLOWED_ORIGINS`, `NEXT_PUBLIC_API_URL`), which
is exactly what a Fargate task definition or Lambda environment would set.
No code path assumes the home-lab network, and Alembic migrations are
already written against vanilla SQLAlchemy/PostGIS with no Omen-specific
assumptions (see the `include_object` filter in `migrations/env.py`, which
exists to skip PostGIS's own `tiger`/`topology` tables regardless of host).

**The one real exception: `OLLAMA_HOST`.** LLM summarization currently
points at `192.168.4.50:11434` -- a GPU box on the home LAN (RTX 5070, see
`docs/RUNBOOK.md`'s "Powerstation IP drift" gotcha). This does not migrate
by just moving containers to AWS; it's the one component genuinely tied to
home infrastructure. Options at migration time, in rough order of
preference:

1. **Swap to a hosted LLM API** (Anthropic/OpenAI/Bedrock) for
   summarization. Least infra to manage, ongoing per-token cost instead of
   sunk hardware cost -- probably the right call once volume justifies AWS
   at all, since it also sidesteps needing a GPU instance. Directly
   relevant to the "LLM cost management at scale" ticket (caching + a
   cheap triage model in front of the expensive one applies here too).
2. **Hybrid**: keep Ollama on the Powerstation, reach it from AWS over a
   VPN/Tailscale tunnel. Avoids a rewrite of `summarize.py`'s prompt
   handling, but reintroduces the exact home-network-dependency fragility
   (IP drift, single point of failure, no redundancy) that this migration
   would otherwise be solving.
3. **Self-hosted GPU instance in AWS** (`g4dn`/`g5` family running Ollama).
   Removes the home-network dependency entirely but is the most expensive
   option by far -- GPU instances are billed whether or not a
   summarization job is running, unlike the sunk-cost home GPU.

Everything else -- Postgres/PostGIS, FastAPI, Next.js, the ingestion
pipelines (LegiScan/Legistar/iQM2/GDELT, all outbound-only HTTP) -- has no
comparable blocker.

## Target architecture

| Component | Home-lab today | AWS target |
|---|---|---|
| Database | `postgis/postgis` container | RDS for PostgreSQL with the `postgis` extension enabled. Confirm the target RDS engine version's supported PostGIS version at migration time (RDS lags upstream PostGIS releases by version) -- currently pinned to `postgis/postgis:16-3.4` locally. |
| Backend | FastAPI container, `uvicorn` | ECS Fargate, not Lambda. FastAPI holds a persistent SQLAlchemy connection pool (`app/db.py`); Lambda's per-invocation cold-start model fights that (would need RDS Proxy + a rewrite to lazy-init the pool per invocation, plus a Mangum adapter). Fargate runs the existing container image with zero code changes. |
| Frontend | Next.js container, `next dev` | ECS Fargate running `next build && next start`, **not** `next dev` as currently configured (see "Known gap" below) -- or S3 + CloudFront if/when the app moves to static export, which it currently doesn't (server-rendered pages hitting the API at request time). |
| LLM summarization | Ollama on home GPU | See options above -- likely a hosted API. |
| Ingestion pipelines | `docker compose exec` one-off runs + cron on Omen | EventBridge Scheduler + ECS scheduled tasks (or Lambda, since these are bounded batch jobs with no persistent connection pool concern), same container images. |
| Reverse proxy / TLS | Cloudflare Tunnel (no inbound ports) | ALB + ACM, or keep Cloudflare in front of the ALB for continuity (DNS doesn't need to change either way). |
| Backups | `pg_dump` cron -> rsync to a Pi | RDS automated snapshots supersede this outright. |
| Secrets | `.env` file, Docker Compose env vars | AWS Secrets Manager or Parameter Store, injected as task-definition env vars -- same variable names, no application code changes. |

## Known gap found during this audit

`docker-compose.yml`'s `frontend` service runs `npm run dev`, i.e. Next.js
dev-server mode, in what's otherwise the production deployment. This
works but isn't what "clean AWS migration" should carry forward --
`next dev` doesn't optimize the build and behaves differently from `next
start` under load. Worth switching to `next build && next start` in
`docker-compose.yml` regardless of AWS timing; flagging here since this
audit is what surfaced it. Not fixed in this pass -- out of scope for a
verification/documentation ticket, and switching the live frontend's run
mode deserves its own change and testing pass.

## Trigger threshold: when to actually move

No single metric alone; move when **any** of these hold, since each
represents a different way home hosting stops being sufficient:

- **Reliability**: more than one home-network/power/ISP outage per
  quarter that takes the public site down for a real user-visible window
  (Cloudflare Tunnel already means no port-forwarding fragility, but the
  origin -- Omen -- is still a single physical machine on a residential
  connection).
- **Traffic**: sustained load that visibly competes with other services
  on the same home-lab host, or that a residential upload connection
  can't serve responsively (state this in terms of the actual symptom --
  slow response times under load -- rather than a specific number, since
  the residential connection's real ceiling isn't measured yet).
- **Data volume**: nationwide expansion (per the Roadmap) multiplies bill
  volume by roughly 50x FL's, which is also when local Postgres storage
  and the manual backup-to-Pi process stop being appropriately sized.
- **Team**: a second person operating this who doesn't have SSH access to
  Omen -- AWS's IAM model handles multi-operator access; ad hoc SSH keys
  don't.

None of these are close today (single state, one operator, home hosting
has been stable). This is a documented decision point, not a near-term
plan.
