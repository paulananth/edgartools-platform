# Decide graph partition reuse and candidate-generation publication

Type: grilling
Status: resolved
Blocked by: 02, 06

## Question

How should exported MDM changes rebuild only affected graph partitions while
still producing one complete immutable Relationship Generation Snapshot that
can be fully verified and atomically activated?

Decide the stable partition key, content hash independent of generation
watermark, property/evidence hash inputs, unchanged-partition reuse, changed
node/edge rebuild, retirement and eligibility filtering, generation identity
across retries, parity/completeness checks, and pointer activation. Reconcile
the existing Postgres generation-builder lifecycle with physical Snowflake
graph publication and eliminate normal workflow tails that sync one generation
while verifying another.

## Answer

Grilled 2026-08-26. Almost everything this ticket asks to decide is
already fully built — `MdmGraphGeneration`/`MdmGraphPartition` (schema
comment: "07-04, RSYNC-04") already implement the stable partition key
(`generation_id`/`kind`/`type_name`/`shard_index`, unique constraint), a
content hash computed from an intrinsic fingerprint (`kind`, `type_name`,
`shard_index`, `mdm_watermark`, `rule_version`, `schema_version`,
`input_fingerprint`) deliberately reusable *across* generations (its own
docstring: "a partition with a `content_hash` matching a prior `built`
partition from any generation is reused"), a separate `property_hash`,
explicit `status IN ('pending','building','built','reused','failed')`
with `reused_from_partition_id`, node/edge kind separation, and a full
`building → verified → activated`/`failed` generation lifecycle. The CLI
already requires an explicit `--generation-id` on the relevant
subcommands rather than operating on an implicit "whatever's active."
"Retirement/eligibility filtering" and "parity/completeness checks" map
onto the extensive release-readiness vocabulary already decided and built
in an adjacent map (`Relationship Coverage Record`, `Per-Type Exact
Relationship Parity`, `Approved Relationship Exclusion`, `Relationship
Applicability Ledger`) — not re-decided here.

**Generation identity across retries:** confirmed via the CLI's own
observed default pattern (`generation_id = args.generation_id or
str(uuid.uuid4())`) — a retry mints a fresh generation, it does not resume
a failed one in place. Matches this system's general pattern elsewhere
(ledger epochs, revisions) of immutable attempts that are superseded, not
patched.

**Reconciling the Postgres generation-builder lifecycle with physical
Snowflake publication:** already structurally answered, not a new
decision — Postgres (`graph.py`) owns generation/partition planning and
status tracking; Snowflake SQL, driven by that Postgres state
(`snowflake_graph.py`'s `SnowflakeGraphSyncExecutor`/`SnowflakeGraphVerifier`),
does the actual physical work. This split was already confirmed
deliberate (not duplicated) by the `single-path-per-layer` map's own
investigation.

**The one genuinely real, still-open gap — this map's own charted fact
from before any ticket existed**: "normal graph workflow tails can sync a
new generation while verifying the previously active one." Confirmed via
code search: no mutual-exclusion mechanism (lease, lock, or unique index)
exists anywhere preventing two concurrent generation-build pipeline
executions, despite this repo using exactly that pattern
(`uq_source_fetch_work_active_key`) for the analogous problem elsewhere.
This is not a parameter-confusion bug — generation-id scoping is already
correct throughout — it's a missing system-level serialization guard.
Decided: a partial unique index on `mdm_graph_generation` limiting
non-terminal generations (`status IN ('building','verified')`, not yet
`activated`/`failed`) to one at a time — chosen over a lease-table/advisory-lock
approach (more new code, same guarantee) and over Step-Functions-level
mutual exclusion (external to the data model, weaker guarantee). A
rejected concurrent attempt fails outright rather than queuing — a queued
retry risks replaying a now-stale request instead of picking up current
state on the next natural trigger, matching this repo's general
current-state-driven-retry preference. Concrete migration and test
deferred to new [Ticket 40](40-serialize-concurrent-graph-generation-builds.md).
