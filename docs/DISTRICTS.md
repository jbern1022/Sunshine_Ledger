# Districts (state House, state Senate, US House)

Todoist 6hvxmFvCHr9x6cGp (district entity), 6hvxx9jRhJ5VVPPG (congressional).

## Loading (once, on the docker host)

```bash
docker exec sunshineledger-backend-1 python -m app.pipeline.load_boundaries --districts       # SLDL + SLDU (already loaded in prod)
docker exec sunshineledger-backend-1 python -m app.pipeline.load_boundaries --congressional    # TIGER 2024 CD119, 28 districts
docker exec sunshineledger-backend-1 python -m app.districts.service                           # build District rows + attach boundaries
docker exec sunshineledger-backend-1 python -m app.pipeline.demographic_overlay                # ACS, now incl. CD (needs CENSUS_API_KEY)
docker exec sunshineledger-backend-1 python -m app.federal.roster                              # members + tenures
```

Congressional polygons are stored as `scope_type="congress_district"` so they
never appear on the state-legislative sponsorship map (`/map/districts` reads
`scope_type="district"` only).

## Model

- `map_plans` (scope `state_legislature` | `congress`, effective dates) and
  `districts` (chamber `house` | `senate` | `us_house`, code `HD-101` /
  `SD-024` / `CD-012`). Several plans are in force at once, one per scope.
  After a redistricting add a new plan and districts; never edit old ones.
- Members come from `office_tenures` (dated). A person with no tenure on
  record for that kind of office falls back to the district on their current
  record, labelled `current_roster`.
- Sponsored bills: tenure covering `coalesce(introduced_date, last_action_date)`.
- `GET /districts`, `/districts/{code}`, `/districts/at?lat=&lon=` (point in
  polygon, nothing leaves the server), `district=` on `/bills` and `/people`.

## Check before relying on it

- Both plans use effective_from 2022-11-08 (the first election under those
  maps). Confirm against enactment, and confirm Florida has not enacted a newer
  congressional plan than the Census 2024 files reflect.
- ACS for congressional districts uses the Census `congressional district`
  geography in the 2024 5-year release (119th Congress boundaries).

## Not built

- Street address to district. It needs a geocoder, which would send the
  address to another service; that is a privacy decision for the owner.
  `/districts/at` takes a point and is local.
- Federal sponsorships/votes (Congress.gov key), so CD pages list members but
  no bills yet.
- Regions, and city commission districts (phase B).
