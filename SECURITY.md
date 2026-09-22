# Security Policy

Sunshine Ledger is a public-read civic transparency site, live at
https://sunshineledger.josephbernal.com. It has no user accounts. It
stores no personal data except the optional email address someone can
attach to a flag they submit.

## Reporting a vulnerability

**Please don't open a public issue for security problems.**

Report them privately through GitHub's
[private vulnerability reporting](https://github.com/jbern1022/Sunshine_Ledger/security/advisories/new).
Include:

- what's affected (URL, endpoint, or file)
- steps to reproduce
- what an attacker could do with it

This is a solo, nights-and-weekends project. Expect an acknowledgement
within 7 days. A fix or a plan follows once the report is confirmed.

## In scope

- The public frontend (`sunshineledger.josephbernal.com`)
- The public API (`sunshineledger-api.josephbernal.com`)
- The code in this repository

## Out of scope

- Rate-limit or denial-of-service testing against the live site. It runs
  on home-lab hardware.
- Findings that only affect an outdated dependency with no reachable path
  in this app
- Social engineering, and physical attacks on the hosting infrastructure

## Good-faith research

If you test in good faith, stay in scope, and don't access, change, or
keep data beyond what you need to show the issue, you won't face any
complaint or legal action from this project.
