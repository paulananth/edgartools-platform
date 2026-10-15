# Implementation tasks: Bookkeeping P2

Aggregated after verified rebase to `bebebcb2`, using latest phase task JSONL
for this branch and the last-five-commit window. Exact-match task deduplication
produced seven tasks. Original review provenance is retained in the JSONL records.
These overlap the same control modules: implement sequentially, A then B then C.
The list below is priority-sorted, not execution order: A starts with T1; B covers
T2 and T6's authority/bootstrap; C covers T3/T4/T5 and T6's enablement. T7 documents
and rehearses each delivery before that delivery is enabled.
Effort is provisional active work; large qualification trials add elapsed time.

- [ ] **T2 (P1, human: 2 days / CC: 3-4 hours) — admission** — Protect root and generated admission and freeze definitions
  - Surfaced by: ceo-review — Both CEO voices identified absent protected admission and forged SQL routes
  - Files: edgar_warehouse/bookkeeping/clean/engine.py, edgar_warehouse/bookkeeping/clean/database.py, edgar_warehouse/bookkeeping/clean/migrations/007_admitted_scope.sql, tests/integration/test_generated_bookkeeping_postgres.py, tests/integration/test_configured_bookkeeping_postgres.py
- [ ] **T4 (P1, human: 1 day / CC: 1-2 hours) — completion** — Qualify readiness and coherent terminal reconciliation
  - Surfaced by: ceo-review — Codex CEO bounded finalize can preserve quadratic audits; Claude warns redundant counter
  - Files: edgar_warehouse/bookkeeping/clean/engine.py, tests/integration/test_generated_bookkeeping_postgres.py, tests/integration/test_configured_bookkeeping_postgres.py
- [ ] **T6 (P1, human: 1 day / CC: 2-3 hours) — operator-interface** — Expose submission authority and safe validation controls
  - Surfaced by: devex-review — DX missing submitter bootstrap, mode visibility, full-audit tightening and actionable recovery
  - Files: edgar_warehouse/bookkeeping/clean/cli.py, edgar_warehouse/bookkeeping/clean/database.py, edgar_warehouse/bookkeeping/clean/engine.py, edgar_warehouse/rules/cli.py, tests/unit/test_configured_bookkeeping_contract.py, tests/integration/test_configured_bookkeeping_postgres.py, edgar_warehouse/workers/control.py
- [ ] **T3 (P2, human: 1 day / CC: 1-2 hours) — control** — Enable qualified per-unit validation contexts
  - Surfaced by: ceo-review — P2 unrelated-N scans remain after command-local reuse
  - Files: edgar_warehouse/bookkeeping/clean/engine.py, tests/integration/test_configured_bookkeeping_postgres.py
- [ ] **T1 (P2, human: 1 day / CC: 1-2 hours) — control** — Remove duplicate audits within each command
  - Surfaced by: ceo-review — CEO alternatives and duplicate journal_event construction
  - Files: edgar_warehouse/bookkeeping/clean/engine.py, tests/integration/test_configured_bookkeeping_postgres.py
- [ ] **T5 (P2, human: 1 day / CC: 2-3 hours) — qualification** — Measure complete control paths with fixed dependency closures
  - Surfaced by: ceo-review — Both CEO voices require full-process value gates and dependency/backlog workloads
  - Files: scripts/benchmarks/benchmark_bookkeeping_control.py, tests/integration/test_configured_bookkeeping_postgres.py, tests/integration/test_generated_bookkeeping_postgres.py
- [ ] **T7 (P2, human: 0.5 day / CC: 1 hour) — operator-docs** — Document and rehearse bounded setup upgrade and recovery
  - Surfaced by: devex-review — DX install journey, matched docs, cross-version drain and safe rollback
  - Files: docs/configured-capture.md, skills/bookkeeping/RUN.md, skills/bookkeeping/RECOVERY.md, README.md
