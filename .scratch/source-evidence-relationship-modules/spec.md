# Source Extract evidence and Relationship Interval ownership

Operator: implement both together. Base `1f1c55edc`; own branch/worktree `codex/source-evidence-relationship-modules-20261017`.

Source Extract follows [the discussed design](source-extract-spec.md). The operator's explicit implement instruction settles its final design confirmation.

## Relationship Interval calculation

Deepen the existing relationship projection interface to take prior relationship bodies by ID and reconcile observed starts after all existing temporal checks and ultimate-parent derivation. Preserve that exact order, results, reviews and stable IDs. Do not correct temporal semantics in this change. Existing `project` calls without stored history retain their behavior. The Merge Stage retains indexed reads, ownership filtering, scope, locks and atomic saves; it no longer calls a separate period-history patch.

Read prior rows once through existing scoped retrieval. Supply only relationship bodies to the calculation. Keep review handling and retirement outside it. No SQL/schema/rule changes, wider scope traversal or new framework. Projection is pure with respect to caller-supplied prior evidence; do not mutate stored input.

## Seams and proof

The pre-agreed Source Extract interface, source.read worker/verifier, Name Frequency publication, relationship projection and real Merge Stage are the test surfaces. Characterize stored observed starts against profile eligibility, hierarchy overlap/cycles, succession and derived ultimate parents before changing ownership. Retain Person stated/observed capacities, N-PORT quarter revisions, first-start PostgreSQL cases, identity merge/reversal, scoped reads, concurrency and recovery tests. Semantic fixes require separate evidence and scope.

GoF consult: changing partition/lookup evidence currently crosses private worker interfaces; stored-start retention changed Merge Stage and relationships together in #1023 after #771/#851. Plain functions and a small opened-extract object suffice. Costs: another stateful interface, lazy-validation/fingerprint regressions, and temporal-ordering regression risk. No hierarchy, performance claim or publication-policy movement.

No provider access, shared-store changes, deployment or merge is authorized by this implementation request. Use invented local fixtures and disposable PostgreSQL for disruptive acceptance tests. Full CI supplies broad-suite coverage; each affected local invocation stays below five minutes.
