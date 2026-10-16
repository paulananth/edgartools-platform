<!-- /autoplan restore point: /Users/aneenaananth/.gstack/projects/paulananth-edgartools-platform/codex-bookkeeping-p2-measurement-autoplan-autoplan-restore-20261015-210600.md -->
# Bookkeeping P2 measurement harness

Status: intake for /autoplan; not approved or implemented.
Baseline: `origin/main` at `8ed547ab`, 2026-10-15 ET.

## Problem and decision this enables

An approved P2 design already exists at
`../bookkeeping-p2-autoplan/PLAN.md` (PR #977). Its runtime work is unstarted.
This smaller plan makes the current control cost reproducible before changing it:
how much does work on K selected units and D dependencies grow as unrelated work N
and undelivered journal backlog B grow? Which cost is validation, destination work,
PostgreSQL round trips or process startup? A baseline is evidence for a later fix,
not a fix, a performance improvement, or domain/source qualification.

## User boundary and ownership

User selected the measurement harness after a live coordination review. Keep every
production module, source rule, skill and existing test unchanged. Claude owns
N-PORT/OpenFIGI onboarding, Rust primitives, test cleanup and existing proof work.
Only new harness/test files and this private workstream's planning files are candidates.
No edits to `tests/integration/test_configured_bookkeeping_postgres.py`, shared
fixtures, `edgar_warehouse/bookkeeping/clean/engine.py`, database grants or migrations.
Recheck open PRs/worktrees and run overlap guard before each commit and push.
Use synthetic data only, no provider calls, no cloud service, no shared databases.

## Proposed deliverable

A standalone repository benchmark script, not a new warehouse command or service:
`uv run python scripts/benchmarks/benchmark_bookkeeping_control.py`.
It runs unchanged Bookkeeping/Rules/Journal code against disposable PostgreSQL 16,
separate restricted runtime and verifier roles, temporary immutable artifacts and
invented records. Reuse `tests/support/pg16.py`, migrations and public methods;
do not import fixtures from another test module or copy the entire acceptance suite.
No arbitrary database-address flag. Fail before mutation if ambient database
variables or a non-owned server could be selected. Clean up only resources this
invocation created; every subprocess and the whole run has a deadline under five
minutes. Report interrupted/incomplete runs explicitly and retain usable partial data.

Tentative implementation files (maximum four code/test files):
- `scripts/benchmarks/benchmark_bookkeeping_control.py`: CLI, ownership/lifecycle,
  fixture construction, unchanged protocol execution, report and comparison.
- `tests/unit/test_bookkeeping_control_benchmark.py`: report, validation and lifecycle
  failure tests without Docker.
- `tests/integration/test_bookkeeping_control_cost_postgres.py`: real PostgreSQL 16
  smoke, role separation and measured operation/correctness checks.
- A small new helper beside the script only if independent reviewers justify it.

## Workloads and measurements to specify during review

Exercise frozen-work read/selection, tasks+claim+envelope, renew, report,
verifier admission, delivery+retry and full check/finalize. Independent units,
fixed dependency closures, generated work and journal backlog must be distinguished.
Smoke uses small inputs; larger N is opt-in with a deadline and a declared case
matrix. Never stop the runtime by adding workload size refusals. Workload sizing
and test deadlines bound the experiment, not production work.

Record wall-clock nanoseconds, SQL statements, rows returned, `_frozen`/artifact
reads, selected K and dependency closure D, N, backlog B, process mode and runtime
fingerprints. Rows returned are not rows visited by the database. Run untimed
instrumented diagnostics separately from plain timed trials, and keep setup,
migration, instrumentation and command startup costs distinct. A fresh process
runs the actual CLI entry point when reporting subprocess results; an in-process
result is labeled as such. No speedup or asymptotic pass/fail claim from wall time
alone. State correctness and expected outcome are checked for every case.

## Output and acceptance

Emit a versioned JSON report plus a short plain-language summary, with only
allowlisted metadata and counts. Do not log SQL parameters, exception text,
connection strings, environment values or source records. Missing requirements,
failed assertions, incompatible comparisons, timeouts and expected protocol
refusals have distinct outcomes. A report states complete/incomplete explicitly.
Successful reruns with the same fingerprint give comparable measurements; different
code/database/fixture/protocol fingerprints refuse automatic speedup comparison.

Acceptance requires real restricted-role PostgreSQL evidence, a subprocess smoke
through unchanged entry points, deterministic metric classification fixtures,
correct duplicate-delivery and failure outcomes, no leaked child/container after
normal exit or cancellation, no interaction with Claude's resources, and a report
that never converts a missing/incomplete measurement into success.

## NOT in scope

- P2 runtime audit reuse, admitted scope or per-unit validation (future deliveries A/B/C).
- Changes to retained Bookkeeping bounds, generated ordinals or sampling policy.
- Database migrations, grants redesign, cache changes or alternate control schema.
- Shared test cleanup, new generic helpers in shared support, or changing profiles.
- AWS/hosted performance claims, installed source cutover or live source requests.
- CI workflow edits, scheduled benchmarks, dashboards or hard timing gates.

## Existing evidence to refresh, not reuse as current proof

The prior P2 research counted repeated scans; the accepted plan has 28 qualification
areas and seven future tasks. Inspect current engine `_frozen`, `renew`, `finalize`,
`deliver`, CLI routing, generated-work handling and test support before choosing
individual cases. Code inspection establishes proposed instrumentation seams only;
implementation tests will establish behavior. No measurement has run in this slice.

## Review sequence

CEO SELECTIVE EXPANSION, no UI design review, DX POLISH, engineering last.
Independent Claude and Codex voices run sequentially per phase. Scope challenges
are queued for the final gate. Every phase writes its findings, registries,
decisions and task artifacts before the next begins.
