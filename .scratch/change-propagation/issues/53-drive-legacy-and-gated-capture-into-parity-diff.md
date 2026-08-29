# 53 — Drive both legacy and gated capture into the parity diff

**What to build:** A 1-CIK (then 100-CIK) harness *run* that actually
invokes the legacy filing-artifact capture path and the ledger-gated path
for the same window and CIK scope, dumps both captured-artifact sets, and
feeds them to Ticket 51's `compare_capture_snapshots`. Pass is still
equal-or-superset with zero silent gaps.

**Blocked by:** 52 — Check whether the capture-parity harness exercises
the legacy path (resolved)

**Status:** ready-for-agent

Type: task

- [ ] One test (network mocked at the SEC edge, real silver + ledger)
  runs legacy capture for Apple CIK `320193` *and* gated
  `drive-filing-discovery-for-date --cik-list 320193` for the same sealed
  business date, then `compare_capture_snapshots` on snapshots built from
  those runs (`artifact_from_silver_raw_object` /
  `artifact_from_source_fetch_decision`), not hand-labeled fixtures.
- [ ] The legacy side is the real artifact pipeline
  (`_run_configured_form_artifact_pipeline` / `fetch_filing_artifacts` or
  `targeted-resync` / `bootstrap-next --cik-list`), not a second gated
  run relabeled `"legacy"`.
- [ ] Unrelated CIKs are not processed on either path (`--limit 100`
  proven the same way, second test).
- [ ] Distinct `cause_reference` per path. Does not record gated family
  catch-up on a CIK-scoped run (Ticket 51's skip stays).
- [ ] This is still not Ticket 27: it does not retire the legacy path.

## Notes

Surfaced by [52 — Check whether the capture-parity harness exercises the
legacy path](52-check-harness-exercises-legacy-capture.md). Ticket 51
shipped the compare seam and gated `--cik-list`; Decision 2 still needs
both *producers* in one proof. Ticket 46 already runs both in-process
inside `daily-incremental` when the flag is on — that call shape is the
obvious driver, if the test can observe each path's captured set
separately (two `cause_reference` values, or a pre/post snapshot of
legacy silver keys vs gated ledger rows).
