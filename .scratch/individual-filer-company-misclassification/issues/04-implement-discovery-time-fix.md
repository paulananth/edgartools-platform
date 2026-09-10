Type: task
Status: resolved
Blocked by: 03

## Question

Design and implement the two code changes Ticket 03 specified: (a) skip
the `sec_company` (+ address + former-name) write when SEC's own
`entityType` isn't `'operating'`/`'investment'`, and (b) separately
downgrade/exclude `sec_company_sync_state`'s tracking status once
`entity_type` is known non-company, so these CIKs stop being re-fetched
in full on every subsequent `daily_incremental` run.

## Answer

Both fixes land at the single real choke point Ticket 03 traced --
`stage_submission`/`_stage_submission_locked` (`silver_store.py`) and
`_apply_submission_snapshot_to_silver` (`warehouse_orchestrator.py`),
both called from exactly one place in the codebase
(`_run_submissions_bronze_then_silver`), so the fix covers every caller
(`daily_incremental`, `bootstrap-next`, `load_history`) automatically --
no separate check needed for whether `bootstrap-next`/`load_history`
shares the bug shape, since they share the fix point.

**Shared classification function** (`edgar_warehouse/loaders/
bronze_submission_extractors.py`): `REPORTING_COMPANY_ENTITY_TYPES =
frozenset({"operating", "investment"})` and
`is_reporting_company_entity_type(entity_type)`. Both fix points call
this same function, so the write-skip and the tracking-status demotion
can't drift apart. Missing/empty `entityType` fails open (treated as a
reporting company) -- an implementer decision beyond what Ticket 01/03
analyzed, since only `'operating'`/`'investment'`/`'other'` have been
observed live and a missing value has never been shown to correlate with
`'other'`.

**Fix (a), correctness:** `_stage_submission_locked` now skips
`stage_company_loader`/`stage_address_loader`/`stage_former_name_loader`
(and their merges) when `is_reporting_company_entity_type(main_payload.get("entityType"))`
is false. `stage_manifest_loader`/filing rows are deliberately left
ungated -- real filing history (Form 3/4/5/144/13D/13G) is not a
company-universe claim and needs to survive untouched for Ticket 02's
future person re-derivation.

**Fix (b), cost:** `_apply_submission_snapshot_to_silver` now overrides
`tracking_status` to a new value, `"non_company"`, when the same check is
false -- mirroring `_demote_deregistered_ciks`'s existing unconditional-
overwrite pattern for Form 15. `_filter_ciks_to_universe` already only
selects `tracking_status='active'` CIKs for future `daily_incremental`
sweeps, so no change was needed there -- a non-company CIK now gets its
full submissions.json fetched exactly once more (the run that discovers
its true entity type), never again.

**Deliberately not done here** (matches Ticket 02's decision and the
map's own scope): no cleanup of the ~33K already-corrupted `sec_company`
rows. This fix only stops new contamination and new wasted re-fetches
going forward.

**Verification:** 3 new unit tests
(`tests/unit/test_stage_submission_entity_type_gate.py`) prove the
classification function's edge cases (`'operating'`/`'investment'`/
`'other'`/`None`/`''`) and that `stage_submission` against a real
`SilverDatabase` skips company/address/former-name writes but keeps
filing history for an individual filer, while a real company still
writes normally. 1 new test in `tests/unit/test_submission_phase_order.py`
proves the tracking-status override fires through
`_apply_submission_snapshot_to_silver`'s real (bulk-batched) call shape.
Full repo suite green: 3182 passed, 7 skipped, exit 0.

**3-axis `/code-review` (Standards/Spec/GoF), per CLAUDE.md hard rule,**
all clean -- no hard violations, no scope creep, no structural
(GoF-pattern-worthy) problem. Two minor notes, not acted on: (1) the
`tracking_status` allowlist/override block in
`_apply_submission_snapshot_to_silver` has now grown twice (deregistered,
then non_company) via the same mechanical edit -- GoF review: still one
occurrence, still cheap, not worth extracting yet, revisit if a third
terminal status is ever added; (2) the override's interaction with the
adjacent `"deregistered"` branch (a CIK could in principle be both) isn't
explicitly commented -- harmless today since both values are excluded by
the same `active`-only filter, noted here rather than churning the code
for it.
