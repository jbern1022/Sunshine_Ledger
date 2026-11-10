# Privileged access audit (2026-11-10)

Todoist 6hrmmvf6GRGfCp8p. Owner decision 2026-10-29: reader MFA is optional;
privileged access requires MFA through a separate administrator
authentication; do not assume the reader Cognito setup secures admin routes;
do not migrate the admin identity provider automatically; do not put
interactive MFA on machine service accounts. This is the "inspect and document
actual coverage and gaps" step. Nothing was changed.

## What exists

One shared HTTP Basic credential (`app/auth.py::require_admin`). Constant-time
comparison; fails closed when `ADMIN_PASSWORD` is unset (every request 401). In
production the password is set and the username is the default `admin`.
Unauthenticated calls to every route below return 401 (checked live
2026-11-10 for the promise queue, flag review and layer review routes).

Routes behind it:

| Route | Does |
|---|---|
| `GET /flags/admin` | list challenges |
| `POST /flags/admin/{id}/triage` | set severity, mark disputed |
| `POST /flags/admin/{id}/decide` | decide a challenge, create a correction record |
| `POST /corrections/admin` | publish a correction |
| `POST /responses/admin` | publish a right-of-reply |
| `GET /bill-layers/admin/unreviewed` | list unreviewed layer blocks |
| `POST /bill-layers/admin/{layer_id}/review` | approve/reject a layer block |
| `PATCH /bills/tags/{bill_tag_id}` | hide or restore a topic badge |
| `GET /promises/admin/queue` | promise review queue |
| `POST /promises/admin/{id}/review` | approve/reject/classify a promise statement |

Not behind it, by design: ingestion and every `python -m app.pipeline.*` /
`app.federal.*` / `app.promises.*` job. They run by `docker exec` on the
docker host and use no HTTP credential, so they are the "machine" side and need
no interactive MFA.

## Gaps

1. **No second factor.** Password only. This is the gap the decision names.
2. **One shared identity.** Every action is recorded as reviewer `admin`
   (`promise_reviews.reviewer`, correction and flag decisions). With more than
   one reviewer the log cannot say who did what.
3. **Default username.** `admin` is guessable, so an attacker needs only the
   password.
4. **No lockout or failed-attempt limit.** Basic auth attempts count only
   against the global 120/minute/IP default; there is no failure log or alert.
5. **The new review page** (`/admin/promises`) keeps the password in page
   memory only and sends it on each call over HTTPS. It is not linked,
   disallowed in `robots.txt`, and still just the same password.
6. **Reader Cognito does not cover any of this.** Reader accounts (when built)
   would be a separate user pool; nothing in the admin routes consults it.

## Options, smallest first (for the owner)

- **Now, no code:** a long random password and a non-default
  `ADMIN_USERNAME`, rotated in `deploy.env` (restart the backend).
- **Now, no code:** put Cloudflare Access (it already fronts the tunnel) in
  front of the API's `*/admin*` paths and the `/admin` page, requiring its own
  MFA. That gives per-person identity and a second factor without touching the
  app, and the app's password remains as a second check.
- **Planned (the approved direction):** a separate administrator Cognito pool
  with MFA required, the admin routes accepting its tokens, and the reviewer
  name taken from the token. Not started; depends on the Cognito integration
  tickets and AWS access.
- **Small code change if wanted:** a failed-attempt limit on the admin routes
  (e.g. 10/minute/IP) and a log line for each failure.
