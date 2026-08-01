# Bind daily artifacts to the forced-index accession union

Type: task
Status: claimed
Blocked by: 50, 53

## Question

How must `daily_incremental` prevent a bounded daily CIK set from expanding
into an unbounded historical artifact pass while preserving required filing
and relationship coverage?

## Required work

- Carry the exact accession union from the forced seven-day daily-index
  recheck into daily artifact candidate selection; do not reduce that handoff
  to impacted CIKs.
- Continue refreshing submissions metadata for impacted CIKs, but do not feed
  every historical `recent` or pagination accession from those submissions
  into the daily artifact pipeline.
- Select configured ownership, ADV, proxy, 13F, Item 5.02, and Item 2.02 work
  only from the exact forced-index accession set for this recurring path.
- Assert before attachment iteration that every selected candidate is in the
  exact forced-index accession union. Treat any out-of-union accession as a
  fail-closed expansion-contract violation.
- Keep historical backfill, strict release, repair-manifest, and explicit
  operator workflows separate and unchanged unless their own contract
  explicitly selects history.
- On `PoolTimeout`, close/reset the shared edgartools HTTP client before a
  bounded retry; do not continue through a poisoned pool for thousands of
  candidates.
- Make exhausted retries or an opened artifact circuit fail the recurring
  command with an explicit partial disposition; ordinary daily mode must not
  report successful pipeline completion after abandoning remaining
  accessions.
- Emit exact daily-index accession count/digest, configured candidate count,
  out-of-union count, recent/pagination source counts, form/lookback rejection
  counts, network fetches, cache/fast-parse skips, retries, failures,
  circuit-breaker disposition, exact processed/remaining accession counts, and
  elapsed time.
- Add an adversarial fixture showing that an impacted CIK with years of
  historical configured forms processes only the forced-index accessions.
- Add a PoolTimeout fixture proving reset occurs before retry and retry count
  remains bounded.
- Add a circuit-open fixture proving the recurring command fails and cannot
  publish a normal completion disposition.

## Done when

Focused tests and one immutable-Release-Candidate production execution show
that the recurring daily path cannot reproduce the observed
148,524-candidate expansion, preserves all relevant forms present in the
forced index window, recovers safely from a transient exhausted pool, and
completes the full downstream chain within the accepted six-hour bound.

The implementation must reproduce the invariants and failure semantics
established by
[ticket 53's direct-evidence findings](53-research-findings.md).

## Progress (2026-07-31 — claimed by Codex after Claude handoff)

The latest production execution is terminal, not still running. Authoritative
Step Functions and CloudWatch evidence for
`daily-incremental-ticket03-1785413694` confirms the ticket's failure contract:

- `RunWarehouseTask` received 3,082 CIKs and selected 148,524 artifacts.
- The artifact circuit opened after 20 consecutive errors with a reported
  140,011 remaining accessions.
- The command emitted `filing_artifact_pipeline_completed` anyway, with 140
  errors, 1,081 network accessions, 303 silver skips, 7,736 raw objects, and
  8,373 rows written.
- The ECS task exited 0 and published silver, so Step Functions treated
  `RunWarehouseTask` as successful despite the abandoned artifact set.

No implementation has started in this Wayfinder session. The next work is to
bind recurring artifact selection to the exact forced-index accession union,
make exhausted retry/circuit disposition fail closed, and prove the ordinary
`PoolTimeout` reset path is reachable before any new production timing run.
