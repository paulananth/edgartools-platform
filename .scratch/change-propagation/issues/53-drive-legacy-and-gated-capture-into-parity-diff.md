# 53 — Drive both legacy and gated capture into the parity diff

**What to build:** A 1-CIK (then 100-CIK) harness *run* that actually
invokes the legacy filing-artifact capture path and the ledger-gated path
for the same window and CIK scope, dumps both captured-artifact sets, and
feeds them to Ticket 51's `compare_capture_snapshots`. Pass is still
equal-or-superset with zero silent gaps.

**Blocked by:** 52 — Check whether the capture-parity harness exercises
the legacy path (resolved)

**Status:** resolved

Type: task

- [x] One test (network mocked at the SEC edge, real silver + ledger)
  runs legacy capture for Apple CIK `320193` *and* gated
  `drive-filing-discovery-for-date --cik-list 320193` for the same sealed
  business date, then `compare_capture_snapshots` on snapshots built from
  those runs (`artifact_from_silver_raw_object` /
  `artifact_from_source_fetch_decision`), not hand-labeled fixtures.
- [x] The legacy side is the real artifact pipeline
  (`_run_configured_form_artifact_pipeline` / `fetch_filing_artifacts` or
  `targeted-resync` / `bootstrap-next --cik-list`), not a second gated
  run relabeled `"legacy"`.
- [x] Unrelated CIKs are not processed on either path (`--limit 100`
  proven the same way, second test).
- [x] Distinct `cause_reference` per path. Does not record gated family
  catch-up on a CIK-scoped run (Ticket 51's skip stays).
- [x] This is still not Ticket 27: it does not retire the legacy path.

## Notes

Surfaced by [52 — Check whether the capture-parity harness exercises the
legacy path](52-check-harness-exercises-legacy-capture.md). Ticket 51
shipped the compare seam and gated `--cik-list`; Decision 2 still needs
both *producers* in one proof. Ticket 46 already runs both in-process
inside `daily-incremental` when the flag is on — that call shape is the
obvious driver, if the test can observe each path's captured set
separately (two `cause_reference` values, or a pre/post snapshot of
legacy silver keys vs gated ledger rows).

## Answer

`run_dual_path_filing_artifact_parity` in `capture_parity.py` runs
legacy `fetch_filing_artifacts` (edgartools `get_filing` +
`download_bytes`) for the scoped daily-index accessions, snapshots
`sec_raw_object` **before** gated writes the same table, then runs
`run_filing_artifact_gated_capture_for_business_date(..., cik_list=)`
with the same `download_bytes` patched onto
`source_family_registry.download_filing_content_bytes`. Gated artifacts
come from Source Fetch Decision + CAPTURED work
(`captured_artifact_reference` fills evidence when the decision column
is still empty). Ticket 51's `compare_capture_snapshots` is unchanged.

Tests (`tests/application/test_dual_path_capture_parity.py`):
- Stage 1 Apple: shared Logical Source Key, distinct `cause_reference`,
  legacy artifacts have no `decision_id`, gated artifacts do.
- Stage 2: `limit=100` over a 101-CIK list; unrelated CIK 789019 is in
  the sealed index but not in the first 100, so neither path fetches it.
  CIK-scoped gated capture does not call `record_catchup_progress`.
  Tests patch gated SEC download at the registry edge; the runner does
  not import `unittest.mock`.

Does not retire the legacy path (Ticket 27).
