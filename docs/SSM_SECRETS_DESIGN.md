# Design: production settings from SSM Parameter Store

Todoist 6hxjxV2Jr627M5vp (due 2026-12-08), part of the $100 AWS gate.
**Status: proposal. Nothing here is built or changed until Joe approves.**

## Problem

Production settings live in one hand-edited file on docker-host,
`/home/joe/sunshine-ledger/deploy.env`. The Woodpecker deploy step mounts it
and copies it to `.env`. Since 2026-11-26, `scripts/sync-env.sh ssm-push --yes`
also copies it into SSM (`/sunshine-ledger/prod/env/*`, SecureString, Standard
tier) for the pilot-light standby.

That leaves two copies kept in step by hand:
- **The standby runs stale settings** if someone forgets `ssm-push` after an edit, and nothing warns.
- **Edits happen in a shell on the host**, with no record of who changed what or when. A hand-copied file contributed to the 2026-09-20 outage.
- **Cognito adds secrets** (pool client secret, backend key) that would need the same double bookkeeping.

## Proposal: SSM is the source, the host file becomes a cache

1. **One place to edit.** Settings are changed with `scripts/sync-env.sh set KEY` (reads the value from a prompt, never the command line) or in the AWS console. Every change is a new parameter version, logged by CloudTrail (trail `sunshine-ledger-audit`, already on).
2. **Deploy reads SSM.** The Woodpecker deploy step runs `aws ssm get-parameters-by-path --with-decryption` and writes `.env` (mode 600), then **writes the same content to `deploy.env`** as the last-known-good cache.
3. **Home-internet fallback.** If AWS can't be reached, the deploy uses the cached `deploy.env` and prints a warning. Deploys during an outage still work, and the standby already reads SSM directly.
4. **Drift check.** The nightly runs `sync-env.sh ssm-diff`. Any key that differs between the running `.env` and SSM is reported in the nightly log and status email, with names only, never values.

### Credential

The deploy step needs a read-only AWS credential. The options:

| Option | Pros | Cons |
|---|---|---|
| **A. New IAM user `sunshine-ledger-config-reader`** (recommended) | Least privilege: `ssm:GetParametersByPath` on `/sunshine-ledger/prod/env/*` and `kms:Decrypt` on the AWS-managed `aws/ssm` key (via SSM only). Key stored as a Woodpecker secret, never on disk. | One more key to rotate (90 days, added to the rotation list next to the backup writer) |
| B. Reuse `sunshine-backup` | No new key | Mixes a write-only backup credential with secret reads. If either job is compromised, both are. |
| C. IAM Roles Anywhere | No long-lived key | **Denied by the project's SCP** (seen 2026-11-25) |

No new exposure: the host already holds every value in `deploy.env`.

### Cost

$0. Standard-tier parameters and standard throughput are free, and the
`aws/ssm` key is AWS-managed. Each deploy and each nightly make about 2-4 API calls.

## Rollout (about 2 hours, one session)

1. `sync-env.sh ssm-diff`. SSM must match `deploy.env` exactly before switching.
2. Create the reader user and policy. Joe adds the access key as the Woodpecker secret `aws_config_reader` (repo settings, trusted).
3. Ship the deploy step change behind a flag (`ENV_SOURCE=ssm`, default `file`):
   - Deploy once with `file`, then once with `ssm`, and diff the two `.env` files by key hash.
   - Make `ssm` the default.
4. Add `sync-env.sh set KEY` and `unset KEY`. Keep `pull` and `diff` for inspecting.
5. Retire `push`, so editing `deploy.env` by hand is no longer the workflow. The file stays as the cache.
6. RUNBOOK: replace the "edit deploy.env, then ssm-push" instructions with "`set`, then redeploy".

**Rollback:** set `ENV_SOURCE=file`. The cache is always the last `.env` that worked.

## Open questions for Joe

1. Option A (new read-only user) is the recommendation. OK?
2. Should the Woodpecker secret be available to the deploy step only (recommended), or to all steps?
3. Cognito's secrets (`sunshine-ledger-cognito-backend-dev`): put them under the same path now, or when Cognito ships (March)?

## Not in scope

- Secrets Manager. It costs $0.40 per secret per month, and rotation isn't needed for these keys yet.
- Moving Futbol or Pajarito settings. Each is a separate project, and this pattern can be copied later.
