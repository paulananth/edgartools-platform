# Bookkeeping measurement harness test plan

Status: proposed tests, none implemented or run. Branch:
`codex/bookkeeping-p2-measurement-autoplan`. Repository: paulananth/edgartools-platform.
This plan covers synthetic artifact.copy control work only. No source/domain,
provider, hosted or performance-improvement qualification is implied.

## Affected Pages/Routes

No browser pages/routes: standalone repository script and unchanged root Bookkeeping
CLI. New tests live only in `tests/unit/test_bookkeeping_control_benchmark.py` and
`tests/integration/test_bookkeeping_control_cost_postgres.py`.

## Key interactions to verify

Help without database/native imports; exact flags and family-specific sizes;
owned local PG16; approved synthetic Rules and separated worker/verifier roles;
fixed catalog and correct observation boundaries; honest JSON/exit outcomes;
partial report and safe recovery after failure/cancellation.

## Unit groups (new unit test module)

| ID | Cases and assertions |
|---|---|
| U01 | --help exits 0 with stdlib-only imports even when SQL/native modules unavailable; documented defaults/axes/errors visible |
| U02 | Mutually exclusive preset/case; unsupported families; invalid sizes/type/range; invalid repeat/deadline; smoke rejects size/repeat; no resource creation on refusal |
| U03 | Missing Docker/image/dependency produces problem/cause/fix/help code, exit 2, no source/cloud/shared-DB fallback |
| U04 | Remote effective Docker context/DOCKER_HOST refused; allowed resolved local Unix socket pinned for every later command; no context configuration mutation |
| U05 | Owned marker registered before create; lost create ack reconciles exact name + nonce; wrong nonce/foreign resource never stopped |
| U06 | Every timed/diagnostic repeat invokes independent state preparation; unexpected obtained-K/state mismatch fails; no warmed-mutated trial accepted |
| U07 | Known fake cursor/list/artifact fixtures yield correct client executions/helper materialized rows/base-read bytes; no fetch consumption/reissued query/double-count; detach wrappers on all exits |
| U08 | Budget decreases across phases; reserve remains for cleanup; child timeout cancels/reaps group; remaining cells not_run; no timing aggregate from a truncated completed subset |
| U09 | Version-1 schema, enum/type/finite-number checks, normalized fixture identity independent of UUID/temp root, native identity separate from build proof; sensitive-key/raw-value canaries absent from every emitter |
| U10 | Invented complete/incomplete JSON examples; null unsupported counts include reasons; success requires all declared outcomes and confirmed cleanup; correctness-control refusal distinct from unexpected error |
| U11 | Existing report/symlink untouched; newly owned target atomically published; disk-full/write error returns safe nonzero with no false success; stdout mode retains durable internal report |
| U12 | Stop/inspect timeout or daemon unavailable produces cleanup_unconfirmed and owned-ID advice; SIGKILL/host-loss limitation explicitly documented, no guaranteed cleanup claim |

Unit fakes test deterministic harness behavior only; they never stand in for the
role/protocol/cleanup proofs below.

## PostgreSQL/process groups (new integration test module)

Reuse migration/store/profile APIs and support helpers, not another test fixture.
Use an invocation-owned local PostgreSQL 16 Docker container. Missing prerequisites
FAIL and stop; never skip or xfail the qualification route.

| ID | Cases and assertions |
|---|---|
| P01 | Validated local endpoint, immutable PG16 image ID and actual version; three fresh stores; ambient bogus DSNs/context cannot redirect a connection or cleanup |
| P02 | Simulated lost create acknowledgement reconciles actual created owned container; unrelated sentinel remains; normal/setup-error teardown confirms exact owned resource absent |
| P03 | Owner migrates then closes; worker/verifier distinct restricted logins/profile grants; direct control UPDATE/DDL denied; session_user/exact duty membership checked; verifier claim/report and worker verifications/admit denied with unchanged state; separate verifier attachment mandatory; successful expected operation proves grants usable |
| P04 | Flat N=4/12,K=1 and selected N=12,K=1/3 report actual N/K/state counts; one selected effect only; no unrequested work executes |
| P05 | Version-2 input.from chain D_nodes/D_edges=1/3 at N=12,K=1: prerequisite receipts admitted, selected target precedes unrelated pending work; exact transitive closure touched; altered prerequisite evidence refuses without execution |
| P06 | Real parent reporting/verifier admission seals 4/8 generated children; N=5/9, correct ordinals and expected_count; original runtime bounds unchanged |
| P07 | N=12,W=8 with B=1/4/8, limit=1: all 8 envelopes pre-appended so J=8, valid pre-ack preserves N/W/J; measured backlog operation explicitly duplicate reconciliation; lost-ack fixture has committed exact Journal event and pending control ack; retry leaves one event and completes one ack |
| P08 | Empty allowed run: tasks empty, checks/finalize agree; deliberately changed envelope renew raises Blocked and does not advance work; same Blocked in a happy case fails the harness |
| P09 | Independent prepared states for renew/report/verifications/admit/check/finalize; each operation's expected transition/evidence checked, worker compute outside timing |
| P10 | Fresh sys.executable child calls root cli.main for all catalog CLI verbs; default cells claim/checks/finalize; correct worker/verifier endpoints; empty claim/false checks/malformed output/unexpected exit classified by contents, not code alone; finalize CLI includes delivery; CLI exit 3 handled by state, never blanket success |
| P11 | Repeat 2 on a small mutating family + diagnostic trials: clone all three clean store templates per observation, prove previous pending trial leaves no rows/intents/leases, equal pre-state signatures/dimensions, fresh run IDs and artifact roots; samples retained separately, never empty/drained trials mislabeled |
| P12 | Known tiny real operation: independent SQL observation verifies event counters by store; _rows materialization count excludes scalar paths explicitly; artifact read bytes counted once; instrumented/plain outcomes equivalent and instrumentation detached |
| P13 | Bounded child/DB query/lock/Docker-call timeout in isolated environment: incomplete report, requested cells retained, remaining cells not_run, no successful overall exit |
| P14 | Plain safe report inspected for allowlisted counts/metadata only; private root CLI stdout reduced to outcomes; no raw SQL, URI, key values, credentials, DSNs, exceptions or invented payload records serialized |
| P15 | Normal exit, worker exception, setup interruption, Ctrl-C and SIGTERM each reap owned child and stop exact container within reserve; independently inspect owned IDs; foreign sentinel survives |

