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
