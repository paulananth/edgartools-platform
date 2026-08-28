# 36 — Wire the MDM publication outbox into real MDM commits

**What to build:** Make the already-built, currently-dormant transactional
publication queue (`edgar_warehouse/mdm/publication.py`) actually fire from
real MDM processing, and make an actual coordinator drain it, so
relationship-changing MDM commits become exportable exactly once instead
of never being enqueued at all.

**Blocked by:** None — the design decision is already made (Ticket 06);
this is pure wiring.

**Status:** ready-for-agent

- [ ] Every MDM processing pass tied to one upstream `cause_reference`
  (per Ticket 04's Run identity) calls `request_publication` exactly once
  inside the same transaction as its own commit, carrying `cause_reference`
  in `source_summary` — confirmed via `git grep request_publication` showing
  real callers outside `publication.py` and its own tests for the first
  time.
- [ ] `claim_next_publication_request`/`advance_publication_lifecycle` are
  driven by an actual scheduled coordinator (CLI cron, Step Function, or
  equivalent) rather than only existing as manually-invoked CLI probes
  (`mdm publication-claim`/`-status`) — confirmed via `git grep
  advance_publication_lifecycle` showing a real, non-test caller.
- [ ] A live end-to-end test (or prod dry run) proves a real MDM commit
  enqueues a request, a coordinator claims and advances it through
  `graph_pending → graph_building → graph_verified → graph_active`, and
  `compute_publication_freshness` reports healthy status throughout.

## Notes

Surfaced while resolving [06 — Decide MDM affected-key closure and
publication outbox](06-decide-mdm-closure-and-outbox.md) — see that
ticket's Answer for the full design rationale. Both the writer side
(`request_publication`) and the consumer side
(`claim_next_publication_request`/`advance_publication_lifecycle`) are
fully built and unit-tested in isolation but have zero production callers
today — confirmed via `grep -rln "request_publication(" edgar_warehouse/
tests/` returning only `publication.py` itself and three test files.

## Answer

**Bullet 1 deviates from Ticket 06's literal wording, documented deliberately:**
`git grep cause_reference edgar_warehouse/mdm/` returns exactly one hit —
`013_acquisition_ledger.sql`'s `source_fetch_decision.cause_reference`
column, a field on the acquisition-ledger subsystem (`edgar_warehouse/
acquisition/`) that MDM's own pipeline (`edgar_warehouse/mdm/pipeline.py`)
never reads. Ticket 06's "once per upstream cause_reference" decision
assumed a cross-subsystem identity that doesn't exist in code today, and
wiring one in would be new plumbing well beyond "pure wiring" (this
ticket's own scope line). Used the identity that *does* exist instead:
`MDMPipeline.run_id`, the run's own physical identity (already threaded
through `run_companies`' resumability work). `MDMPipeline.run_all()`
(`edgar_warehouse/mdm/pipeline.py`) now calls `request_publication` exactly
once per invocation, after `derive_relationships()` completes, gated on
`resolved_total > 0 or stats.relationships_written > 0` so an empty run (no
new companies/advisers/securities/persons/funds and no new relationships)
never enqueues a no-op request. `run_id` falls back to a generated `uuid4`
if the caller didn't supply one (mirrors `mdm sync-graph`'s existing
`generation_id` fallback), and is carried in `source_summary` alongside
per-entity-type counts for operator visibility.

Note `run_all()`'s five entity-resolution steps and every relationship-type
worker each commit through their own independent session (mdm-run-step-
parallelism ticket 02) — there is no single top-level transaction spanning
the whole Run for `request_publication` to be atomic *with*. The enqueue
instead commits as its own atomic unit, immediately after the last
already-committed step finishes — "one request represents one Run's worth
of already-durable MDM changes," not "atomic with any individual write,"
which is the granularity Ticket 06 actually needs (a Run-level publication
signal) even though it isn't literally what `publication.py`'s own
docstring describes for its general-purpose atomicity contract.

**Bullet 2 — the coordinator, and a significant finding it depended on
resolving first:** before wiring the consumer side, checked whether the
Ticket 08 generation-builder pipeline (`edgar_warehouse/mdm/generation.py`,
whose `building`/`verified`/`activated`/`failed` status vocabulary closely
mirrors the outbox's `graph_building`/`graph_verified`/`graph_active`/
`failed` states) was the intended target. It is not safe to wire to today:
`build_partition` is pure Postgres-side bookkeeping — it flips a status
column and writes zero rows to Snowflake. `git grep` across `cli.py`/
`graph.py` confirmed no code anywhere connects `generation.py`'s
`create_generation`/`plan_generation_partitions`/`build_partition`/
`fan_in_generation` to `SnowflakeGraphSyncExecutor` (the class that
performs the real Snowflake write) — the two are entirely separate,
never-joined code paths. Wiring the outbox's consumer to `generation.py`
would have produced a coordinator that faithfully advances
`MdmPublicationRequest.lifecycle_state` to `graph_active` while never
causing a single real Snowflake write — a dashboard that lies. This also
retroactively explains a fact noted in Ticket 40's own investigation
(`mdm_graph_generation` sits empty in prod): the generation-builder
pipeline was never wired to real execution in the first place, so nothing
using it could ever populate real graph data. Filed as its own gap, not
fixed here (out of this ticket's "pure wiring" scope) — see **Not yet
specified** below.

Wired the consumer to the machinery that *is* real instead: the same
`SnowflakeGraphSyncExecutor`/`SnowflakeGraphVerifier` classes `mdm
sync-graph`/`mdm verify-graph` already call in prod today (per CLAUDE.md's
Phased Pipeline). New function `drain_publication_queue` in
`publication.py` claims up to `max_requests` eligible requests and advances
each through `graph_building` (calls an injected `sync_fn`) →
`graph_verified` (calls an injected `verify_fn`) → `graph_active`, or
`failed` with the error recorded on any exception/`False` verify result —
one bad request never sinks the rest of the drain. `sync_fn`/`verify_fn`
are injected (not called directly) specifically so the coordinator's
lifecycle-progression logic is provable against a real SQLAlchemy session
with a stubbed Snowflake step, without needing live Snowflake access to
test state transitions — this was deliberate, not a shortcut: it's what
makes bullet 3's proof possible in this environment at all. New CLI
subcommand `mdm publication-drain` (`edgar_warehouse/mdm/cli.py`,
`_handle_publication_drain`) is the real, non-test caller — it wires
`sync_fn`/`verify_fn` to `SnowflakeGraphSyncExecutor.from_env().sync(...)`/
`SnowflakeGraphVerifier(...).verify(...)`, the exact construction
`_handle_sync_graph`/`_handle_verify_graph` already use.

Following Ticket 44's own precedent exactly (per its own established
shape, reused deliberately rather than inventing a new mechanism): added
`mdm_publication_drain` as an eighth mode on the already-consolidated
`edgartools-<env>-mdm-utility` state machine (`write_mdm_utility_definition`,
`infra/scripts/deploy-aws-application.sh`) rather than a bespoke new state
machine, sized on the medium MDM task profile (it calls both sync and
verify machinery in one invocation, same cost class as `mdm_sync_graph`
alone). A new `configure_publication_drain_schedule` function (mirroring
`configure_fence_monitor_schedule` line for line) creates an EventBridge
rule invoking it every 5 minutes — sized to publication.py's own
`WARNING_AGE_SECONDS=300` freshness SLO, since draining any slower would
trip that SLO on an otherwise-healthy queue by construction. Off by
default: gated behind an explicit `--configure-publication-drain-schedule
enable` flag, never run as a side effect of an ordinary deploy — not yet
invoked against any real environment as of this entry.

**Bullet 3 — proven at the SQLite/injected-stub seam, not against live
Postgres or Snowflake:** `tests/mdm/test_run_all_step_concurrency.py::
TestRunAllEnqueuesPublicationRequest::
test_full_chain_from_run_all_through_drain_reaches_graph_active` runs the
real chain — `MDMPipeline.run_all()` resolves companies and enqueues a
request, `compute_publication_freshness` reports `status="normal"` with
one `mdm_committed` row, `drain_publication_queue` (with a stubbed
`sync_fn`/`verify_fn`) claims and advances it to `graph_active`, and
`compute_publication_freshness` reports `status="normal"` again with the
row now counted under `graph_active` — against a real SQLAlchemy session
(SQLite here; the same `publication.py`/`pipeline.py` code path runs
unmodified against Postgres in prod). This is the strongest proof
available in this session's environment, but it is **not** the literal
"live end-to-end test (or prod dry run)" bullet 3 asks for — no real
Postgres, no real Snowflake, `sync_fn`/`verify_fn` are stubs.
**Still open, not done in this pass:** an actual prod dry run (`mdm run`
enqueues a request in the real MDM Postgres store, `mdm publication-drain`
claims it and performs a real Snowflake sync/verify) — blocked on: this
fix reaching a deployed image (see CLAUDE.md's image-rebuild table:
`edgar_warehouse/mdm/**` changed here, so an MDM image rebuild is
required), and an operator explicitly enabling the new EventBridge
schedule per the off-by-default design above.

**`/code-review` finding, fixed:** the Standards-axis pass caught that
`verify_fn`'s Snowflake verify call silently dropped the GH-251 review-
publish step (`_publish_graph_review`) that `mdm verify-graph` always makes
on a successful verify — exactly the "sibling path silently diverged"
pattern this repo's own CLAUDE.md documents repeatedly (`ShardedSilverReader
._TABLES`, the silver-loader OPERATE+SELECT gap, etc.). Fixed:
`verify_fn` now calls `_publish_graph_review` (gated behind a new
`--skip-review-publish` flag, mirroring `verify-graph`'s own flag/behavior
exactly, publish failures never fail the drain's own pass/fail result) so
every generation verified through `publication-drain` also lands in the
`MDM_GRAPH_REVIEW` operator dashboard, not just ones verified through the
manual `mdm verify-graph` path. New test:
`test_successful_drain_publishes_each_generation_to_the_review_contract`.

**Test coverage added:** 29 tests in `tests/mdm/test_graph_publication_queue.py`
(7 new `TestDrainPublicationQueue` cases: empty queue, successful
graph_active advancement, sync_fn exception → failed, verify_fn False →
failed, `max_requests` bound, expired-lease recovery, generation_id reuse
across the three transitions — plus the 22 pre-existing queue-mechanics
tests, unmodified); 9 tests in `tests/mdm/test_run_all_step_concurrency.py`
(3 new `TestRunAllEnqueuesPublicationRequest` cases plus the end-to-end
chain test above, alongside the 5 pre-existing run_all concurrency tests,
unmodified); 4 tests in `tests/mdm/test_publication_drain_cli.py`
(handler wiring: successful drain exits 0 and calls the stubbed Snowflake
classes, a failed verify exits 1, an empty queue exits 0 with nothing
drained, and the review-publish fix above); 8 tests in
`tests/architecture/test_mdm_utility_state_machine.py` (existing suite,
extended: `mdm_publication_drain` added to `_EXPECTED_MODES` and to the
no-override-workflows check). Full repo suite green (re-run after the
review-publish fix): 2701 passed, 4 skipped.

**Not yet specified (surfaced here, not resolved):** whether/how the
Ticket 08 generation-builder pipeline (`generation.py`) should eventually
be wired to real Snowflake execution — today it is pure Postgres bookkeeping
with no writer behind it, `mdm_graph_generation` sits empty in prod (as
Ticket 40 also observed independently), and nothing in this ticket's
"pure wiring" scope covers fixing that. A future ticket should decide
whether that pipeline gets wired to `SnowflakeGraphSyncExecutor` the way
this ticket's coordinator was, is repurposed, or is retired in favor of the
simpler `sync-graph`/`verify-graph` pair this ticket's coordinator already
uses successfully.
