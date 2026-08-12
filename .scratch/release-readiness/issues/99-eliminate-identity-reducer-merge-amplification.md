# Eliminate Identity-Reducer Merge Amplification

Type: task
Status: open
Blocked by: none

**2026-08-11 recovery note:** this ticket was designed and written 2026-08-01 by a
Codex session, preserved via a `claude-handoff` stash rather than landed, and is
being landed here 10 days later. Its `Status: resolved` in the original stash
reflected the *design* being decided, not the implementation existing in the
codebase — no code from the "Merge and hydration boundary" / "Streaming staging
and conditional promotion" sections below was ever applied; verified via source
inspection (`silver_protection.py` has no `merge_candidates_into_canonical`,
`StorageLocation` has no `download_verified_file`/`write_staged_file`/
`promote_staged_file`). Corrected to `open` accordingly.

**Partial overlap with [ticket 76](76-fix-reduce-identity-refresh-double-fetch.md)
(resolved 2026-08-03, after this ticket was written):** ticket 76 already fixed
the "downloads each input again during merge" half of the amplification this
ticket describes below — `reduce_identity_refresh` now reads each reference/delta
object from storage exactly once per call (not twice), via an in-memory
`dict[relative_path, bytes]` captured during the pre-loop verification pass. That
is a strictly narrower fix than what this ticket proposes: it removes the
*duplicate read*, but the four separate full-canonical-DB copies (one per
`merge_candidate_into_canonical` invocation — reference + 3 deltas) and the
in-memory-bytes staging/promotion path described below are still live on `main`
as of this note. The single-ordered-merge-session redesign and the streaming
`StorageLocation` file APIs remain the real, unimplemented core of this ticket.

## Question

How should `reduce-identity-refresh` consume one verified reference snapshot and
all ordered batch deltas in a single bounded canonical merge so each immutable
input is downloaded/checksummed once and the 1.07 GB canonical database is not
copied once per candidate?

The implementation must preserve ticket 58's fail-closed contract: exact
run/image binding, complete declared batch coverage, deterministic manifest
order, per-input checksum verification, existing protected-table conflict
semantics, reducer-only retry after an ETag conflict, and exactly one canonical
promotion. It must also emit bounded phase progress and timings for manifest
validation, input download/checksum, baseline hydration, each logical input
merge, staging, and promotion without reverting to noisy per-record logs.

Use `/gof-refactor-reviewer` and code history before modifying the merge
boundary, then `/tdd` and `/code-review`. Regression and representative-DuckDB
tests must prove semantic equivalence to sequential merging, one read per
immutable input per attempt, one full canonical copy per attempt, bounded
memory/disk use, and operator-visible progress. Production acceptance compares
reducer duration and bytes/read-copy amplification against corrected run
`daily-rc-81c0e04168fb-20260801T141043Z`.

## Answer (2026-08-01)

Keep the run-scoped reducer and its one-promotion contract, but replace the
current bytes-in-memory, one-candidate-at-a-time execution with a **single
ordered local merge session**. This is an algorithmic refactor, not a new GoF
pattern: history shows repeated correctness repairs inside the merge primitive,
but no stable family of interchangeable algorithms or workflow variants that
would justify Strategy, Template Method, or another abstraction. Preserve
`merge_candidate_into_canonical(...)` as a one-input compatibility wrapper over
the new engine.

### Merge and hydration boundary

Add `merge_candidates_into_canonical(candidate_paths, canonical_path,
output_path, progress_callback=None)` in `silver_protection.py`:

1. Copy canonical to `output_path` exactly once.
2. Open one bounded DuckDB connection and attach the output once.
3. Attach each verified candidate read-only in manifest order, run the existing
   unclassified-table, schema-evolution, conflict-resolution, and protected-row
   logic against the output's *current* state, then detach it before proceeding.
4. Aggregate the existing `MergeResult` counts per logical input. A failure in
   any input aborts the session and makes no canonical publication.

