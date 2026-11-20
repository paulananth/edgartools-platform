# access-audit: Define one responsibility

Type: task
Status: resolved
Priority: P1
Blocked by: 01
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [access-audit](../../../skills/access-audit/SKILL.md)
Step: 1 of 6
Skill dependencies: data-platform
Applicability: Review the skill or access changes being finalized; run only applicable read-only platform checks.

## Question

Which decisions and artifacts belong here, and which must be handed to another skill?

## Scope and evidence

Establish this boundary: Independently assess applicable access controls and evidence gaps; remediation stays a separate authorized action.

Inventory existing instructions against the neighboring owners: the owning operations skill handles authorized remediation, then access-audit rechecks. Reconcile the current index and references before moving any text.

Start from skills/access-audit/SKILL.md: Hard stops, Objectives, The gate before finalising a skill role or login. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Define one responsibility](./01-data-platform-responsibility.md)

Priority rationale: Independent access evidence is cross-cutting; remediation is separate.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] List decisions, inputs and outputs owned here using current repository evidence; verified by reading `skills/access-audit/SKILL.md`, its scripts, `tests/unit/test_access_audit.py`, the skills index row, and every repository reference to the skill (`aws-snowflake-operations`, `data-operations/HOSTED-LOADS.md`, `data-operations/scripts/readiness.py`, `data-platform/CONNECTIONS.md`, `infra/scripts/harden-hosted-roles.py`). (2026-11-20 18:11 ET)
- [x] Assign each overlapping responsibility one authoritative owner and a named handoff; verified by reviewing the [handoff table](../../../skills/access-audit/SKILL.md#decisions-artifacts-and-handoffs) and the [Snowflake fix procedure](../../../skills/aws-snowflake-operations/SKILL.md#fixing-an-access-finding), and by `tests/unit/test_guides_name_existing_paths.py` (the linked paths exist; it does not check anchors or routing). (2026-11-20 18:11 ET)
- [x] Demonstrate the boundary on a restricted runtime role, a denied audit view and an overprivileged role detected without mutation; link retained work rather than duplicating it. Verified by the named fixture tests under `## Answer`. No live audit was run. (2026-11-20 18:11 ET)
- [x] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md. PR #1968 squash-merged at 2026-11-20 18:08 ET as `30ae0e7b631df6db9d9560f7da3cb6a1cbe4f4d9` after the checkout-only path fix. Its updated-head CI passed 12 checks. (2026-11-20 18:11 ET)
- [x] Moving `access_remediate.py` is not applicable here: this ticket does not authorize a test-code move. The script stays under `skills/access-audit/scripts`, and the procedure links to it. (2026-11-20 18:11 ET)
- [x] Learning → skill: an auditor's verdict and the fix are separate owners; the fix hands back to a fresh audit, and only that re-run's PASS (or a signed acceptance) closes a finding. Recorded in [Decisions, artifacts and handoffs](../../../skills/access-audit/SKILL.md#decisions-artifacts-and-handoffs) and [Fixing an access finding](../../../skills/aws-snowflake-operations/SKILL.md#fixing-an-access-finding). (2026-11-20 18:11 ET)

## Answer

Access Audit owns the independent verdict: which objectives apply, how each
control is graded from live read-only evidence, the PASS/FAIL/NOT_TESTED
report and coverage matrix, the gate before finalising a skill, role or
login, and whether a finding is closed. It owns no fix. The owners it hands
to are in [Decisions, artifacts and handoffs](../../../skills/access-audit/SKILL.md#decisions-artifacts-and-handoffs):

- Snowflake access fixes (access-admin identity, Terraform plan, recorded
  words, apply): AWS and Snowflake Operations, [Fixing an access finding](../../../skills/aws-snowflake-operations/SKILL.md#fixing-an-access-finding).
  That skill's Access identities section pointed the apply back to
  access-audit; it now points to its own procedure.
- AWS fixes: AWS and Snowflake Operations.
- PostgreSQL role guards (CST, TMO, LOG): Data Operations, role guards in
  `HOSTED-LOADS.md`.
- The load decision on today's audit: Data Operations' readiness gate,
  which consumes the `postgres` audit's failing control ids.
- Audit logins and variables: Data Platform `CONNECTIONS.md` (reader duty)
  and AWS and Snowflake Operations (Snowflake audit identity).
- GitHub settings and the operator's own accounts: the operator; closed by
  a re-run's PASS or a signed acceptance.

Boundary cases, fixture level (`tests/unit/test_access_audit.py`, unchanged,
retained work; these grade invented evidence and read no live system):

- Restricted runtime role: `test_a_clean_platform_has_no_failure[postgres]`
  (a `pg_monitor`-only audit login passes IND).
- Denied audit view: `test_a_control_the_auditor_cannot_see_is_not_tested_never_passed`
  (a hidden or refused view is NOT_TESTED, never PASS).
- Overprivileged role detected without mutation: the LPR cases of
  `test_each_weakness_fails_its_own_objective` (a superuser login, an
  `OWNERSHIP` grant) and the administrator-connection refusals
  (`test_an_administrator_snowflake_connection_is_refused_without_the_flag`,
  `test_a_non_audit_aws_identity_is_refused_without_the_flag`). The
  controls grade collected evidence; the audit issues no write.

A live demonstration needs a read-only audit run against a disposable or
hosted platform; it was not run in this session.

Blocker 01: PR #1956 is commit `f8233ff25e6e61933568121d8fa5dd6e883e0862`,
an ancestor of `origin/main` (checked with `git merge-base --is-ancestor`).

The installed `write-skill` guidance is a symlink to the gstack installation;
its `gstack-skill-bill` identifies this checkout's `access-audit` as a user
skill. There is no installed `access-audit` link in `~/.agents/skills`. The
installed `aws-snowflake-operations` link points to a separate checkout, so no
installed copy was changed. This repository's `skills/link.sh` links skills
from this checkout when explicitly run.

## Validation and remaining work

- `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_profiling_genericity.py`: 141 passed. This checks documentation genericity; it does not validate access behavior or routing.
- `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_guides_name_existing_paths.py tests/unit/test_access_audit.py::test_a_clean_platform_has_no_failure tests/unit/test_access_audit.py::test_a_control_the_auditor_cannot_see_is_not_tested_never_passed tests/unit/test_access_audit.py::test_each_weakness_fails_its_own_objective tests/unit/test_access_audit.py::test_an_administrator_snowflake_connection_is_refused_without_the_flag tests/unit/test_access_audit.py::test_a_non_audit_aws_identity_is_refused_without_the_flag`: 39 passed. This verifies linked paths and the named fixture cases; it does not demonstrate a live audit.
- `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_access_audit.py`: 48 passed, 2 failed because this no-project environment lacks SQLAlchemy; the first failure is `ModuleNotFoundError: No module named 'sqlalchemy'`, and the second is the consequent `cannot connect as the diagnostic login`. The scripts and tests are unchanged from `origin/main`.
- `gstack-skill-bill skills/access-audit` before and after: 10,692 bytes both times; identified as a user skill under this checkout. No skill size change.
- `git diff --check`: clean.
- Open: the live boundary demonstration, publication (branch push and PR), and the deferred script move.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
