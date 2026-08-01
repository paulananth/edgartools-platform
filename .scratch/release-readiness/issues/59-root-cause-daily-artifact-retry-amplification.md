# Root-cause Daily Artifact Retry Amplification

Type: research
Status: resolved
Blocked by: none

## Question

Why can a bounded Daily Identity Refresh exceed its six-hour full-chain limit
after only a small number of artifact failures, and what retry/resume contract
must change before the recurring schedule is eligible for activation?

## Triggering evidence

The fixed-image production execution `daily-post-txt-fix-20260801T005633Z`
completed company identity, then its first `RunWarehouseTask` processed 5,120
of 5,122 bounded artifact candidates, made 40,728 network fetches, and failed
closed for two candidates after about 2h42m in artifact processing. Step
Functions then retried the whole warehouse task rather than resuming the two
remaining candidates.

## Required investigation

- Identify the two failed candidates and their exact failure classes.
- Measure whether the retry repeats already-successful capture/parser work and
  which stages are safely idempotent versus unnecessarily repeated.
- Trace Step Functions retry granularity and the artifact pipeline's persisted
  progress/remaining-candidate semantics.
- Apply an evidence-backed 5 Whys analysis, distinguishing the correct
  fail-closed disposition from avoidable full-task retry amplification.
- Specify the follow-up decision needed to make a bounded, resumable artifact
  retry contract without permitting partial success to masquerade as complete.

## Done when

The root cause, safe boundary, and a concrete follow-up decision are recorded.
The at-most-six-hour daily gate remains failed until a new immutable-image
execution completes the entire downstream chain within the bound.

## Answer (2026-08-01)

The `.txt`-path accession fix is working: the fixed-image execution completed
company identity and reached the bounded recurring-artifact stage. The new
overrun is instead a retry-granularity failure. The first artifact worker did
nearly all of its assigned work, then the platform correctly failed closed for
two immutable-content conflicts. Step Functions treated that terminal task
failure as generically retryable and restarted the *entire* `daily-incremental`
command. It has no durable, per-accession remaining-work input to resume.

### Direct evidence

Production execution `daily-post-txt-fix-20260801T005633Z`, using warehouse
image digest `sha256:72d4e4aa493520dda1c9327250f64388ce2bfed1c575cabfd65cb6efd3633f4d`,
entered `RunWarehouseTask` after its bounded company-identity stage. Its first
worker (`b42116682c2a43e2b105e6d3d576283c`) then reported:

- 5,122 selected accessions; 5,120 processed;
- 40,728 SEC network fetches and 39,331 rows written;
- 9,714 seconds (2h41m54s) in the artifact stage; and
- two errors, then `recurring artifact pipeline had 2 failed candidates` and
  ECS exit code 2.

The two candidates are both CIK `2143673` and both failed the immutable-object
guard, not SEC accession validation or a network request:

1. `0000905148-26-003370` — existing
   `filings/sec/cik=2143673/accession=0000905148-26-003370/primary/form3.xml`
   has different content.
2. `0001999371-26-016256` — existing
   `filings/sec/cik=2143673/accession=0001999371-26-016256/primary/otpp-form3_072826.xml`
   has different content.

The conflicts are deterministic legacy-data mismatches, not SEC/network
failures. The two existing objects were written on July 30 before commit
`5ca3041` changed artifact persistence from transformed
`edgartools attachment.content` bytes to the exact raw SEC HTTP response. Live
SEC SHA-256 values differ from the stored immutable bytes for both candidates
(`bd7cbc…a8d` vs `69ce7d…275`; `0fe913…a9a2` vs `876900…201d`). The immutable
guard correctly refused to overwrite the legacy representation. Neither error
was candidate-retried (`retry_count=0`) because immutable-content
`WarehouseRuntimeError` is non-transient. These two terminal outcomes were
then amplified into another full worker invocation.

### 5 Whys

1. **Why can this bounded daily execution exceed six hours after two failed
   candidates?** Its first artifact worker spent 2h42m completing 5,120 of
   5,122 candidates, then a second full worker began. That comes after the
   already-measured company-identity time, so the chain cannot meet the gate.
2. **Why were those two candidates unresolved?** Their destination keys contain
   legacy transformed `attachment.content` bytes, while the current exact-raw
   SEC capture produces different bytes. The immutable guard deliberately
   refuses to overwrite either value.
3. **Why did two unresolved candidates make the worker fail?** Recurring
   artifact mode correctly records non-transient candidate failures, finishes
   the rest of the selected set, and raises a fail-closed `WarehouseRuntimeError`
   when any remain.
4. **Why did that worker failure restart all completed work?** The generic
   `RunWarehouseTask` Step Functions `States.TaskFailed` retry invokes the
   full `daily-incremental --run-id <execution>` command again, rather than a
   worker scoped to the two unresolved candidates.
5. **Why cannot the retry consume only unresolved work?** The artifact loop's
   selected set, counters, and `remaining_accessions` are process-local
   telemetry. `emit_partial` reports aggregates but does not persist a
   run-bound per-accession outcome ledger or a durable resume manifest.

**Root cause:** legacy transformed artifact bytes conflict with the new
byte-exact capture contract; the guard correctly fails closed. The avoidable
runtime amplification is a second root cause: generic full-command retry has
no durable per-accession outcome/resume contract, so it cannot distinguish
that terminal repair case from transient task recovery.

## Required follow-up

[Decide a durable daily-artifact resume and disposition contract](60-decide-durable-daily-artifact-resume-disposition.md)
must define a run-bound candidate ledger, safe retry classification, and an
explicit terminal-repair path for immutable conflicts. Until it is implemented
and a fresh immutable-image execution completes the *whole* downstream chain
within six hours, the daily schedule must remain disabled and the gate remains
failed.

## Retry-amplification confirmation (2026-08-01)

At 07:50 EDT, Step Functions started a third full `RunWarehouseTask` attempt
for the same execution. It uses the old `edgartools-prod-large:94` task
definition and image `sha256:72d4e4aa...`, again with exactly
`daily-incremental --recurring-index-lookback-days 7 --run-id
daily-post-txt-fix-20260801T005633Z`. The new worker rehydrated the 1.07 GB
canonical silver artifact, selected 10,491 CIKs, and began reprocessing the
same 5,122 artifact candidates. Its two predecessors each failed on the same
two immutable-content conflicts after redoing the full candidate population:

- attempt 1: 9,714 seconds (2h41m54s) in artifacts, then exit 2;
- attempt 2: 12,756 seconds (3h32m36s) in artifacts, then exit 2.

This is direct production confirmation of the existing 5-Whys conclusion, not
a distinct defect: the generic task retry makes no use of the partial
telemetry, and no durable per-accession resume input exists. The correct next
work remains ticket 60's operator decision; do not create a duplicate ticket.
