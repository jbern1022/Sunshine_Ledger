# ADR: reader authentication with Amazon Cognito behind our own sessions

Status: **draft for review, 2026-11-10.** Todoist `6hrmhJX2CG2qWwFG` (parent `6hWPfQj65r54vP8G`).
Planning only: no AWS resource exists, nothing is provisioned, nothing here is a price quote.
Everything marked **UNVERIFIED** must be checked against the dated AWS pages before build.
Supersedes the sign-in section of `ACCOUNTS_DESIGN_QUESTIONS.md` (magic links), which was a
recommendation; the owner chose Cognito on 2026-10-29.

## Decisions already made by the owner (2026-10-29, not reopened here)

1. Cognito is the identity and credential backend; Essentials tier is the proposed starting tier.
2. Sunshine Ledger builds its own sign-up, login, verification, recovery, challenge and error screens;
   Cognito Managed Login is not used. The ordinary login experience uses our branding, and AWS is
   disclosed accurately in privacy material.
3. Methods at launch: email and password, optional passkeys, authenticator-app TOTP. SMS off; no
   social providers.
4. Reader MFA is **optional but prominently encouraged**. Once enabled it is honored on every later
   password sign-in and on factor management; no silent fallback. Administrator MFA is required and is
   a separate workstream (`ADMIN_ACCESS_AUDIT.md`); the reader pool's optional setting never governs it.
5. Lost-authenticator recovery framework: prefer a registered user-verifying passkey or a working
   backup; otherwise a documented support review; password reset alone never removes MFA. An approved
   factor reset requires replacement-factor enrollment before normal access, revocation of all
   sessions, and notice to the verified email. If ownership cannot be established the old account stays
   protected and nothing transfers to a new account. Privileged recovery is stricter and separate.
6. Application sessions are ours: opaque, HttpOnly, Secure cookies with server-side authorization.
   Cognito tokens are validated, not used as the browser session.

## Shape of the integration

```
browser ──(our screens)──▶ our API ──(Cognito API/SDK, server side)──▶ Cognito user pool
   ▲                          │  validates Cognito tokens, maps sub → local user, mints our session
   └── opaque session cookie ◀┘
```

* **The browser never holds Cognito tokens.** Our API performs the sign-in calls on the browser's
  behalf (custom UI, so this is the direct API flow, not the hosted OAuth code flow), validates the
  returned ID and access tokens (signature against the pool's JWKS, issuer, audience/client id,
  `token_use`, expiry), and then creates a local session. This also means the browser passes
  passwords and one-time codes to our API over TLS: they are **never logged or persisted** (request
  logging for `/auth/*` must exclude bodies; a test asserts it).
* **Identity mapping.** `users` has `id` (our UUID), `cognito_sub` (unique, the stable provider
  subject; never the email, which can change), `email` (copied after verification, for notices only),
  `status` (`active | suspended | deleted`), `created_at`, `last_sign_in_at`. Authorization is always
  by our `users.id`; a Cognito group or attribute never grants anything in the app.
* **Entitlements** attach to `users.id` as the opaque subject (`app/entitlements.py`, already built).
* **Sessions.** Table `sessions`: `id`, `user_id`, `token_hash` (SHA-256 of a 256-bit random token),
  `created_at`, `last_seen_at`, `idle_expires_at`, `absolute_expires_at`, `revoked_at`,
  `revoked_reason`, `auth_time` and the factors used (`pwd`, `totp`, `passkey`). Idle and absolute
  lifetimes are **proposed: 30 minutes idle for sensitive actions after re-auth, 14 days idle and 90
  days absolute for ordinary reading**; owner to confirm. Cookie: `__Host-` prefix where the domain
  layout allows (site and API are separate subdomains today, so a parent-domain cookie with
  `SameSite=Lax` and a CSRF token on state-changing requests, as proposed earlier).
* **Re-authentication.** Sensitive operations (enroll or remove a factor, change email, delete the
  account, export data) require a sign-in within the last N minutes (**proposed 10**); otherwise the
  API answers `401 reauth_required` and the UI asks.

## Invalidation: what ends a local session

Provider revocation does **not** end our sessions on its own, so every event below is handled by us.

| Event | Local effect |
|---|---|
| User signs out | revoke that session |
| "Sign out everywhere" | revoke all of the user's sessions |
| Password change or completed reset | revoke all sessions (the next sign-in creates a new one) |
| MFA enabled, disabled, or factor replaced | revoke all sessions; notify the verified email |
| Approved recovery (factor reset) | revoke all sessions first; require replacement-factor enrollment before a normal session can be minted (see gate below) |
| Suspension by an operator | set `status=suspended`, revoke all; every request checks status |
| Account deletion | delete local rows (below), revoke all, delete the Cognito user |
| Cognito reports the user disabled or deleted | detected on the next token validation or refresh; revoke |

Every authenticated request checks: session exists, not revoked, within idle and absolute limits, and
`users.status = 'active'`. A background refresh of Cognito state is **not** assumed; the explicit events
above are the invalidation mechanism, and a daily job reconciles `users.status` with the pool.

## The MFA-recovery gate (the case the owner flagged)

In a pool where MFA is optional, deleting the TOTP factor must not quietly return the account to
password-only access. So the gate lives in **our** server, not only in the pool:

* `users.mfa_required` becomes true once the user enrolls a factor, and is cleared only by an explicit
  user action that passed re-authentication **with the existing factor**, or by an approved support
  recovery that records who approved it and why.
* Minting a session for a user with `mfa_required` demands that the Cognito sign-in result carried a
  completed MFA challenge (or a user-verifying passkey). A password-only result is refused with
  `mfa_required`, even if the pool itself would have allowed it.
