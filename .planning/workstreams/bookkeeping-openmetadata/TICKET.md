# Bookkeeping load observability in OpenMetadata

The platform owns a separate reporter. Bookkeeping remains independently
usable; reporting cannot change a load or prevent its execution.

## Goal acceptance: all four stakeholders

Operator, 2026-11-05: satisfy data engineering, data quality management,
data governance, and master/reference-data end users 100%. These gates are
part of the active transparency goal, not optional follow-ups. Each requires
current behavioral evidence; unsupported or unverified needs remain open.

- [ ] Data engineering: every load has discoverable identity, exact progress,
  step states, freshness, retries/failures, lineage, verified outputs and recovery
  guidance. Reporting outages and missed/stale loads remain visible.
- [ ] Data quality management: distinguish definitions from executed results;
  expose outcomes, trends, corrections and unresolved defects with evidence.
- [ ] Governance: understandable domains/terms/classifications, accountable
  owners, review state, provenance, lineage and policy evidence. No invented
  owners or approvals; absence remains an explicit gap.
- [ ] Master/reference-data consumers: find the right data, understand its row
  meaning and reference-code definitions, verify currency/quality/readiness,
  trace field provenance, locate a usable consumption path and responsible owner.
- [ ] KISS: each stakeholder can answer their core questions from a concise
  summary with supporting evidence available on demand. Visual usability remains
  unverified: the operator authorized UI assessment, but the review browser
  reaches sign-in and the existing-session browser host is unavailable.

## Implementation checklist

- [x] Add a sanitized one-statement observation and stable paged discovery;
  live PostgreSQL aggregate counts matched the existing status API (2026-11-05 07:07 ET).
- [x] Add the external `observe loads` tool for exact state, step counts,
  attempts, checks, delivery backlog and observation time; all 322 retained
  loads were confirmed by native readback (2026-11-05 07:07 ET).
- [x] Verify string-encoded integer precision, readback, timestamp collision
  allocation, stale-update refusal and safe partial failures with local tests
  and live collision/replay evidence (2026-11-05 07:07 ET).
- [x] Verify all 322 retained identities independently: 322 distinct native
  executions, no missing or extra IDs. A bounded repeat invocation completed
  six confirmed sweeps with exit 0 and no failures (2026-11-05 07:07 ET).
- [x] Review Standards, Spec and GoF below; targeted local tests cover state,
  pagination, outage/retry, readback, collisions, precision, redaction and
  control independence (2026-11-05 07:07 ET).
- [ ] Verify real-engine regression tests in CI, including MySQL and SQL Server.
- [x] Correct equal-timestamp discovery after CI exposed duplicate/missing runs:
  the cursor now follows the existing ascending UUID tie order. The unchanged
  regression failed before the fix; it and the typed observation/read test passed
  on disposable PostgreSQL (2 passed, 2026-11-05 17:38 ET).
- [x] Document tool, state mapping, snapshot freshness, single-reporter ownership
  and missing row/quality result evidence in `skills/bookkeeping/OBSERVABILITY.md`
  (2026-11-05 07:07 ET).
- [ ] Publish a PR and verify CI for its final head.
- [x] Learning → skill: native catalog and ingestion schemas share a Swagger
  name but require different fields. Pin the catalog schema and require real
  readback; native defaults may be added without changing supplied evidence.
  Documented in `skills/bookkeeping/OBSERVABILITY.md` (2026-11-05 07:07 ET).

## Review: Standards

Local validation at 2026-11-05 07:09 ET: 37 behavior/architecture tests passed
with testmon; 96 documentation genericity/path checks passed. New real-engine
read and cursor assertions are included in the existing storage-adapter suite
for CI. They were not run locally against MySQL or SQL Server.

`storage.py:279` uses one read statement and full-width aggregates, with no
migration or control write. The control CLI remains domain-independent; local
architecture tests actively block application/domain imports. The reporter
emits safe cause codes and excludes raw receipts, logs and credential values.
Selected-engine behavior beyond PostgreSQL remains a CI gate, not a local claim.

CI run 42025023690 failed the unchanged equal-timestamp cursor regression on
PostgreSQL, MySQL and SQL Server: three results included a duplicate and missed
one expected identity. The predicate used `<` while the UUID tie order was
ascending. The one-character `>` correction preserves that order and fixes the
PostgreSQL reproduction. No test expectation was changed. The branch was
rebased onto current main at 2026-11-05 17:38 ET; range-diff confirmed the original
reporter commit was unchanged by the rebase. All three CI engines must pass on
the corrected head.

## Review: Spec

`load_observer.py:99` requires matching native readback, including identity and
exact parameters. `discover` at line 139 pages every retained run. The first
real sweep exposed a dotted-identity bug, then one real timestamp collision;
both were fixed before the final 322/322 confirmation. Output row counts and
quality results remain explicitly unavailable. Continuous operation requires
the bounded tool to be run by the platform's normal scheduler; no service was
silently installed. The broader four-stakeholder gates above remain open.

## Review: GoF

`engine.py:592` provides a generic observation; `load_observer.py:157` composes
it with the existing native transport. This is the existing external-application
seam, with plain functions and no callbacks into loaders or remote reporting
inside control. The cost is a read API, CLI adapter, tests and documentation;
there is no evidence justifying a class hierarchy or execution-engine refactor.

## Design review

GoF consult: leave existing execution code in place. History shows deliberate
control-only CLI and separate application composition (journal recovery).
Use that same seam for a small external adapter; adding callbacks or an Observer
inside Bookkeeping would couple load progress to a remote catalog. The cost is
one generic read API plus one application tool, with no migrations or new
execution transitions. No pattern hierarchy is justified.
