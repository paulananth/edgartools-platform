# MDM resumable execution module

Design agreed through the architecture discussion. Implementation has not started.

Reviewed source: `66ab7b43ab2fd04472a233b48a33727fb2f0b210`.
Recorded: 2026-10-17 14:02:53 ET.

## Agreed decisions

- The module owns complete resumable manifest execution: manifest validation, source-record reading, frozen mapping selection, batch progression and reconciliation.
- Normal worker execution processes the whole manifest. An explicit bounded mode processes a record budget and returns progress for a later invocation of the same run.
- Preserve single-atomic-batch preview.
- The worker retains artifact transport/staging, lease authority and receipt production. The verifier retains independent read-back and receipt verification.

## Responsibility split

| Module | Responsibility |
|---|---|
| Proposed `edgar_warehouse/mdm/clean/execution.py` | Own manifest reading/validation, source-record conversion, mapping pins, stage order, bounded execution, complete execution and no-progress detection. Accept the existing Store; do not read connection settings or construct engines. |
| Proposed `edgar_warehouse/mdm/clean/connections.py` | Hold the existing environment-backed engine construction and restricted-role selection used by worker, CLI and context command. No new connection lifecycle behavior. |
| Existing `workers/mdm_merge.py` | Stage authenticated artifacts, derive the same MDM run identity from the effect key, supply Store and lease authority, call execution, produce receipts and independently verify them. |
| Existing `mdm/clean/cli.py` | Command argument translation, preparation/report presentation and other existing command handlers. No manifest execution implementation. |
| Existing `mdm/clean/run.py` | Durable run scope, event history and reconciliation. Retain the current coordinator rather than introducing another coordinator abstraction. |
| Existing Merge Stage and PostgreSQL | Mastering decisions and authoritative destination checks, atomic effects/checkpoints/outbox writes and lease fencing. |

These are implementation module names, not new business terms. No CONTEXT.md vocabulary change or ADR is needed for this reversible extraction. No retired execution command is restored.

## Execution semantics

Complete execution stops when every manifest batch is committed (`missing_batches` is empty). Publication and stewardship reviews retain their separate lifecycle; `end_to_end_complete` is not the execution loop's stop condition.

Bounded execution retains current semantics: count new work, skip already-observed batches, charge retained duplicates zero, preserve manifest stage order, and never split an atomic batch. An insufficient budget for the next atomic batch remains an explicit error. The invocation budget does not cap the Merge Stage's affected-master or relationship scope.

Pin every source mapping required by the manifest before starting the run. Resume uses the run's existing pins; newly registered mappings apply to new runs. Preview reads existing pins when present and does not register a new run. Preserve existing validation, deferred-record, source occurrence, quality-report and failure behavior.

## Runtime fingerprints and transition

The current fingerprint is an explicit file-byte list, not automatic import traversal. Replace the CLI dependency with execution and connection code; include the moved implementation's relevant semantic dependencies. Check that the worker no longer imports connection or execution behavior through CLI code.

A command-presentation-only edit must leave the merge fingerprint unchanged; a change to execution or restricted-role connection behavior must change it. Preserve runtime mismatch rejection. The refactor itself changes the fingerprint; an in-flight run needs its pinned runtime to finish. Do not relabel changed code with an old digest.

Complete executable/dependency reproducibility remains the separately tracked P1 work in TODOS.md. This scoped extraction does not claim to close it or expand source-readiness dependency pins beyond their existing contract.

## Implementation sequence

1. Establish explicit expected-answer checks through the execution seam, retaining the existing PostgreSQL behavioral tests.
2. Extract connection setup and update its real consumers, preserving restricted-role selection and engine disposal ownership.
3. Move manifest/batch execution and mapping pins; move complete-execution progression and no-progress detection out of the worker. Keep bounded execution and preview available at the same module seam.
4. Update the merge runtime file list and tests, remove obsolete internal helpers when all consumers are migrated, and verify no production runtime import points back to CLI execution.
5. Review Standards, Spec and GoF separately; keep ordinary functions and existing Store/RunCoordinator rather than adding a framework.

## Proof required before implementation is called complete

- Same expected committed batches, receipts, checkpoints and quality reports for complete and bounded execution.
- Stop between batches, change a registered mapping, resume and verify original mapping versions; a new run uses the new version.
- Preserve single-batch preview, stage ordering, duplicate handling and explicit no-progress errors.
- Lost acknowledgement/retry produces no repeated effect; forged receipts are refused by independent read-only verification; expired destination authority is refused.
- Command-only changes do not alter the merge fingerprint; execution and connection behavior changes do.
- Preserve tests for source digest/path confinement, deferred evidence and occurrences.
- Use affected tests with testmon; each local invocation stays below five minutes. PostgreSQL proofs use an isolated test environment, protecting the shared development stores. Required CI remains intact.

Existing evidence anchors: `tests/integration/test_clean_run_pins_postgres.py`, `tests/integration/test_mdm_merge_worker_postgres.py`, `tests/integration/test_configured_bookkeeping_postgres.py`, `tests/mdm/test_clean_quality.py`, and `tests/unit/test_mdm_worker_artifacts.py`. Inspect the current assertions when updating imports; do not replace PostgreSQL acceptance with mocks or frozen retired-code oracles.

## Status

Design decisions agreed. No source changes, test execution, qualification, deployment or merge has occurred. Learning → skill: none yet; assess skill changes against the implemented behavior and proof.
