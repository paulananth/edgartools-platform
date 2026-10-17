<!-- /autoplan restore point: /Users/aneenaananth/.gstack/projects/paulananth-edgartools-platform/codex-bookkeeping-p2-measurement-autoplan-autoplan-restore-20261015-210600.md -->
# Bookkeeping P2 measurement harness

Status: APPROVED by the operator, 2026-10-16 08:54 ET. CEO, DX and final engineering reviews completed; implementation not started.
Code inspected at `8ed547ab`; planning branch rebased onto current `origin/main` at `3064a4e4`, 2026-10-16 ET. Since the review, Claude merged ticket bookkeeping and N-PORT onboarding. The inspected Bookkeeping/Rules/Journal runtime, shared support, targeted integration tests, CLI, pyproject and lockfile are unchanged; verified with a scoped Git diff before this final rebase.

## Problem and decision this enables

An approved P2 design already exists at
`../bookkeeping-p2-autoplan/PLAN.md` (PR #977). Its runtime work is unstarted.
This smaller plan makes the current control cost reproducible before changing it:
how much does work on K selected units and dependency closure D grow as total run size N, unrelated work U
and undelivered journal backlog B grow? Which observations identify repeated validation work, and which elapsed costs
remain unattributed? Record process startup separately. A baseline is evidence for a later fix,
not a fix, a performance improvement, or domain/source qualification.

## User boundary and ownership

User selected the measurement harness after a live coordination review. Keep every
production module, source rule, skill and existing test unchanged. Claude owns
N-PORT/OpenFIGI onboarding, Rust primitives, test cleanup and existing proof work.
Only new harness/test files and this dedicated workstream's planning files are candidates.
No edits to `tests/integration/test_configured_bookkeeping_postgres.py`, shared
fixtures, `edgar_warehouse/bookkeeping/clean/engine.py`, database grants or migrations.
Recheck open PRs/worktrees and run overlap guard before each commit and push.
Use synthetic data only, no provider calls, no cloud service, no shared databases.

## Proposed deliverable

A standalone repository benchmark script, not a new warehouse command or service:
`uv run --no-sync --offline python scripts/benchmarks/benchmark_bookkeeping_control.py`.
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

Record elapsed nanoseconds, application SQL executions, the explicitly partial
Bookkeeping _rows materialization subtotal, `_frozen`/base-artifact reads/bytes, selected K and dependency closure D, N, backlog B, process mode and runtime
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
failed assertions, invalid eligibility metadata, timeouts and expected protocol
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
| New main script with inline lifecycle + two new test modules (three files) | 3–4 days / 7–10h | Complete if the larger main script remains clear | Avoids ownership overlap; fewer files but lifecycle/report/fixture concerns share one module | Viable smaller alternative. |
| New bounded harness and new tests, using existing stores/support | 3–4 days / 7–10h | Complete for the selected local synthetic baseline | Four new code/test files; explicit small lifecycle helper required | Recommend. |
| Adopt pgbench/pyperf or build a benchmark service | 3–5 days / 1–2 days | SQL-only pgbench misses Python control; pyperf calibration needs bounded integration; service adds unrelated infrastructure | New dependency or service does not remove protocol fixture work | Defer service; borrow measurement principles, add no dependency. |

The first two could both produce useful diagnostic counts. The dedicated lifecycle helper wins because it makes failure, process and report boundaries reviewable; both alternatives use only new files and avoid active Claude ownership. Four files is a borderline-size taste choice, surfaced at the final gate.

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

Review of engine history and support shape favors plain functions and a context manager with an explicit owned-resource record. There is no evidence for a Strategy/Observer hierarchy, plug-in framework or production refactor. Keep lifecycle in a small sibling lifecycle helper and report/spec/operation orchestration in the main script; never copy all acceptance-test configuration or alter existing shared helpers.

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

Verification: future new unit and PostgreSQL lifecycle/report tests. File ownership: new main script, new sibling lifecycle helper, new unit and integration modules only. Other sections add no independent implementation tasks; they refine these two contracts.

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
| Unresolved | None: operator approved both recommendations at the final gate |

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

# Phase 2 — UI scope assessment

Skipped: no UI scope. The plan contains no frontend components, views, screens,
layout or browser behavior. CLI help and JSON output are developer-facing scope,
so Phase 2.5 runs fully. No design score or design-model consensus is invented.

# Phase 2.5 — Developer experience review (DX POLISH)

## Step 0 — Product, persona and first-use assessment

**Persona:** an experienced platform engineer, or a coding agent acting for that
engineer, in an existing checkout. They know Bookkeeping's business role but should
not need to read private engine methods to run a baseline. Their job is to collect
trustworthy evidence without contacting data sources or disrupting Claude's work.
They have local Python/uv and may or may not have a ready Docker environment;
Rust/native dependencies can make a cold install materially slower than a warm run.

Initial intake DX completeness was 5/10: a script name and desired outputs were
present, but exact first-run cases, setup remedies and outcome codes were missing.
No first-use time has been measured. Target warm-environment time to a useful smoke
report is under five minutes including experiment startup/cleanup; a cold dependency
or Docker installation is separate and has no unverified time promise.

## Developer empathy narrative

I have a performance question, an active checkout, and another agent working next
to me. I want one command that produces evidence without asking me to copy any
production credentials. I will first run help and expect it to tell me which local
services and packages I need. If Docker is asleep, I want a direct explanation and
a command I can use to start the existing local environment, before any setup
changes happen. I do not want a benchmark that hangs while pulling an image.

Once the smoke starts, I need to see which small cases it requested and when it
will stop. A report with one sample is useful for checking the wiring; it is not
enough to tell my colleague that a change is faster. If half the cases time out,
I need that fact beside the numbers. I also want to know whether the numbers came
from the same Python code and native extension I just checked out. When I finish,
I expect my temporary database to be gone and the other agent's resources intact.
Later, when P2 changes the control path, these fixture definitions and recorded
identities should still explain what a valid paired comparison would require.

## Competitive DX benchmark and evidence

The relevant alternatives are measurement tools and the existing acceptance test,
not commercial onboarding products. Research used official documentation because
a browser session was not available for this review; no data-provider site was
requested. No competitor latency or TTHW was physically measured.

| Alternative | Documented strength | Gap for this operator | Planned harness position |
|---|---|---|---|
| Existing PG16 acceptance tests | Real migrations, roles and protocol assertions | No stable benchmark report/finite experiment contract; active Claude file ownership | Reuse store/support APIs, keep new tests/files |
| [pgbench 16](https://www.postgresql.org/docs/16/pgbench.html) | SQL scripts and transaction/client measurements | Does not execute Python frozen-work validation by itself | Same clarity of workload, with unchanged Python protocol |
| [pyperf](https://pyperf.readthedocs.io/en/latest/run_benchmark.html) | Process metadata, multiple runs and explicit benchmark hygiene | Does not supply the three-store protocol fixture; automatic calibration can exceed this budget | Borrow separation/provenance, no new dependency |
| [Python timing](https://docs.python.org/3.12/library/time.html#time.perf_counter_ns) | Built-in integer elapsed counter | No fixture, lifecycle or reporting conventions | Small standard-library timer inside explicit experiment boundaries |

## Magical moment specification

A single smoke invocation leaves a safe report saying which operations succeeded,
which counters were observed, what N/K/D/B meant and whether cleanup completed.
It can reveal repeated whole-run validation without asserting a speedup. The delivery
vehicle is the existing repository plus one script, not an installed service or a
new warehouse command. `--help` works before PostgreSQL/native imports and explains
the default cases, bounds, report fields, safe failure codes and limitations.

Proposed copy/paste path after implementation (these commands are not run proof):

```bash
uv sync --extra mdm-runtime --group dev
# Confirm the configured Docker context answers (`docker info`).
# Explicit prerequisite, outside the benchmark's five-minute budget:
docker pull postgres:16-alpine
uv run --no-sync --offline python scripts/benchmarks/benchmark_bookkeeping_control.py --help
uv run --no-sync --offline python scripts/benchmarks/benchmark_bookkeeping_control.py --preset smoke --output /tmp/bookkeeping-smoke.json
uv run --no-sync --offline python scripts/benchmarks/benchmark_bookkeeping_control.py --case flat-read --sizes 4,12,100 --repeat 3 --output /tmp/bookkeeping-flat.json
```

No DSN, provider identity or cloud credential is needed. The script docstring/help
holds the tutorial, operation reference and measurement-limit explanation so no
shared README or existing docs file needs an edit. A missing native prerequisite
has a setup remedy; it cannot be treated as a successful skipped benchmark.

## Nine-stage developer journey

| Stage | Goal | Friction found | Resolution / acceptance |
|---|---|---|---|
| Discover | Know the entry point | New script not in root README | Exact script path in ticket/tasks; self-contained --help |
| Evaluate | Understand claims | Baseline confused with speedup | First paragraph says synthetic measurement only |
| Install | Prepare Python/native/Docker | Cold install unpredictable | Explicit prerequisite commands, no hidden pulls |
| Hello world | Obtain first useful report | Matrix initially unbounded | Fixed smoke catalog, 240s default and honest incomplete status |
| Configure | Select a small experiment | Ambiguous N/K/D and modes | Case-scoped --sizes; requested/actual dimensions; --repeat |
| Integrate | Consume JSON | Unknown schema/outcomes | Versioned allowlisted object and documented exit codes |
| Debug | Find cause/fix safely | Raw stderr risks secrets | Stable code + problem/cause/remedy/help section |
| Upgrade | Compare evidence over time | New code forbidden by old fingerprint rule | Metadata distinguishes experiment/runtime identity; no calculator yet |
| Operate | Repeat/stop/clean | Shared resources or hangs | Owned IDs, deadline and explicit cleanup confirmation |

## First-time developer confusion report

Roleplay is design inspection, not a claim of running the unimplemented harness.
At the first command I would ask whether I need a database address: answered no,
only a server this invocation owns. At the first failed run I would ask whether
exit 3 means performance failure: the exit map below separates expected protocol
outcomes from incomplete or failed harness execution. At the first report I would
ask why a missing count is zero: missing counters must be null with coverage reason.
At the first scaling attempt I would ask whether N means unrelated work: the frozen
case contract defines total N and independent U and reports both actual values.

## Pass 1 — Getting started

The golden path is prerequisite check, help, then a fixed smoke command. Help must
avoid importing heavy runtime/native/database modules so it remains useful when
setup is incomplete. Native compilation, cold package fetches and image downloads
are disclosed setup time; there is no evidence yet for an end-to-end cold target.
Plan score 8/10; a 10 requires timing the warm first-use path on the supported local
environment and proving each prerequisite failure leads to a workable remedy.

## Pass 2 — API/CLI/SDK design

Use the existing Python invocation and conventional flags: --preset, --case,
--sizes, --repeat, --deadline-seconds, --output. `--preset smoke` and `--case` are
mutually exclusive; absence selects smoke. Per-family numeric ranges are validated
before resource creation. Default repeat is one for smoke and three for explicit
case runs. There is no --database-url, --baseline, hosted mode or legacy wrapper.
Human summary goes to stderr; versioned JSON goes to the output file, or stdout
only when `--output -` is explicit. Never mix progress with JSON.
Plan score 9/10; a 10 requires actual help/invalid-flag tests and tested commands.

## Pass 3 — Error messages and debugging

Every emitted error contains a stable safe code, what failed, likely cause, next
action, and a `--help` section reference. Example invented message: `PG16_IMAGE_MISSING:
Local PostgreSQL image is unavailable. Run docker pull postgres:16-alpine, then
repeat the smoke command. See --help: prerequisites.` It contains no raw exception.

Proposed exit contract: 0 = all requested cells satisfy their declared outcome and
cleanup is confirmed; 2 = invalid request or missing prerequisites before experiment;
1 = setup/correctness/report failure; 3 = incomplete/deadline/cleanup-unconfirmed.
Ctrl-C exits 130 and SIGTERM 143 after bounded cleanup, with incomplete report where
possible. An expected blocked control can pass only when it was explicitly declared
in the case catalog; runtime CLI code 3 is interpreted as that CLI's state outcome,
never blindly propagated as harness success. Plan score 9/10; proof pending.

## Pass 4 — Documentation and learning

The source docstring is the small tool's tutorial/reference/explanation, accessible
through --help. It includes complete synthetic examples, case dimensions, expected
codes, cleanup recovery, sample-count cautions and measured-versus-unmeasured costs.
JSON schema fields are documented beside their creation; no private engine name is
required to use the tool. Findings are attached to the existing P2 plan instead of
creating a second user-facing guide tree. Plan score 8/10; a 10 requires a fresh
reader to follow the examples and inspect an actual safe report without assistance.

## Pass 5 — Upgrade and migration

Report schema version is explicit from the first implementation. Old report objects
are never loaded or executed by this slice; the future comparison contract can
reject incompatible versions explicitly. Existing CLI/runtime names and production
configuration remain unchanged, so there is no application migration or codemod.
Document any report-format change before claiming new and old observations are
eligible. Plan score 9/10; a 10 requires the first real compatibility fixture pair.

## Pass 6 — Developer environment and tooling

Use uv and the repository's mdm-runtime/dev dependencies. On macOS the existing
Docker route is supported; the fixed PG16 image must be preloaded. Native
import identity is recorded by relative module label plus content hash, not by
printing an absolute home path. Source/build correspondence is independently proven
or explicitly unknown; import success never proves checkout freshness.
Ambient database variables are removed from children; only owned endpoints and
selected roles are supplied privately. No new CI configuration, dependency or
backend is added. Plan score 8/10; environment compatibility and cleanup remain
untested until implementation.

## Pass 7 — Community and ecosystem

This is a repository engineering tool for maintainers, with GitHub PR review and
the existing ticket as its contribution/support path. No new SDK language, public
service, forum or usage-tracking channel is needed. The tool's help points to the
case contract and the P2 workstream for bug reports. New support machinery would
be unrelated scope. Plan score 8/10; a 10 requires useful feedback from first users.

## Pass 8 — DX measurement

Record phase durations and requested/completed/failed/not-run case counts locally.
A future manual first-use check times the warm smoke path and records setup blockers
without adding telemetry. Feedback loop, cognitive load and interruption recovery
are assessed via copy/paste success, error remedies and useful partial reports;
no survey or analytics service is necessary for this tool. Plan score 8/10; a 10
requires observed first-use and a cancellation recovery attempt by a fresh reader.

## DX scorecard (plan quality, behavior untested)

| Dimension | Score | Prior intake | Trend / evidence needed for 10 |
|---|---|---|---|
| Getting started | 8 | 5 | Better specification; warm path still needs timing |
| API/CLI/SDK | 9 | 5 | Exact flags/cases; executable help tests pending |
| Errors | 9 | 4 | Exit/remedy map; failure injection pending |
| Documentation | 8 | 5 | Complete help content planned; copy/paste proof pending |
| Upgrade | 9 | 4 | Schema/identity separated; actual fixture pair pending |
| Environment | 8 | 5 | Owned PG16/native provenance; supported-host proof pending |
| Community | 8 | 7 | Existing contribution path reused; no new forum needed |
| DX measurement | 8 | 5 | Durations/completeness specified; no observed first-use yet |

Overall plan score 8.4/10 (67/8); prior 5.0/10. TTHW unmeasured → warm target <5min;
cold setup unknown, explicitly outside that target. Competitive rank: target
Competitive, not demonstrated. Magical moment designed via one local command.
Product: repository CLI tool. Mode: DX POLISH. Six principle coverage areas are
specified: simple start, learn by doing, explicit uncertainty, bounded defaults
with case/repeat/deadline overrides, contextual examples, and a meaningful report.

## DX implementation checklist (all future evidence)

- [ ] Warm first useful smoke report under five minutes, including cleanup.
- [ ] Existing dependency installation is one uv command; Docker/image setup documented separately.
- [ ] First run produces meaningful observations or explicit actionable failure/incomplete status.
- [ ] Magical moment: safe, interpretable report from one benchmark command.
- [ ] Every error has problem, cause, remedy and help reference.
- [ ] CLI names/defaults/mutual exclusions pass help and invalid-input tests.
- [ ] Copy/paste synthetic examples run, including scaling and cancellation.
- [ ] Report schema/eligibility limits and future format-upgrade policy documented.
- [ ] CI execution requires only existing dependencies/PG16 facilities; no new workflow.
- [ ] Changelog/review evidence follows existing repository release process.
- [ ] Learning → skill: name the changed line, or none, after verification.

TypeScript/SDK types, free-tier billing, deprecation codemods, interactive docs search
and a new community channel are inapplicable: no SDK/service/public website or
breaking application API is introduced. Existing text search and GitHub remain the
support paths; no unimplemented item is checked as behavior proof.

## NOT in scope / reuse / TODOs

No root README edits, new website, telemetry, service, SDK, CI timing gate or new
community infrastructure. Reuse uv, Docker, existing PG16 migration/support
APIs and GitHub review. Existing P2 work owns future runtime qualification; zero
new TODOs are added. The optional skill-tooling appendix is inapplicable because
this deliverable is a Python engineering script, not a new skill or MCP service.

## Implementation Tasks (DX)

- [ ] **D1 (P1, human: 3h / coding agent: 45min)** — CLI/docs — Implement import-light help, exact flags/defaults, safe outcomes and copy/paste guidance in the main script; verify in the new unit tests and the fresh-process PG16 smoke.

Every other DX finding refines CEO C1/C2 or D1; no padding task is added.

## CLAUDE SUBAGENT (DX — independent review)

Actual read-only Claude CLI attempt exited 1 after 12.4 seconds: the configured
Fable 5.1 model requires usage credits. No independent Claude findings exist.

## CODEX SAYS (DX — developer experience challenge)

Actual independent Codex review exited 0 after 133 seconds. Five findings:
three blockers (plain uv launcher may sync before the deadline; CLI/output contract
was incomplete; owned Docker does not imply local Docker), one required provenance
refinement, and one optional versioned example improvement. All five are accepted
within the same files. The frozen case contract now specifies offline no-sync warm
commands, exact flags/axes/collision and recovery paths, validated local endpoint,
source/build uncertainty and invented complete/incomplete examples. No extra service,
report importer or provider request was added. This is design resolution, not proof.

## DX DUAL VOICES — CONSENSUS TABLE

| Dimension | Claude | Codex | Consensus |
|---|---|---|---|
| Getting started <5min? | N/A | Warm launcher corrected; target unmeasured | N/A |
| CLI names/defaults? | N/A | Exact table needed, now specified | N/A |
| Actionable errors? | N/A | Safe outcomes accepted, remedies require implementation proof | N/A |
| Docs complete? | N/A | Examples/output rules added | N/A |
| Upgrade safe? | N/A | Metadata-only boundary accepted | N/A |
| Environment friction? | N/A | Docker locality/build provenance corrected | N/A |

0/6 dual-model confirmations; Codex-only independent voice. No new taste choice
or user challenge beyond the two CEO choices. DX overall remains plan-quality
8.4/10; implementation evidence and warm TTHW are unmeasured.

## DX roleplay timestamps (simulated, not elapsed execution)

T+0:00: README “Getting started” names the platform, but this new standalone tool
isn't installed yet; the proposed exact script path/help must bridge discovery.
T+0:30: pyproject's local source-contract dependency implies native setup; the
explicit uv sync/prerequisite remedy prevents treating an import failure as a skip.
T+1:00: existing pg16 helper uses Docker; the new preflight must reject remote
contexts and distinguish missing image from a DB failure.
T+2:00: proposed smoke/report path explains incomplete cases and privacy; no actual
smoke has run. T+3:00: the operator can interpret the proposed fields; actual use
and the under-five-minute target remain acceptance work.

## DX decisions appended

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|---|---|---|---|---|---|
| D11 | DX | Standard-library-only help and no-sync offline warm execution | Mechanical | P5 | Prevent hidden setup before the experiment timer | Plain uv run as bounded warm path |
| D12 | DX | One fixed flag/axis/output contract and unique durable recovery root | Mechanical | P1/P5 | A developer must know exactly what is requested and where partial output lives | Undecided output defaults/overwrite |
| D13 | DX | Validate and pin the effective local Docker endpoint | Mechanical | P1 | Container ownership alone does not establish locality | Inheriting a remote Docker context |
| D14 | DX | Record native identity and independent/unknown build correspondence | Mechanical | P5 | Hash/import cannot prove native source freshness | Claiming source match from successful import |
| D15 | DX | Add invented complete/incomplete report examples in existing new files | Mechanical | P2 | Makes schema comprehensible with no new framework | Additional report importer/website |
| D16 | DX | Preserve existing CLI names; no warehouse command or SDK | Mechanical | P4 | Standalone repository harness fits operator workflow | New public command surface |
| D17 | DX | Reuse GitHub support; no telemetry/community service | Mechanical | P3/P4 | Maintainer tool does not justify separate infrastructure | Analytics/new forum |

## DX completion summary

Eight passes, persona, empathy, benchmark, magical moment, nine-stage journey,
confusion report, exact CLI/errors, scorecard and implementation checklist are
written. Independent Codex found five issues and their plan resolutions are above;
Claude unavailable is explicit. No UI/design score. New TODOs: 0. Future task D1
covers the DX work; existing C1/C2 receive the locality/provenance/report refinements.
All DX changes are specified before engineering starts.

Engineering input refreshed after its initial rebase; final checkpoint refreshed on 2026-10-16 ET after main advanced. This branch changes five new planning files only. Claude runtime/fixtures/skills remain untouched.

# Phase 3 — Engineering review (last)

## Step 0 — Scope challenge, reuse, research and confidence

The minimum complete delivery is a reproducible local synthetic baseline with
correct case semantics, trustworthy measurements and bounded owned cleanup. Four
new code/test files are justified: main orchestration/report/CLI, small lifecycle
support, unit tests and one dedicated PG16 integration module. There is no new
service/class hierarchy, source feed, packaged binary or production migration.
Distribution is the checked-out repository and uv, with existing CI discovery of
new test files; standalone package/image publishing is explicitly out of scope.

Current engine and CLI, migration/grant code, Artifacts and the actual PG16/support
helpers were reread. Existing configured/generated tests provide format/protocol
precedents, not coverage of the new harness. Root `cli.main` routes Bookkeeping
before loading other domains: do not introduce a native/Rust import requirement to
this independent control path merely for fingerprinting. Native metadata is
not_loaded/not_exercised unless it was actually imported; optional identity cannot
claim source-engine throughput or checkout/build correspondence.

Official [Python subprocess documentation](https://docs.python.org/3.12/library/subprocess.html)
provides timeouts and process-session primitives; process creation itself and host
loss are not a hard real-time guarantee. [SQLAlchemy events](https://docs.sqlalchemy.org/en/20/core/events.html)
provide client execution hooks, not rows visited inside SQL functions. [Docker
context inspection](https://docs.docker.com/reference/cli/docker/context/inspect/)
provides the endpoint metadata needed for local preflight. These built-ins are
Layer 1 reuse; a new profiling framework or daemon is unnecessary. Existing P2
TODOs own optimization and hosted qualification; no deferred item blocks collecting
an honest current local baseline.

Prior project learning applied: control/database functions remain authoritative;
a caller's expected outcome is not authority. We never manufacture verified rows,
change grants or replace runtime checks to make a benchmark pass. Proposed risks
below are plan/interface findings, not observed runtime regressions. Suppressed
findings: none promoted from speculative future code; implementation is absent.

## Standards

Only this workstream's planning files are changed now. Future code uses a fresh
Codex branch/worktree, no production/shared support/test edits, overlap guard
before commit and push, file-based messages, uv and affected testmon runs under
five minutes. Public outputs use counts/invented fixture metadata only. Tests fail
for absent PG16 prerequisites rather than skip; full CI remains required at PR time.
No source/provider call, hosted store, AWS resource or merge is part of this ticket.

## Spec

The operator chose a Bookkeeping P2 measurement harness. This implements the
baseline part of broad P2 task T5 and leaves runtime audit reuse, admission,
per-unit checks, limits, generated ordinals and sampling unchanged. The deliverable
ends at correct reports and proof of the harness; it neither claims a speedup nor
claims real source/domain qualification. CEO/DX amendments are inputs to this final
review, not later phases that can silently invalidate it.

## GoF

`gof-refactor-reviewer` is available and its evidence/default-leave-it method was
applied. Engine history includes completion checking, configured capture and fan-in
changes; the PG16 helper has a simpler isolated history. This shows real evolving
protocol responsibilities, but no present cost that justifies moving runtime logic
or adding a Strategy/Observer hierarchy for a standalone measurement script.
Use ordinary functions, an explicit owned-resource record and a context manager;
new indirection would increase review/merge cost without solving this task.

## 1. Architecture review

```text
benchmark_bookkeeping_control.py  [new]
  parse/validate -> local preflight -> case catalog + report state
       |                                     |
       v                                     v
bookkeeping_benchmark_support.py [new]    fresh trial process/session
  endpoint validation / budget /          -> existing root CLI OR Bookkeeping API
  owned container record                  -> unchanged Rules / Bookkeeping / Journal
  bounded start / stop                    -> local immutable artifact.copy evidence
       |                                     |
       +--> isolated PostgreSQL 16 <---------+
       |
       +--> safe recovery marker; exact-ID cleanup; no global resource discovery/deletion
new unit tests / new PG16 integration tests -> verify public harness behavior
```

**E1 [P1, confidence 9/10]: receipt dependencies must be actual inputs.**
`engine.py` `_receipt` calls `_resolve_item` recursively and verifies the immutable
receipt, while `worklist` only creates that path for a version-2 `input.from` or
composed input. A chain declared only in `step.requires` does not establish the
same receipt-validation cost. Freeze a version-2 receipt chain and place the
selected pending target before unrelated pending work, so `tasks(limit=1)` actually
selects it. Record logical step-gate dependencies separately from receipt closure.
This completes the selected case rather than adding a new feed or matching policy.

**E2 [P1, confidence 9/10]: the parent owns all cancellation and cleanup.**
The current helper's `_docker` has no timeout and exposes no immutable container
identity; reusing it unchanged cannot prove bounded acquisition/teardown. Use the
new small lifecycle file, fixed local Docker endpoint and a nonce label registered
before create, verified ID after create, bounded exact-name reconciliation after
lost acknowledgement, and bounded per-call/DB connect/statement timeouts. SIGTERM
and Ctrl-C unwind through the same resource owner; a hung daemon returns explicit
cleanup_unconfirmed. Do not promise automatic recovery after SIGKILL or host loss.

Budget is a supervised software deadline, not a guarantee against kernel/process
creation stalls. Every operation child uses a new session and argument-list launch
without shell interpretation; on deadline terminate its owned process group, allow
its grace interval, kill/reap if needed, then stop only the registered container.
Fixture/build/operation effects occur in the owned child/server/filesystem only.
Native package probing cannot import unrelated source/MDM modules into the root
Bookkeeping CLI, which already intentionally avoids those domains.

## 2. Code quality review

**E3 [P1, confidence 9/10]: choose a counter seam whose coverage is honest.**
`engine._rows` materializes a list, but tasks also calls `conn.scalars(...).all()`;
`after_cursor_execute` is too early to know how many SELECT rows the consumer read.
Count client SQL executions per owned store engine via SQLAlchemy hooks, and
count materialized rows at the known `_rows` return seam only. Name this metric
`bookkeeping_rows_materialized_via_rows_helper`, with explicit excluded scalar/status
paths; never use cursor.rowcount or consume/reissue a result just to count it.

`Artifacts.json -> verified -> read` is a nested chain. Count read calls and
successful returned bytes once at `Artifacts.read`, and expose JSON/verified call
counts as distinct nonadditive diagnostics if useful. Streamed reads have separate
coverage and are unsupported/null unless instrumented independently. All wrappers
restore original objects in finally, preserve values/exceptions and live only in
a diagnostic child; no instrumented elapsed observation enters plain timings.

Keep safe error enums and report construction explicit rather than serializing
SQLAlchemy exception objects, engine URLs or CLI return documents. Child raw output
is private fixture data and is never copied to the public report; successful CLI
JSON is parsed/checked privately and reduced to outcomes/counts. Output collision
handling and atomic persistence cannot replace an unrelated existing report.

## 3. Test review — full path and user-flow mapping

All new harness paths are currently unimplemented and untested. Existing acceptance
tests exercise runtime precedents, not the new script; we do not report them as
passing new-harness coverage. Each path below has a required test, with unit tests
for deterministic pure/lifecycle logic and actual PG16 tests when mocks would hide
role, migration, protocol or resource behavior. No existing runtime regression is
introduced by this planning-only diff; implementation must re-audit actual branches.

```text
NEW MAIN SCRIPT                                     DEVELOPER FLOW
  parse -> help (U01)                               find tool -> help without DB/native (U01)
        -> invalid combinations/size (U02)            bad input -> actionable exit 2 (U02)
  preflight -> missing deps/image (U03)              setup blocked -> remedy, no mutation (U03)
            -> remote endpoint (U04)                 remote context -> refusal (U04/P01)
            -> local endpoint (P01)                 ready local env -> owned server (P01)
  owner register -> create -> lost ack (U05/P02)     interrupted setup -> exact recovery (U05/P02)
  migrations/roles -> denied owner writes (P03)      run safely beside another agent (P02/P03)
  fixture -> flat/select (P04)
          -> receipt chain (P05)
          -> sealed generated (P06)
          -> backlog/lost ack (P07)
          -> zero/refusal (P08)
  trial -> API operations (P09)                     explicit case -> correct state/observations (P04–P09)
        -> actual CLI (P10)                         smoke -> fresh-process evidence (P10)
        -> fresh state/repeats (U06/P11)             repeat -> equal preconditions, no empty retries (P11)
        -> counters isolated (U07/P12)               read report -> costs named accurately (U07/P12)
        -> deadline or child failure (U08/P13)       slow/hung run -> incomplete, not_run retained (P13)
  report -> schema/privacy/eligibility (U09)         consume JSON -> no raw data/secrets (U09/P14)
         -> complete/incomplete samples (U10)        inspect omissions -> explicit null/reason (U10)
         -> collision/write failure (U11)           rerun -> original file preserved (U11)
  cleanup -> normal/error/Ctrl-C/SIGTERM (P15)       cancel -> child reaped, owned server gone (P15)
          -> daemon failure/unknown (U12)            recover -> nonzero + safe marker (U12)
NEW LIFECYCLE HELPER: endpoint/budget/create/ID/recovery/stop paths above U04/U05/U08/U12/P01/P02/P15.
```

Coverage now: 0/27 test groups implemented or run; 27/27 groups have a specified
proof requirement. U01–U12 are 12 unit groups, P01–P15 are 15 PG16/process groups.
A group may parameterize multiple catalog operations/branches and is not a promised
test count. Target quality is behavior + edges + failure, not existence-only checks.
PG16 denial, migrations, receipt chains, duplicate reconciliation and CLI/process
cleanup are mandatory integration/E2E paths. No LLM runtime/prompt changes exist,
so no model eval suite is required for the deliverable.

See [TEST-PLAN.md](TEST-PLAN.md) for assertions and bounded commands. One operation
case proves only that named synthetic profile/process path; no Company/Person/source
claim is made. New branches discovered during implementation must be added to its
checklist/tests instead of assuming this planning diagram is an exhaustive code audit.

## 4. Performance review

**E4 [P2, confidence 9/10]: fixture setup and runtime cost have coupled dimensions.**
Version-1 manifests fan units across steps, so a chain would accidentally multiply N;
use version 2 with explicitly counted per-step units. Vary D while holding N/K fixed,
disclose W/receipt bytes that must change, and keep N/W fixed for backlog B cases.
Do not pool the generated-parent case with flat work or a retry with empty delivery.
Larger complete-run setup uses real transitions and may exhaust its budget; that is
an incomplete experiment, not a reason to bypass protocol or add production caps.

Record raw uninstrumented durations, fixed case order, repeat count and cache policy.
No cache flush, new runtime cache, SQL index or altered scan policy is authorized.
The parent keeps only safe report samples/counts; fixture payloads stay small and
local, so report memory scales with requested observations rather than stored work
rows. PostgreSQL function internals, server rows visited, network-only time, source
engine throughput and destination compute remain explicitly unattributed.

## Engineering NOT in scope and existing reuse

Reuse existing Bookkeeping/Rules/Journal and migration/profile-grant APIs, the
artifact.copy worker, approval/protocol helpers where applicable, PG16 constants
and address conventions, Python subprocess/context-manager primitives and SQLAlchemy
events. Do not import the existing acceptance fixture or edit shared support.
No new runtime migration, database enforcement movement, limit change, cache,
provider qualification, cloud rollout, CI file, generic framework or packaged
benchmark release. Root README/source-specific skill changes remain outside scope.

## Engineering failure modes

| Boundary | Realistic failure | Planned handling | Required test | Silent design gap? |
|---|---|---|---|---|
| Request | Invalid axis combination | Exit 2 before provision | U02 | No |
| Local endpoint | Remote context or changed env | Reject/pin validated Unix endpoint | U04/P01 | No |
| Acquire | Docker creates then client loses ack | Exact name + nonce reconciliation | U05/P02 | No |
| Authority | Owner role accidentally used | Reject fixture; denial checks | P03 | No |
| Dependencies | requires-only chain misses receipts | Version-2 from chain and verified postconditions | P05 | No |
| Generated | Expansion metadata N differs | Assert actual sealed accounting | P06 | No |
| Delivery | Retry is empty or different envelope | Committed Journal event, pending exact ack | P07 | No |
| Metrics | Cursor consumed/double-counted bytes | Read-preserving scoped seams; coverage names | U07/P12 | No |
| CLI | Code 3 incorrectly means success | Interpret declared state outcome | P10 | No |
| Repeats | Leases/empty backlog change later samples | Recreate independent pre-state | U06/P11 | No |
| Deadline | Child/DB/Docker hangs | Bounded process/query calls and cleanup reserve | U08/P13 | No |
| Output | Crash truncates report or leaks raw values | Atomic owned writes and allowlist | U09/U11/P14 | No |
| Cancel | Parent exits leaving resources | Catchable signal path, reap owned processes | P15 | No |
| Host loss | SIGKILL/daemon unavailable | Marker/unconfirmed; no automatic-clean claim | U12 | No |

Zero unmapped/silent critical gaps in the design. All behavior remains unproved.

## Worktree parallelization and execution

Sequential implementation, no parallelization opportunity for this small shared
script/support contract. Order: C1 lifecycle -> C2 evidence schema -> D1 interface
-> E5 fixtures/measurement -> E6 proof/report review. Tests are written alongside
each unit, with final real PG16 verification last; do not defer all correctness
work until the end. Recheck Claude PRs/worktrees at pickup; if a new file has become
owned by another runtime, stop for the ownership decision before editing it.

## Implementation Tasks (engineering)

- [ ] **E5 (P2, human: 1 day / coding agent: 2h)** — protocol measurement — Implement the frozen synthetic cases, exact receipt closure, fresh-state trials and truthful metrics in the new main script; verify every catalog family with the new PG16 tests.
- [ ] **E6 (P1, human: 1 day / coding agent: 2h)** — proof — Prove roles, CLI routing, metric preservation, privacy, deadline/cancellation and owned cleanup using only the new test files; run bounded affected tests and inspect a safe smoke report.
- [ ] **Learning → skill** — name a demonstrated skill correction, or none; no speculative skill edit.

Architecture/lifecycle E1/E2 refine C1 and E5; counter E3 refines C2/E5; performance
E4 refines E5/E6. No redundant task is added for the same finding.

## Engineering completion summary

| Required field | Result |
|---|---|
| Scope challenge | Complete measurement scope accepted; four new code/test files, no new service |
| Architecture | 2 interface/ownership findings resolved in contract |
| Code quality | 1 instrumentation coverage finding resolved |
| Test review | Full code/user-flow diagram; 27 unimplemented groups mapped, 0 silently deferred |
| Performance | 1 fixture coupling finding resolved; no runtime optimization |
| NOT in scope / reuse | Written above |
| TODOs | 0 new items; existing broad P2 owns runtime/hosted follow-up |
| Failure modes | 14 paths; 0 unmapped silent design gaps; actual tests pending |
| Outside voices | Actual Claude unavailable; actual Codex result appended after reconciliation |
| Parallelization | One sequential lane; preserve independent Claude worktrees |
| Lake score | 4/4 in-scope engineering corrections choose complete evidence |
| Retrospective | Intake/CEO/DX checkpoint commits only; no reverted runtime implementation |

## CLAUDE SUBAGENT (Eng — independent engineering)

Actual read-only Claude attempt exited 1 after 10 seconds: configured Fable 5.1
requires usage credits. No findings or consensus can be attributed to Claude.

## CODEX SAYS (Eng — architecture, tests and failure modes)

Actual independent Codex review exited 0 in 264 seconds. Six findings: receipt-chain
selection semantics; partial SQL/row counters; database-wide reset/connection policy;
backlog versus Journal cardinality; insufficient cross-duty denial proof; missing
SQL/CLI/delivery failure classifications. Findings 1–4 blocked the draft engineering
gate. All six have concrete resolutions in the authoritative engineering amendments
to CASE-MATRIX and TEST-PLAN; a focused independent recheck follows before the gate.
Native imports are not required for this control path. Runtime/benchmark behavior
is still unmeasured. The primary findings E1–E4 were recorded independently above.

## Engineering final recheck and consensus

Independent Codex focused recheck: PASS, exit 0 after 54 seconds. All six findings
resolved; no remaining planning blocker in the amended experiment/test contract.
The result explicitly distinguishes future proof from planning defects. Claude's
credit failure remains unavailable; no cross-model consensus is claimed.

| Dimension | Claude | Codex final | Consensus |
|---|---|---|---|
| Architecture sound? | N/A | PASS: clean three-store reset and explicit connections | N/A |
| Test coverage planned? | N/A | PASS: 27 proof groups, six findings mapped | N/A |
| Performance risks addressed? | N/A | PASS: partial counters and coupled dimensions explicit | N/A |
| Security/authority covered? | N/A | PASS: actual cross-duty denial required | N/A |
| Error paths specified? | N/A | PASS: SQL expiry, Journal outage, CLI semantics | N/A |
| Deployment/rollback bounded? | N/A | PASS planning only: owned local resources and cleanup limits | N/A |

0/6 dual-model confirmations. Engineering code/test behavior is unproved until
implementation; a successful warm smoke remains a required acceptance gate.

## Engineering decisions appended

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|---|---|---|---|---|---|
| D18 | Eng | Use actual version-2 receipt chain, select intended target, disclose coupled dimensions | Mechanical | P1/P5 | requires alone measures a different path | Dependency labels without verified input links |
| D19 | Eng | Explicit partial row subtotal and base-read bytes; unverified predictions kept separate | Mechanical | P5 | Avoid missing scalars/double counting or invented measured proof | Aggregate rows/round trips inferred from hooks |
| D20 | Eng | Clone all three clean stores per observation; cold lazy production engines | Mechanical | P1/P5 | Fresh UUID alone leaves global indexes/intents/pools contaminated | Reusing databases with prior trial state |
| D21 | Eng | Fix Journal J=8 and label backlog operation duplicate reconciliation | Mechanical | P1 | Isolate cardinality while preserving actual protocol | Empty-to-populated Journal confounded with B |
| D22 | Eng | Prove both cross-duty denials and mandatory separate verifier | Mechanical | P1 | Distinct logins alone do not prove separation | Direct-write denial as complete authority proof |
| D23 | Eng | Test expired SQL authority, real Journal outage, CLI contents and successful warm smoke | Mechanical | P1 | Correct timeout/zero CLI exit alone is not acceptance | Refusal/empty/failed output accepted as success |
| D24 | Eng | Do not import native/source modules for control fingerprinting | Mechanical | P3/P5 | Root bookkeeping intentionally isolates domains | Irrelevant native dependency in measured control |
| D25 | Eng | Rebase onto current main checklist-only update and preserve provenance | Mechanical | P6 | Own branch refreshed, reviewed code unchanged | Stale branch state or touching Claude's checkout |

Total: 25 decisions, 23 mechanical recommendations and 2 taste choices; 0 user
challenges. Changes to settled runtime scope were not proposed. Each taste choice
was accepted as recommended by the operator at the final approval gate.

## Cross-phase themes

- Trustworthy evidence rather than inferred speed: CEO identified attribution and
  changing trial states; DX identified hidden launcher setup; Eng identified counter
  coverage, database-wide reset and coupled Journal state. High-confidence repeated
  independent signal, resolved through explicit boundaries/metadata and real proof.
- Bounded local ownership: CEO found unbounded helper lifecycle; DX found remote
  Docker context risk; Eng specified exact owned identity/reset/cleanup and failure
  evidence. The resulting harness cannot silently select a shared/hosted endpoint.
- Claims follow proof: every phase distinguishes plan quality, code identity,
  synthetic acceptance, source qualification and hosted performance. No new runtime
  or provider behavior has been executed here.

## Deferred work and task aggregation

Zero new global TODOs: the approved broader P2 plan already owns command-local audit
reuse, admitted scope, per-unit validation and hosted/source qualification. No new
service or generic comparator is justified. See [IMPLEMENTATION-TASKS.md](IMPLEMENTATION-TASKS.md)
for the five exact-deduplicated tasks, phase provenance and sequential order. The
current slice supplies baseline evidence to those existing P2 decisions.

## Final approval choices

Recommendation 1: four new code/test files, including a small owned lifecycle
helper. Alternative: three files with lifecycle inline in the main script; same
scope/proofs, larger orchestration module. Recommendation 2: record complete
baseline eligibility metadata now and defer cross-revision speedup calculations.
Alternative: add a comparator now, increasing scope and acceptance cases; requires
an amended engineering review before implementation.

Planning estimates: about 3–4 human days or 7–10 active coding-agent hours, plus
CI/qualification elapsed time. Estimates are provisional; default smoke completion,
resource cleanup and native/environment compatibility remain unmeasured. Approval
would approve this plan, not merge, deployment, source activation or production
optimization. The operator replied “approved” to the final gate on 2026-10-16 08:54 ET.
Both recommendations are accepted: four files with a dedicated lifecycle helper,
and baseline eligibility metadata with cross-revision calculations deferred.
The planning ticket is complete. Runtime implementation, PR/merge, activation and
deployment remain separate work.

## Pre-gate verification

| Required output | Verified artifact/status |
|---|---|
| Restore point | External original plan contents verified exactly; pointer retained at top |
| CEO | Step 0A–0F, all ten sections, alternatives, reuse/delta, rescue/failure registries and six diagrams; spec recheck PASS |
| CEO voices | Actual Claude credit failure; Codex six concerns resolved; consensus table N/A |
| Design | No UI assets/flows; explicit skip reason |
| DX | All eight passes, persona/empathy/benchmark/magical moment, nine stages, confusion report, scorecard/checklist and exact CLI contract |
| DX voices | Actual Claude credit failure; Codex five findings resolved; consensus N/A |
| Engineering last | Scope, architecture, quality, full test mapping, performance, Standards/Spec/GoF; independent focused recheck PASS |
| Engineering voices | Actual Claude credit failure; Codex six findings and final PASS; consensus N/A |
| Tests | TEST-PLAN.md maps U01–U12/P01–P15; proposed/unexecuted; external engineering test-plan copy updated |
| Tasks | Latest per-phase JSONL scoped to branch/recent commits; five deduplicated tasks/four future code-test files |
| Cross-phase themes/audit | Three themes, D01–D25 unique; two taste choices, zero user challenges |
| TODOs/ownership | No duplicate TODO; only five new planning artifacts; live overlap guard required before final commit |
| Approval | Operator approved both recommendations; planning complete; implementation, PR, merge and deployment not performed |

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|---|---|---|---|---|---|
| CEO Review | /autoplan → /plan-ceo-review | Scope and strategy | 1 + spec recheck | APPROVED, planning only | 6 Codex concerns resolved; spec 9/9/9/9/8 |
| Codex Review | /autoplan independent voices | Independent phase challenges | 4 CLI runs | Completed, exit 0 | CEO 6; DX 5; Eng 6 + focused PASS |
| Eng Review | /autoplan → /plan-eng-review | Final architecture and proof contract | 1 + focused recheck | PASS, planning only | 6 independent findings resolved; 27 future proof groups |
| Design Review | Conditional | No frontend scope | 0 | Skipped, no UI scope | Explicit no-UI assessment |
| DX Review | /autoplan → /plan-devex-review | Developer first use | 1 | APPROVED, planning only | 5 Codex findings resolved; plan 8.4/10; warm TTHW unmeasured |
| Claude voices | /autoplan independent Claude | Cross-model challenge | 3 actual CLI attempts | Unavailable | Configured model requires usage credits; 0 consensus confirmations |

**CODEX:** Final focused engineering recheck passed after receipt closure, metric
coverage, complete reset, Journal cardinality, duty denial and negative controls
were specified. No benchmark/behavior proof was run.

**VERDICT:** APPROVED by the operator. CEO + DX + ENG plan reviews complete.
Implementation/PG16 qualification, full CI, source activation and deployment remain
separate work. Four future code/test files; no production changes in this branch.

NO UNRESOLVED DECISIONS
