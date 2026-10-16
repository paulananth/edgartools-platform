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
| delivery-backlog | N=12,W=8; B=1,4,8; deliver limit=1 | Build 8 verified intents, pre-deliver 8-B outside timer | Backlog effect with N/W fixed; per-run intents only, P2 A |
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
smoke runs or explicitly fails/incompletes; roles/cancellation/privacy are proven;
and reports document eligibility and measurement limits. It does not mean a full
larger matrix completed, that control became faster, or that the broad P2 is shipped.

## Frozen cell identifiers and eligibility scope

Every cell ID is `<family>/<operation>/<process-mode>/<dimensions>/<trial-kind>/<repeat-index>`.
The catalog's shorthand K means K_requested; K_obtained is asserted separately.
D always expands to D_nodes and D_edges, never a single ambiguous report field.
Family operations: flat-read=`tasks`,`frozen-diagnostic`; selected-width=`tasks`;
dependency-closure=`tasks`; renew-report-admit=`renew`,`report`,`verifications`,`admit`;
generated-read=`tasks`,`frozen-diagnostic`; delivery-backlog=`deliver`;
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
