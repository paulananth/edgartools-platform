# MDM resumable execution module

Type: task
Status: claimed

Implement the operator's [agreed design](../spec.md). The implementation base
is `5e1061ec4` from refreshed `origin/main`; the architecture review used
`66ab7b43`. Work belongs to `codex/mdm-execution-module-20261017` in its own
worktree. No deployment, shared-store mutation or merge is part of this ticket.

## Parts

- [x] Verify live ownership, affected callers and GoF consultation before code changes — fresh worktree at `5e1061ec4`, caller/history inspection, merged #1037 head verified clean, overlap guard passed (2026-10-17 14:33 ET).
- [x] Establish a failing behavioral check at the agreed execution/fingerprint seam — CLI edit changed the merge digest (1 failure); complete execution refused the new Store-only interface (1 failure); unpinned matching implementation change left digest unchanged (1 failure) (2026-10-17 14:33 ET).
- [x] Extract shared connection setup and update its real consumers — CLI/context/worker imports updated; real PG16 role-selection checks pass (2026-10-17 14:33 ET).
- [x] Move manifest validation, batch reading and mapping pins into execution; own complete progression, bounded execution and atomic preview — 77 focused cases passed, followed by 11 selected PostgreSQL/runtime cases including new modes and worker recovery (2026-10-17 14:33 ET).
- [x] Remove worker orchestration and CLI runtime coupling; audit scoped fingerprint dependencies — worker calls execution once; fingerprint checks pass for CLI independence and execution/connection/matching changes (2026-10-17 14:33 ET).
- [x] Migrate committed diagnostic/proving script callers; retain historical measurements without rerunning captured source data — seven callers migrated and syntax-checked; no remaining Python import of moved CLI functions (2026-10-17 14:36 ET).
- [x] Preserve PostgreSQL behavior: mappings, stage order, replay, receipts, deferred evidence, quality reports and fencing — affected core/run/execution group: 70 passed in 20.03s; commands/quality/artifacts/worker/publication group: 156 passed in 32.93s (2026-10-17 14:36 ET).
- [x] Prove actual killed-worker recovery after one durable batch, with unchanged retry effects and independent receipt verification — real subprocess SIGKILL after one confirmed batch; same run resumes to two batches/checkpoints `[1, 1]`, stable retry receipt, independent reader verifies; worker file: 4 passed in 23.66s (2026-10-17 14:41 ET).
- [x] Run affected tests with testmon, each invocation under five minutes; preserve isolated PostgreSQL cleanup — affected groups 70 + 156 + 62 passed; installed proof 4 passed in 180.63s; worker recovery group 4 passed in 23.66s; scoped Pyright clean (2026-10-17 14:41 ET).
- [x] Review Standards, Spec and GoF; fix findings and document runtime transition — separate Standards/Spec agents and implementing-agent GoF review found no actionable issues; the added kill-proof test also received both independent reviews; see `review.md` (2026-10-17 14:40 ET).
- [ ] Commit, push and open a reviewable PR; run full CI with a deadline.
- [x] Learning → skill: none — existing MDM engineering guidance on pinning, batching, destination enforcement and isolated proofs remains accurate; command/operator workflows are unchanged. The implementation interface and one-time fingerprint transition are documented in the runtime responsibility map (2026-10-17 14:41 ET).

## GoF consultation

The present cost is concrete: `mdm_merge.runtime_files` includes all of
`clean/cli.py`, while the merge worker imports both connection setup and
execution from it. Command presentation edits change the pinned merge runtime.
Recent mapping-pin (#1037) and run-report (#968) fixes also span execution and
coordination. Use ordinary functions in a focused execution module; retain
Store, RunCoordinator and independent receipt verification. A general framework
or new hierarchy would add indirection without useful variation. The main
Facade liability is scope creep into transport, publication or database authority.

## Verification

Every local test invocation uses
`TESTMON_DATAFILE=~/.cache/edgartools/testmondata uv run --no-sync pytest --testmon`.
The final affected groups also use `--testmon-noselect` so their explicitly
named tests all execute. PostgreSQL proof uses `PG16_SERVER=docker` and fixtures
stop their isolated containers. No invocation has approached five minutes.

`uv run --no-sync --with pyright pyright` on execution, connections and the
merge worker: 0 errors, 0 warnings. Scoped fingerprint tests: CLI-only edits
leave the digest unchanged; execution, restricted-role connection setup and
matching implementation edits change it. Two type-check findings in the moved
dynamic JSON/module metadata were resolved without changing runtime semantics.

Existing full executable reproducibility work in TODOS.md is separate; this
ticket does not close it. Runtime transition is documented in
`docs/architecture/runtime-responsibilities.md`.

Installed proof at committed code `3a5c118f`: 4 passed in 180.63 seconds
(181.60 seconds for the deadline-controlled invocation), on configured Company,
raw Person, XML streaming recovery and configured GLEIF mapping/publication
recovery. The bundle was installed from this commit, outside the checkout, and
the checks used isolated PostgreSQL 16. Context/configured-mapping/runtime-pin
checks also passed: 62 cases in 5.30 seconds.

The isolated `uv sync --frozen --extra mdm --extra s3 --extra mdm-runtime`
completed in about 95 seconds. The local pgserver launcher then failed before
tests reached application code: macOS `shmget` exhausted the shared-memory
allocation. Disposable Docker PostgreSQL 16 was already available and is used
for proof, with fixture cleanup; no shared development database was changed.
