# 52 — Check whether the capture-parity harness exercises the legacy path

**What to build:** Nothing. Confirm or refute: Ticket 51's 1-CIK / 100-CIK
harness never runs the legacy filing-artifact capture path, and the only
thing it actually exercises is the compare (plus gated `--cik-list`
scoping).

**Blocked by:** 51 — Build the 1-CIK then 100-CIK filing_artifact
capture-parity harness (resolved)

**Status:** resolved

Type: research

## Question

Ticket 10 Decision 2 requires running *both* paths side-by-side for a
window and diffing captured-artifact sets. Ticket 51 shipped
`compare_capture_snapshots` and `drive-filing-discovery-for-date
--cik-list`. Does any test or CLI path in that work actually invoke
legacy capture (`fetch_filing_artifacts` /
`_run_configured_form_artifact_pipeline` / `targeted-resync` /
`bootstrap-next --cik-list`), or is the "legacy" side only a labeled
fixture feeding the diff?

## Answer

**Confirmed: Ticket 51 does not exercise the legacy capture path.** The
only live capture driver it added is gated (`drive-filing-discovery-for-date
--cik-list`). The dual-path "diff" is synthetic.

Evidence:

1. `tests/acquisition/test_capture_parity.py` never imports or calls
   `fetch_filing_artifacts`, `_run_configured_form_artifact_pipeline`,
   `targeted-resync`, or `bootstrap-next`. Every "legacy" input is
   `_snapshot("legacy", …)` — a hand-built `CaptureArtifact` tuple.
2. `test_drive_filing_discovery_cik_list_skips_unrelated_cik_and_does_not_record_catchup`
   runs only `drive-filing-discovery-for-date` with `cik_list=[320193]`.
   That is the gated Facade, not the legacy artifact pipeline.
3. `compare-filing-artifact-capture` is JSON-in / JSON-out. It does not
   start either capture command. Operators are supposed to have already
   produced both snapshots; nothing in Ticket 51 produces the legacy one.
4. Ticket 46's `daily-incremental` path *still* runs legacy capture
   (`_run_submissions_bronze_then_silver` →
   `_run_configured_form_artifact_pipeline`) and *then* gated capture when
   `--enable-filing-artifact-gated-capture` is on. That side-by-side
   *invocation* exists in production code. Ticket 51's tests do not use
   it: `test_daily_incremental_gated_capture.py` mocks both
   `_run_submissions_bronze_then_silver` and
   `_run_filing_artifact_gated_capture` and never diffs their outputs.

What Ticket 51 *does* exercise: the compare contract (equal-or-superset,
silent-gap fail, out-of-scope CIK fail, distinct `cause_reference`) and
gated CIK scoping (including skip-catch-up). That is necessary and not
sufficient for Ticket 10 Decision 2.

Follow-up: [53 — Drive both legacy and gated capture in one harness and
diff their real captured-artifact sets](53-drive-legacy-and-gated-capture-into-parity-diff.md).
