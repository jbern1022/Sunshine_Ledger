# Promise baseline (2026 Florida legislature winners)

Todoist: 6hvxpp58fXp6cgfp (parent) and 6hvxrjFpXCFP6xvp, 6hvxrjHc369MQR8p,
6hvxrjGmcGjQ66Pp, 6hvxrjMqXGM5QfWp, 6hvxrjM44Ch3438G. Owner decisions of
2026-11-03 govern; this file is how the built pieces fit together and what is
still open.

## Pipeline

1. **Winners** `python -m app.promises.winners winners.csv --source-url URL [--certified]`
   Seat-level list (cycle, chamber, district, name, party, incumbent) from a
   Division of Elections export. `results.elections.myflorida.com` returns a
   block page to scripts, so the CSV is downloaded in a browser. Re-run with
   `--certified` after certification: changes are written to `change_log`, a
   certified seat is never set back. Winners link to an existing person only
   when chamber, district and name all agree.
2. **Sites** `python -m app.promises.sites --senate-pages` and
   `--csv sites.csv` (`chamber,district,url[,kind,discovered_via]`).
   Only the candidate's own pages. Social platforms are refused. A directory
   may be used to find a URL (`discovered_via=directory`), never as a source.
3. **Crawl** `python -m app.promises.crawler [--max-requests N] [--pace S]`
   robots.txt honoured (incl. Crawl-delay), 60 s per host by default, 400
   requests per run, same-host links to issues/about/news pages only (8 pages
   per site), HTML only, 3 MB cap, cross-host redirects refused. Snapshots are
   stored by sha256 under `SNAPSHOT_DIR` (`/data/snapshots`, a compose volume)
   with fetch time and hash. A re-run resumes: finished pages are skipped,
   `unavailable` ones retry after a day. A gone site is marked offline and the
   Internet Archive copy is snapshotted (capture time stored separately).
4. **Extract** `python -m app.promises.extract` (needs Ollama: run from the
   Mac, not Docker). Passages are kept only if found byte for byte in
   `snapshot_text(body)`; offsets, source URL and capture time are stored; the
   model's labels are drafts under `auto_labels`. `verify_item` re-checks.
5. **Review** `GET /promises`, `GET /promises/{id}`, `POST /promises/{id}/flag`
   (public); `GET /promises/admin/queue`, `POST /promises/admin/{id}/review`
   (admin). Queue order: flagged, drafted commitments, the rest, oldest first.
   Every action is logged. `GET /promises/coverage` lists the gaps.

There is no fulfillment column anywhere; verdicts need a human and a later,
separate design.

## Not done / needs someone

- **No winners are loaded.** Needs the Division of Elections CSV export
  (browser download). Run `winners` unofficial now, `--certified` after
  certification.
- **Campaign-site URLs have no automatic source.** State candidate listings
  rarely carry them and House member pages are keyed by member id. Supply
  them through `sites --csv` (found by hand or from a directory, recorded as
  such). Incumbent senators get their flsenate.gov page automatically.
- **New people are not created.** A winner with no existing person stays
  unlinked; a dated-tenure model is the tenure-end ticket (6hvxq2x37jGMjR5G).
- **No frontend yet** for the public list, the flag button or the review
  queue; the API is done and tested.
- **Migration** `d7a3c1e8b5f2` sits on `b6d2f9a3c715` (main's head). If
  `feat/tag-quarantine` merges first, repoint `down_revision` at its head.
- **docker-compose.yml** gains a `snapshots` volume on the backend; the
  deploy recreates the backend container.
- Statement dates are left empty unless a later step can read them off the
  page; `captured_at` is always the fetch time.
