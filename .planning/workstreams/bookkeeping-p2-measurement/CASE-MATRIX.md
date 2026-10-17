# Frozen experiment contract (proposed, no measurements yet)

All fixtures are invented `artifact.copy` protocol work; none qualifies Company,
Person, acquisitions, mastering, any source feed or source-engine throughput.
Use approved Rules, immutable artifact manifests and real public transitions.
Setup writes schema/roles through owner APIs only. Never fabricate verified rows.

## Dimensions

- N = total work items in the measured run after any sealed expansion.
- K_requested / K_obtained = selected tasks requested / actually returned; never conflate them.
- D_nodes / D_edges = unique verified prerequisites / dependency edges for selected work.
- U = unrelated work items; record it explicitly, never use N to mean U.
- W = verified items before the measured operation; state counts must sum to N.
- B = undelivered Bookkeeping journal intents for this run before delivery.
- G_parents / G_children = verified expansion parents / generated children.
- A_bytes = frozen Rules/input/receipt artifact bytes actually loaded in diagnostics.

Store intended AND actual dimensions; immutable identities/temporary artifact roots
are normalized out of the fixture-spec digest, while real artifact hashes remain
verified by the unchanged runtime. Record the normalized template/seed, schema,
worker profile, protocol, migration checksums and actual imported module/native hashes.
A run UUID or temporary path alone must not make equivalent fixture specs differ.

## Required catalog

| Case | Sizes (small default; opt-in scale) | Pre-state and operation | Isolated question and consumer |
|---|---|---|---|
| flat-read | N=4,12; scale 100,1000; K=1,D=0,W=0 | Running, all pending; `_frozen` diagnostic and `tasks(limit=1)` in distinct trials | Run-wide validation/selection baseline for P2 A/C |
| selected-width | N=12; K=1,3; D=0,W=0 | Fresh all-pending equivalent run for each claim | Effect of selected work for P2 C |
| dependency-closure | N=12; K=1,D_nodes=1,3 (chain), W=D_nodes | Verified prerequisites built first; claim target with valid receipts | Dependency validation baseline for P2 C; W changes with D and is disclosed |
| renew-report-admit | N=4,12; K=1,D=0 | Separate leased / running-candidate-ready / reported-and-verified-report-ready trials | Distinct timings for `renew`, `report`, `verifications`, `admit`; worker/verifier execution outside timer |
| generated-read | N=5,9; one sealed parent + 4,8 children | Parent verified through existing protocol; children pending | Reconstruct generated accounting; no runtime cap or ordinal change |
| delivery-backlog | N=12,W=8,J=8; B=1,4,8; limit=1 | Pre-append all 8 envelopes, acknowledge 8-B outside timer | Duplicate-reconciliation backlog baseline, N/W/Journal size fixed; P2 A |
| delivery-lost-ack | N=4,W=1,B=1 | Commit exact journal envelope, leave Bookkeeping ack pending; then deliver | Real duplicate reconciliation, not retry on an empty queue |
| check-finalize | N=4,12; W=N; B=0 | All work verified and journal drained; separate `check` and method `finalize` trials | Full-run completion baseline, P2 B/C; setup reported separately |
| fresh-cli | N=4; K=1 or W=N | New interpreter through root `cli.main`: claim, renew, report, admit, checks, finalize | Real CLI behavior + startup cost; `finalize` includes delivery, never equate to method-only finalize |

Correctness control `zero-work-checks`: N=0, allow_zero_work=true, `check` returns
passing empty accounting; complete only after unchanged finalize confirms complete.
Control `blocked-envelope-renew`: N=4, valid leased task with altered envelope
profile; `renew` must refuse as `Blocked` and must not advance work. These controls
are included in default smoke, with one observation each, and are not scaling claims. Generated fixtures use the existing expansion
contract in `tests/integration/test_generated_bookkeeping_postgres.py` as evidence
of format, without importing its fixture or editing that test.

## Default and larger experiments

`--preset smoke` requests flat-read N=4,12 plus renew-report-admit N=4,
delivery-lost-ack N=4, check-finalize N=4 and fresh-cli N=4 (exact cells `cli-claim`, `cli-checks`, `cli-finalize`), one timed observation
and one separate diagnostic observation per method operation. The full requested
case list is written before setup; deadline exhaustion leaves remaining cells
`not_run` with a reason and makes the invocation incomplete. A one-sample smoke
proves wiring/correctness only; it cannot establish a performance trend.

