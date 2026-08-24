# 19 — Complete the filing-to-Silver acceptance seam

**What to build:** Carry a discovered filing candidate from its authorized
Fetch Decision through verified Bronze evidence and Logical Source Revision to
a verified Silver publication or an explicit terminal non-publication outcome.

**Blocked by:** 05 — Decide silver delta publication and scope-completion
semantics; 18 — Materialize ordered logical source revisions

**Status:** resolved

- [x] Expected Silver producers, tables, and scopes are sealed before processing
  and each records a verified publication or explicit no-impact outcome.
- [x] Success requires read-back verification of authoritative Silver state;
  parser success, landing upload, workflow success, or load-command success is
  insufficient by itself.
- [x] Source Change Status joins decision, capture, revision, processing,
  expected-producer progress, blocker, and next action for the candidate.
- [x] A Silver failure leaves prior Silver authoritative and blocks only later
  revisions for the same logical key.
- [x] The acceptance test asserts durable external evidence rather than
  concrete Facade, Strategy, or handler implementation classes.

## Answer

New module `edgar_warehouse/acquisition/processing.py` (`ProcessingLedger` +
`SilverFinalizer`, generic across source families) plus new
`source_processing_decision`/`source_expected_producer` tables and a new
`edgartools_acquisition_silver_finalizer` database role -- Ticket 03 splits
"processors claim work" (sealing what a revision requires) from "the Silver
finalizer verifies and finalizes publications" (recording a verified/failed
producer outcome) as two distinct owners, so this gets its own role rather
than reusing `ACQUISITION_PROCESSOR`. Family-specific wiring for
`filing_artifact` lives in a new `edgar_warehouse/acquisition/
silver_acceptance.py`, writing to and reading back DuckDB's `sec_raw_object`
(`edgar_warehouse/silver_store.py`'s existing `upsert_raw_object`/
`get_raw_object`).

**Blocked-by note (same pattern as Ticket 18):** Ticket 19 listed Ticket 05
("Decide silver delta publication and scope-completion semantics") as a
blocker; Ticket 05 is still open and scoped to the future Snowflake landing
zone (producer/window/attempt/file identities, immutable landing paths,
table-specific upsert/retirement/replacement, eliminating mutable same-key
Parquet/manifests). This ticket's bounded first slice targets DuckDB's
`sec_raw_object` for a single family (`filing_artifact`), per
silver-snowflake-migration's own Decisions-so-far (DuckDB remains
canonical today; MDM's cutover is Ticket 12, still pending) -- Ticket 05's
edge is stale for this narrower target. Ticket 05 stays open for the real
Snowflake delta-publication contract later migration tickets (21-24) need.

