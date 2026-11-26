# Accounts data layer: where reader data lives, and why (2026-11-26)

Todoist `6j2w23fWpMQ233gG` (P1). Reconciles 6hCMm7FWfJ47jCgp, 6hWPfQj65r54vP8G, 6hWPfQgc9xWJqxJG,
6hWPfQqX443vpgCp, 6hrmhxW4cj9jXvgp and the dev Cognito setup. Companion to `ADR_READER_AUTH_COGNITO.md`
(identity) and `ACCOUNTS_BUILD_STATUS.md` (module-by-module state). **Planning only: nothing here is deployed,
switched on or paid for.** Prices marked *unverified* must be checked on AWS's pricing pages before relying on them.

## Decision

**Keep reader data in the existing PostgreSQL database; use Cognito only for credentials and factors.**
Do not add DynamoDB + Lambda/API Gateway for profiles and watchlists now. Revisit if (and only if) the
primary site moves off the home server.

## What exists today (all behind `AUTH_ENABLED=false`, so every route is a 404 in production)

| Need from the ticket | How it is met | State |
|---|---|---|
| Cognito authentication | `app/cognito_provider.py` (user-password flow, server-side; tokens dropped after `GetUser`) | Built; verified against dev pool `us-east-2_IDPul5NQZ` 2026-11-25 |
| Internal stable user ID mapped from `sub` | `users.id` (UUID) with `users.cognito_sub` unique; authorization always by `id`, never email | Built |
| Sessions | `auth_sessions`: only the SHA-256 of an opaque cookie token; 14 d idle / 90 d absolute; revocation | Built |
| MFA | TOTP challenge at sign-in; **enrollment** (`/auth/mfa/setup`, `/auth/mfa/verify`) | Challenge built; enrollment on branch `feat/totp-enrollment` |
| Watchlists with stable IDs | `watches` (bill / official / topic-by-jurisdiction), 300 cap, free for every account | Built |
| Daily digests | `pending_alerts` queue + digest builder (`app/alerts.py`) | Built; **does not send** (needs SES production access) |
| Export / deletion | `account_data.export_user`, deletion with provider retry, retention purge | Built |
| Anonymous browsing unchanged | No route requires an account; Impact Lens answers never leave the browser | Holds |

## Why PostgreSQL and not DynamoDB (today)

| | Existing PostgreSQL (home server) | DynamoDB + Lambda + API Gateway |
|---|---|---|
| Recurring cost | $0 extra (already running) | Small at pilot scale (on-demand, *unverified*), but a second system to pay for and watch |
| Consistency with the rest | Watches reference bills/officials by the same IDs, in the same transactions and backups | Cross-store references; deletion and export span two systems |
| Backups / recovery | Already in the nightly dump, S3 off-site copy, weekly restore test on the standby | New backup, retention and restore path to build and test |
| Availability during a home outage | Standby serves **read-only**: account writes (sign-in creates a session row, follows, deletion) answer 503 until home is back | Writes would keep working |
| Code | Built and tested (1,300+ backend tests) | Rewrite of sessions, watchlists, export and deletion |
| Privacy surface | One datastore to disclose and audit | Another AWS service on the privacy page and in the deletion path |

The only real advantage of moving is **writes during a home outage**. Outages this month were minutes to hours,
the standby already keeps the site readable, and a reader who can't follow a bill for an hour loses little. That
does not justify a second data store, a rewrite and a second recovery path. If the primary site later moves to
the cloud, the whole database moves with it and the question disappears.

## Still to design or build (ticket items not covered above)

1. **Optional private profile (locale, ZIP/district, preferences).** Recommendation: **no server-side ZIP or
   district in v1.** Impact Lens answers stay in the browser by design; storing a ZIP next to an email is location
   data we would then have to disclose, export, delete and protect. Locale and email preferences are harmless and can
   be a small `user_preferences` row when needed. Owner decision.
2. **Notification consent.** Digests stay off per account until the reader turns them on (explicit opt-in, not a
   default), with the time and the wording shown recorded; every digest carries one-click unsubscribe (RFC 8058).
   Turning digests on does not happen at sign-up.
3. **Sending.** SES from `no-reply@bernalfieldworks.com` once production access is granted (case 179566470600566);
   bounces and complaints already go to the account suppression list, the `sunshine-ledger-ses-feedback` topic and
   two reputation alarms.
4. **Lost-authenticator recovery**: the approved framework (ADR) still needs its support-review procedure.
5. **Privacy page** changes ship in the same release as registration (Cognito, the session cookie, retention).

## Exact AWS access (least privilege)

| Principal | Allowed | Notes |
|---|---|---|
| Backend (IAM user `sunshine-ledger-cognito-backend-dev`) | `cognito-idp:AdminGetUser`, `AdminDeleteUser` on the one pool | Exists; rotate by 2027-02-23. Prod pool gets its own user. |
| Public sign-in calls (InitiateAuth, SignUp, AssociateSoftwareToken, ...) | No IAM: Cognito app-client calls authenticated by the user's own credentials | Client secret in SSM |
| Digest sender (future) | `ses:SendRawEmail` on `identity/bernalfieldworks.com`, condition `ses:FromAddress` = `no-reply@...` | Same pattern as the omen-alerts SMTP user |
| Standby | Reads the SSM settings and backups only; never writes reader data | Read-only by design |

## Cost guardrails (within the $150 Sunshine budget)

Cognito: the Essentials tier has a free allowance of monthly active users that the pilot (5-10 people) will not
approach (*unverified, check before launch*). SES: about $0.10 per 1,000 messages (*unverified*); a daily digest to
100 readers is about 3,000 messages a month. No new always-on service. The budget alerts at $75/$100/$125/$150.

## Staged rollout

1. **Dark** (now): code deployed, `AUTH_ENABLED=false`, every route a 404.
2. **Owner test**: `AUTH_ENABLED=true`, `REGISTRATION_OPEN=false`; accounts created by hand in the dev pool;
   full flow including TOTP enrollment, export and deletion.
3. **Closed pilot** (5-10 journalists/residents, Todoist 6hxjxVFcfWmmGcqG): prod pool, invited accounts only,
   digests opt-in, SES production access in place.
4. **Public sign-up**: only after the privacy, export/deletion, retention, security-test and scoped legal gates in
   6hCMm7FWfJ47jCgp pass. `REGISTRATION_OPEN=true` is the switch.
