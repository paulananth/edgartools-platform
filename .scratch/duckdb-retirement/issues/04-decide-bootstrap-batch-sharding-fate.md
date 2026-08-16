# Decide bootstrap-batch's Sharding Mechanism Fate

Type: grilling
Status: open
Blocked by: 07

## Question

`bootstrap-batch` (run by `edgartools-prod-silver-mdm-gold`'s `BatchSilver`
Map, `MaxConcurrency=3`, always with `--artifact-policy skip` per CLAUDE.md's
key invariants) has its own working, measured, tested CIK-sharded
hydrate/publish mechanism — `pipeline-throughput-architecture`'s Ticket 12,
a real 76s→3.2s per-batch optimization. The closed silver-snowflake-
migration map's Ticket 06 flagged this as "likely obsolete once silver
lives natively in Snowflake (no more local monolith/shard split to reason
about at all), but not yet confirmed." This map's charting grilling
confirmed it's in scope here.

Decide: does `bootstrap-batch` simply start calling the same shared
`_run_submissions_bronze_then_silver` write site the other four commands
use (per this map's assumed target: parse writes only to the Snowflake
landing zone), eliminating the sharded hydrate/publish mechanism entirely?
Given `bootstrap-batch` is explicitly a *reprocessing* pipeline over
already-loaded bronze (not new SEC fetches) — does re-emitting already-
resolved rows into an append-only landing zone even do useful work, given
dbt's latest-`parse_sequence`-wins collapse would just dedupe them away?
If bootstrap-batch's actual purpose (re-deriving silver rows from bronze
after a parser/logic fix, without new SEC calls) still has value under the
new architecture, what does it look like — does it become a targeted
`INSERT ... SELECT`-style landing-zone reprocessing pass instead of a
local DuckDB rebuild? What happens to `MaxConcurrency=3` once shard
ownership (the thing that made concurrency safe) no longer exists as a
concept?

## Deliverable

A decided fate for `bootstrap-batch`'s current sharding mechanism and
what (if anything) replaces its reprocessing capability under a
DuckDB-free architecture.