`--case` selects one catalog family and `--sizes` valid sizes for that family;
`--repeat` defaults to 3 for explicit scaling experiments. The invocation always
has the same total budget, so a large matrix may be incomplete and must be split
into separate invocations. Record fixed ascending case order, no hidden warmup,
and local warm-filesystem cache policy; no claim of cold OS/page cache or randomized
statistical significance. Each trial has independently recreated equivalent state.

## Measurement boundaries

- In-process uninstrumented operation: `perf_counter_ns` directly around the named
  public method only; `_frozen` itself is explicitly a private diagnostic seam.
- Fresh CLI: parent end-to-end elapsed is authoritative; a child pre/post entry
  marker may separately describe imports versus entry-point execution. Never
  derive cost by subtracting measurements from unrelated processes.
- Diagnostics: separate equivalent state, scoped SQLAlchemy execution listeners and
  scoped wrappers for `_frozen`/artifact reads. Count client SQL executions by store,
  and rows actually materialized (not cursor.rowcount on SELECT). If observing rows
  requires altering consumption, instrument the known `_rows`/result-consumption
  seam without reissuing SQL; unsupported paths are null with a coverage reason.
- SQL functions' internal statements/rows visited, network-only latency and worker
  compute attribution remain unmeasured. Report combined elapsed and these limits.
- Setup, migrations, fixture preparation, worker/verifier compute, subprocess startup
  markers, diagnostics and cleanup have separately labeled durations/coverage.

## Budget and ownership

Default total 240 seconds; `--deadline-seconds` accepts 30–285. Includes provisioning,
trials, report persistence and cleanup, and is enforced from parent entry. Reserve
at least 20 seconds for cleanup/reporting; operation child deadlines never exceed
remaining budget. Prerequisite package/image installation is an explicit separate
step, never an automatic unbounded download inside the experiment.

A small new harness-only lifecycle helper may reuse `pg16.IMAGE`/`Server` and the
readiness query pattern. It must own a UUID-named Docker container and record its
intended name/nonce before `docker run`, then its immutable ID, so a lost creation
ack is recoverable by exact name plus ownership verification. Every Docker call
and readiness query is bounded. Do not call the existing unbounded server context
and pretend an outer timer fixes resource leaks. No arbitrary DSN, no ambient
`PG16_SERVER` backend switch, and no Docker global prune.

The parent supervises process groups and handles ordinary exception, Ctrl-C and
SIGTERM; cleanup uses only recorded owned resources. Docker-daemon failure becomes
`cleanup_unconfirmed`; SIGKILL/host loss leaves an owned recovery marker and cannot
be promised automatic cleanup. Counts-only public JSON never includes database
addresses, role passwords, file contents, raw SQL, raw child output or exception
messages. Recovery instructions use the invocation-owned container identity, and
are emitted only for that invocation's resources.

## Report and stopping rule

One versioned JSON report contains every requested case/cell, raw timing samples,
separate diagnostic samples/coverage, expected/actual outcome, pre/post state counts,
phase durations, fingerprints, completeness and cleanup result. Summary uses median
and range only when samples exist, never pools different states or omitted trials.
No absolute latency gate, complexity claim, or speedup claim belongs to this slice.

Same-runtime scaling eligibility checks fixture template, fixed dimensions, profile,
process mode, outcome, harness/protocol/migration/runtime/environment identity.
Intentional varying dimensions are declared. Runtime revision and normalized fixture
spec are distinct identities. Save metadata sufficient for a future explicitly paired
cross-revision comparison, but do not implement cross-revision speedup calculation
here. This baseline-only choice is surfaced as a final taste decision.

Done means the named catalog can produce correct, honest observations; the default
smoke completes on a supported warm environment within budget; roles/cancellation/privacy are proven;
and reports document eligibility and measurement limits. It does not mean a full
larger matrix completed, that control became faster, or that the broad P2 is shipped.

## Frozen cell identifiers and eligibility scope

