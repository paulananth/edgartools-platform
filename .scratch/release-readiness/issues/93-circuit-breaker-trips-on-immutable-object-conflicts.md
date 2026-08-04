# 93 — `filing_artifact_pipeline`'s circuit breaker trips on immutable-object conflicts, not just real systemic failures

Type: task
Status: open

## Question

Found live 2026-08-04 while retrying [ticket 42](42-decide-execute-fundamentals-backfill.md)'s
sample artifact-fetch (`bootstrap-batch --artifact-policy all_attachments`) on `large` after
its first attempt OOM'd on `medium`. The retry exited **0** (looks clean) but actually did
almost nothing:

```
{"attempted_accessions": 45, "consecutive_errors": 20, "event": "filing_artifact_circuit_open",
 "processed_accessions": 2, "remaining_accessions": 3147, "run_id": "ticket42-sample-artifacts-retry-large-..."}
{"accession_count": 3149, "circuit_breaker_disposition": "closed", "errors": 43,
 "event": "filing_artifact_pipeline_completed", "processed_accessions": 2,
 "remaining_accessions": 3147, ...}
```

All 43 errors are `WarehouseRuntimeError("immutable object '...' already exists with different
content")` — the exact same error class [ticket 87](87-immutable-object-conflict-apple-form4.md)
already root-caused (SEC-side byte drift on already-captured documents) and fixed for
`targeted-resync --scope-type cik` (per-accession isolation: catch, skip, continue, record in
`accessions_conflict_skipped`). `bootstrap-batch`'s `filing_artifact_pipeline` has no equivalent
isolation, and its circuit breaker (designed to protect against systemic failures like SEC rate
limiting or an outage) counts these individually-recoverable, expected conflicts toward its
20-consecutive-error threshold — tripping after 20 conflicts and abandoning the remaining 3,147
accessions, while still reporting `circuit_breaker_disposition: "closed"` and exit code 0 in the
final summary (misleadingly looks like a clean, if small, success).

All 43 conflicts trace to CIK 1800 and 4 Form-4 co-filer/reporting-owner CIKs (1294731, 1787479,
1867666, 2102715 — none in the 20-CIK `--cik-list` passed to this run, pulled in via Form 4's
issuer+owner path structure). Likely residue of the first (OOM'd, ticket 42) attempt's partial
bronze writes for CIK 1800's Form 4s, now conflicting with SEC's currently-served bytes for the
same documents -- consistent with, but not yet confirmed to be, the same "SEC serving drifted
slightly since our earlier capture" root cause ticket 87 found for Apple. Not yet confirmed
whether this is that same byte-drift pattern or a different, repo-side cause (e.g. a document-path
collision across the 5 CIKs) -- needs the same byte-diff investigation ticket 87 did before
assuming the explanation transfers.

## Root cause confirmed (2026-08-04)

Sampled 3 of the 43 conflicting accessions (all CIK 1800 Form 4s), same method as ticket 87:

| Accession | Stored `LastModified` | Stored bytes | Fresh bytes | Diff |
|---|---|---|---|---|
| 0001385262-26-000019 | 2026-07-30T02:17:47Z | 4388 | 4389 | trailing `\n` after `</ownershipDocument>` |
| 0001577544-26-000010 | 2026-07-30T02:17:48Z | 4337 | 4338 | same |
| 0001879701-26-000008 | 2026-07-30T02:17:48Z | 4402 | 4403 | same |

All three: content byte-identical except one trailing newline SEC's archival server now
serves that wasn't present at capture time. Fresh fetch is stable across repeats (re-fetched
twice more, identical MD5 both times). Critically, **all stored objects were captured
2026-07-30 -- days before this session's sample backfill (2026-08-04) even ran** -- ruling
out the initial hypothesis that these were residue from ticket 42's OOM'd first attempt.
This is the same SEC-side archival-serving drift ticket 87 characterized for Apple, just
recurring far more densely here (43 instances in one CIK's Form 4 corpus vs. Apple's 1
originally found, though ticket 87's own live-verification later found 27 for Apple on a
full resync too) -- confirms this is a widespread, ongoing pattern affecting many
previously-captured documents, not a rare one-off. **Not a repo-side bug, not a path
collision, not a residue-from-today issue.**

