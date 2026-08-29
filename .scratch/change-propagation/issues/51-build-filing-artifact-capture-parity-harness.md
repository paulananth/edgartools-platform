# 51 — Build the 1-CIK then 100-CIK filing_artifact capture-parity harness

**What to build:** Ticket 10 Decision 2's side-by-side verification gate
for `filing_artifact`: compare the legacy capture path's captured-artifact
set against the ledger-gated path for the same window and CIK scope.
Pass is equal-or-superset with zero silent gaps. Stage 1 is one CIK
(`0000320193`, Apple). Stage 2 is `--limit 100`, not full `load_history`.
Unrelated CIKs are not processed. One `cause_reference` per path.

**Blocked by:** 10 — Decide baseline, migration, cutover, and rollback
sequencing (resolved); 46 — Wire `filing_artifact`'s gated driver into
`daily_incremental` (resolved)

**Status:** resolved

Type: task

- [x] Stage 1: scope resolves to exactly Apple CIK `320193` by default
  (`limit=1`).
- [x] Stage 2: `--limit 100` keeps the first 100 scoped CIKs and drops
  anything past that; unrelated CIKs are not in the comparison scope.
- [x] Diff Verified Source Evidence, Source Fetch Decision rows, and
  Silver Logical Source Keys. Pass only when gated is equal-or-superset
  of legacy on every surface, with zero keys present only on legacy.
- [x] Distinct non-empty `cause_reference` per path. Shared or missing
  cause fails closed. Do not mix Identity Backstop Sweep or MDM
  Reconciliation Backstop into this harness.
- [x] A CIK-scoped gated discovery run does not call
  `record_catchup_progress` for the date (a subset must not claim the
  family's catch-up barrier).
- [x] Observe-only CLI `compare-filing-artifact-capture` (JSON snapshots,
  excluded from the warehouse orchestrator like `gold-verify-live`).
  Does not repair either path.

## Notes

Ticket 46 proved gated capture in isolation (including a live 2026-08-28
run against 4,491 sealed daily-index candidates) but never against the
legacy path's own output for the same window. Ticket 27's removal-evidence
bullets stay blocked until a real Decision 2 window passes this harness;
shipping the harness is not itself Ticket 27.

GoF: no existing compare module. Closest sibling is Ticket 41's
observe-only aggregator (injected readers, JSON, CLI outside
`COMMAND_REGISTRY`). 1-CIK vs 100-CIK is the same algorithm with a
different `limit` — not Template Method, not Strategy classes. Leave
`drive_filing_discovery.py`'s family wrappers as the existing
parameterized Strategy reuse.

## Answer

`edgar_warehouse/acquisition/capture_parity.py` is the Decision 2 compare
seam. `resolve_parity_scope` defaults to Apple CIK `320193` at `limit=1`
and keeps the first N CIKs at `limit=100`. `compare_capture_snapshots`
diffs Logical Source Keys, Verified Source Evidence (keys that have a
reference), and Source Fetch Decision rows (keys that have a
`decision_id`). Pass is gated equal-or-superset on every surface, plus
distinct non-empty `cause_reference` values, plus zero out-of-scope CIKs.

CLI `edgar-warehouse compare-filing-artifact-capture --business-date …
--legacy-snapshot … --gated-snapshot …` is observe-only JSON in / JSON
out, excluded from `COMMAND_REGISTRY` like `gold-verify-live`. It does
not run either capture path and does not repair. Operators produce those
JSON files after a scoped legacy `targeted-resync` / `bootstrap-next
--cik-list` run and a scoped `drive-filing-discovery-for-date --cik-list`
run. `artifact_from_silver_raw_object` / `artifact_from_source_fetch_decision`
map live `sec_raw_object` and Source Fetch Decision rows onto the same
compare key (`{cik}/{accession}/full-submission-text`) so dumps do not
invent Logical Source Keys. Evidence and decision surfaces compare
*presence per key*, not cross-path reference-string equality — legacy
`sha256` and gated `verified_evidence_reference` are different encodings
of the same captured artifact.

`drive-filing-discovery-for-date --cik-list` filters sealed daily-index
rows so a 1-CIK or 100-CIK gated run can actually be produced. A scoped
run skips `record_catchup_progress` so a subset cannot claim the family's
date-level catch-up barrier.

Tests: `tests/acquisition/test_capture_parity.py` and
`test_drive_filing_discovery_cik_list_skips_unrelated_cik_and_does_not_record_catchup`.
This does not retire the legacy path (Ticket 27) and does not mix
Identity Backstop Sweep or MDM Reconciliation Backstop.