Every catalog family has its own success/outcome assertions. All fresh-CLI verbs
are qualified at N=4; only claim/checks/finalize are required default smoke cells.
Profile = artifact.copy only; adding a source/profile/process claim requires its
own cases before that claim is published.

## Critical paths and edge cases

```text
request -> validate/local endpoint -> register owner -> acquire -> migrate/roles
    -> fixture preconditions -> plain timed operation OR separate diagnostic
    -> postconditions -> safe partial report -> owned cleanup -> final status
```

Cancellation is tested during provisioning, during an operation and during cleanup. Lost Docker
creation acknowledgement and lost Journal acknowledgement are different failures
and need different reconciliation assertions. Output failure must still trigger
cleanup. Cleanup failure must prevent success. Expired SQL authority uses a valid two-second lease and bounded real wait. Real Journal outage disables connections to only the owned trial Journal DB and terminates only its owned sessions; failure must retain intent, then restoring connections permits actual retry. No test uses global Docker prune or
another runtime's resource. Assert normal/refusal/empty/error/deadline/signal/output
collision branches, not just return-object existence.

## Bounded execution commands (future implementation)

Prerequisites installed explicitly with the documented uv/Docker route. Each local
test invocation gets a supervising subprocess timeout of 285 seconds, including
teardown, using a small standard-library wrapper if no timeout utility is available.
Use TESTMON_DATAFILE=$HOME/.cache/edgartools/testmondata and preserve cacheprovider.
The testmon cache can deselect tests, so first qualification must explicitly run
these new files with a fresh dedicated TESTMON_DATAFILE under that same cache
root (do not delete another session's testmon data).

```bash
TESTMON_DATAFILE=$HOME/.cache/edgartools/testmondata-bookkeeping-benchmark-qualification \
uv run --no-sync --offline pytest --testmon tests/unit/test_bookkeeping_control_benchmark.py
TESTMON_DATAFILE=$HOME/.cache/edgartools/testmondata-bookkeeping-benchmark-qualification \
uv run --no-sync --offline pytest --testmon tests/integration/test_bookkeeping_control_cost_postgres.py -k 'roles or flat or selected or dependency or generated'
TESTMON_DATAFILE=$HOME/.cache/edgartools/testmondata-bookkeeping-benchmark-qualification \
uv run --no-sync --offline pytest --testmon tests/integration/test_bookkeeping_control_cost_postgres.py -k 'delivery or operations or cli or repeats or metrics'
TESTMON_DATAFILE=$HOME/.cache/edgartools/testmondata-bookkeeping-benchmark-qualification \
uv run --no-sync --offline pytest --testmon tests/integration/test_bookkeeping_control_cost_postgres.py -k 'lifecycle or cleanup or timeout or privacy'
uv run --no-sync --offline python scripts/benchmarks/benchmark_bookkeeping_control.py --preset smoke --output /tmp/bookkeeping-qualification-new.json
```

Actual test names/batches must preserve the 27-group mapping and cover all selected
items. Record collected/executed counts and expected IDs so empty -k selection or
testmon deselection cannot masquerade as qualification. If a batch approaches its
budget, split it before rerunning; never run an unbounded local suite. CI still runs
its existing full gates. No local test command was executed in this planning ticket.

## Exit and report acceptance

Exit 0 requires every requested cell's declared outcome, valid report and confirmed
cleanup; exit 2 invalid/prerequisite; exit 1 correctness/setup/report failure;
exit 3 incomplete/deadline/cleanup-unconfirmed; signals retain 130/143. Documented
precedence must cover combined failures. Larger scaling reports may be incomplete
and cannot be used for speedup claims. Unknown/unmeasured values stay null with a
reason. Native build correspondence remains unknown unless independently proven;
no forced native import into Bookkeeping control.

## Checklist

- [ ] Implement all U01–U12 and P01–P15 proof groups with actual branch inventory.
- [ ] Run affected bounded testmon batches; record selected/executed groups and safe evidence.
- [ ] Inspect safe smoke report and independently confirm owned cleanup.
- [ ] Review Standards, Spec and GoF against the final implementation diff.
- [ ] Run overlap guard, full required CI, and obtain named merge approval separately.
- [ ] Learning → skill: record a verified correction or none, with actual ET completion stamp.

Connection/reset contract: fresh clones of all three migrated empty templates per observation; production engine factories with pool_pre_ping=true, lazy first connection INSIDE API timing; shared server/OS caches declared. Unsupported scalar-row paths invalidate aggregate consumed-row totals; helper subtotal is named explicitly.
