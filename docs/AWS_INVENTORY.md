# AWS inventory: Sunshine_Ledger project (account 269314582841, us-east-2)

Generated from the live account on 2026-11-26 (read-only `aws ... list/describe`). Everything was created by
hand with the CLI, not from a template, so **this file is the record**: update it in the same change as any
AWS change. CLI profile `sunshine-ledger` (`aws login`). No secrets here.

| Area | Resource | Purpose | Notes |
|---|---|---|---|
| Storage | S3 `sunshine-ledger-backups-269314582841` | Nightly `pg_dump` from docker-host (03:00) | Versioned, SSE-S3, TLS-only; lifecycle `expire-backups-30d` (current 30 d, noncurrent 7 d) + `cleanup-delete-markers` |
| Compute | EC2 `i-03091be8f8e6ee682` `sunshine-ledger-standby` (t3a.medium, stopped) | Pilot-light failover (RUNBOOK) | SG `sg-0001d6d3d507228a1` with 0 inbound; IMDSv2; termination protection; tags `standby-mode`, `standby-git-ref`, `automation` |
| Compute | Lambda `sunshine-ledger-standby-control` (py3.12) | Starts/stops the standby on the uptime alarm; weekly refresh | Source `scripts/standby/control_lambda.py`. Env: ALARM_NAME, TOPIC_ARN, SCHEDULER_ROLE_ARN, FUNCTION_ARN, FAILBACK_DELAY_MINUTES, HEALTH_CHECK_ID |
| Compute | Lambda `sunshine-ledger-uptime-bridge` (py3.13) | Route 53 check status -> metric `SunshineLedger/Uptime` `Healthy` (dimension `Check=sunshine-ledger-api`) | Source `infra/aws/uptime-bridge/lambda_function.py`. **CHECK_NAME must stay `sunshine-ledger-api`** |
| Monitoring | Route 53 health check `99a2181a-2ae5-5102-09f3-e72c11a0aa0d` | HTTPS_STR_MATCH on `/health` for `"read_only":false` (home only) | Global service; ~$2.75/mo (unverified) |
| Monitoring | Alarm `sunshine-ledger-api-down` | Healthy < 1 for 2 x 5 min, missing = breaching | -> SNS `sunshine-ledger-uptime-alerts` (email + control Lambda) |
| Monitoring | Alarms `sunshine-ledger-ses-bounce-rate` (>5%), `sunshine-ledger-ses-complaint-rate` (>0.1%) | SES reputation | -> `sunshine-ledger-uptime-alerts` (the control Lambda ignores them) |
| Messaging | SNS `sunshine-ledger-uptime-alerts` | Alarm notifications | Subscribers: admin@bernalfieldworks.com, control Lambda |
| Messaging | SNS `sunshine-ledger-ses-feedback` | SES Bounce + Complaint for bernalfieldworks.com | Subscriber: admin@bernalfieldworks.com (confirmed 2026-11-26); only SES (this account/identity) may publish |
| Scheduling | `sunshine-ledger-uptime-bridge-every-5-min` | Runs the bridge | |
| Scheduling | `sunshine-standby-weekly-refresh` | Sundays 10:00 America/New_York -> control Lambda `{action: refresh}` | |
| Config | SSM `/sunshine-ledger/prod/env/*` (31 SecureStrings) | Copy of docker-host `deploy.env` for the standby | Keep in step: `scripts/sync-env.sh ssm-push --yes` |
| Config | SSM `/sunshine-ledger/dev/cognito/*` | Dev pool id, client id, client secret (SecureString) | |
| Identity | Cognito `us-east-2_IDPul5NQZ` `sunshine-ledger-dev` | Reader accounts (dev) | MFA OPTIONAL, software token on; USER_PASSWORD_AUTH |
| Email | SES identity `bernalfieldworks.com` (verified) | Cognito mail, digests, omen alerts | DKIM + MAIL FROM `mail.bernalfieldworks.com`; account suppression list (bounce, complaint); sandbox until case 179566470600566 |
| Cost | Budget `sunshine-ledger-monthly` $150 | Alerts 50/80/100/125% + forecast | Counts spend before credits |

## IAM

| Principal | Can do | Notes |
|---|---|---|
| Role `sunshine-ledger-standby` (EC2) | SSM core; GetObject `backups/*`, ListBucket prefix `backups/`; Get SSM `/sunshine-ledger/prod/env*`; Publish to the alert topic | No SSH keys |
| Role `sunshine-ledger-standby-control` (Lambda) | Start/Stop and retag (`standby-mode` only) instances tagged `role=standby`; read alarms; publish; create `sunshine-standby-*` schedules; pass the scheduler role; `route53:GetHealthCheckStatus` on the one check | |
| Role `sunshine-ledger-standby-scheduler` | Invoke the control Lambda | |
| Role `sunshine-ledger-uptime-bridge-role` | `route53:GetHealthCheckStatus` on the one check; PutMetricData | Repoint the resource when the check is replaced |
| Role `sunshine-ledger-uptime-bridge-scheduler-role` | Invoke the bridge | |
| User `sunshine-ledger-backup-writer` | PutObject `backups/*` only | Key on docker-host (profile `sunshine-backup`); rotate by 2027-02-23 |
| User `sunshine-ledger-cognito-backend-dev` | AdminGetUser, AdminDeleteUser on the dev pool | Key in deploy.env; rotate by 2027-02-23 |
| User `ses-smtp-omen-alerts` | `ses:SendRawEmail` as `omen-alerts@bernalfieldworks.com` only | Proxmox SMTP target; rotate by 2027-02-23 |

## Rules learned the hard way

* **Before changing any monitoring piece, set `automation=disabled` on the standby.** (2026-11-26: see the RUNBOOK incident.)
* The managed SCP blocks SNS and CloudWatch alarms in us-east-1, Roles Anywhere, cost-allocation tags and billing dashboards; build monitoring in us-east-2.
* `aws login` signs into whichever project the browser last opened at settings.aws.com.
