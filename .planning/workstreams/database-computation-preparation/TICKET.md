# Database computation and publication preparation

Status: in progress, Codex; starting main 7f1e8856.

Operator: qualify moving pure transformations and payload preparation into
programs; retain indexed retrieval and transaction/concurrency enforcement.
Configured core computation belongs in Rust, callers/custom code in Python.

## Parts

- [x] Inventory active SQL computation/callers, inspect history and GoF design, and check ownership. DECISIONS.md records callers/history; existing facade/function seams retained; dedicated worktree and guards pass; 2026-10-11 20:44 ET.
- [ ] Implement exact PostgreSQL JSONB serialization in the Rust core behind the Python facade; qualify SQL byte/hash parity, numeric/Unicode boundaries and explicit limits.
- [x] Move active outbox publication payload reconstruction and verification into programs using immutable indexed inputs, preserving existing payloads and all hashes. Initial 1,010 exact SQL/native comparisons and 17 public/compatibility cases pass; live program callers inspected; 2026-10-11 20:38 ET.
- [ ] Add a checksummed additive migration and compatible claim APIs, preserving generation order, restricted roles, stale/expired fences, atomic intent and lost-ack recovery.
- [x] Assess remaining database transformations and record explicit migrate/retain decisions with evidence and prerequisites; do not imply unsupported ports are delivered. DECISIONS.md identifies indexed retrieval, integrity checks and state-dependent transitions; 1,019 affected maintained tests including those retained paths pass; no Snowflake replacement qualification claimed; 2026-10-11 20:46 ET.
- [ ] Compare bounded old/new preparation and full publication paths, transfer, SQL calls and memory; record acceptance and measured tradeoffs.
- [x] Update architecture/skill guidance only where implemented behavior changes; verify affected commands/examples and runtime identity. Guard passes; skill validator passes; doctor resolves all 131 commands, native engine loads; publication runtime pins adapter/facade/binary; 2026-10-11 20:44 ET.
- [ ] Run maintained affected tests and real PostgreSQL 16 upgrade, concurrency and recovery acceptance.
- [ ] Review Standards, Spec and GoF independently; resolve findings.
- [ ] Guard, commit, publish PR, verify CI, merge and report exact delivery with no deployment claim.
- [ ] Preserve publication's original byte domain by deriving the native output budget from immutable stored parts, including JSONB numeric expansion beyond compact request size.
- [ ] Rebase onto freshly fetched main after Claude's profiling PR #923, preserving both workstreams and rechecking changed upstream tests.

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
