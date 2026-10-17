# Source evidence and relationship calculation review

Fixed base: `1f1c55edc`. Initial implementation `845345d5`; installed proof extension `a46a405e`; Spec correction `4f953cd5`.

## Standards

Independent review and recheck found no remaining actionable issues. Dedicated Codex branch/worktree and overlap guards preserve parallel ownership. Bounded receipt/lookup handling, consumer publication and indexed/atomic destination duties remain intact. No schema, provider access, deployment or shared-store changes.

190 affected tests passed in 26.66s; 62 real PostgreSQL tests passed in 130.69s, including killed-worker recovery, first observed starts, N-PORT revisions, merge/reversal, indexed scope and transaction checks. After the identity-property correction, 93 affected cases passed in 6.63s. All invocations used testmon and a deadline below five minutes. The shared-cache foreign-key error was isolated with a worktree-specific cache without deleting the shared cache.

Pyright: source_read, source_readings and relationships are clean. Comparison against the same base shows exactly the same 12 pre-existing diagnostics in merge and name_frequency, with no new messages/rules. Complete runtime/dependency reproducibility remains a separately tracked concern.

## Spec

Independent initial review found one partial requirement: inspect a defensive copy of the reading identity before iteration. A missing-property test failed, the reading property was added, and the assertion plus the 93-case group passed. Independent recheck of 4f953cd5 found no remaining findings.

The module owns one authenticated private index, contract access, bounded lookup resolution and lazy ordered table events. Name Frequency retains exact recipe/full publication/count/population checks and final publication. Lookup version semantics and separate budgets remain unchanged; existing materializing/incremental loader differences survive.

Relationship projection takes stored bodies and reconciles observed starts after all existing temporal checks and ultimate-parent derivation. Six pre-refactor characterizations pin those interactions. The Merge Stage retains scoped prior retrieval, ownership filtering, review/retirement handling and atomic saves.

## GoF

The available gof-refactor-reviewer skill was applied before implementation and during root/independent review. No additional pattern is justified. The small opened-extract object owns real private state; Python generators supply iteration. The relationship function remains the calculation seam. Both improvements delete caller knowledge rather than add forwarding alone. Main liabilities are lazy-validation/fingerprint compatibility and temporal ordering; tests pin them. No speed or memory improvement is claimed.

## Qualification status

Installed-package proof passed from committed 4f953cd5 outside the checkout: 2 tests in 149.71s, including extraction/evidence and empty restricted-PG16 mastering/publication/recovery. Full CI is pending. Local tests are not deployment or full-population qualification. Existing runs must finish with their pinned runtime; changed reader and relationship code produce new fingerprints.

Reviewed 2026-10-17 19:55 ET.
