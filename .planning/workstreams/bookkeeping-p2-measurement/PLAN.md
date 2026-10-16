<!-- /autoplan restore point: /Users/aneenaananth/.gstack/projects/paulananth-edgartools-platform/codex-bookkeeping-p2-measurement-autoplan-autoplan-restore-20261015-210600.md -->
# Bookkeeping P2 measurement harness

Status: CEO review completed; DX/engineering pending; not approved or implemented.
Baseline: `origin/main` at `8ed547ab`, 2026-10-15 ET.

## Problem and decision this enables

An approved P2 design already exists at
`../bookkeeping-p2-autoplan/PLAN.md` (PR #977). Its runtime work is unstarted.
This smaller plan makes the current control cost reproducible before changing it:
how much does work on K selected units and dependency closure D grow as total run size N, unrelated work U
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
No arbitrary database-address flag. Ignore/remove ambient database settings from child
environments and construct only invocation-owned addresses internally. Clean up only resources this
invocation created; every subprocess and the whole run has a deadline under five
minutes. Report interrupted/incomplete runs explicitly and retain usable partial data.

Tentative implementation files (maximum four code/test files):
- `scripts/benchmarks/benchmark_bookkeeping_control.py`: CLI, ownership/lifecycle,
  fixture construction, unchanged protocol execution, report and eligibility metadata.
- `tests/unit/test_bookkeeping_control_benchmark.py`: report, validation and lifecycle
  failure tests without Docker.
- `tests/integration/test_bookkeeping_control_cost_postgres.py`: real PostgreSQL 16
  smoke, role separation and measured operation/correctness checks.
- `scripts/benchmarks/bookkeeping_benchmark_support.py`: small owned, bounded PG16 lifecycle helper justified by the CEO review.

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
Successful reruns require matching experiment eligibility, not just matching code.
Separate normalized fixture identity from runtime identity. Preserve metadata for future
explicitly paired cross-revision comparison; this slice calculates no cross-revision speedup.

Acceptance requires real restricted-role PostgreSQL evidence, a subprocess smoke
through unchanged entry points, deterministic metric classification fixtures,
correct duplicate-delivery and failure outcomes, confirmed owned cleanup after
normal/cooperative cancellation (or explicit cleanup_unconfirmed failure), no
interaction with Claude's resources, and a report
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

The detailed experiment definitions and stopping rule are frozen in [CASE-MATRIX.md](CASE-MATRIX.md).

# Phase 1 — CEO review (SELECTIVE EXPANSION)

## Step 0A — Premise challenge

The operator selected a measurement harness, not the whole previously approved P2 optimization. That is the right immediate question: quantify where control cost grows before selecting an implementation. Reading `_frozen`, `renew`, `finalize` and `deliver` shows repeated validation paths; it does not establish their measured cost. No historical scan count is copied into a new result.

Three premises need correction in the intake. A code fingerprint must be allowed to differ in an explicitly labeled baseline/candidate comparison, otherwise the tool cannot assess the future fix. A five-minute experiment budget cannot guarantee a cold environment install or every requested matrix size; setup prerequisites and incomplete experiments must be separate. Finally, existing `pg16.server()` hides the Docker resource identity and runs Docker commands without timeouts, so it cannot by itself prove bounded cancellation and cleanup. These are harness contract corrections within the selected scope, not changes to the operator's runtime direction.

## Step 0B — What already exists

| Subproblem | Existing code | Reuse and boundary |
|---|---|---|
| PostgreSQL 16 address/readiness | `tests/support/pg16.py`: `IMAGE`, `Server`, `_ready` | Reuse constants/address shape; no shared edits. Use harness-owned bounded lifecycle where existing context cannot satisfy deadlines. |
| Three stores, migrations and grants | Existing Rules, Bookkeeping and Change Journal migration APIs; acceptance-test setup | Call migration/grant APIs; don't import another test module's fixture or duplicate its entire suite. |
| Rule approval | `tests/support/rules_approval.py` | Reuse frozen export/approval helper with invented rules. |
| Worker/verifier protocol | `tests/support/bookkeeping_protocol.py`: `complete`, `verification_report` | Reuse existing support where behavior matches; measured operation remains the actual method/CLI. |
| Frozen work, leases and receipts | `edgar_warehouse/bookkeeping/clean/engine.py` | Run unchanged. `_frozen` is a diagnostic counting seam, never a replacement validator. |
| CLI mapping | `edgar_warehouse/bookkeeping/clean/cli.py`, root `cli.main` | Claim CLI invokes `tasks`; finalize CLI includes delivery. Label these composite paths exactly. |
| P2 delivery design | Approved PR #977 plan and existing TODOs | Preserve audit/admitted/per-unit decisions and existing limits. This slice supplies baseline evidence only. |

## Step 0C — Dream state and delta

```text
CURRENT: inspected repeated validation; historical counts; no reproducible current baseline
    |
THIS PLAN: isolated PG16 + synthetic protocol fixtures -> timed trials + separate diagnostics
    |                                                   -> versioned, comparable evidence
12-MONTH IDEAL: proven P2 improvements + source-qualified workloads + operator-approved hosted proof
```

This plan leaves optimization, source qualification and deployment entirely unfinished. Its value is a reusable answer to whether measured control cost follows selected work K/dependencies D, total run work N, or delivery backlog B. Future performance work must preserve correctness and authority rather than merely reduce scan counts.

## Step 0C-bis — Alternatives

| Approach | Human / coding-agent estimate | Completeness | Risk and maintenance | Decision |
|---|---|---|---|---|
| Extend one existing acceptance test with counters | 1 day / 2–3h | Partial: reproducible counts, weak standalone lifecycle and CLI evidence | Overlaps Claude's existing test ownership; makes a correctness suite carry benchmark semantics | Reject for this slice. |
| New bounded harness and new tests, using existing stores/support | 2–3 days / 6–9h | Complete for the selected local synthetic baseline | Four new code/test files; explicit small lifecycle helper required | Recommend. |
| Adopt pgbench/pyperf or build a benchmark service | 3–5 days / 1–2 days | SQL-only pgbench misses Python control; pyperf calibration needs bounded integration; service adds unrelated infrastructure | New dependency or service does not remove protocol fixture work | Defer service; borrow measurement principles, add no dependency. |

The first two could both produce useful diagnostic counts. Dedicated files win because they avoid active ownership and make failure, process and report boundaries reviewable. Four files is a borderline-size taste choice, surfaced at the final gate.

## Step 0D — Expansion decisions

Accept within the harness: separate uninstrumented timings and instrumented diagnostic trials, explicit state reset, safe partial reports, comparison eligibility, and cancellation/cleanup proof. These are necessary to trust a measurement and introduce no runtime behavior change. Accept a fourth new harness-only lifecycle helper if it is needed to expose owned resource identity and bounded subprocess cleanup.

Reject a performance service, CI timings gate, production tracing, generalized fixture framework and runtime fast path. They either duplicate existing work or exceed this task. Add no new global TODO: broad P2 optimization and hosted qualification already have an owner and plan. No operator direction has been challenged.

## Step 0E — Temporal interrogation

Human hour 1 checks ownership and the existing support; agent estimate 20–30 minutes. Hours 2–3 define report/fixture/measurement semantics and bounded owned resources; agent 1–2h. Hours 4–5 build the operation cases and failure tests; agent 2–3h. Hour 6+ runs affected PostgreSQL proofs and examines reports, potentially another 2–3h agent time. These are planning estimates, not measured delivery times; each local proof run stays below five minutes, and large matrices are separate invocations.

## Step 0F — Mode

SELECTIVE EXPANSION: keep the complete measurement slice; accept only changes needed to make its evidence trustworthy. UI scope is absent: no screens, interactive views or frontend assets. CLI flags, machine reports and developer setup require DX review next.

## 1. Architecture

The harness owns resource lifecycle and synthetic setup; existing Rules owns approved configuration, Bookkeeping owns work and leases, and Change Journal owns append/verify evidence. Separate setup-owner, worker runtime, verifier and journal roles are used in their existing databases. Owner connections close before measured runtime operations, and denial tests must establish that a runtime is not silently operating as owner.

```text
harness parent (budget, safe report, resource IDs)
  -> owned PG16 supervisor -> Rules DB / Bookkeeping DB / Journal DB
  -> fixture builder -> frozen artifacts + approved synthetic Rules
  -> fresh operation child -> unchanged API or actual cli.main
  <- timed result OR separate diagnostic counts + correctness outcome
```

Happy path, empty selection, expected blocked protocol and execution failure are distinct cases. A run cannot move from incomplete to accepted just because it emitted some timings. Resource ownership must be explicit before cleanup, and no shared database address is accepted.

## 2. Errors and rescue

Unknown prerequisites are actionable setup failures, not successful skips. A protocol `Blocked` exception is expected only when the named fixture deliberately requests refusal; the same exception in a happy case fails the case. A general DB or process exception never becomes an expected refusal by matching its text.

| Method/boundary | Exception/result | Rescued? | Rescue action | Operator impact |
|---|---|---|---|---|
| Parse/preflight | `SystemExit`, `ValueError`, `FileNotFoundError` | Yes | Usage or stable prerequisite code; no mutation | Setup remedy shown; no benchmark success |
| Spawn/readiness | `CalledProcessError`, `TimeoutExpired`, `RuntimeError`, `DBAPIError` | Yes | Stop exact owned resource; record safe code | Incomplete/setup failure, no raw stderr |
| Fixture/migrations | `DBAPIError`, `Blocked`, `OSError` | Yes | Close stores, unwind owned resources | Failed setup; no timings treated as trials |
| Measured operation | `Blocked`, `ValueError`, `DBAPIError`, `AssertionError` | Yes | Match only declared outcome; retain safe counts | Case fail or explicit expected refusal |
| Child/deadline | `TimeoutExpired`, abnormal return, `KeyboardInterrupt`, SIGTERM | Yes | Cancel process group, allow cleanup budget, mark incomplete | No speedup; partial report preserved |
| Report write | `OSError`, invalid JSON/schema | Yes | Atomic replace only after schema validation; safe terminal code | Failure; never overwrite a good baseline silently |
| Cleanup | subprocess failure/timeout, `OSError` | Yes | Retry bounded exact resource; `cleanup_unconfirmed` if needed | Nonzero exit and exact owned-ID recovery advice |
| Eligibility metadata | `ValueError`, inconsistent dimensions/schema | Yes | Reject invalid internal case/report data | No accepted sample until corrected |

## 3. Security and authority

There is no provider, AWS, hosted database or general SQL input. An invocation creates its own PostgreSQL server and uses only internally constructed addresses; ambient database settings are ignored/removed from child environments rather than printed or used. Docker control itself is a privileged local capability already used by the existing acceptance support, so the harness exposes only fixed image and owned resource operations.

| Threat | Mitigation | Planned proof |
|---|---|---|
| Ambient production DSN | No address flag; allowlisted child env, internally assigned store addresses | Poison ambient variables and assert only owned endpoint is contacted |
| Owner authority leaks into timing | Separate engines/roles; dispose owner setup engines | Runtime write-denial + distinct user/current-role checks |
| SQL/record/secret values enter reports | Allowlist categorical codes, counts and fingerprints; no raw SQL/exception/stdout | Canary-sensitive values across every failure emitter |
| Cleanup touches Claude resources | Exact created container ID + invocation nonce; no prune/prefix deletion | Foreign-resource sentinel survives all cleanup paths |
| Invalid report values | Schema/type/finite-number validation; no raw object serialization | Invalid schema, NaN and unexpected fields rejected |

## 4. Data flow and edge cases

```text
fixture spec -> approved rules + immutable inputs -> correct pre-state
   -> timed operation -> post-state assertion -> timing sample
   -> equivalent fresh pre-state -> diagnostic operation -> count sample
samples + case outcomes + environment -> validated allowlist -> atomic JSON + text
```

Do not reuse a mutated state between trials. Claims lease units, reports advance state, delivery drains backlog and finalize can compact a run; each needs fresh equivalent preconditions outside the operation timer. Generated work is sealed through the existing public protocol and its actual final N/ordinals are recorded. Duplicate delivery is tested as a distinct retry fixture; the initial delivery and retry cannot be pooled as identical timing samples.

## 5. Code quality and GoF

Review of engine history and support shape favors plain functions and a context manager with an explicit owned-resource record. There is no evidence for a Strategy/Observer hierarchy, plug-in framework or production refactor. Keep lifecycle in a small optional sibling helper and report/spec/operation orchestration in the main script; never copy all acceptance-test configuration or alter existing shared helpers.

Use business-facing names such as selected units, dependency closure, run size and journal backlog. Private `_frozen` and artifact access instrumentation is a reversible diagnostic hook scoped to one child; detach it in `finally` and never patch validation results. Source-contract Rust and Python module fingerprints describe the actual imported code, not merely the current checkout.

## 6. Tests and evals

```text
CLI parse -> preflight -> owner create -> migrate/roles -> fixture
  -> [timed | diagnostic] -> [success | expected refusal | failure | deadline]
  -> schema/privacy -> [comparable | incompatible] -> owned cleanup
```

Every branch above needs a meaningful test. Unit tests exercise schema, eligibility metadata, timing/diagnostic separation and lifecycle error handling. New PostgreSQL tests prove current migrations, restricted-role transitions, successful operations, refusal, duplicate retry and cleanup with real stores; no mocks substitute for that evidence. Fresh CLI child tests confirm root entry-point routing and exit semantics. The harness contains no LLM prompts/runtime behavior, so model eval suites are inapplicable; reviewer prompts are process artifacts only.

## 7. Performance

Wall time uses a monotonic nanosecond counter and reports raw samples, median and range with repeat count, without confidence claims for tiny samples. SQL statement counts describe client-executed statements; rows returned describe materialized rows, not PostgreSQL rows visited or statements nested inside database functions. `_frozen` call counts and artifact loads are a separate diagnostic pass. Startup, setup, migration and cleanup are separate phase durations.

Vary one of N/K/D/B at a time against a reference case; preserve other fixture dimensions. Do not infer a complexity class or an improvement from noisy laptop timing. In-process isolation and fresh CLI process modes are separate case IDs; CLI finalize includes delivery, so its number cannot be relabeled as method-only finalize.

## 8. Observability

Each requested case is represented even if setup or the deadline prevents it. Required fields include report version, harness/fixture/runtime hashes, operation/profile, process mode, intended/actual dimensions, expected/actual outcomes, raw timing samples, diagnostic availability and cleanup status. The summary tells an operator what was measured and what remains unknown; missing diagnostics are null with a reason, never a fabricated zero.

Reports contain invented fixture metadata and counts only. Capture child logs privately during execution and transform only allowlisted codes into the report; never echo raw exception chains or database addresses. Preserve partial results atomically before final cleanup so a failure can still leave useful evidence.

## 9. Deployment and rollback

```text
fresh own worktree -> prerequisite check -> owned local PG16 -> proof -> report -> stop owned PG16
rollback: stop child -> stop owned container by ID -> remove owned temp artifacts -> keep safe report
```

There is no deployment, migration of shared stores or feature switch. The current branch changes planning only; future implementation uses a fresh branch because used/merged ticket branches cannot be continued. A completed normal/error/SIGTERM path must confirm cleanup; SIGKILL/host loss cannot be guaranteed by Python and must yield an unfinished run marker with manual owned-resource recovery, never a false clean result.

## 10. Future trajectory

Use one versioned report contract so a future runtime change can supply a labeled candidate report. The following cross-revision contract is future work, not a calculator or report-ingestion feature in this slice. Automatic comparison requires the same harness/fixture/protocol, workload, process mode, outcome and comparable environment; a different source revision is allowed only as an explicitly recorded variant. This avoids both comparing unrelated experiments and forbidding the intended before/after code comparison.

Reversibility is 5/5: remove the standalone new harness/tests without changing production behavior. The remaining debt is intentional: synthetic fixtures do not prove source-specific processing, hosted latency, production distributions or P2 runtime correctness. Those stay in the existing approved work, with no new duplicate TODO.

## 11. Design scope

No UI assets, screens or frontend behavior are changed. The artifact is terminal/JSON developer tooling, reviewed in DX next; visual design review is skipped with that reason.

## Failure Modes Registry

| Codepath | Failure mode | Rescued? | Planned test? | User sees | Logged safely? |
|---|---|---|---|---|---|
| Preflight | Missing image/native/dependencies | Yes | Yes | Actionable setup failure | Yes |
| Setup | Wrong role or incomplete migration | Yes | Yes, real PG16 | Failure; no valid sample | Yes |
| Trial state | Warm mutated fixture reused | Yes, assert pre-state | Yes | Case failure | Yes |
| Instrumentation | Counters alter timed trial | Yes, isolated passes | Yes | Distinct/missing diagnostics | Yes |
| Protocol | Unexpected refusal mislabeled success | Yes | Yes, real PG16 | Failure | Yes |
| Eligibility | Inconsistent case dimensions | Yes | Yes | Invalid cell, no accepted summary | Yes |
| Deadline | Child or Docker call hangs | Yes, supervisor budget | Yes | Incomplete | Yes |
| Cleanup | Owned resource persists | Yes, explicit unresolved status | Yes | cleanup_unconfirmed, nonzero | Yes |
| Report | Sensitive data or truncated write | Yes, allowlist/atomic replace | Yes | Safe failure | Yes |

These are design resolutions and planned tests, not passing behavior evidence. No silent/unmapped critical gap remains in the design; implementation proof is pending.

## NOT in scope

The eight exclusions in the intake stand: runtime P2 fast paths; retained bounds/sampling/ordinals; shared schema/grants/caches; Claude's tests and source work; provider/hosted qualification; AWS rollout; CI timing gates; benchmark service or generic profiling framework. New runtime findings are recorded for the existing P2 owner instead of silently expanding this ticket.

## Required diagrams and stale-diagram audit

System, data, state/error, local execution and rollback diagrams are above. State is `requested -> setup -> ready -> running -> complete|failed|incomplete -> cleanup_confirmed|cleanup_unconfirmed`; reporting never upgrades an incomplete state. No existing file containing an architecture diagram is touched. New diagrams describe the proposed harness only, and must be checked against implementation before claiming they represent shipped behavior.

## Implementation Tasks (CEO)

- [ ] **C1 (P1, human: 4h / coding agent: 1h)** — lifecycle — Bound and identify every owned local resource; prove cooperative cancellation and report unconfirmed cleanup.
- [ ] **C2 (P1, human: 4h / coding agent: 1h)** — evidence contract — Separate fixture state, timing, diagnostics and comparison eligibility in a versioned counts-only report.

- [ ] **Learning → skill** — record the skill line changed, or none; check only after actual verification and an ET clock read.

Verification: future new unit and PostgreSQL lifecycle/report tests. File ownership: new main script, optional new sibling helper, new unit and integration modules only. Other sections add no independent implementation tasks; they refine these two contracts.

## CEO completion summary

| Required field | Result |
|---|---|
| Mode / System audit / Step 0 | SELECTIVE; current `_frozen`/renew/report/deliver/finalize and support inspected; three premise corrections above |
| Architecture | 2 findings: authority separation and ownership lifecycle |
| Errors | 8 boundaries mapped; 0 silent design gaps; behavior proof pending |
| Security | 5 threats; 0 unresolved high design findings |
| Data flow | 4 mutating-state/retry edge cases specified |
| Quality | 1 finding: avoid framework/shared-fixture duplication |
| Tests | Branch diagram written; all new code remains unimplemented |
| Performance | 3 findings: independent dimensions, instrumentation separation, truthful metric names |
| Observability | Case completeness and safe partial reports required |
| Deployment | Local only; SIGKILL limitation explicit |
| Future | Reversibility 5/5; runtime/source/hosted work remains outside this slice |
| Design | Skipped, no UI scope |
| NOT in scope / reuse / dream delta | Written above |
| Registries | 8 rescue boundaries, 9 failure paths, 0 silent design gaps |
| TODO / expansions | 0 new TODOs; 5 harness-completeness expansions accepted; unrelated expansion rejected |
| CEO plan / outside voices | Persist external CEO plan after voice reconciliation; voice results appended below |
| Lake score | 5/5 in-scope expansions choose complete evidence; no production expansion |
| Diagrams / stale diagrams | 6 applicable kinds represented; 0 existing diagrams touched |
| Unresolved | Four-file dedicated harness taste choice; final approval pending |

## CLAUDE SUBAGENT (CEO — strategic independence)

Actual Claude CLI model `claude-fable-5-1` exited 1: usage credits required.
No findings produced. Marked unavailable, not counted as agreement.
Private raw outputs remain outside the repository; no model was silently substituted.

## CODEX SAYS (CEO — strategy challenge)

Independent `gpt-6-astra` CLI review completed exit 0 in 87 seconds. Six concerns:
comparison fingerprints; bounded lifecycle/cleanup; underspecified workload dimensions;
metric attribution; mutated repetitions; missing stopping rule. All are plan gaps,
not objections to the operator's measurement-only direction. Resolutions are the
frozen case contract, separate diagnostics/fresh state, bounded owned lifecycle,
and baseline-only report metadata. Cross-revision calculation stays deferred.

## CEO DUAL VOICES — CONSENSUS TABLE

| Dimension | Claude | Codex | Consensus |
|---|---|---|---|
| Premises valid? | N/A | Three corrections | N/A, single-model |
| Right problem? | N/A | Baseline appropriate | N/A |
| Scope calibrated? | N/A | Freeze stopping rule | N/A |
| Alternatives explored? | N/A | Reuse support, avoid second qualification suite | N/A |
| Competitive risk? | N/A | Maintenance/compare usefulness is the risk | N/A |
| Six-month trajectory? | N/A | Preserve future comparison metadata | N/A |

0/6 dual-model confirmations; no fabricated consensus. Two taste choices:
four new files for isolation/bounded lifecycle; baseline metadata now with future
cross-revision calculation deferred. No user challenges.

<!-- AUTONOMOUS DECISION LOG -->
## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|---|---|---|---|---|---|
| D01 | CEO | Reuse store APIs/support, no shared edits | Mechanical | P4 | Avoid active Claude surface and duplicate suites | Editing existing acceptance test |
| D02 | CEO | Dedicated harness, up to four new code/test files | Taste | P1/P5 | Bounded owned lifecycle needs explicit resource IDs | Folding all lifecycle into existing tests |
| D03 | CEO | Fresh state for every timed/diagnostic observation | Mechanical | P1 | Claims/reports/admission/delivery mutate state | Repeating on one drained/completed run |
| D04 | CEO | Separate timings and diagnostics; name client metrics precisely | Mechanical | P5 | Counters cannot attribute all elapsed work | SQL counts as server scans/round-trip latency |
| D05 | CEO | Save comparison eligibility; defer cross-revision ratios | Taste | P3/P5 | Satisfies current baseline without generic comparator | Full before/after calculator now |
| D06 | CEO | Freeze case catalog, default smoke and incomplete outcomes | Mechanical | P1 | Finite deliverable without shrinking production scope | Unspecified full qualification project |
| D07 | CEO | Owned Docker supervisor with bounded calls and recovery identity | Mechanical | P1/P5 | Existing helper cannot guarantee deadline/cleanup | Unbounded helper behind an outer timer |
| D08 | CEO | Preserve limits/ordinals/sampling and broad P2 ownership | Mechanical | P4/P6 | Operator selected measurement, prior rulings stand | Runtime optimization/cap changes |
| D09 | CEO | No duplicate TODO or service | Mechanical | P3/P4 | Existing P2 plan owns deferred runtime work | New benchmark service/backlog copy |
| D10 | CEO | Claude unavailable; actual Codex independent voice retained | Mechanical | P6 | CLI credit failure, authorized degradation | Claiming two-model agreement |

## CEO spec review

Fresh spec reviewer found four contract ambiguities: N/U wording, metadata versus
comparison-file ingestion, unnamed correctness/CLI smoke cells, and the future
implementation checklist's Learning → skill item. All are corrected in the plan
and case contract before DX starts. Initial plan-quality scores: completeness 8,
consistency 7, clarity 8, scope 9, feasibility 8; these are not runtime scores.

CEO spec recheck: PASS; plan scores 9/9/9/9/8 (completeness/consistency/clarity/scope/feasibility). No runtime proof claimed.

## Technical references

Use integer monotonic elapsed observations; see [Python perf_counter_ns](https://docs.python.org/3.12/library/time.html#time.perf_counter_ns). Keep process/environment and samples explicit; [pyperf benchmarking guidance](https://pyperf.readthedocs.io/en/latest/run_benchmark.html) informs the design but introduces no new dependency. [PostgreSQL 16 pgbench](https://www.postgresql.org/docs/16/pgbench.html) supplies SQL workload benchmarking; it cannot measure the Python control path by itself. This is a design inference, not a measured comparison.
