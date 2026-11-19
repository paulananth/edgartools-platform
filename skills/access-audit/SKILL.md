---
name: access-audit
description: Audits who can do what on any platform of the data stack as an independent SOX IT-general-controls, SOC 2 and ITSM auditor - Snowflake, PostgreSQL, AWS, GitHub and the operator's workstation today, others by adapter - with platform-neutral objectives, read-only evidence, a PASS/FAIL/NOT_TESTED report and a coverage matrix. Use before finalising a skill, role, login or access change, and on a schedule for the access review.
---

# Access audit

Work lean: check each step against [the seven wastes](../data-platform/SKILL.md#the-seven-wastes) and drop what adds no value.

The auditor tests whether access is **least-privilege, approved, recorded, monitored and reviewable**, on every platform the
data stack touches. The controls are 14 platform-neutral **objectives** mapped to SOX IT general controls (access, program
change, operations), SOC 2 trust criteria (CC6 logical access, CC7 monitoring, CC8 change management, A1 capacity) and ITIL
practices (service access, change enablement, monitoring, information security). Each platform is an **adapter** that reads
its own evidence and grades the objectives it can. The auditor finds and reports and never changes anything; remediation is a separate, approved, code-driven step.

## Hard stops

| Never | Instead |
|---|---|
| Let the auditor change anything | The audit identity is read-only. Fixing is a separate step with its own identity (see Remediate): plan, the operator's recorded words, apply, then a fresh audit |
| Use, change, disable or plan against the operator's overall administrator account (`ANANP11`) or a connection that signs in as it | The audit refuses those connections; the remediation refuses any plan that touches the account; a finding about it is reported and needs the operator's signed acceptance |
| Audit as an administrator and call it independent | A read-only audit identity per platform; an administrator run needs `--as-admin` and fails that platform's IND |
| Print a password, key, token, address or a value from the data | The adapters return counts and role names only; keep it that way |
| Mark a control PASS from reading code or a document | Test it against the live system; no live test is NOT_TESTED, and an objective an adapter lacks is a gap (`-`) |
| Treat what the auditor cannot see as clean | The adapter returns NOT_TESTED when its view is empty or refused |
| Close a finding without evidence | The re-run's PASS, or a signed acceptance of the risk in the ticket |
| Finalise a skill, role or login with an open FAIL that is not accepted | See the gate below |

## Run it

```bash
set -a; . ~/.config/edgartools/hosted/reader.env; set +a     # the read-only Postgres login; never print it
export AUDIT_SNOWFLAKE_CONNECTION=<SnowCLI connection of the read-only auditor role>
export AUDIT_AWS_PROFILE=<read-only audit profile (SecurityAudit)>
export AUDIT_GITHUB_REPO=<owner/name>
python scripts/access_audit.py --list     # which platforms are configured
python scripts/access_audit.py            # exit 1 when any control fails; --json keeps a record
```

A platform is audited when its variable is set; `--platform NAME` limits the run, `--principal NAME` adds a role or user the
platform's usage views have not shown yet (they lag). The workstation adapter always runs.

| Platform | Evidence | The read-only identity holds |
|---|---|---|
| Snowflake | `ACCOUNT_USAGE` views, `SHOW` of parameters, warehouses and monitors | the security, usage and governance viewer database roles and `MONITOR USAGE ON ACCOUNT` |
| PostgreSQL | catalogs and settings | the diagnostic login (`pg_monitor`) |
| AWS | IAM account summary and credential report, CloudTrail, S3 public-access block, budgets | the `SecurityAudit` managed policy (plus `iam:GenerateCredentialReport`) |
| GitHub | branch protection, secret scanning, the caller's permission | a token with read access to the repository |
| Workstation | client credential files: counts of plain-text passwords and loose file modes | the operator's own account; values are never read out |

## Objectives

| Id | Objective | Why an auditor asks |
|---|---|---|
| IND | The audit identity is read-only and independent | The tested must not test itself |
| ADM | Two or more administrators, MFA, no standing root credential | One admin is a single point of failure and compromise |
| OPS | Daily operations do not run as, or default to, an administrator | Segregation of duties |
| AUT | No password-only privileged login; service identities use keys or roles | No shared or phishable secret |
| LPR | No unexpected ownership, grant-management or wildcard-admin power | The escalation path |
| NET | A network or public-exposure boundary applies | Boundary protection |
| CST | Cost and capacity guards (monitors, budgets, connection limits) | A runaway cannot spend or exhaust without a stop |
| TMO | Execution is bounded (statement or session timeouts) | A runaway statement cannot run for days |
| POL | Credential policies exist | Standards enforced, not hoped for |
| LOG | Access and changes logged; transport and storage encrypted | Who did what, when |
| CHG | Every access principal has a ticket and is defined in code; protected branch with a review | Change enablement: approver, reason, back-out |
| SEC | No plain-text secret; secret files private; secret scanning on | Credential hygiene |
| ROT | Credentials rotate on a dated, owned schedule | AWS keys are tested; elsewhere read the ticket |
| REV | Access is reviewed on a schedule with a signed record | A person reads it: NOT_TESTED until a record exists |

The report ends with a **coverage matrix**, objective by platform: `P` pass, `F` fail, `?` not tested, `-` the adapter has no
test for it. A `-` is a gap in the audit, not a clean platform: close it by extending the adapter or record why it does not apply.

## Add a platform

Add `audit_platforms/<name>.py` with `NAME`, `configured(env)`, `collect(env, as_admin)` (read-only; counts and names only;
refuse an administrator identity), `principals(evidence)` (the roles and users to check for a change record) and
`controls(evidence)` returning `base.control(NAME, objective, ok, evidence, fix, tested=...)` for each objective it can
test; list it in `PLATFORMS` in `access_audit.py`, then add its clean case and one weakness per objective to
`tests/unit/test_access_audit.py`. Databricks, OpenMetadata and any further cloud follow this contract.

## Remediate

Findings are closed as code, by the skill, with no hand steps (`scripts/access_remediate.py`; the Terraform root is
`infra/terraform/access/snowflake/accounts/prod`):

1. `bootstrap` creates a key pair for a dedicated **access-admin** service identity (a role that creates roles, users and
   policies and grants them; never `ACCOUNTADMIN`) and prints the one-time SQL that creates it, holding the public key only. An
   account owner runs that SQL once; nothing else is ever run by hand.
2. `plan` runs Terraform as that identity and summarises creates, updates and destroys. It refuses a plan that touches the
   operator's own administrator account, and any destroy unless `--allow-destroy`.
3. `apply --words "<the operator's exact words>"` records the words with the ET time and the plan counts
   (`.scratch/access-audit/approvals.jsonl`), then applies the saved plan.
4. Re-run `access_audit.py`; the finding is closed only by the re-run's PASS.

Objects made before the root existed are imported once, so a plan shows no change for them. A permission error from the
access-admin identity is reported as the missing privilege to grant it; it is never worked around with an administrator.
A finding about a person's own account (their MFA, their password) has no code fix: it is reported, and closes by the
operator's signed acceptance (owner, reason, expiry) or by moving the work to a service identity.

## Rating and report

A failing control carries the objective's severity: **high** where one credential can change or read everything or leave no
trail (ADM, OPS, AUT, LPR, LOG, SEC), **medium** where a guard is weak (IND, NET, CST, TMO, POL, CHG, ROT, REV). Report, in
order: scope and evidence date; counts (pass, fail, not tested) and the matrix; each finding as control, evidence numbers,
risk in plain words and the fix; what was not tested and why. Evidence is counts, never values.

## The gate before finalising a skill, role or login

The audit ran as a read-only identity on every platform the change touches; every FAIL it touches is fixed or has a signed
acceptance (owner, reason, expiry date) in its ticket; the new principal has a ticket and is in code (CHG); its credential is a
key or role, or a secret held outside the repository, with a rotation date; and the re-run shows no new FAIL.

## Limits

- Snowflake `ACCOUNT_USAGE` and AWS's credential report lag by minutes to hours; a principal made a moment ago may not show.
- CHG finds only the principals an adapter names (Snowflake users and roles starting `EDGARTOOLS`, plus `--principal`).
- The controls are evidence of design and operation on the day read, and say nothing of another day.
