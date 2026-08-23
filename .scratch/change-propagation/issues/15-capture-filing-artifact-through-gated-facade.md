# 15 — Capture one filing-artifact family through the gated Facade

**What to build:** Carry one explicitly authorized SEC filing-artifact request
through a non-bypassable acquisition Facade and an executable source-family
Strategy into verified immutable Bronze evidence and finalized ledger state.

**Blocked by:** 14 — Establish the acquisition ledger and status spine

**Status:** resolved

- [x] The Facade accepts an existing fenced Fetch Decision and cannot invent a
  URL, logical key, cause, or authorization.
- [x] The first Source Family Registry Strategy supplies the filing family's
  fetch and completeness behavior while shared authorization, hashing, Bronze
  finalization, and ledger transitions remain outside the Strategy.
- [x] Download completion requires an immutable content-addressed Bronze write,
  read-back verification, and finalization of the exact artifact reference.
- [x] Identical bytes may reuse one Bronze object while every observation keeps
  distinct manifest and ledger lineage.
- [x] The Facade does not parse source data, publish Silver, or coordinate
  downstream stages, and the acquisition command uses the bundled handler
  registration introduced by Ticket 13.

## Answer

Delivered as `edgar_warehouse/acquisition/facade.py` (the non-bypassable
`build_capture_facade`) plus the first Source Family Registry entry,
`edgar_warehouse/acquisition/source_family_registry.py`'s
`FilingArtifactPolicy`, and a new `capture-filing-artifact` CLI command
registered through Ticket 13's handler seam
(`edgar_warehouse/application/workflows/capture_filing_artifact.py`). Landed
in two commits on PR #446 (merged `6e4079cc`):

1. Initial implementation: the Facade takes an already-fenced
   `SourceChangeStatus`/`FetchLease` (never invents a URL, key, cause, or
   authorization — verified by a direct-call test against a stale/non-
   fetchable status), invokes the registry-selected policy, writes
   content-addressed immutable Bronze via `write_immutable_bytes` keyed by
   `sha256(payload)`, and independently reads the object back to verify
   before finalizing the ledger.
2. Code-review fix (parallel Standards + Spec `/code-review`): the ledger
   was finalizing `CAPTURED` state but never durably recording *which*
   Bronze object backed it — only the in-memory return value carried
   `raw_evidence_hash`. Added `source_fetch_work.captured_artifact_reference`
   (with a CHECK constraint requiring it non-blank when `CAPTURED`),
   threaded through `AcquisitionLedger.finalize_fetch` and the Postgres
   `finalize_source_fetch` stored procedure (widened 5→6 params, every
   literal signature reference updated in lockstep across
   `013_acquisition_ledger.sql` and `mdm_post_restore.sql`).

Verified twice, independently: the full test suite (`tests/acquisition/
test_facade.py`, `tests/acquisition/test_source_family_registry.py`,
`tests/application/test_capture_filing_artifact_command.py`,
`tests/integration/test_acquisition_ledger_postgres.py` against real
Postgres via Docker/Colima), and a manual end-to-end smoke test against
real infrastructure (not mocks): an ephemeral `postgres:16-alpine`
container with migration `013_acquisition_ledger.sql` applied fresh, and a
real live SEC filing (Apple's latest Form 4). Confirmed
`captured_artifact_reference` is durably recorded in Postgres and that
identical bytes across two independent decisions reuse one Bronze object
while each decision keeps its own distinct ledger lineage.