Every cell ID is `<family>/<operation>/<process-mode>/<dimensions>/<trial-kind>/<repeat-index>`.
The catalog's shorthand K means K_requested; K_obtained is asserted separately.
D always expands to D_nodes and D_edges, never a single ambiguous report field.
Family operations: flat-read=`tasks`,`frozen-diagnostic`; selected-width=`tasks`;
dependency-closure=`tasks`; renew-report-admit=`renew`,`report`,`verifications`,`admit`;
generated-read=`tasks`,`frozen-diagnostic`; delivery-backlog=`deliver-backlog-reconcile`;
delivery-lost-ack=`deliver-reconcile`; check-finalize=`check`,`finalize-method`;
fresh-cli=`cli-claim`,`cli-renew`,`cli-report`,`cli-admit`,`cli-checks`,`cli-finalize`.
Default smoke includes all method operations in its listed families plus the three
explicit CLI cells above and both correctness controls. Diagnostic-only frozen cells
have no plain timing claim; every other method cell requests one timing and one
separate diagnostic observation. CLI cells request end-to-end timing and safe status;
internal diagnostics are unavailable unless a separate instrumented child is run.

In this slice eligibility means validating the internal case dimensions and emitting
normalized comparison metadata. It has no report-file ingestion, --baseline flag,
speedup calculation or cross-revision comparison engine. Tests cover schema and
metadata compatibility rules on invented dictionaries, without creating a second
report-import interface. A future paired comparison may use the recorded metadata
only after its own implementation review.

## Exact command and output contract (DX amendments)

Installation is separate: `uv sync --extra mdm-runtime --group dev`. Warm execution
uses `uv run --no-sync --offline python scripts/benchmarks/benchmark_bookkeeping_control.py ...`.
Help imports standard library only. If uv/environment is unavailable, help can also
be read with `python3 scripts/benchmarks/benchmark_bookkeeping_control.py --help`;
repo runtime commands still use uv. The warm first-use proof times the shell command
through confirmed cleanup, not only the timer after Python starts. Its result is
unmeasured until implementation.

| Flag | Default / permitted combinations | Meaning |
|---|---|---|
| --preset | smoke when neither preset nor case given; only smoke currently supported | Fixed catalog cells above; rejects --sizes and --repeat |
| --case | Mutually exclusive with --preset; one family | Requests all listed operations of that family |
| --sizes | Only with variable-size --case; defaults to family's small sizes | Varies the named axis below; positive integers, fixed runtime constraints retained |
| --repeat | Explicit --case only; default 3; integer 1–10 | Number of independent timing AND diagnostic trials per applicable operation/cell |
| --deadline-seconds | 240; integer 30–285 | Parent-entry total budget including reserved cleanup/reporting |
| --output | Default unique invocation-directory/report.json; explicit new path or - | Existing file/symlink refused before provisioning; - emits JSON only on stdout and still persists owned report |

Size axes: flat-read=N; selected-width=K_requested (N fixed at 12);
dependency-closure=D_nodes (chain D_edges=D_nodes, N=12); renew-report-admit=N;
generated-read=G_children (one parent; N=1+G_children, existing <=128 per parent);
delivery-backlog=B (N=12,W=8; values 1..8); check-finalize=N.
Delivery-lost-ack and fresh-cli are fixed-size families and reject --sizes.
K_requested may not exceed available pending work; dependency size must leave a
selected target within N; invalid combinations fail before any container is created.
Correctness controls run once in smoke, are not repeat-scaled and are never pooled
with timing families. CLI cells have only timing/status unless explicitly separate
diagnostics are implemented; null plus coverage reason is valid, not zero.

Every invocation reserves a unique mode-0700 directory under the OS local temp
root before provisioning. It contains `report.json` and a safe recovery marker
with invocation nonce, intended container name, confirmed container ID when known,
phase, cleanup status and no addresses/credentials/data. Report copies to --output
are atomically published only into this invocation's newly reserved target;
existing reports are never replaced. Private fixture files/child logs are deleted
after cleanup; safe reports persist. Stdout mode retains the same durable internal
copy and prints its location on stderr. If final report persistence fails, exit 1;
cleanup_unconfirmed/timeout takes precedence as exit 3, and signal exits remain
130/143. Never emit a success summary before cleanup is confirmed.

