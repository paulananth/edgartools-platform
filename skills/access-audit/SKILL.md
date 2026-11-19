---
name: access-audit
description: Audits who can do what on the hosted data platform as an independent SOX IT-general-controls, SOC 2 and ITSM auditor - Snowflake and PostgreSQL roles, logins, network and cost guards, audit logging, change records and secret handling - read-only, with a PASS/FAIL/NOT_TESTED report. Use before finalising a skill, role, login or access change, and on a schedule for the access review.
---

# Access audit

Work lean: check each step against [the seven wastes](../data-platform/SKILL.md#the-seven-wastes) and drop what adds no value.

The auditor tests whether access is **least-privilege, approved, recorded, monitored and reviewable**. It maps each control to
SOX IT general controls (access to programs and data, program change, computer operations), SOC 2 trust criteria (CC6 logical
access, CC7 monitoring, CC8 change management, A1 capacity) and ITIL practices (service access management, change
enablement, monitoring and event management, incident management, information security). It finds and reports; it never fixes.

## Hard stops

| Never | Instead |
|---|---|
| Fix a finding while auditing it (grant, revoke, rotate, create a role) | Report it; the fix is its own change under data-operations or aws-snowflake-operations, with its own ticket |
| Audit as an administrator and call it independent | The read-only auditor role; an administrator run needs `--as-admin` and fails AUD-00 |
| Print a password, key, token, address or a value from the data | The script prints counts and role names only; keep it that way |
| Mark a control PASS from reading code or a document | Test it against the live system; a control with no live test is NOT_TESTED |
| Close a finding without evidence | The re-run's PASS, or a signed acceptance of the risk in the ticket |
| Finalise a skill, role or login with an open FAIL that is not accepted | See the gate below |

## Run it

```bash
set -a; . ~/.config/edgartools/hosted/reader.env; set +a     # the read-only diagnostic login; never print it
export AUDIT_SNOWFLAKE_CONNECTION=<a SnowCLI connection for the read-only auditor role>
python scripts/access_audit.py            # exit 1 when any control fails; --json for a record
```

The auditor role holds Snowflake's security, usage and governance viewer database roles and `MONITOR` on the account, and
nothing that writes. Until it exists, an administrator run (`--as-admin`) is the only evidence and is itself a finding.

## The controls

| Id | Control | Why an auditor asks |
|---|---|---|
| AUD-00 | The audit ran as a read-only auditor | Independence: the tested must not test itself |
| AC-01 | At least two administrators (one break-glass), each with MFA | One admin is a single point of failure and of compromise |
| AC-02 | No administrator defaults to ACCOUNTADMIN | Least privilege by default |
| AC-03 | Daily operations do not run as ACCOUNTADMIN (under 5% of queries) | Segregation of duties |
| AC-04 | No password-only login by an administrator | Strong authentication |
| AC-05 | Service identities use key pair, no password | No shared or phishable secret |
| AC-06 | No non-admin role holds ownership or grant-management | Privilege escalation path |
| NW-01 | An account network policy applies | Boundary protection |
| OP-01 | Every warehouse has a resource monitor | Cost and capacity control |
| OP-02 | The statement timeout is bounded | A runaway statement cannot run for days |
| AU-01 | Password and authentication policies exist | Credential standards enforced, not hoped for |
| DB-01 | The diagnostic login cannot write or administer | The monitoring account is truly read-only |
| DB-02 | Only the platform's own roles are login superusers | No hidden super-power |
| DB-03 | Connections, disconnections and DDL are logged; TLS and SCRAM on | Monitoring and transport |
| DB-04 | Data-changing statements are audited (pgaudit) | Who changed which data |
| DB-05 | Every login role has a connection limit | One login cannot take the instance |
| CM-01 | Each access role or user has a change record in a ticket | Change enablement: approver, reason, back-out |
| CM-02 | Each is defined in code | A role made by hand does not survive a rebuild |
| SC-01 | No plain-text password in a client file; secret files private | Credential hygiene |
| KR-01 | Rotation is dated and owned | Not machine-testable: read the ticket |
| AR-01 | Access is reviewed on a schedule with a signed record | Not machine-testable: read the review tickets |

## Rating and report

Each failing control is a finding with a severity the auditor assigns: **high** when it lets one credential change or read
everything or leaves no trail (AC-01, AC-04, SC-01, DB-04), **medium** when it weakens a guard (NW-01, OP-01, OP-02, AU-01),
**low** otherwise. Report, in this order: the scope and the evidence date; the counts (pass, fail, not tested); each finding as
control, evidence numbers, risk in plain words and the fix; what was not tested and why. Evidence is counts, never values.

## The gate before finalising a skill, role or login

A change is finalised when: the audit ran as the read-only auditor; every FAIL it touches is fixed or has a signed acceptance
(owner, reason, expiry date) in its ticket; the new role or login has a ticket (CM-01) and is in Terraform (CM-02); its
credential is a key pair or a secret held outside the repository, with a rotation date; and the re-run shows no new FAIL.

## Limits

- Snowflake's `ACCOUNT_USAGE` views lag by up to a few hours: a role created a moment ago may not show there yet.
- CM-01 and CM-02 look only for the names the audit found (roles and users named `EDGARTOOLS...`); a name outside that pattern
  is not covered.
- Controls are evidence of design and operation on the day; they say nothing of a day not read.
