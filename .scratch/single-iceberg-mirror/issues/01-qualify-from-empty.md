# Qualify one Iceberg mirror database from an empty test source

Status: claimed
Type: task

## Parts

- [x] Verify current managed-mirror database and Iceberg constraints against official create/procedure references, 2026-11-15 12:54 ET.
- [x] Update platform and installed mirror skills with isolated qualification, Iceberg format and explicit expected results, 2026-11-15 12:54 ET.
- [x] Reuse Docker/psql/Snow CLI and existing clients; no demonstrated orchestration gap and no new helper script, 2026-11-15 12:54 ET.
- [x] Validate 122 policy/genericity/path/installed-portability checks and Standards/Spec/GoF reviews; installed mirror validation passed, 2026-11-15 12:54 ET.
- [x] Publish the skill update in draft PR #1805; local checks and fixture execution verified on the skill changes, CI remains pending, 2026-11-15 12:56 ET.
- [ ] Run the hosted synthetic qualification after a concrete test-resource plan and explicit billable-operation approval.
- [x] Learning → skill: SINGLE-DATABASE-ICEBERG.md separates documentation, executed local fixture, hosted Iceberg, tag enforcement and production consolidation; no new helper was needed, 2026-11-15 12:54 ET.

## Scope

The requested consumer target is one mirror database containing Iceberg tables
from final master, reference and silver outputs, selected by approved mappings
and tags. The current three source databases are not consolidated by this task.
No billable mirror, new hosted instance, source migration or destructive cleanup
has been approved. The existing production target name is reserved for a later
approved production deployment, not consumed by a qualification run.

## Local execution evidence

The documented seed, committed cross-schema mutations and rollback SQL blocks
ran on disposable PostgreSQL 16 with no network access or shared volume. One
database held three schemas, three selected tables and six exclusion controls.
All nine initial rows and all nine final rows matched exact independent
expectations, including the integer above binary floating-point precision and
the wide decimal. Every selected table was logged and had a primary key.
Rollback left the final set unchanged. Elapsed time: 3.23 seconds; the container
was removed. This is fixture proof, not a Snowflake or automated-tag proof.

121 skill-policy/genericity/path checks and isolated skill-bundle portability
passed. Installed mirror skill validation passed. Hosted Iceberg, consumer
access, tag resolution/publication, dbt and production consolidation remain
not run or blocked at their explicit gates.

## Approval artifact

[HOSTED-TEST-PLAN.md](../HOSTED-TEST-PLAN.md) names a new disposable hosted
instance, one Iceberg target, the exact fixture scope, a 90-minute deadline,
cost boundaries and scoped cleanup. It is not executed. Existing production
stores and the reserved production target remain untouched.
