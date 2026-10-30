# Complete Rules, Bookkeeping and Change Journal portability

Status: claimed by Codex; Rules implementation checkpoint, installed qualification and review pending; Bookkeeping remains incomplete.
Base: `7e8fd545b`; branch `codex/control-store-portability-20261029`.
Parent: [Platform portability](../platform-three-databases/01-migrate.md).

## Parts

- [x] Reconcile actual normal callers, existing selected-engine helpers, retained drafts and qualification evidence; preserve unrelated work — 2026-10-29 23:25 ET: live source/history and worktree inventory; Journal already has selected-engine storage, Rules and Bookkeeping still have normal-call gaps. Archived work and unrelated main changes preserved.
- [ ] Complete Rules owner migration and restricted agent/approval duties on PostgreSQL/MySQL with immutable historical migrations and populated recovery.
- [ ] Complete Rules normal save/version/proof/approval/activation/export on both engines; preserve immutable content, exact evidence and authorization against direct bypass and concurrency.
- [ ] Complete Bookkeeping normal initialization and worker/verifier grants on both engines.
- [ ] Complete Bookkeeping normal start/claim/heartbeat/report/verify/completion/checkpoint/generated-work/resume/finalize and destination authority/recovery on both engines; keep durable state enforcement authoritative at its destination.
- [ ] Verify and retain existing Change Journal selected-engine support and independent package; implement only demonstrated gaps in normal append/replay/read/receipt/delivery/migration/rights behavior.
- [ ] Qualify normal configured callers and installed workers/verifiers, migration/health commands, rollback/recovery, unchanged replay and populated upgrades; reuse applicable existing proofs.
- [ ] Review Standards, Spec and GoF; publish bounded implementation PRs and qualify final heads before merge.
- [ ] ~~Full SQL Server qualification~~ deferred until the PostgreSQL/MySQL gate; retain existing SQL Server adapter checks and Journal qualification.
- [x] Resolve Rules CLI overlap before editing that file — 2026-10-29 22:26 ET: operator explicitly assigned edgar_warehouse/rules/cli.py to Codex in this session; archived Claude work is preserved. The real guard continues to report that known overlap; no other overlap is authorized.
- [ ] Learning → skill: publish demonstrated reusable learning separately or record none.

## Settled scope and seams

The operator explicitly invoked implement for these three stores. Existing
platform scope requires one configuration-driven implementation, PostgreSQL/MySQL
first, SQL Server last. Test the already-agreed normal public CLI/store and
worker/verifier boundaries, not adapter helpers as a substitute. Use focused
red/green cases there and keep local invocations below five minutes; CI runs the
full suite. Current Change Journal qualification already covers three engines;
verify its current ordinary caller and preserve the proof instead of rewriting it.

Shared Rust/Python owns deterministic preparation; each database retains durable
storage, indexed reads, uniqueness, permissions, leases/fencing, current-state
validation and atomic transitions. Keep existing package/facade seams, configuration
pins and caller signatures. Database dialect details are storage concerns.
No source onboarding/activation, provider requests, hosted cutover or production
schema changes are authorized by this implementation task. Disruptive tests use
isolated test databases/roles, never the shared operational stores.

## Rules checkpoint (2026-10-29 23:25 ET)

The first bounded PR implements Rules only. Bookkeeping and the final cross-store
gate stay open below; this checkpoint does not claim the parent effort complete.

- [x] Normal lifecycle, CLI status, populated migration and actual selected-engine MDM reading reuse — PostgreSQL/MySQL normal-caller tests passed, 2026-10-29 23:25 ET.
- [x] Direct acquisition-proof bypass, immutable history/proof, stale approval evidence and concurrent activation — retained PostgreSQL approval tests plus new selected-engine negative tests passed, 2026-10-29 23:25 ET.
- [x] MySQL empty/populated interrupted migration recovery, cached runtime revocation, unknown migration version and invalid completion flag — ten MySQL cases passed; five PostgreSQL normal cases passed and five MySQL-only cases skipped explicitly, 2026-10-29 23:25 ET.
- [x] Retain current Journal qualification — nine normal Journal cases passed on each engine in combined runs (MySQL 18 passed; PostgreSQL 38 passed, five MySQL-only skips), 2026-10-29 23:25 ET. No Journal implementation change needed at this checkpoint.
- [ ] Qualify committed Rules CLI from the independently installed five-wheel bundle on both engines.
- [ ] Review Standards, Spec and GoF and publish the bounded Rules PR; final CI must pass before readiness.
- [ ] Learning → skill: document only demonstrated reusable installation/qualification changes, on a separate skill branch/PR.

## Initial GoF consult

Current Rules combines its normal facade with PostgreSQL text SQL. Bookkeeping
already has typed inspection/run-check/resume storage helpers, but its normal
owner install, grants and lifecycle still call PostgreSQL routines. Journal
already selects its normal storage adapter. Reuse those interfaces and native
control preparation rather than a parallel control engine, policy registry or
store hierarchy. Inspect each actual transition and race before changing it.
