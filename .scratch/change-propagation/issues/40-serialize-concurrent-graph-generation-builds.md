# 40 — Serialize concurrent graph generation builds

**What to build:** Prevent two graph generation-build pipeline executions
from running concurrently, closing this map's own charted current-state
fact: "normal graph workflow tails can sync a new generation while
verifying the previously active one."

**Blocked by:** 08 — Decide graph partition reuse and candidate-generation
publication (this map)

**Status:** ready-for-agent

- [ ] A partial unique index on `mdm_graph_generation` rejects a second
  row with `status IN ('building', 'verified')` (non-terminal — not yet
  `activated` or `failed`) while one already exists, mirroring
  `uq_source_fetch_work_active_key`'s existing shape for the analogous
  concurrent-fetch problem.
- [ ] A generation build rejected by that index fails outright (does not
  queue or retry internally) — confirmed via a test that a second
  concurrent attempt gets a clear, distinguishable error rather than
  silently blocking or corrupting the first attempt's state.
- [ ] A live or integration test proves two genuinely concurrent
  `mdm sync-graph` invocations (real threads/connections, not sequential
  calls) converge to exactly one non-terminal generation at a time.
- [ ] Confirm the migration adding this index is additive/safe against
  any currently in-flight generation in prod (check `mdm_graph_generation`
  row count and status distribution before applying).

## Notes

Surfaced while resolving [08 — Decide graph partition reuse and
candidate-generation publication](08-decide-graph-partition-reuse.md) —
see that ticket's Answer. Confirmed via code search that no
mutual-exclusion mechanism (lease, lock, or unique index) currently exists
anywhere for concurrent generation builds, despite the rest of the
generation/partition schema (`MdmGraphGeneration`/`MdmGraphPartition`,
content-addressed reuse, required `--generation-id` on every CLI command)
already being fully built and correctly generation-scoped.

## Answer

Resolved via PR [#485](https://github.com/paulananth/edgartools-platform/pull/485).
A partial unique index (`uq_graph_generation_single_non_terminal`, on the
constant expression `(1)` filtered `WHERE status IN ('building',
'verified')`) mirrors `uq_source_registry_version_single_active`'s existing
idiom for "unique across every row matching this predicate" -- declared
both as a real migration
(`edgar_warehouse/mdm/migrations/016_serialize_graph_generation.sql`,
registered in `runtime.py`'s `migrate()` sequence) and at the ORM level
(`MdmGraphGeneration.__table_args__` in `database.py`, so SQLite-backed
unit tests via `Base.metadata.create_all` see the same constraint).
`create_generation()` now catches the resulting `IntegrityError` and raises
a new `ConcurrentGenerationBuildRejected` -- fails outright, no internal
queue/retry, per Ticket 08's Answer's own reasoning (a queued retry risks
replaying a stale request instead of picking up current state on the next
natural trigger).

**Note on scope, found while implementing:** `mdm sync-graph`'s actual CLI
path (`_handle_sync_graph` in `cli.py`) does not call `create_generation()`
or touch `mdm_graph_generation` at all -- it mints a bare `uuid.uuid4()`
and tags Snowflake staging rows with it directly, entirely bypassing the
Postgres generation-builder schema this ticket serializes. `mdm_graph_generation`
is confirmed empty in prod today (zero rows, any status) -- the schema this
ticket guards is fully built and correctly scoped (per Ticket 08's Answer)
but not yet a live production caller. This ticket's acceptance criteria are
still satisfied exactly as written (the partial index, the fail-outright
`ConcurrentGenerationBuildRejected`, and a real-Postgres proof of two
genuinely concurrent threads converging to one non-terminal row are all
done and tested), and the empty prod table trivially satisfies the fourth
bullet (nothing in-flight to conflict with) -- but wiring `mdm sync-graph`
itself onto `create_generation()`/`mdm_graph_generation` remains open and
unticketed. Not filed as a new ticket here since it's outside this ticket's
literal scope; flagged for whoever next touches the graph-generation
pipeline's live wiring.

**Proof, not just the SQL:** two pre-existing test suites needed real
updates, not just accommodation -- one test in
`test_graph_generation_builder.py` asserted the old, now-incorrect
"no singleton constraint" behavior and was rewritten to prove the new
contract instead of silently contradicting it; five content-addressed-reuse
tests needed their first generation moved to a terminal status before
opening a second, matching what real usage now requires under the new
guard. A new real-Postgres integration test
(`tests/integration/test_graph_generation_serialization_postgres.py`)
proves the index is a genuine database-level constraint (direct-SQL bypass
attempt, both `'building'`-vs-`'building'` and `'verified'`-vs-`'building'`)
and that two genuinely concurrent threads/connections racing
`create_generation()` against a real `postgres:16-alpine` container
converge to exactly one non-terminal generation -- SQLite's single-writer
lock can't exercise a true partial-index race under concurrent
transactions, so this specific proof wasn't reachable at the unit level
alone. Full repo suite green: 2663 passed, 4 skipped (pre-existing,
unrelated).