Example selected-width run:
`uv run --no-sync --offline python scripts/benchmarks/benchmark_bookkeeping_control.py --case selected-width --sizes 1,3 --repeat 3 --output /tmp/bookkeeping-width-new.json`.
Example backlog run:
`uv run --no-sync --offline python scripts/benchmarks/benchmark_bookkeeping_control.py --case delivery-backlog --sizes 1,4,8 --repeat 3 --output /tmp/bookkeeping-backlog-new.json`.
For cancellation press Ctrl-C; inspect the retained report and owned recovery
marker. If cleanup is unconfirmed, the tool prints an exact owned-ID recovery
command and explains how to verify the invocation nonce/name before using it;
never suggest a global prune or deleting all pg16 containers.

### Local Docker and provenance

Resolve the effective Docker endpoint without changing user context. Reject ssh,
tcp/http or other remote endpoints before creation; do not echo endpoint values.
Support existing local Unix sockets for the configured Docker context on macOS and the
local Docker Unix socket on Linux; validate the resolved socket path/type. Pass
that validated local endpoint explicitly to every Docker subprocess so subsequent
environment/context changes cannot redirect cleanup. Docker daemon unavailability
or unsupported context returns a safe prerequisite error and a local-context remedy.
An invocation-owned container on a remote context does not satisfy this contract.

Record allowlisted Python implementation/version, relevant dependency versions,
OS family/architecture, Docker server version, Docker CPU/memory allocation,
container CPU/memory settings, immutable image ID and actual PostgreSQL version.
Use hashes/relative labels for imported Python/native files. Native binary identity
and native source/build correspondence are separate fields; correspondence is
`unknown` unless independent build evidence proves source tree/toolchain/profile.
Import success and hashing alone do not prove freshness. Missing native dependencies
have the explicit setup/rebuild remedy
`uv sync --extra mdm-runtime --group dev --reinstall-package source-contract`;
Rust compilation is outside the experiment budget. Unknown build correspondence
limits eligibility metadata and claims, without fabricating a source match.

Unit fixtures/help contain compact invented version-1 complete and incomplete
report examples, with nullable unsupported diagnostics and all outcome enums.
No external report ingestion or format converter is introduced.

## Engineering amendments — authoritative experiment semantics

### Receipt closure and target selection

Dependency fixtures use a version-2 manifest: one unit in each prerequisite step,
with `input: {from: {step: previous_step, key: previous_key}}` after the first unit;
the selected target names the last prerequisite through the same `from` mechanism.
Every prerequisite is completed and admitted by the existing protocol. Order steps
as chain -> selected target -> unrelated independent work, with unique output/lease
resources, so tasks(limit=1) selects the intended target rather than an earlier
unrelated pending unit. Assert the actual selected identity privately.

D_nodes/D_edges describe the transitive receipt graph of input.from/compose, not
just the step.requires gate. Record configured step count and gate requirements
separately. U=N-|selected union receipt closure|; chain variants hold N=12,K=1,
but W, U, step count and receipt bytes necessarily vary and are disclosed. This is
a coupled dependency-closure baseline; do not attribute elapsed differences solely
to D. An ancestor-artifact corruption control must refuse the selected operation,
proving that the intended receipt path is actually consulted.

### Database-wide reset and connection policy

Create/migrate the three canonical empty store databases once, install restricted
roles/profile grants, close all connections, and keep these empty schemas as clean
templates. Before EVERY timing/diagnostic/control observation, clone ALL three
stores into invocation-owned fresh database names, then prepare only that cell's
valid pre-state. Runtime accepts explicit owned clone addresses; canonical-name
checks belong to the existing migration APIs and are satisfied when creating the
templates. Do not rerun those migrations against alternate clone names or change
migration checks. All three cloned stores must have no runs/intents/events/leases
from previous cells. Roles remain fixed and their membership is checked once and
fingerprinted. Dispose/drop only owned trial engines/databases outside timing.

Actual CREATE DATABASE cloning uses a local owner, properly quoted synthetic names
and bounded statement/connect/lock timeouts. Close owner/setup connections before
the operation. A preceding trial deliberately leaving pending work must not change
the next cell's initial inventory. Database/global index population is part of
eligibility metadata. Server/OS caches are shared and declared warm/uncontrolled;
cloning does not establish cold caches or statistical comparability.

