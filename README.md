# Sunshine Ledger

A Bernal Labs project. Florida state and local bill tracker: plain-language
"what it does" / "who it affects" summaries, county/city-level impact
mapping, and hidden-by-default expandable source citations.

Full requirements: [`docs/Sunshine_Ledger_BRD.docx`](docs/Sunshine_Ledger_BRD.docx),
[`docs/Sunshine_Ledger_Project_Charter.docx`](docs/Sunshine_Ledger_Project_Charter.docx),
[`docs/Sunshine_Ledger_Phased_Roadmap.docx`](docs/Sunshine_Ledger_Phased_Roadmap.docx).

This repo implements the full **Roadmap MVP build order, Steps 1–10**:
schema → summarization-quality gate tooling → one-bill-by-hand proof →
automated LegiScan/Legistar ingestion → browse/search frontend → map view →
Miami/Jacksonville local bills → flag-this feedback → homepage IP geo-filter
→ thin GDELT headline layer.

## Stack

- **Backend**: Python / FastAPI / SQLAlchemy 2.0 / GeoAlchemy2 / Alembic, Postgres + PostGIS
- **Frontend**: Next.js (App Router) / TypeScript / Tailwind / react-leaflet
- **LLM**: Ollama (point `OLLAMA_HOST` at your home-lab instance, e.g. the Powerstation)

## Schema (Roadmap Step 1)

Shared graph schema per the BRD glossary — `entities` / `relationships` /
`events` / `sources` / `spatial_contexts` — plus two bill-specific tables:
`bills` (1:1 extension of a `bill`-type entity) and `claims` (one row per
displayable statement, e.g. one "what it does" summary), joined to
`sources` through `claim_sources` so each claim can show its own source
count without fetching a whole bill's citations at once. See
[`backend/app/models/`](backend/app/models/).

## Running it

```bash
cp .env.example .env   # fill in LEGISCAN_API_KEY / OLLAMA_HOST when you have them
docker compose up -d --build
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.pipeline.seed
```

Then open http://localhost:3010 (browse) and http://localhost:3010/map.
API docs at http://localhost:8010/docs.

`docker compose up` on a local Docker Desktop host auto-applies
`docker-compose.override.yml` (bind mounts + hot reload). Deploying to a
remote Docker host (e.g. via `docker context`) should skip it:

```bash
docker context use <your-remote-context>
docker compose -f docker-compose.yml up -d --build
docker compose -f docker-compose.yml run --rm backend alembic upgrade head
docker compose -f docker-compose.yml run --rm backend python -m app.pipeline.seed
```

Set `NEXT_PUBLIC_API_URL` in `.env` to whatever address your **browser**
can reach the API at — `localhost` only works if the frontend and your
browser are on the same machine.

### Seed data vs. real data

`python -m app.pipeline.seed` loads 8 sample bills (state + Miami +
Jacksonville) and approximate county boundary polygons, so the app is
fully browsable without any API keys. All seed bill numbers are tagged
`(DEMO)` and boundary polygons are explicitly marked as non-survey-accurate
placeholders — replace them before any real deployment:

```bash
# Real county boundaries (BRD 5.3 requires actual TIGER/Line geometry).
# Nationwide county file -- filter to Florida via state_fips="12".
# Use NAMELSAD, not NAME -- it includes the "County" suffix already used
# everywhere else (bill geo_scope_names, seed data), so scope_name matches
# with zero transformation.
docker compose exec backend python -c "
import httpx, zipfile
from pathlib import Path
from app.db import SessionLocal
from app.pipeline.load_boundaries import load_tiger_shapefile

url = 'https://www2.census.gov/geo/tiger/TIGER2024/COUNTY/tl_2024_us_county.zip'
resp = httpx.get(url, timeout=120, follow_redirects=True)
open('/tmp/tl_county.zip', 'wb').write(resp.content)
zipfile.ZipFile('/tmp/tl_county.zip').extractall('/tmp/tiger_county')

db = SessionLocal()
load_tiger_shapefile(db, Path('/tmp/tiger_county/tl_2024_us_county.shp'),
    scope_type='county', name_field='NAMELSAD', state_fips='12',
    name_filter=['Miami-Dade County', 'Duval County'])
"

# Real Florida state bills (needs LEGISCAN_API_KEY in .env). Omit `limit`
# for the full session (~1,900 bills, ~3 min at observed throughput).
docker compose exec backend python -c "
from app.db import SessionLocal
from app.pipeline.legiscan import ingest_state_bills
db = SessionLocal()
ingest_state_bills(db, limit=20)
"

# Real Jacksonville local bills (public Legistar API, no key needed)
docker compose exec backend python -c "
from app.db import SessionLocal
from app.pipeline.legistar import ingest_local_bills
db = SessionLocal()
ingest_local_bills(db, client_name='jaxcityc', limit=20)
"

# Real Miami local bills -- Miami's Legistar client ('miamifl') turned out
# to hold only a handful of legacy records with no sponsor data. The city's
# actual active legislative record lives on a different Granicus product
# (iQM2, miamifl.iqm2.com) with no public API, so this scrapes it instead:
docker compose exec backend python -m app.pipeline.miami_iqm2
```

