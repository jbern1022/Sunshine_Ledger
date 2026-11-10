# Accounts, watchlists and alerts: what is built and what is not (2026-11-10)

Everything here is on the unpushed branch `feat/local-2026-11-10-offline`, has **no routes**, no AWS
dependency and no public surface. Public registration stays closed until the privacy, export/deletion,
retention, security-test and scoped legal gates in Todoist `6hCMm7FWfJ47jCgp` pass. Design:
`ADR_READER_AUTH_COGNITO.md`.

| Piece | Module | Table (migration) | State |
|---|---|---|---|
| Entitlements for pilot access | `app/entitlements.py` | `entitlement_grants` (`d1e4b7a2c9f6`) | Built, tested. Free set cannot be gated. |
| Users and server-side sessions, MFA gate, recovery states, revocation | `app/sessions.py` | `users`, `auth_sessions` (`e2f5c8b3d0a7`) | Built, tested with a fake sign-in result. |
| Export, deletion with provider retry, retention purge | `app/account_data.py` | none | Built, tested. Retention periods are proposals. |
| Watchlists (bills, officials, topics by jurisdiction) | `app/watchlists.py` | `watches` (`f3a6d9c4e1b8`) | Built, tested. 300-entry cap proposed. |
| Alert queue and digest builder | `app/alerts.py` | `pending_alerts` (`a5c8f1e6d3b0`) | Built, tested. Does not send. |

The migration chain was run on a scratch database: up to head, down three, up again, all clean.

## Not built (and why)

1. **Routes** (`/auth/*`, `/watchlist`, `/account/export`, `DELETE /auth/me`): they need the Cognito adapter
   and CSRF/cookie wiring, and must be reviewed for exposure before they exist at all.
2. **Cognito adapter** (sign-up, verify, sign-in, reset, TOTP, passkeys): needs a dev user pool (AWS access)
   and the unverified items in the ADR (prices, region support).
3. **Email** (verified sender, SPF/DKIM/DMARC, bounce and suppression handling, unsubscribe): needs AWS/SES
   and a sending domain. No alert is ever sent until this exists.
4. **Frontend screens** (sign-up, sign-in, MFA enrollment, recovery, account page, follow buttons).
5. **Support-review process** for lost authenticators (ownership proof, reviewer authority, escalation).
6. **Privacy page and notices** for the AWS identity provider, session cookie and retention schedule; the
   "no accounts / one cookie" statements change in the same release as registration.
7. **Scoped legal review** of accounts and official-following.

## Decisions still needed from the owner

Session lifetimes; whether anonymized grant rows survive deletion; retention periods; watchlist cap;
whether `official` follows are enabled in the first public release (`watchlists.ENABLED_KINDS` is the switch).

## Decisions recorded 2026-11-10 (owner agreed to the recommendations)

* **Watchlists are free** for every account (no entitlement needed). Alerts, digests, saved searches, notes and exports stay professional features, free during the pilot.
* Confirmed as proposed: session lifetimes (14 days idle, 90 days absolute, 10-minute re-authentication window), retention (unverified sign-ups 7 days, expired session rows 30 days), a 300-entry watchlist cap, anonymized grant rows kept after account deletion, and the Impact Lens nightly budget (60 minutes, 200 bills).
* The Impact Lens `?lens=1` flag comes off when the hand-labeled baseline shows zero wrong mappings; the labeling is the owner's.
* Still open: whether `official` follows are in the first public release (switch: `watchlists.ENABLED_KINDS`), and the Tampa/Orlando ruling.

## Update 2026-11-10 (evening): routes are built, switched off

`app/api/auth.py` adds `POST /auth/sign-in`, `/auth/totp`, `/auth/password-reset/confirm`, `/auth/sign-out`,
`/auth/sign-out-all`, `GET /auth/me`, `/auth/me/export`, `POST /auth/me/delete`, and `GET/POST /watchlist` (+ `/{id}/remove`).
**Every route answers 404 while `AUTH_ENABLED` is false (the default)**, so deploying them exposes nothing. When on: the
session is an opaque HttpOnly SameSite=Lax cookie; state-changing calls need the double-submit `X-CSRF-Token` and a trusted
`Origin`; failures at sign-in are one uniform 401; deleting the account needs a sign-in in the last 10 minutes; a restricted
(recovery) session can do nothing else; passwords and codes are never logged (a test captures logs). Provider: Cognito from
`COGNITO_REGION/USER_POOL_ID/CLIENT_ID[/CLIENT_SECRET]`, else 503. New settings: `AUTH_ENABLED`, `SESSION_COOKIE_DOMAIN`,
`SESSION_COOKIE_SECURE`. Still needed to go live: a real user pool (AWS), the screens, SES, the privacy-page change, and the
gates in `6hCMm7FWfJ47jCgp`.

## Update 2026-11-10 (evening): the account page is built, switched off

`/account` (`components/AccountPanel.tsx`, `lib/account.ts`): sign-in with the second step, a uniform error for credential
failures, account summary, sign out / sign out everywhere, data download, delete with an explicit confirmation and the
re-sign-in message, a restricted recovery session that sees nothing else, and the watchlist with unfollow. It is a 404
unless the site is built with `NEXT_PUBLIC_AUTH_ENABLED=true` (a build-time flag, like `NEXT_PUBLIC_API_URL`), and the API
routes behind it are 404 unless `AUTH_ENABLED=true`. Not built: sign-up and email verification screens, MFA enrollment (QR
and manual key), passkey registration, password-reset request screen, recovery screens, "follow" buttons on bills,
officials and topics. Each of those needs the real user pool to be designed against.