Measured API engines use existing production get_engine factories (pool_pre_ping=true),
constructed fresh after preparation without connecting. First physical connection,
dialect initialization and pool checkout within the operation are INCLUDED in API
elapsed time. CLI elapsed naturally includes its corresponding startup/connection
work. Diagnostic counterparts use the same factory/state policy. Setup/assertion
queries are outside listeners/timers. Record this exact cold-engine policy; do not
mix it with preconnected/warm-pool observations. Raw DBAPI pings/driver initialization
outside SQLAlchemy execution hooks are NOT counted as application SQL executions.

### Journal population and delivery semantics

For delivery-backlog, hold N=12,W=8 AND Journal event cardinality J=8. After creating
eight valid intents, append/verify all eight exact envelopes to Journal without
acknowledging Bookkeeping, then acknowledge 8-B through actual delivery outside the
timer. Measured limit=1 delivery is duplicate reconciliation for every B=1,4,8;
label operation `deliver-backlog-reconcile`, never fresh-insert delivery. Pre-state
checks establish exact B/J/W and one post-state acknowledgement. Preparation/cache
history still differs and is disclosed. Constant client SQL counts do not prove
that database backlog has zero cost. Fresh insertion and lost-ack reconciliation
are distinct fixture/outcome labels and never pooled.

### Metric accounting and calibration

Required diagnostic metrics: application SQL executions per store engine; `_frozen`
call count; `bookkeeping_rows_materialized_via_rows_helper`; base Artifacts.read
calls and successfully returned bytes. The rows-helper metric is a partial subtotal,
not an aggregate of all consumed SQL rows. Selection via scalars().all(), scalar
function results and JSON payload elements are separately named coverage categories;
if not instrumented, they are null/unsupported and `total_consumed_sql_rows` is null.
SQL execution counts are not server-internal statement counts or round-trip counts.

For a simple one-step N<=1000 flat first-claim fixture, code inspection predicts
3 frozen calls, 9 explicit application SQL executions and 3N+4 rows through _rows,
plus N selected keys and one scalar result outside that subtotal. These are
UNVERIFIED predictions for the inspected revision, not measured results or permanent
CI performance assertions. Compare them with actual diagnostics after implementation,
explain discrepancies, and preserve current physical evidence. Journal.append itself
verifies, and deliver verifies again: inspect/measure all three Journal application
SQL executions per event; never assume two. Small calibration fixtures execute known
explicit SELECT/scalar/list paths to prove the counters without permanently encoding
an inefficient runtime shape into the correctness suite.

Count byte length once at Artifacts.read; json/verified call counters are nonadditive.
Never consume/reissue a query to count rows or replace runtime return values. Scoped
wrappers/listeners restore on every exit and apply only to diagnostic children.
Native source-contract is not imported merely to fingerprint it: the root Bookkeeping
CLI intentionally avoids other domains. Record not_loaded/not_exercised if absent;
source/build correspondence remains unknown unless independently proven.

### Authority, negative controls and acceptance

Verify session_user, restricted-role attributes and exact profile membership. Worker
must not inherit verifier duty; verifier must not inherit worker duty. Against these
real roles, verifier claim/report and worker verification/admission must refuse and
leave work unchanged. Explicitly attach a separate verifier before using protocol
helpers; reject helper fallback to the worker instance.

Add focused failure classification tests: real expired SQL authority (valid two-second
lease with bounded wait); actual owned Journal connection refusal with retained intent
and later successful retry; empty CLI claim, false CLI checks, malformed child output
and unexpected child exit. For Journal outage use only the owned trial database's
ALLOW_CONNECTIONS/owned-session control, then restore it before retry; no shared store
or mocked Journal substitutes for that PostgreSQL failure-path proof. Malformed output
can use a unit child fixture; actual CLI success/refusal semantics use real PG16.
Parse CLI JSON privately and assert operation-specific contents, not just exit code.

A completed warm default smoke within its budget is REQUIRED acceptance evidence.
A correct incomplete/timeout report proves failure handling only. If default smoke
cannot complete on the supported warm environment, acceptance remains incomplete
and the operator receives the observed evidence before any preset change. Cancellation
proof covers provisioning, active operation AND cleanup; SIGKILL/host loss remains an
explicit recovery limitation. These corrections do not change production behavior.