* A recovery-pending state (`users.recovery_state`): `none → requested → under_review → approved |
  denied`. Only `approved` lets a user enroll a replacement factor; until enrollment completes, the only
  session that can exist is a restricted one that may enroll a factor and nothing else.
* Tests (required before public enablement): password reset does not clear `mfa_required`; removing the
  factor in the pool directly (simulated) still refuses a password-only session; a denied or lapsed
  request leaves the old account protected; a new account cannot claim an old account's watchlists.

Acceptable ownership proof, reviewer authority, escalation and abuse limits for support review are
**not decided here**; they stay open (section "Unresolved").

## Passkeys and MFA compatibility (to be tested, not assumed)

* A passkey can stand in for password plus second factor only when it is user-verifying. The pool
  setting is `WebAuthnConfiguration` with user verification required; Essentials or higher is needed
  (**UNVERIFIED** for our region and SDK version).
* A passkey is not a second factor after a password. Passwordless email or SMS one-time codes do not
  combine with required MFA, so they are not offered.
* What must be tested in a dev pool: a TOTP-enrolled user who also registers a passkey; sign-in with
  each; per-user factor combinations Cognito actually supports; behavior when a passkey is removed.
  Where behavior is unclear the implementation fails closed (refuse the sign-in), never weakens MFA.

## Privacy and data

* Stored by us: user id, `cognito_sub`, verified email, status, session records, entitlement grants,
  watchlists (when built). **Never** Impact Lens answers (lens endpoints ignore the session cookie;
  a test asserts no account table or response has a lens field).
* Stored by AWS: the credentials, factors and email. The privacy page must name AWS as the identity
  provider and say the page's current "no accounts, no login, no passwords" and one-cookie statements
  change at launch. Same release.
* **Deletion:** `DELETE /auth/me` removes our rows in one transaction (user, sessions, watchlists,
  notes, entitlement grants are retained only as an anonymized audit line: `subject` replaced by a hash,
  since grants are the pilot's audit record; owner to confirm that retention) and then calls the Cognito
  delete. If the Cognito call fails the user is marked `deleted` locally and the delete is retried; the
  user is told the order of events.
* **Export:** `GET /auth/me/export` returns the user's own rows as JSON, free at all times
  (`own_data_export` is in the never-gated free set).
* **Exit limitation:** Cognito does not export password hashes, so leaving Cognito later means a forced
  password reset for every user. Passkey credentials and TOTP seeds are likewise not portable.
  **UNVERIFIED** against current AWS documentation; record the finding with a date.
* Retention for unverified sign-ups (proposed: delete after 7 days) and for session rows (proposed: 30
  days after expiry).

## Operations and cost (nothing here is a quote)

* **Environments:** two pools (dev and prod) in separate AWS accounts or at least separate
  IAM boundaries; app clients per environment; no shared secrets. Region: the one closest to the
  docker host that offers the needed features (**UNVERIFIED**).
* **IAM:** the backend gets a role limited to the specific user pool's admin and authentication calls
  it uses; no wildcard on `cognito-idp:*`. Credentials are not in the repo; they follow the existing
  `deploy.env` practice or an instance role if the AWS move (`AWS_MIGRATION.md`) happens first.
* **Email sender:** verification and recovery mail needs a verified sender and SPF/DKIM/DMARC on the
  sending domain. Cognito's default sender has low daily limits, so production uses SES (**UNVERIFIED**
  current limits). Bounce and complaint handling and a suppression list are required before alert mail,
  and are on the critical path for launch.
* **Cost model.** Cognito bills per monthly active user, with a free allowance and per-feature charges
  that differ by tier; SES bills per message. Plan: obtain the current tier prices and free allowance
  from the AWS pricing pages, record them with the retrieval date in this file, and set an AWS budget
  with alerts at 50 / 80 / 100 percent of a small cap. Until the numbers are recorded, the cost model is
  **incomplete by design**; building the budget and alerts is a prerequisite to enabling any pool.
  A rough sensitivity table (10, 1,000, 10,000 monthly active users) is to be added once prices are
  known; do not carry a number from memory into a decision.
* **Abuse controls:** the existing `slowapi` limits plus tighter ones on sign-up, sign-in, resend
  code and recovery (per address and per IP); a lockout that does not reveal whether an address
  has an account (uniform responses and timing on sign-in and reset).

## Build order (each step shippable and gated off)

1. Email sending (SES, domain authentication, suppression list). 2. `users` and `sessions` tables, the
session middleware, CSRF, request-log exclusions, with a fake identity provider behind an interface so
everything is testable without AWS. 3. The Cognito adapter (dev pool): sign-up, verify, sign-in, reset.
4. TOTP enrollment and challenge, the MFA gate and its tests. 5. Passkeys, after the compatibility
tests. 6. Recovery states and the support-review runbook. 7. Deletion, export, privacy-page change.
8. Auth screens. Public registration stays closed until the privacy, legal and release gates pass.

## Unresolved (owner or research needed)

1. Current Cognito tier prices, free allowance and the exact feature list per tier (dated sources).
2. Region and SDK support for user-verifying passkeys together with TOTP.
3. Acceptable ownership proof, reviewer authority and escalation for support recovery.
4. Session lifetimes and re-authentication window (proposals above).
5. Whether anonymized grant rows survive account deletion.
6. AWS account structure for dev and prod; whether auth waits for the AWS migration.
7. Whether email verification may be skipped for any reason (recommendation: never).

## Official sources to read before approving (not read for this draft)

* Amazon Cognito Developer Guide: "Adding MFA to a user pool" (the owner already reviewed this page).
* Amazon Cognito Developer Guide: user pool feature plans and WebAuthn passkey settings.
* Amazon Cognito pricing page and the AWS Free Tier page (retrieve and date).
* Amazon SES developer guide: sending limits, sandbox exit, bounce handling.
