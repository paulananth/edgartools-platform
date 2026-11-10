# Set and Prove the Recovery Maximum

Type: task
Status: resolved
Blocked by: none
Blocks: 05, 07
Labels: wayfinder:task

## Question

What recovery owner, resume procedure and measured maximum make it safe to
enable the new versioned quality receipt format?

## Checklist

- [x] Name the person or role that owns recovery. The platform operator owns
  recovery of a version-2 quality run; the operator decides whether to resume.
  Verified by the "owner, procedure, measurement" section in
  `skills/bookkeeping/RECOVERY.md` (2026-11-09 18:52 ET).
- [x] Document the resume procedure for an interrupted run using the new format.
  Five steps with the exact commands: bounded status, `bookkeeping resume`,
  the run's workers and verifiers again, `bookkeeping finalize`, then the
  per-load results through `rules catalog check --bookkeeping-run`. Every
  command and its required arguments were checked against the live CLI help on
  2026-11-09 (2026-11-09 18:52 ET).
- [x] Measure a disposable resume without using provider data. The proof
  `tests/integration/test_quality_recovery_postgres.py` runs over invented
  source files in a disposable PostgreSQL 16 container, with no provider
  request. Verified by 14 passed (12 unit, 2 integration) (2026-11-09 18:52
  ET).
- [x] Have the operator set the maximum recovery time after reviewing the
  measurement. The operator set it at **5 minutes** on 2026-11-09, after seeing
  the measured range 0.146 s to 0.263 s (2026-11-09 18:52 ET).
- [x] Keep the feature disabled unless the measured resume completes within the
  maximum; record the evidence before enablement. The measured resume is within
  the maximum by three orders of magnitude; the owner, procedure, measurement
  and maximum are recorded in `skills/bookkeeping/RECOVERY.md`. The
  `SILVER_QUALITY_EVIDENCE_V2` opt-in stays unset: the operator has not
  authorized enablement, and the maximum records the gate the measurement must
  meet, not the authorization (2026-11-09 18:52 ET).
- [x] Learning → skill: `skills/bookkeeping/RECOVERY.md` → the "Enable a new
  receipt format" section now carries the version-2 receipt's owner, its
  five-step resume procedure, the measured resume and the operator's maximum
  (2026-11-09 18:52 ET).
- [ ] ~~Enable version-2 quality evidence in production.~~ Deferred to a
  separate operator enablement decision: the recovery maximum is met, but
  enabling the opt-in is a switch-on that the operator has not made, and it
  belongs with the end-to-end proof in
  [Verify a Completed Load End to End](05-verify-a-completed-load-end-to-end.md).
- [ ] ~~Verify a completed load end to end and observe the shipped
  OpenMetadata UI.~~ Deferred to
  [Verify a Completed Load End to End](05-verify-a-completed-load-end-to-end.md)
  and
  [Observe Per-Load History in the Shipped OpenMetadata UI](06-observe-history-in-shipped-openmetadata-ui.md);
  both are separate gates that this ticket does not claim.

## Answer

The proof found a defect that made the resume impossible, and fixing it was
the work.

A version-2 receipt named the attempt and carried a wall-clock observation
time. A unit re-executed after a lost report therefore wrote *different* bytes
to the same immutable output URI, and the artifact store refused the write
("Artifact hash mismatch"). The run could not be resumed in that case at all,
whatever the recovery procedure said.

The receipt now names the work unit, not the attempt, and a re-execution reuses
the observation time already written for that unit. One unit, one receipt, one
observation time, one correlation: a resumed load's evidence is the evidence
the first attempt produced.

Both interruption shapes are now proven over invented data in a disposable
PostgreSQL 16 container:

| Interruption | What the resume does | Result |
| --- | --- | --- |
| Receipt reported, not admitted | The verifier admits the retained candidate | Complete run, admitted evidence |
| Receipt written, report lost | The unit is reclaimed after its lease ends and re-executed; the re-execution reconciles with the retained receipt | Complete run, same receipt bytes |

Measured resume (reopen, work, verify, deliver, finalize), nine runs:
**0.146 s to 0.263 s**. The operator set the maximum recovery time at
**5 minutes**, which the measurement meets by three orders of magnitude.

Evidence:

```bash
env -u PYTHONPATH TESTMON_DATAFILE=~/.cache/edgartools/testmondata \
  uv run --no-sync pytest tests/unit/test_silver_land_quality.py \
  tests/unit/test_bookkeeping_quality.py \
  tests/integration/test_quality_recovery_postgres.py -q -s
```

Result: 14 passed (2026-11-09 18:52 ET). Nine further runs of the integration
proof measured 0.146 s, 0.178 s, 0.180 s, 0.187 s, 0.204 s, 0.216 s, 0.218 s,
0.263 s and 0.263 s.

The wider affected selection (the two quality unit suites, the catalog unit
suite, the recovery proof and the configured Bookkeeping integration suite)
passed 154 tests before the rebase; the rebased branch passed the 14 focused
tests again.

The feature stays disabled. `SILVER_QUALITY_EVIDENCE_V2` remains unset, and
this ticket records the recovery gate, not an authorization to enable it.
