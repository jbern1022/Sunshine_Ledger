# User accounts and watchlists: proposal and open decisions

Status: proposal, 2026-10-21. Nothing is built. Todoist: "user accounts (auth backend) -
register/login/logout/me", "watchlists (bills/people/topics)", "alerts (BLOCKED on email
infra)". Roadmap Phase 2.

## What exists today

- No accounts anywhere: the MVP is public-read by design (BRD).
- Backend: FastAPI, SQLAlchemy, Postgres, Alembic migrations, `slowapi` rate limiting.
- Site and API are on different subdomains of `josephbernal.com`; CORS is an allow-list.
- No email sending (`config.py` has no mail settings), which is why alerts are blocked.
- The Impact Lens is deliberately anonymous: "answers never leave the browser" and
  "accounts and saved profiles" are listed as out of scope in its design.

## Proposal (smallest useful first step)

1. **Accounts with minimal data:** an email address and a password hash (argon2id); no
   name, no profile, no address, nothing from the Impact Lens.
2. **Session cookie:** random opaque token, hashed in the database, `HttpOnly`, `Secure`,
   `SameSite=Lax`, scoped to the parent domain so the site and API share it; CSRF token on
   state-changing requests; rate limits on register and login.
3. **Endpoints:** `POST /auth/register`, `/auth/login`, `/auth/logout`, `GET /auth/me`,
   `DELETE /auth/me` (delete the account and its watchlist rows).
4. **Watchlists:** a table of (account, kind = bill | person | topic, target id), listed
   and edited from the site. No alerts yet.
5. **Alerts later:** needs email infrastructure first, plus an unsubscribe and bounce
   story. Not part of the first step.

## Decisions for Joe (these change the design, so I have not started)

1. **Do we want accounts at all before the Phase 3 legal review?** Watchlists on
   candidates and sponsors are the most electioneering-adjacent feature so far.
2. **Sign-in method:** email + password (no email infrastructure needed), or email magic
   links (better security, but needs mail sending, which does not exist)?
3. **Privacy line:** the Impact Lens promise says answers never leave the browser. Confirm
   accounts never store them, and that watchlists are the only server-side state.
4. **Public launch gating:** require a privacy policy and account-deletion flow first?
   (Counsel review is already a gate for the other Bernal Labs product.)
5. **Abuse and cost:** registration rate limits, email verification or not, and whether
   to cap watchlist sizes.
6. **Where the secret lives:** session signing and any pepper need a secret; confirm it
   goes wherever the backend's other secrets are kept on the host.

## Recommendations (2026-10-26, for Joe to accept or change)

These are my recommendations, one per decision above. None is a decision.

New facts since the proposal: two RSS feeds already exist (`/feed.xml`, recently active
bills, one item per bill; `/corrections/feed.xml`, one item per correction), so
following is possible today without an account, though the bill feed does not announce a
new action on a bill the reader has already seen. The homelab already runs ntfy (alerts
go to `NTFY_ALERT_URL`), which is a push channel that needs no mail server. Admin
authentication exists separately from reader accounts.

1. **Accounts before the Phase 3 legal review?** Not yet. Ship what needs no account
   first: per-jurisdiction and per-topic feeds, and a bill feed that emits one item per
   event. If accounts proceed before the review, limit watchlists to bills and topics and
   hold the person (candidate, sponsor) kind until the review, since that is the
   electioneering-adjacent one.
2. **Sign-in method:** magic links, not passwords. Alerts need outbound email anyway, so
   email has to be built; passwords would add credential storage and breach handling for
   a one-person operation. This makes email the first piece of work: a transactional
   provider, SPF/DKIM/DMARC on the sending domain, bounce handling and a suppression
   list. Drop `argon2id` and the password endpoints from the proposal; keep the opaque
   session token, hashed at rest.
3. **Privacy line:** confirm it, and make it testable. Accounts never store Impact Lens
   answers; watchlists are the only server-side state. Enforce with tests: the lens
   endpoints ignore the session cookie, and no account table or response has a lens field.
   The privacy page currently says the site sets one cookie; a session cookie changes
   that sentence and must be updated in the same release.
4. **Public launch gating:** yes. Before any public registration: a privacy policy that
   covers the email address and watchlist, account deletion that removes all rows
   (`DELETE /auth/me`, cascading), a data export, and a retention rule for unverified
   addresses. Counsel review is a gate here too, as the question suggests.
5. **Abuse and cost:** keep the existing `slowapi` limits and add tighter ones on
   register and on sending a link (per address and per IP). Email verification is implicit
   with magic links. Cap a watchlist at a few hundred entries and an account at one
   address. No alert digests until bounces and unsubscribe work.
6. **Where the secret lives:** in the same place as the backend's other secrets:
   `deploy.env` on the host (`/home/joe/sunshine-ledger/deploy.env`, mode 600) and the Mac
   `.env`, kept in step (a known source of drift). Add the new variables to
   `.env.example` with no values, and write down how to rotate: rotating the signing
   secret logs everyone out, which is acceptable.

Order if all of the above is accepted: (a) outbound email, (b) magic-link auth with
deletion and the privacy-page change, (c) bill and topic watchlists, (d) alerts through
email, with ntfy as an optional channel later. Items (a) and (b) are the only ones that
block the rest.