Extract only the already-tested attached-candidate merge body; do not rewrite
the table policies or conflict rules. Ordered processing is essential because
each later candidate must see schema and rows introduced by earlier candidates,
exactly as it does today.

At reducer startup, validate the small manifest/outcome JSON objects, then
stream the reference snapshot and every declared delta to distinct local files
while computing SHA-256. A checksum mismatch deletes/rejects that local file
and fails before the merge. Keep these immutable, verified local inputs for the
life of the reducer task. On an ETag conflict, download only the new canonical
baseline and rerun the local merge; do not download the unchanged run-bound
inputs again. This is stricter than the original one-read-per-input-per-attempt
target and does not weaken run/image binding because the retained files were
verified against the immutable manifest.

Hydrate canonical once per attempt into a local baseline file and pass the
verified inputs to the multi-candidate engine. If canonical does not yet exist,
use the verified reference as the baseline and merge only the deltas, preserving
the existing first-publication behavior.

### Streaming staging and conditional promotion

Extend `StorageLocation` with file-oriented counterparts to the current byte
APIs:

- `download_verified_file(...)` streams storage to a local path and returns
  byte count plus SHA-256;
- `write_staged_file(...)` uses the existing streaming `upload_file(...)` under
  a fresh `_staging/<uuid>/...` key; and
- `promote_staged_file(..., local_source_path=...)` performs the canonical S3
  `PutObject` from the same seekable local file with the existing destination
  `If-Match`/`If-None-Match` precondition.

The installed S3 service model declares `PutObject.Body` streaming and supports
both `IfMatch` and `IfNoneMatch`, so promotion need not download the staged
object back into memory. The immutable staged object remains available for
audit/recovery. Before promotion, verify that the staged upload and local source
represent the same known SHA-256/size; retain the current preflight ETag check
for a clear diagnostic, but treat the conditional `PutObject` as the atomic
lost-update guard. Keep the byte APIs as compatibility wrappers for other
callers.

### Bounded progress contract

Emit structured, phase-level summaries rather than per-row messages:

- manifest validated: run/image identity and declared input count;
- immutable inputs hydrated: input index/count, label, bytes, checksum result,
  phase and cumulative duration;
- canonical baseline hydrated: attempt, ETag, bytes, duration;
- logical input merged: index/count, label, tables and aggregate row counts,
  duration;
- staging completed: bytes, SHA-256, staged key, duration; and
- promotion completed or conflicted: attempt, baseline/result ETag, duration.

This is at most a small constant plus two events per declared input and one set
per reducer retry. It makes forward progress and an internal stall
distinguishable without returning to record-level CloudWatch churn.

### Proof and expected effect

Before changing the implementation, retain the existing merge suite as
characterization coverage and add representative DuckDB tests that compare the
new multi-input result by semantic content with today's sequential merge for
inserts, authoritative updates, unchanged rows, additive schema, ambiguous
conflicts, unclassified tables, and a later candidate consuming an earlier
candidate's schema/rows. Add spies proving one canonical copy per attempt, one
immutable download per reducer invocation (including an ETag-conflict retry),
one canonical promotion on success, no promotion on any merge/checksum failure,
bounded temporary-file cleanup, and ordered progress events.

For the corrected run's measured objects, the current code performs 3.483 GB of
explicit S3 downloads before staging and another hidden 1.071 GB staged-object
download during promotion: 4.555 GB total. The proposed path downloads the
1.206 GB immutable input set once and the 1.071 GB canonical once: 2.277 GB on
the first attempt, a 50% reduction versus the actual current path. Full local
canonical copying falls from 4.286 GB (four copies) to 1.071 GB (one copy), a
75% reduction. Upload bytes and immutable staging semantics remain unchanged.
These are deterministic byte-amplification reductions, not a promised runtime
speedup; the next immutable-image full-chain run must record phase timings,
peak local disk/memory, S3 bytes, reducer duration, and its terminal result
before ticket 61 or the six-hour schedule gate can close.