## What needs deciding

1. **Root cause**: confirm (via the same byte-diff approach ticket 87 used) whether these 43
   conflicts are genuine SEC-side drift or something else (e.g. a path-collision bug specific to
   Form 4 issuer/owner CIK handling).
2. **Fix shape**: should `filing_artifact_pipeline`'s per-accession error handling (not just
   `targeted-resync`'s) isolate immutable-object conflicts the way ticket 87 did, and/or should
   the circuit breaker's consecutive-error counter exclude this error class entirely (since it's
   individually-recoverable and not a signal of a systemic SEC-side problem)? `bootstrap-batch`,
   `daily_incremental`'s `RunWarehouseTask`, and any other caller of
   `fetch_filing_artifacts`/`filing_artifact_pipeline` share this same gap.
3. **Silent-success masking**: the final `filing_artifact_pipeline_completed` summary reports
   `circuit_breaker_disposition: "closed"` and callers see exit code 0 even when the circuit
   opened mid-run and abandoned the bulk of the candidate accessions -- this should surface as a
   clear failure/partial-completion signal, not something that looks like a normal small run.

## Fix implemented (2026-08-04)

`_run_configured_form_artifact_pipeline` (`warehouse_orchestrator.py`), the shared function
behind `bootstrap-batch`, `daily_incremental`'s `RunWarehouseTask`, and every other caller of
this artifact-fetch loop:

1. **Root fix**: in the per-accession `except` block, an immutable-object conflict (classified
   via the same `_is_immutable_object_conflict` helper ticket 87 introduced) no longer
   increments `consecutive_errors` -- it resets the streak to 0 instead, the same as a real
   success does, since it's an isolated, individually-recoverable condition rather than a
   systemic-failure signal. Still counted in the total `errors` counter and still logged via
   `filing_artifact_failed`, so it's never silent -- just excluded from what trips the breaker.
   A new `conflict_skipped_count` counter tracks these separately (mirrors ticket 87's
   `accessions_conflict_skipped`), surfaced in both the `filing_artifact_pipeline_completed`
   event and the function's return dict.
2. **Reporting fix**: `circuit_breaker_disposition` in the final `filing_artifact_pipeline_completed`
   event was previously a hardcoded `"closed"` literal regardless of whether the circuit
   actually opened earlier in the same run -- now tracks a real `circuit_opened` flag set at
   both `filing_artifact_circuit_open` emission sites, so a genuine future circuit-open (from
   some other error type) reports honestly instead of looking identical to a clean run.

Deliberately unchanged: `release_mode` still hard-fails on any error immediately (its bounded
required-candidate-manifest guarantee is a stricter, different contract than the circuit
breaker); `recurring_mode`'s end-of-run `if errors or repair_required: raise` still fails loudly
on any conflict (daily_incremental should keep surfacing conflicts to an operator even though
`record_terminal_repair` already routes them for resume-skip on the next run) -- both are
existing, deliberate behaviors outside this ticket's scope.

Two new tests in `tests/unit/test_submission_phase_order.py`:
`test_immutable_object_conflict_does_not_trip_circuit_breaker` (5 consecutive conflicts, past
the configured limit of 2, followed by 1 real success -- confirms no circuit-open event fires,
`conflict_skipped_count == 5`, the success still processes, and the final summary reports
`circuit_breaker_disposition: "closed"`) and the pre-existing
`test_recurring_artifact_pipeline_fails_when_circuit_opens` (unchanged, uses `ValueError` --
confirms genuinely systemic error types still trip the breaker as before, proving the fix is
narrowly scoped to this one error class). Verified via `git stash` that the new test fails
pre-fix (`KeyError` first, then a real assertion failure once the return-dict key was added)
and passes post-fix. Full suite green: 1776 passed, 4 skipped, only the pre-existing unrelated
`test_go_live_wizard.py` failure.

Not yet deployed to prod or live-verified against the actual 43-conflict scenario that
surfaced this bug.

## Done when

A decision is made and implemented on both the isolation question and the misleading
exit-0/closed-disposition-after-an-open reporting gap, tested, deployed, and live-verified the
same way ticket 87's fix was (re-run against the same conflicting accessions, confirm they're
skipped-and-logged rather than tripping the circuit).
