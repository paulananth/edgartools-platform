# 20 — Version and activate the Acquisition Universe

**What to build:** Let operators change covered source families, CIKs, forms,
logical keys, and history boundaries through an explicit versioned transition
that proves baseline and catch-up coverage before activation.

**Blocked by:** 16 — Drive filing capture from SEC change discovery; 19 —
Complete the filing-to-Silver acceptance seam

- [x] The Source Family Registry versions logical keys, acquisition mode,
  completeness policy, discovery or polling policy, and required Silver
  producers as executable policy data.
- [x] Adding coverage creates a scoped baseline and catch-up obligation;
  removing coverage ends future acquisition at an explicit boundary without
  retiring existing SEC facts.
- [x] Registry or universe changes cannot activate until every affected family
  is complete through the declared boundary.
- [x] A failed or incomplete transition leaves the previously active universe
  authoritative and exposes a precise blocker and next action.
- [x] Callers select policies only through the registry; they cannot choose a
  Strategy implementation directly.

## Answer

`SourceRegistryLedger` (`edgar_warehouse/acquisition/registry_ledger.py`),
migration `014_source_registry.sql`, and the `mdm registry-*` CLI
subcommands are merged (PR #455) and pass a full real-Postgres integration
suite (`tests/integration/test_source_registry_postgres.py`) alongside 18
SQLite unit tests — including two genuine bugs the Postgres suite found and
fixed (a `session.flush()` ordering race against the partial unique index
enforcing at most one active version, and a migration-rerun idempotency gap
specific to this ticket's single-role design; both documented in CLAUDE.md's
"Ticket 20 Source Family Registry" 5-whys entry). Bullets 3, 4, and 5 are
fully done and proven live against real Postgres role/GRANT semantics, not
just SQLite.

Bullets 1 and 2 were **initially only partially done** — `/code-review`'s
Spec pass found real gaps, not nitpicks: `in_scope_forms` was genuinely
wired into `drive_filing_discovery.py`'s scope filter, but `acquisition_mode`/
`completeness_policy`/`discovery_policy`/`required_producers` were captured
and persisted with no consumer anywhere in the codebase (inert audit
metadata, not executable policy), and `coverage_end_date` was stored but
never compared against any date — a `'remove'`d family was excluded
immediately on activation, not "at an explicit boundary." A third gap
surfaced alongside these: no committed bootstrap path existed to open and
activate the first registry version in prod. All three were real, scoped
decisions rather than obvious bug fixes, so rather than guess at the right
behavior under review pressure, they were filed as
[32 — Wire Ticket 20's remaining registry policy fields, enforce the removal
boundary, and bootstrap the first active version](32-wire-remaining-registry-policy-fields-and-boundary-enforcement.md)
— now resolved. All four fields are real dispatch/validation gates,
`coverage_end_date` genuinely gates future acquisition (with a
`business_date`-not-wall-clock correctness fix found and fixed during that
ticket's own `/code-review` pass), and
`infra/scripts/bootstrap-source-family-registry.sh` (wired into
`install.sh`) is the committed bootstrap path.

**Status:** resolved — all five bullets fully done, proven against real
Postgres.
