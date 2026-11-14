Type: grilling
Status: resolved
Blocked by: 02
Labels: `wayfinder:grilling`

## Checklist

- [x] Implement immutable per-work-unit MDM quality evidence with check identities, counts, and failure actions. 2026-11-13 21:15 ET
- [x] Integrate Bookkeeping admission, unknown handling, and retry-safe recovery behavior. 2026-11-13 21:15 ET
- [x] Record the approved evidence and enablement contract in this ticket. 2026-11-13 21:15 ET
- [x] Validate syntax and patch whitespace with `uv run --no-project python -m py_compile ...` and `git diff --check`; CI remains outstanding. 2026-11-13 21:15 ET
- [x] Learning → skill: update the shared data-quality and Bookkeeping recovery skills; all source adapters use the registered source quality contract and one receipt shape. 2026-11-13 21:15 ET

# Decide MDM Quality Evidence and Bookkeeping Admission

## Question

What immutable per-run evidence should the MDM pipeline produce, and how should
Bookkeeping verify and admit it?

Decide how evidence identifies the rule/check version, run, step, and work
unit; records rows evaluated and rows failed for each check; distinguishes
`flag`, `withhold`, and `exception`; avoids copying source values or provider
identifiers; and behaves on retries, concurrent attempts, incomplete runs, and
recovery. Reuse the completed Silver evidence contract where it fits, while
proving the MDM merge boundary can reproduce or retain the evidence after a
retry. Keep quality outcomes separate from overall pipeline status.

The answer must leave absent or incomplete evidence unknown and state the
recovery/enablement gate before a new receipt version can be used.

## Answer

Operator-approved publication behavior (2026-11-13): publish only counts
from verified work units; label incomplete evidence unknown/`Aborted`; require
exact OpenMetadata readback. Keep quality outcomes separate from pipeline
completion.

Implementation contract:

- Every source adapter reads the registered source contract's `quality` block
  and calls the shared MDM evaluator. Do not add adapter-specific or
  entity-specific result paths. Each check records its configured id, check
  kind, `flag`/`withhold`/`exception` action, checked count and failed count.
- The hashed MDM assertion/deferred provenance retains the executed outcomes
  needed to reproduce evidence from the immutable prepared member. An
  `exception` records its failing check and prior checks, then stops later
  checks for that record; later checks are counted unknown. `flag` and
  `withhold` continue as configured.
- `mastering.merge` emits an immutable receipt with run, step, opaque unit
  reference, observation time, source contract code, quality rule version and
  counts. It contains no source record values or provider record identifiers.
  Journal-skipped batches are re-read under the same pinned registered
  mapping version for counts, without repeating merge writes. Retries reuse
  the receipt's observation time.
- Bookkeeping admits the receipt only for its verified work unit and validates
  identity, action and bounded count relationships. Missing receipts and
  unchecked rows stay unknown. A run can complete while quality is failed or
  unknown; neither outcome changes pipeline completion.
- Require both the frozen `mdm.quality.evidence.v1` check and
  `MDM_QUALITY_EVIDENCE_V1=enabled`. Keep the switch and production check
  configuration off until disposable recovery qualification and operator
  enablement. This change does not activate production rules.
