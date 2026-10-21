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
6. **Where the secret lives:** session signing and any pepper in the same SOPS/secret
   flow as the other keys, or a new one?
