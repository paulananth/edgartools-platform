# Recovery decisions

Read [INDEPENDENCE.md](INDEPENDENCE.md) before selecting an execution recovery
path. `bookkeeping resume` rechecks retained evidence and reopens the run; the
workers and verifiers then continue it. The restricted-role and recovery gates
(mastering to-do 20b) have not run yet, so do not claim qualified recovery. A
dependency failure is implementation work, not a reason to reintroduce a loader
into control.

Read bounded status and leases first. See the
[specification](SPEC.md) for authority and
storage semantics; use live CLI help when an option differs.

## Enable a new receipt format

Keep a new versioned receipt format disabled until its recovery path is ready.
Name the recovery owner, document how an interrupted run resumes from that
format, measure a resume with a disposable run, and set a maximum recovery
time. Enable it only after the measured resume completes within that maximum.
Record the owner, procedure, measurement and maximum with the validation
evidence. Parsing receipts or passing unit tests does not prove resume works.

When a frozen step requests `silver.quality.evidence.v2`, the worker checks
only whether `SILVER_QUALITY_EVIDENCE_V2` is set to `enabled`; it does not
verify these qualifications. Keep the opt-in unset until the operator records
the evidence and authorizes enablement. A request without that exact setting
fails closed.

### The version-2 quality receipt: owner, procedure, measurement

**Owner.** The platform operator owns recovery of a version-2 quality run. The
operator decides whether to resume, and the resume itself is run through
Bookkeeping's own commands by whoever holds the control and worker logins.

**Procedure.** A version-2 receipt names the work unit, not the attempt, and
carries the observation time of that unit's first successful landing. A unit
re-executed after a lost report therefore writes the same bytes to the same
immutable output, and the evidence a resumed load carries is the evidence the
first attempt produced.

1. Read bounded status: `edgar-warehouse bookkeeping status <run-id>`. A
   `reported` unit is awaiting its verifier. A `running` unit's worker stopped
   only once its lease expires; a live lease still holds the unit.
2. Reopen the run: `edgar-warehouse bookkeeping resume <run-id>`. It rechecks
   every completed unit's retained evidence and blocks the run if any evidence
   is corrupt; a `reported` unit's candidate is retained and is admitted by its
   verifier. Exit 3 means the run is not complete yet, which is expected here.
3. Run the workers and verifiers for the run's profiles again, in step order:
   `edgar-warehouse workers work <profile> <run-id> --limit 100` and
   `edgar-warehouse workers verify <profile> <run-id> --reports <report-root>
   --limit 100`. Repeat until the run's units are all verified. A unit whose
   attempt ended is reclaimed only after its lease expires (the default is 120
   seconds); a re-execution reconciles with the receipt it already wrote.
4. Finish: `edgar-warehouse bookkeeping finalize <run-id>`. It delivers control's
   events and records the run's checks; exit 3 means the run is not complete
   yet.
5. Read the admitted quality evidence with `edgar-warehouse rules catalog
   check --bookkeeping-run <run-id>`. It is read-only: its report carries the
   run's admitted quality summary and it never publishes. An incomplete run
   returns a pending report before OpenMetadata is contacted, so it stays
   unknown and is never published as a load's quality result. Publish with
   `edgar-warehouse rules catalog publish --bookkeeping-run <run-id>` only
   when the result is wanted in the catalog.

**Measurement.** A disposable resume was measured (ET) over
invented source files in a disposable PostgreSQL 16 container, with no
provider data: `tests/integration/test_quality_recovery_postgres.py`. Two
interruption shapes were exercised — a receipt reported and not admitted, and
a receipt written whose report was lost — and both resumed to a complete run
with admitted version-2 evidence. Over nine runs the measured resume (reopen,
work, verify, deliver, finalize) was between 0.146 s and 0.263 s.

That measurement is the evidence the operator's maximum is set against. The
operator set the maximum recovery time at **5 minutes**,
after reviewing the measurement. The measured resume is within that maximum by
three orders of magnitude.

The feature stays disabled until the operator authorizes enablement; this
maximum records the gate the measurement must meet, not the authorization
itself.

## General run recovery

These operational cases cover existing runs; they do not demonstrate a
version-2 receipt resume or satisfy the qualification gate above.

Resolve the requested source/feed again and compare its dataset/member set
with the run's frozen manifest. A matching source name alone does not identify
the same feed. Preserve the original Rules digest when recovering a run;
today's authoring document may have changed.

| Observation | Action |
| --- | --- |
| Waiting unit, another owner has an unexpired lease | Let bounded contention retry leave work waiting. Independent scopes can continue. Resume after ownership is available; preserve the current owner's lease. |
| Worker stopped or acknowledgement was lost | Resume the same run. Destination reconciliation precedes execution; retained receipts and business idempotency keys prevent duplicate effects. |
| Expected count exceeds verified count | Inspect pending/waiting units and prerequisite steps. Item listings are bounded; state counts cover the run. Checkpoints cannot advance over holes. |
| All work verified, deliveries pending | Restore ledger availability and resume. Delivery retries the exact event id/envelope. Completion waits for acknowledgement. |
| Publication verification failed | Correct availability/read-back failures, then resume. Exact required consumers must verify. Hosted export/graph adapters are currently unsupported. |
| Missing/corrupt manifest, receipt or output | Preserve failure evidence. When repair is authorized, recover exact original bytes from trusted retained evidence. A replacement scope/hash requires a new run. |
| Worker runtime changed | A run pins each profile's runtime at its first admitted report; a different runtime is refused. Run the pinned runtime, or submit new work. |
| Candidate reported, verifier never admitted it | While the lease is live, run the verifier again. Once it expires, the worker reclaims the unit and reconciles its earlier effect before writing. |
| Rules retired or authoring YAML changed | Resume from the frozen export. Recover its exact bytes if missing; the live active version cannot replace it. |
| Unknown/legacy run id | Use bounded fresh run discovery. Legacy history is not imported; submit new work when no fresh run exists. |
| Compacted run | Retain its summary, references and checkpoints as audit evidence. Compacted runs cannot resume. |

Pass lease proof separately from business payloads. Database time, fencing
tokens and destination transaction guards determine mutation authority.
Completion and journal intent commit together in Bookkeeping; destination
transactions and ledger delivery are separate commits, not a transaction
across databases.

Preserve state, receipts, tokens and expiry rather than setting them with SQL
to turn a run green. Restore the failed dependency and let the engine verify.
Distinguish authorized dependency repairs from unsupported configuration or
capabilities; report the latter as implementation work with the run incomplete.
