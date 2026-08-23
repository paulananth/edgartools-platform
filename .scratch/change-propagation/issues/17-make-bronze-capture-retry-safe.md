# 17 — Make Bronze capture retry-safe and recoverable

**What to build:** Make the gated acquisition path converge safely across
retries, not-modified responses, source failures, worker loss, duplicate bytes,
and a failure between Bronze persistence and ledger finalization.

**Blocked by:** 15 — Capture one filing-artifact family through the gated Facade

**Status:** resolved

- [x] Retries preserve the original decision, cause, observation position,
  request identity, and validators while using a new attempt and higher fence.
- [x] `304` and same-bytes/same-producer observations link to prior verified
  evidence without creating a Logical Source Revision. (same-bytes/same-producer
  half only -- see Answer)
- [x] Non-success responses remain Fetch Attempt evidence and cannot create a
  Bronze Artifact, source revision, Scope Completion, or retirement.
- [x] An orphaned Bronze capture can attach only to its original existing Fetch
  Decision after checksum verification; otherwise it remains quarantined.
- [x] A stale worker and a replayed message cannot overwrite or finalize work
  after a newer fenced attempt succeeds.

## Answer

Landed as changes to `edgar_warehouse/acquisition/ledger.py` and
`edgar_warehouse/acquisition/facade.py`, plus a widened
`finalize_source_fetch` Postgres stored procedure
(`edgar_warehouse/mdm/migrations/013_acquisition_ledger.sql`, edited in
place -- not yet applied to any environment, same precedent as Ticket 15's
own in-place edit of this file).

**Bullet 1 (retry preserves identity, new fence)**: already structurally
true from Tickets 14/15/16 (`create_fetch_decision` is idempotent per
`candidate_id`; `claim_fetch`'s claimable set includes `FAILED`) but had
zero test coverage at a realistic caller seam proving it. Added
`tests/acquisition/test_discovery.py::test_retrying_a_failed_candidate_on_a_later_drive_call_preserves_decision_identity`:
a candidate fails on one `drive_discovery_manifest` call, succeeds on a
later one, with identical `decision_id`/`cause`/`observation_position` and
a higher fencing token.

**Bullet 2 (304 / same-bytes linking)**: the same-bytes/same-producer half
was already satisfied by Ticket 15's content-addressed Bronze writes
(`test_identical_bytes_reuse_one_bronze_object_with_distinct_ledger_lineage`).
The `304`/conditional-GET half is **deliberately deferred** to a new ticket,
[28 — Add conditional-fetch validators and not-modified
linking](28-add-conditional-fetch-and-not-modified-linking.md): it requires
a new `AcquisitionLedger` read API (latest verified capture by logical key,
independent of `decision_id` -- doesn't exist), a new `sec_client.py`
conditional-GET path, and currently has zero live callers
(`DecisionCause.DUE_POLICY` exists but nothing invokes it -- verified via
grep, confirmed independently by the Spec review below). Shipping it here
would be dead code reachable by nothing.

**Bullet 3 (non-success stays Fetch Attempt evidence)**: `finalize_fetch`
gained an optional `failure_detail: str | None` parameter, persisted to
`source_fetch_transition.reason` (previously always the generic
`FETCH_<state>` string) on both the SQLite and the widened
(6→7 arg) Postgres stored-procedure paths, with the CAPTURED+failure_detail
mutual-exclusion guard enforced identically on both (defense in depth). New
`AcquisitionLedger.latest_transition_reason(decision_id)` read method makes
this durably queryable independent of whatever exception the original
caller happened to catch.

**Bullet 4 (orphan quarantine)**: `facade.py`'s `capture()` previously had
an uncaught-exception gap -- if the CAPTURED `finalize_fetch` call itself
failed *after* a verified Bronze write, the exception propagated
unhandled and nothing recorded the failure. Fixed with a new
`OrphanedBronzeCapture` exception and `_finalize_captured_with_retry`: a
bounded retry (default 3 attempts, linear backoff, env-overridable) around
only the CAPTURED finalize call. Never falls back to `finalize(FAILED)` on
exhaustion -- the artifact genuinely was captured, so recording FAILED
would misrepresent it. The work row stays `LEASED`; recovery is
lease-gated, not immediately retryable (a caller that retries before the
lease expires gets `ActiveFetchConflict`, not a fresh attempt) -- documented
directly in the exception's own docstring so this isn't mistaken for a bug
by a future session.

**Bullet 5 (stale worker/replay can't overwrite)**: already true at the DB
layer from Ticket 14 (`UPDATE ... WHERE fencing_token = :token`,
rowcount-gated). Two real gaps found and fixed while re-verifying this
against the NEW code this ticket adds:
1. A parallel Standards+Spec `/code-review` caught that `finalize_fetch`'s
   Postgres branch never translated `finalize_source_fetch`'s stale-token
   `RAISE EXCEPTION` into the Python `StaleFencingToken` type -- only the
   SQLite/generic branch did. `_finalize_captured_with_retry`'s
   `except StaleFencingToken: raise` (added by this ticket, to avoid
   retrying a deterministic "someone newer already won" race) would
   therefore never fire on real Postgres: the error would fall into the
   broad `except Exception`, get retried 3 times pointlessly, and then be
   wrongly raised as `OrphanedBronzeCapture` -- misclassifying a
   *superseded* capture as an *orphaned* one, exactly contradicting that
   exception's own docstring. Fixed by catching the driver error in
   `finalize_fetch`'s Postgres branch, matching on the known message, and
   re-raising as `StaleFencingToken`. Regression test, run against real
   Postgres (Docker/Colima):
   `tests/integration/test_acquisition_ledger_postgres.py::test_finalize_fetch_raises_python_stale_fencing_token_against_real_postgres`
   -- exercises the actual `AcquisitionLedger.finalize_fetch` Python API,
   not raw SQL (prior coverage of this exact race only asserted on stderr
   text from a psql call, never on the Python exception type).
2. Separately: SQLite's `CURRENT_TIMESTAMP` server_default is
   second-granularity, so a decision/claim/finalize created within the same
   wall-clock second tied on `created_at`, making the new
   `latest_transition_reason`'s `ORDER BY created_at DESC` ambiguous. Fixed
   by setting `created_at` explicitly from Python's microsecond-precision
   clock on all three `SourceFetchTransitionRecord` inserts
   (SQLite/generic branch only -- Postgres's own `CURRENT_TIMESTAMP` already
   has microsecond precision).

**Review**: parallel Standards + Spec `/code-review`. Standards review was
clean (only minor judgement-call smells: two structurally-similar-but-
behaviorally-distinct test doubles across `test_facade.py`/
`test_discovery.py`, and env vars parsed on every call rather than cached
-- both left as-is, low severity). Spec review found the stale-fencing-
token-on-Postgres gap above (fixed) and confirmed all other bullets either
fully satisfied or legitimately, non-scope-dodging deferred.

Tests: 6 new in `tests/acquisition/test_ledger.py`, 4 new in
`tests/acquisition/test_facade.py`, 2 new in
`tests/acquisition/test_discovery.py`, 2 new in
`tests/integration/test_acquisition_ledger_postgres.py` (both run against
real `postgres:16-alpine` via Docker/Colima, not mocked). Full repo suite
green.
