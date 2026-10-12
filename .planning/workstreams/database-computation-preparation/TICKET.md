# Database computation and publication preparation

Status: in progress, Codex; starting main 7f1e8856.

Operator: qualify moving pure transformations and payload preparation into
programs; retain indexed retrieval and transaction/concurrency enforcement.
Configured core computation belongs in Rust, callers/custom code in Python.

## Parts

- [x] Inventory active SQL computation/callers, inspect history and GoF design, and check ownership. DECISIONS.md records callers/history; existing facade/function seams retained; dedicated worktree and guards pass; 2026-10-11 20:44 ET.
- [x] Implement exact PostgreSQL JSONB serialization in the Rust core behind the Python facade; qualify SQL byte/hash parity, numeric/Unicode boundaries and explicit limits. Verified: Final byte binding and 1,010 SQL/native comparisons pass, including numeric/Unicode/deep nesting and bounds; 2026-10-12 08:01 ET.
- [x] Move active outbox publication payload reconstruction and verification into programs using immutable indexed inputs, preserving existing payloads and all hashes. Initial 1,010 exact SQL/native comparisons and 17 public/compatibility cases pass; live program callers inspected; 2026-10-11 20:38 ET.
- [x] Add a checksummed additive migration and compatible claim APIs, preserving generation order, restricted roles, stale/expired fences, atomic intent and lost-ack recovery. Verified: 20 real PG16 cases pass, including populated-015 upgrade, roles, mixed claims, fences and public lost-reply recovery; 2026-10-12 08:01 ET.
- [x] Assess remaining database transformations and record explicit migrate/retain decisions with evidence and prerequisites; do not imply unsupported ports are delivered. DECISIONS.md identifies indexed retrieval, integrity checks and state-dependent transitions; 1,019 affected maintained tests including those retained paths pass; no Snowflake replacement qualification claimed; 2026-10-11 20:46 ET.
- [x] Compare bounded old/new preparation and full publication paths, transfer, SQL calls and memory; record acceptance and measured tradeoffs. Verified: Fresh 200/600 artifacts pass all fixed limits; hashes and calculations independently reviewed; RESULTS.md records costs and limitations; 2026-10-12 08:01 ET.
- [x] Update architecture/skill guidance only where implemented behavior changes; verify affected commands/examples and runtime identity. Guard passes; skill validator passes; doctor resolves all 131 commands, native engine loads; publication runtime pins adapter/facade/binary; 2026-10-11 20:44 ET.
- [x] Run maintained affected tests and real PostgreSQL 16 upgrade, concurrency and recovery acceptance. Verified: 1,019 maintained initial tests, 110 post-rebase tests, 39 final byte-path tests and 20 final PG16 cases pass; installed final-head check tracked separately; 2026-10-12 08:01 ET.
- [x] Review Standards, Spec and GoF independently; resolve findings. Verified: All three independent final reviews clear; prior P2 evidence findings resolved and documented in REVIEW.md; 2026-10-12 08:01 ET.
- [ ] Guard, commit, publish PR, verify CI, merge and report exact delivery with no deployment claim.
- [x] Preserve publication's original byte domain by deriving the native output budget from immutable stored parts, including JSONB numeric expansion beyond compact request size. Verified: Authenticated stored-part budget and greater-than-64-MiB native publication test pass; 2026-10-12 08:01 ET.
- [x] Rebase onto freshly fetched main after Claude's profiling PR #923, preserving both workstreams and rechecking changed upstream tests. Verified: Conflict-free rebase onto #923 with identical range-diff; 110 affected/upstream tests pass; latest #924 synchronization tracked below; 2026-10-12 08:01 ET.
- [x] Resolve measured client-memory acceptance failure: 600-record export initially samples 1.526x SQL RSS; use UTF-8 bytes at the native hashing boundary and requalify against unchanged 1.5x limit. Verified: Final 600-record export client RSS 1.313x and journal 1.276x; both pass unchanged 1.5x limit; 2026-10-12 08:01 ET.
- [x] Prove public publication worker recovery after an injected lost acknowledgement following committed verification, with no resend and unchanged receipt; distinguish this from benchmark completed/no-work retry. Verified: 20 final PG16 cases include injected post-commit lost reply; retry/verify return unchanged receipt and sink sends once; 2026-10-12 08:01 ET.

- [x] Synchronize with latest Claude profiling PR #924 and verify its changed tests. Conflict-free rebase onto 7dd6f5ab preserves both implementation commits by range-diff; all 58 affected profiling tests pass; 2026-10-12 08:07 ET.
- [x] Install final committed byte-return runtime without checkout; verify publication helper, doctor and configured publication/recovery. All 3 installed checks at a9cb9938 pass; combined installed/upstream run: 61 passed in 6m07s; 2026-10-12 08:07 ET.

## Acceptance

Exact PostgreSQL JSONB text/hash parity on supported inputs; no change to batch
request hashes, immutable prior payloads, output semantics or authority.
Clients refuse reconstructed payloads differing from the database's committed
expected hash before publication. Existing SQL APIs remain compatible for
frozen runtimes. New publication APIs expose immutable inputs and lease proof;
the database still derives/enforces committed expected hashes, approvals,
freshness, generation/checkpoint progress and recovery. No SQL check is replaced
by trusting a worker-supplied hash.

Placement qualifies with exact semantic/recovery parity and acceptable bounded
full-path cost; a performance improvement is claimed only if measured.
Qualification covers local PostgreSQL 16, not deployment or live SEC access.

Final placement acceptance, fixed before the refreshed qualification: on each
200/600-record consumer sample, native median delivery + independent read-back
+ completed/no-work retry is at most 1.5x SQL, claim response bytes at most 1.1x, SQL
round trips unchanged, and separately sampled client/server RSS at most 1.5x.
These allow a bounded placement cost for program ownership; they are local
acceptance criteria, not a production speedup, physical-memory estimate or RSS
cap. The real journal adapter and its restricted append/read-back must run.

Lost acknowledgement recovery is tested separately by injecting a failure
after durable publication verification; the benchmark itself measures a
completed/no-work retry rather than injecting that failure.
