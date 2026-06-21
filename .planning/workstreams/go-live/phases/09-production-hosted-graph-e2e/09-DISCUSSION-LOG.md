# Phase 9: Production Hosted Graph E2E - Discussion Log

**Date:** 2026-06-21
**Mode:** Handoff-derived context

## Source

The user explicitly scoped Phase 9 after PR #80:

- Phase 8 is complete and merged; do not redo it.
- Phase 9 is the remaining piece of Blocker 4.
- Required work: Native App compute pool provisioning against prod, full graph
  sync/export test, `edgar-warehouse mdm verify-graph` as documented
  acceptance gate, and final launch-gate matrix reconciliation only after
  Phase 8 + Phase 9 proof exists.
- Critical safety constraint: any credential-rotating or credential-emitting
  command must run as one atomic pipeline into its non-printing consumer.

## Decisions Captured

### Phase 8 Boundary
- Phase 8 evidence is trusted as merged input. Phase 9 consumes existing
  secrets; it does not rotate or populate them.

### Native App Target
- Production target is `EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION`, Native App
  `Neo4j_Graph_Analytics`, database role
  `NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE`, and compute pool selector
  `CPU_X64_XS` unless live metadata requires an operator-approved alternative.

### Bounded Production Data
- Because Phase 8 counts were zero on the fresh `mdm` database, Phase 9 plans
  a bounded local MDM smoke before sync/verify if graph inputs are still empty.
  It never runs a full bootstrap or unbounded backfill by default.

### Acceptance
- Strict `edgar-warehouse mdm verify-graph` must pass locally with SQL parity
  and Native App `GRAPH_INFO`, `BFS`, and `WCC` checks before AWS E2E is treated
  as launch evidence.
- `run-aws-mdm-e2e.sh` must run with default preflight enabled. `--skip-preflight`
  is not Phase 9 acceptance evidence.

### Evidence
- Launch gate matrix PASS updates wait until both local strict verify and AWS
  MDM E2E pass. The matrix update references Phase 8 evidence and Phase 9
  evidence together.

## Deferred

- Legacy Neo4j runtime-remnant removal remains future work after production
  hosted graph validation is stable.

## No Interactive Questions Asked

The handoff provided locked operational constraints and acceptance gates. No
additional product/UX decision was needed before planning.
