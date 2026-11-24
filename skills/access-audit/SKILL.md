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
its own evidence and grades the objectives it can. The auditor finds and reports and never changes anything; remediation is a
separate, approved, code-driven step owned by the operations skill of the platform (see [Decisions, artifacts and
handoffs](#decisions-artifacts-and-handoffs)), and the auditor's re-run closes the finding.

## Hard stops

A shared rule keeps its home, named in its row. This table grants no approval, provider access, access change or switch-on.

| Never | Instead |
|---|---|
| Let the auditor change anything | The audit identity is read-only. Fixing is a separate step with its own identity, owned by the platform's operations skill ([handoffs](#decisions-artifacts-and-handoffs)), then a fresh audit |
| Use, change or disable the operator's overall administrator account (`ANANP11`), or audit through a connection that signs in as it | The audit refuses those connections ([Access identities](../aws-snowflake-operations/SKILL.md#access-identities-read-only-first)); a finding about the account is reported and needs the operator's signed acceptance |
| Audit as an administrator and call it independent | A read-only audit identity per platform; an administrator run needs `--as-admin` and fails that platform's IND |
| Print a password, key, token, address or a value from the data | The adapters return counts and role names only; keep it that way (`CLAUDE.md`, "Commits, PRs and secrets") |
| Mark a control PASS from reading code or a document | Test it against the live system; no live test is NOT_TESTED, and an objective an adapter lacks is a gap (`-`) (`CLAUDE.md`, "Tests") |
| Treat what the auditor cannot see as clean | The adapter returns NOT_TESTED when its view is empty or refused |
| Close a finding without evidence | The re-run's PASS, or the operator's signed acceptance of the risk in the ticket |
| Accept a risk for the operator, or record an acceptance as given | A signed acceptance is the operator's own words, stamped `{{now}}` (`CLAUDE.md`, "Task checklists"), with the owner, reason and expiry date, given when asked. Accepting a risk is a new kind of decision (`CLAUDE.md`, "Talking with the operator"), never a routine approval |
| Finalise a skill, role or login with an open FAIL that is not accepted | See the gate below |

## Start here: audit a change

Inputs: the change being finalised and the platforms whose access it touches, each platform's read-only audit connection
(below), the roles or users the change adds or alters, and the [Objectives](#objectives). Output: a PASS, FAIL and NOT_TESTED
report with the coverage matrix ([Rating and report](#rating-and-report)), each finding's remediation reference in
[handoffs](#decisions-artifacts-and-handoffs), and the [gate](#the-gate-before-finalising-a-skill-role-or-login)'s verdict.
Before a Snowflake or AWS run, open [AWS and Snowflake Operations](../aws-snowflake-operations/SKILL.md) (`CLAUDE.md`, "Skills
and guides"); the login files and their duties belong to [Connections](../data-platform/CONNECTIONS.md). Reading a platform's
own access records is no request to a data provider.

1. **Decide applicability.** Name each platform where the change adds or alters a role, login, grant, credential, connection or
   audited setting. None: record the gate as not applicable with that reason, never PASS, and stop; nothing runs.
2. **Prepare.** Use a Python where `edgar_warehouse` imports (the installed package, or a checkout's `uv` environment): the
   postgres adapter imports it on every command, `--list` included. Work in this skill's folder and pass `--repo` the checkout
   root (`../..` in a checkout): CHG reads tickets under `.scratch/` and Terraform under `infra/` there, and finds none
   anywhere else. Set only each touched platform's variable, and check it is set without printing it:

| Platform | Set | Evidence | The read-only identity holds |
|---|---|---|---|
| Snowflake | none to set: the `edgartools-audit` SnowCLI connection of the auditor role (`AUDIT_SNOWFLAKE_CONNECTION` overrides it) | `ACCOUNT_USAGE` views, `SHOW` of parameters, warehouses and monitors | the security, usage and governance viewer database roles and `MONITOR USAGE ON ACCOUNT` |
| PostgreSQL | the stores folder's `reader.env` (a hosted store's is `~/.config/edgartools/hosted/`), sourced | catalogs and settings | the diagnostic login (`pg_monitor`) |
| AWS | `AUDIT_AWS_PROFILE`: a read-only audit profile; an ambient `AWS_PROFILE` or `AWS_ACCESS_KEY_ID` also counts as set | IAM account summary and credential report, CloudTrail, S3 public-access block, budgets | the `SecurityAudit` managed policy (plus `iam:GenerateCredentialReport`) |
| GitHub | `AUDIT_GITHUB_REPO`: `owner/name`, read with the `gh` CLI | branch protection, secret scanning, the caller's permission | a token with read access to the repository |
| Workstation | nothing; it always runs | client credential files: counts of plain-text passwords and loose file modes | the operator's own account; values are never read out |

3. **List, then audit** exactly the touched platforms, in one command-scoped subshell with tracing off. Name each new Snowflake
   role or user with `--principal`: the usage views lag, and the option is read for Snowflake only.

```bash
( set +x; set -a; . <stores folder>/reader.env; set +a                      # PostgreSQL only; never print it
  export AUDIT_SNOWFLAKE_CONNECTION=<SnowCLI connection of the auditor role>   # Snowflake only
  python scripts/access_audit.py --repo ../.. --list
  python scripts/access_audit.py --repo ../.. --platform <touched> --principal <new role or user>  # --principal: Snowflake only
)
```

   `--list` is expected to exit 0 and print `configured: <names>`, with `workstation` always among the names. A touched
   platform that is not listed is a stop. The audit exits in one of three shapes:
   - **exit 0**: one line per control (`RESULT ID severity title [refs]`, its evidence counts, and its fix when it is not
     PASS), the matrix, then `== N pass, 0 fail, N not tested`;
   - **exit 1 with that count line**: at least one FAIL, listed first;
   - **exit 1 with an error and no count line**: an adapter refused its identity (an administrator, or the operator's own
     account) or could not read its evidence, such as a platform named with `--platform` whose variable is not set. Every
     platform is read before any is graded, so nothing was graded.
   Add `--json` to keep the run's record ([handoffs](#decisions-artifacts-and-handoffs)). It prints the same controls as one
   list, with no matrix and no count line; the matrix is each `id`'s result, laid out by objective and platform.
4. **Grade against the [gate](#the-gate-before-finalising-a-skill-role-or-login)** for each touched platform. Name every
   NOT_TESTED and `-` control as not tested.
5. **Hand off** each FAIL (control id, evidence counts, the fix it names) to the owner in its
   [handoffs](#decisions-artifacts-and-handoffs) row. Re-run step 3 on that platform after the fix. Only that re-run's PASS,
   or the operator's signed acceptance, closes it.

**Stop**, and name the blocker to its owner, when:
- a touched platform's variable or file is missing (the operator sets it in their own terminal);
- a run ends with an error and no count line: that platform is not tested, and its identity is fixed first (never
  `--as-admin` for the gate: it fails IND);
- a FAIL that the change touches has no signed acceptance (the gate's one question).

## Objectives

| Id | Objective | Why an auditor asks |
|---|---|---|
| IND | The audit identity is read-only and independent | The tested must not test itself |
| ADM | Two or more administrators, MFA, no standing root credential | One admin is a single point of failure and compromise |
| OPS | Daily operations do not run as, or default to, an administrator | Segregation of duties |
| AUT | No password-only privileged login; service identities use keys or roles | No shared or phishable secret |
| LPR | No unexpected ownership, grant-management or wildcard-admin power | The escalation path |
| NET | A network or public-exposure boundary applies | Boundary protection |
| SCH | Nothing lives in a database's `public` schema; every object is in its store's own schema (PostgreSQL only; read in each platform database) | A schema nobody owns is open to every login, and what is exposed from it is not governed |
| CST | Cost and capacity guards (monitors, budgets, connection limits) | A runaway cannot spend or exhaust without a stop |
| TMO | Execution is bounded (statement or session timeouts) | A runaway statement cannot run for days |
| POL | Credential policies exist, and equal `rules/snowflake_policy.yaml` (Snowflake: values, and the schema they live in; a policy in any other database is drift) | Standards enforced, not hoped for |
| LOG | Access and changes logged; transport and storage encrypted | Who did what, when |
| CHG | Every access principal has a ticket and is defined in code; protected branch with a review | Change enablement: approver, reason, back-out |
| SCR | No plain-text secret; secret files private; secret scanning on | Credential hygiene |
| ROT | Credentials rotate on a dated, owned schedule | AWS keys are tested; elsewhere NOT_TESTED, since a person reads the ticket's dated record |
| REV | Access is reviewed on a schedule with a signed record | A person reads it: NOT_TESTED until a record exists |

A database's own logins, made with the instance and used by the platform (its administrator account and application login), are left out
of the connection-limit count: a limit on them can lock the platform out. Every login this platform makes is counted.

The report ends with a **coverage matrix**, objective by platform: `P` pass, `F` fail, `?` not tested, `-` the adapter has no
test for it. A `-` is a gap in the audit, not a clean platform: close it by extending the adapter or record why it does not apply.

## Add a platform

Add `audit_platforms/<name>.py` with `NAME`, `configured(env)`, `collect(env, as_admin)` (read-only; counts and names only;
refuse an administrator identity), `principals(evidence)` (the roles and users to check for a change record) and
`controls(evidence)` returning `base.control(NAME, objective, ok, evidence, fix, tested=...)` for each objective it can
test; list it in `PLATFORMS` in `access_audit.py`, then add its clean case and one weakness per objective to
`tests/unit/test_access_audit.py`. Databricks, OpenMetadata and any further cloud follow this contract.

**Credential-policy values.** Where a platform keeps a policy a role cannot read without a privilege that could also change it
(Snowflake's `APPLY`), the platform's administrator owns a read-only reader that returns the policies as
`{"password": [...], "authentication": [...]}` (each `{database_name, schema_name, name, properties}`), and the auditor holds
use of that reader only. Snowflake's is the procedure `AUDIT_CREDENTIAL_POLICIES` in the Gold database's `CONTROL` schema
(`infra/terraform/access/snowflake`). A new platform returns the same shape from its own reader; `policy_drift` compares it
with the policy file, whatever the vendor. The code and its tests
follow `CLAUDE.md`'s "Code review" and test-writing rules.

## Decisions, artifacts and handoffs

Access audit owns the independent verdict: which objectives apply, how each control is graded from live read-only evidence, the
report and coverage matrix, the gate below, and whether a finding is closed. It owns no fix. Hand the finding (control id,
evidence counts, the fix it names) to the owner below, then re-run the audit on that platform; do not repeat a run only to
recreate its report.

| Decision or artifact | Authoritative owner | Handoff |
|---|---|---|
| Objectives, adapters, grading, the PASS/FAIL/NOT_TESTED report and the coverage matrix (`scripts/access_audit.py`) | Access audit | Keep the `--json` record of the run; a later run on the same platform is the recheck. |
| The read-only audit logins and their connection variables | [Data Platform](../data-platform/CONNECTIONS.md) (the PostgreSQL reader duty) and [AWS and Snowflake Operations](../aws-snowflake-operations/SKILL.md#access-identities-read-only-first) (the Snowflake audit identity); the AWS and GitHub audit identities hold what [Start here](#start-here-audit-a-change) lists | The audit receives only the variables listed in Start here; it refuses an administrator identity. |
| Fixing a Snowflake access finding: the access-admin identity, the Terraform plan, the operator's recorded words and the apply | [AWS and Snowflake Operations](../aws-snowflake-operations/SKILL.md#fixing-an-access-finding) | Carry the finding; after the apply, re-run the audit. Only that re-run's PASS closes it. |
| Fixing an AWS access finding | [AWS and Snowflake Operations](../aws-snowflake-operations/SKILL.md), which owns every AWS command | Same: carry the finding, re-run the audit after the change. |
| Fixing a PostgreSQL role guard (connection limit, timeouts, `work_mem`, audit classes) | [Data Operations](../data-operations/HOSTED-LOADS.md#before-a-load-starts) (role guards) | Carry the failing CST, TMO or LOG control; re-run the audit on `postgres` after the guards are applied. |
| Whether a load may start on today's audit | [Data Operations](../data-operations/HOSTED-LOADS.md#the-gate-nothing-loads-until-the-infrastructure-is-ready-and-tested) (the readiness gate) | The gate runs the `postgres` audit and reads its failing control ids; it decides the load, the audit decides the controls. |
| GitHub repository settings and the operator's own accounts (MFA, passwords, workstation files) | The operator; no skill holds code for them | Report the finding; it closes by a re-run's PASS or the operator's signed acceptance (owner, reason, expiry) in the ticket. |

## Rating and report

A failing control carries the objective's severity: **high** where one credential can change or read everything or leave no
trail (ADM, OPS, AUT, LPR, LOG, SCR), **medium** where a guard is weak (IND, NET, CST, TMO, POL, CHG, ROT, REV). Report, in
order: scope and evidence date and time in ET; counts (pass, fail, not tested) and the matrix; each finding as control, evidence numbers,
risk in plain words, the fix and the owner it is handed to ([handoffs](#decisions-artifacts-and-handoffs)); what was not
tested and why. Evidence is counts, never values.

## The gate before finalising a skill, role or login

The audit ran as a read-only identity on every platform the change touches; every FAIL it touches is fixed or has the
operator's signed acceptance ([Hard stops](#hard-stops)) in its ticket; the new principal has a ticket and is in code (CHG); its
credential is a key or role, or a secret held outside the repository, with a rotation date; and the re-run shows no new FAIL. Each
NOT_TESTED or `-` control on a platform the change touches is named in the report as not tested, never counted as a pass.

- A change that touches no platform's access (no role, login, grant, credential, connection or audited setting) records the
  gate as not applicable, with that reason, never as PASS.
- An open FAIL with no acceptance stops the finalising: ask the operator one question, naming the finding, the decision and
  your recommendation (`CLAUDE.md`, "Talking with the operator").
- Passing the gate grants no approval, access change, activation or switch-on.

## Resume an audit

Keep progress in the existing onboarding log or task record for the change under review. Use its single `## Resume` section as
the common progress record ([Data Platform's record and resume rules](../data-platform/RESUME.md#the-record)); do not create an
audit-specific state store. Update it when an audit stops, completes, or hands findings to an owner. Record public names and
repository paths only; never copy credentials, addresses, role membership, or data values into the record.

Record:

- the change and platforms in scope, the applicable principals or settings by public name, and the objectives assessed;
- the evidence date and time in ET, the audit adapter/skill revision, and each platform's `--json` artifact path and sha256;
- each objective's PASS, FAIL, NOT_TESTED or `-` result, its evidence counts, and each finding's status and remediation owner;
  for an accepted finding, link the operator's signed acceptance with its owner, reason and expiry;
- pending read-only rechecks, their owning skill, and the next action as an unchecked checklist item.

Resume by comparing the recorded scope, inputs, revision and evidence date with the change and read-only evidence needed now:

1. **Reuse** completed objective results only for the same platform, principal or setting, objectives and adapter revision, while
   the evidence is within the review window recorded for this task. Keep the original artifact and date; continue at the first
   unchecked action. Do not rerun completed objectives just to recreate their report.
2. **Invalidate** results for an affected platform when its scope, principal or setting changes; invalidate results assessed
   under changed objectives or adapter logic. Reassess each invalidated objective with fresh read-only evidence. Keep prior
   artifacts and mark the affected results reopened; never replace them with a claim that the old evidence still applies.
3. **Block** when the record or artifact is missing, its hash differs, the evidence date is outside the recorded review window,
   the review window was never recorded, or the applicable scope cannot be established. Name the missing evidence and its owner;
   do not infer PASS or reuse stale results.
4. **Hand off** every open finding to the operations skill named in [Decisions, artifacts and handoffs](#decisions-artifacts-and-handoffs).
   That owner records authorized remediation in the same task record. Access audit then performs only the pending read-only
   recheck and records its result there. Leave every unfinished action unchecked.

## Examples: staged interruption

An invented task record says a PostgreSQL connection-limit change is in scope, its recorded review window is still open, and
the `postgres` artifact is hashed. Its objectives show CHG and IND complete;
CST is FAIL and has been handed to Data Operations; the CST recheck is unchecked. The interruption occurs before remediation.
With the same setting, objectives, adapter revision and in-window artifact, resume at the first unchecked action: **Data
Operations handles the authorized role-guard remediation**. Access audit does not repeat CHG or IND. After that owner records
completion, the next action is **access-audit rechecks CST on `postgres` with read-only evidence**. If the setting or adapter
revision changes before resumption, the affected result is reopened and the next action becomes its fresh audit; if the artifact
is absent or outside its recorded window, resume is blocked pending valid evidence.

## Limits

- Snowflake `ACCOUNT_USAGE` and AWS's credential report lag by minutes to hours; a principal made a moment ago may not show.
- CHG finds only the principals an adapter names (Snowflake users and roles starting `EDGARTOOLS`, plus `--principal`).
- The controls are evidence of design and operation on the day read, and say nothing of another day.

## Handshake

Its findings feed [data-operations](../data-operations/SKILL.md) readiness (AUDIT); fixes to a platform's access go to [aws-snowflake-operations](../aws-snowflake-operations/SKILL.md). The table of who owns what and hands off to whom is [OWNERSHIP.md](../OWNERSHIP.md).