Note on Legistar client tokens: they aren't guessable from the city name.
Miami's is `miamifl`, Jacksonville's is `jaxcityc` -- found by probing the
live API / searching the city's public portal, not from any documentation.

## Steps 8–10

- **Step 8 — flag this (BRD 5.5).** Every bill card has a "Flag this" link
  that posts to `POST /flags` (reason text + optional email). Flags route
  to manual review only — there's deliberately no public `GET /flags`
  endpoint or open-editing UI; review them directly in Postgres
  (`SELECT * FROM flags WHERE status = 'pending'`).
- **Step 9 — homepage geo-filter (BRD 5.6).** [`frontend/middleware.ts`](frontend/middleware.ts)
  detects the visitor's state/city from `CF-Connecting-IP` (once behind the
  planned Cloudflare Tunnel) or `X-Forwarded-For`, and redirects a first-time
  visit from Florida to `/?jurisdiction=<city or FL>`. A `sl_geo_resolved`
  cookie makes this a one-time default per browser — the jurisdiction
  dropdown always lets you view everything regardless of what was detected.
  Direct/local access without a reverse proxy has no IP to detect, so it's a
  safe no-op in dev.
- **Step 10 — GDELT headlines (BRD 5.7).** [`app/pipeline/gdelt.py`](backend/app/pipeline/gdelt.py)
  pulls keyword-matched headlines per bill from GDELT's free DOC 2.0 API and
  stores each as an `Event(event_type='news_mention')` + `Source`, deduped
  by URL. No sentiment/stance scoring (deferred to Phase 2 per BRD 5.7).
  Run as a periodic batch, not interactively — GDELT's free tier rate-limits
  aggressively and its window isn't published; the client throttles to one
  request per ~8s and retries on 429, but a burst across many bills can still
  get throttled, in which case affected bills are skipped for that run
  rather than failing the whole batch:
  ```bash
  docker compose exec backend python -m app.pipeline.gdelt
  ```

## The build-order gates (Roadmap Section 8)

Before trusting the automated pipeline above on real bills:

1. **Step 2 gate — summarization quality.** Run
   `python -m app.pipeline.review_summaries` (needs `OLLAMA_HOST` reachable)
   against 15–20 *real* bills and read the output critically. Swap the
   bundled `sample_data/sample_bills_for_review.json` for real bill text
   pulled from LegiScan first — the bundled file is illustrative only.
2. **Step 3 proof-of-shape.** `python -m app.pipeline.one_bill_by_hand`
   pushes one bill through pull → summarize → geo-tag → store → display,
   to prove the schema/pipeline shape before trusting Step 4's automation.
3. **Step 7 gate — local data feasibility.** After ingesting Miami and
   Jacksonville for real, be honest about how much manual cleanup was
   needed before deciding whether 5-city local coverage (a later phase) is
   realistic.

## Repo layout

```
backend/
  app/models/       Entity/Relationship/Event/Source/SpatialContext + Bill/Claim/Flag
  app/api/          FastAPI routers: /bills, /map, /flags
  app/pipeline/      legiscan.py, legistar.py — ingestion
                      miami_iqm2.py — Miami-specific scraper (see note above)
                      summarize.py, review_summaries.py — LLM + Step 2 gate
                      geotag.py, load_boundaries.py — BRD 5.3 geo-tagging
                      one_bill_by_hand.py — Step 3 proof
                      gdelt.py — Step 10 headline pull
                      seed.py — sample data for local dev/demo
  migrations/        Alembic
frontend/
  app/                Next.js pages: browse (/), map (/map)
  components/         BillCard (sources, flag-this, news), MapView
  middleware.ts        Step 9 IP-based geo-filter
docs/                 Source BRD / Charter / Roadmap
```

## Security notes for public exposure

Hardened ahead of exposing this beyond the LAN via Cloudflare Tunnel:

- **CORS** is a config-driven allowlist (`CORS_ALLOWED_ORIGINS`), not a
  wildcard. Add the public domain there before it's live.
- **Rate limiting** (`slowapi`): 120/min per IP globally, 5/min per IP on
  `POST /flags` specifically (the one public write endpoint).
- **Security headers**: `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy` set on every response.
- **Error responses** are plain Pydantic validation errors — no
  tracebacks; confirmed no `--reload`/debug mode in the production compose
  file (only `docker-compose.override.yml`, used for local dev, adds it).

**When wiring up the Cloudflare Tunnel ingress, only route the frontend
and backend services.** Do not add Postgres (`POSTGRES_PORT`, default
5433) to the tunnel config — it has no auth hardening applied and was
never intended to be internet-reachable.

Still open, worth deciding before going fully public: there's no
authentication anywhere (matches the BRD's public-read, no-accounts MVP
scope) and no CAPTCHA-equivalent on `/flags` beyond the rate limit — low
risk at current traffic levels, worth revisiting if abuse shows up.

## Not yet built (out of this session's scope)

- BRD 5.8: Florida election calendar surfacing
- A dedicated standalone sources page (sources currently expand inline on
  the bill card only, per BRD 5.4's "inline rather than a separate page")
- Everything in Phase 2/3 and Nationwide Expansion (rhetoric layer, ACS/BLS
  overlays, ballot lookup, federal entities) — deliberately deferred per
  the Roadmap