**Bullet 1 (sealed expected producers):** `ProcessingLedger.
seal_expected_producers` derives the Processing Decision automatically from
a revision's own `content_impact` (Ticket 18): `NO_IMPACT` seals with zero
expected producers and is immediately `silver_outcome=PUBLISHED` ("explicit
no-impact outcome"); `CHANGED` seals `disposition=PROCESS_REQUIRED` with the
caller-declared producer set (`ExpectedProducerSpec`: producer_name,
target_table, scope_reference) and starts `silver_outcome=PENDING`. Idempotent
per `revision_id` (`uq_source_processing_decision_revision`), same
insert-then-reread-on-`IntegrityError` pattern as Ticket 18.
`ProcessingDisposition` declares Ticket 03's full seven-value set as real
schema, but this ticket's code path only ever produces `PROCESS_REQUIRED`/
`NO_IMPACT` -- the other five (`OUT_OF_SCOPE`, `OPERATOR_EXCLUDED`,
`SUPERSEDED`, `QUARANTINED`, `RETRYABLE_FAILURE`) are Ticket 25's
conflict/repair/exclusion workflows and Ticket 26's epoch rebuild, out of
this bounded first slice by design -- documented in `ProcessingDisposition`'s
own docstring after Spec review flagged the narrowing as previously
undocumented.

**Bullet 2 (read-back verification):** `SilverFinalizer.
record_producer_outcome` is the only path that may record `VERIFIED`, and
`silver_acceptance.finalize_filing_artifact_candidate` only ever calls it
with `VERIFIED` after `silver.get_raw_object(raw_object_id)` reads the row
back from DuckDB and confirms its `sha256` matches the revision's
`raw_evidence_hash` -- a write that lands but reads back wrong content is
recorded `FAILED`, not `VERIFIED` (`test_finalize_marks_failed_on_read_back_
mismatch`, injects a corrupting write and asserts the mismatch is caught).

**Bullet 3 (extended Source Change Status):** `AcquisitionLedger.
source_change_status` (Ticket 14) and every existing caller are untouched --
a new `processing.read_source_change_status_detail` (Python, ORM-based) and
a new `source_change_status_detail` SQL view (for direct operator Postgres
access) both join decision + fetch state + revision + processing +
expected-producer progress + blocker + next action. Spec review caught a
real sibling-divergence bug here: the SQL view's `next_action` CASE mapped
`LEASED`/`FAILED` fetch states, but the Python function only had a
`CAPTURED` branch -- fixed to mirror the view's mapping exactly, locked in by
`test_source_change_status_detail_reflects_leased_and_failed_fetch_states`.

**Bullet 4 (same-key ordering):** sealing a revision requires the
immediately preceding revision for the same key to already have
`silver_outcome=PUBLISHED`; a `PENDING` or `FAILED` prior blocks every later
revision for that key (tested for both, plus that a `FAILED` block is
permanent, not transient, and that unrelated keys are never affected).
Real DB backstop: `uq_source_processing_decision_active_key`, a partial
unique index mirroring `uq_source_fetch_work_active_key`, makes two
concurrently `PENDING` processing decisions for one key impossible. An
earlier draft used `SELECT ... FOR UPDATE` for the ordering check itself;
live Postgres testing found PostgreSQL requires UPDATE privilege for that,
which the processor role deliberately lacks on `source_processing_decision`
-- removed in favor of a plain committed read, safe because
`silver_outcome` only ever transitions away from `PENDING` once and never
reverts, so a stale read can only under-report readiness (a transient,
self-healing false block), never over-report it. `SilverFinalizer.
record_producer_outcome`'s own multi-producer rollup *does* keep
`.with_for_update()` (the finalizer's column-scoped UPDATE grant does
satisfy Postgres's privilege check, confirmed live) -- proven under genuine
concurrency by
`test_concurrent_producer_settlement_rollup_converges_to_published` (two
threads, two separate connections, settling two different producers under
one Processing Decision).

**Bullet 5 (durable external evidence):** every test in
`tests/acquisition/test_silver_acceptance.py` exercises
`finalize_filing_artifact_candidate` against a real `SilverDatabase`
(DuckDB) and reads `sec_raw_object` back independently -- assertions are on
what actually landed in that store, never on which internal object was
invoked.

**Deliberate scope narrowing (documented in `silver_acceptance.py`, not
silently omitted):** `filing_artifact`'s `canonical_source_hash` and
`domain_content_hash` both equal `raw_evidence_hash` -- there is no real
transport normalization or interpretation for full-submission-text yet
(that is later, per-family migration work). This means `content_impact` for
this family cannot yet distinguish "new transport bytes, same domain
content" (Ticket 03's `NO_IMPACT` case); only a byte-for-byte-identical
resubmission is detected as `NO_IMPACT` today. A later family migration
must not inherit this as an assumption once real parsing exists.
`discovery.py` is deliberately untouched -- pulling a `SilverDatabase`
(DuckDB) dependency into it would re-acquire the legacy-orchestrator
coupling its own docstring says it exists to avoid;
`finalize_filing_artifact_candidate` instead consumes an already-CAPTURED
`decision_id` as a standalone function. Wiring this into a live
discovery-drive call, if wanted, is separate follow-up work, not bundled
into this ticket.

**Review:** Standards + Spec `/code-review` ran as parallel sub-agents
against the real diff (`git diff HEAD` on top of merged Ticket 18). Both
completed this time (no session usage-limit interruption, unlike Ticket 18).
Standards found one real bug -- `read_source_change_status_detail` never
called `set_postgres_role` (the same missing-role-on-a-new-read-helper shape
that has recurred across this session's history) -- fixed, and confirmed
fixed against real Postgres (the bug is Postgres-role-gated only; SQLite
tests could never have caught it). Standards also flagged a test reaching
into `ProcessingLedger`'s private `_existing_for_revision` instead of a
public accessor -- fixed by promoting it to a public `read_for_revision`
method (real gap in the class's own interface, not just a test smell).
Spec found the `ProcessingDisposition` narrowing (documented above) and the
`next_action` sibling-divergence bug (documented above and fixed). Spec
confirmed bullet 4's ordering rule is correct including the FAILED-permanent
vs. PENDING-transient distinction, confirmed the hash-degeneracy narrowing
was already honestly documented, and confirmed no scope creep (the new
`source_change_status_detail` SQL view is literally what Ticket 03 asks for,
not an addition beyond spec).

Tests: 25 in `tests/acquisition/test_processing.py` (generic mechanism,
including a real multi-threaded concurrency proof for concurrent sealing of
the same revision), 7 in `tests/acquisition/test_silver_acceptance.py`
(`filing_artifact` wiring against a real `SilverDatabase`), 2 new SQL-text
assertions in `tests/acquisition/test_migration.py`, and 2 new end-to-end
tests in `tests/integration/test_acquisition_ledger_postgres.py` (real
`postgres:16-alpine`: the full seal/finalize/ordering round trip through
the actual Python API plus grant-boundary proofs -- processor cannot UPDATE
`source_expected_producer`, finalizer cannot INSERT it, finalizer's UPDATE
grants are column-scoped on both new tables; and the genuine concurrent
multi-producer rollup race). Full repo suite green: 2445 passed, 4 skipped,
only the 2 pre-existing unrelated
`test_bootstrap_dbt_snowflake_secret.py` failures.
