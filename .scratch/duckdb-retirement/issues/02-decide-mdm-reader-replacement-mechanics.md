# Decide MDM's ShardedSilverReader Replacement Mechanics

Type: grilling
Status: open
Blocked by: 07

## Question

The closed silver-snowflake-migration map's Ticket 03 already decided the
*target*: MDM's `ShardedSilverReader`/`_TABLES` allowlist retires in favor
of Snowflake-native GRANTs on a dedicated reader role — explicitly framed
as fixing the exact silent-gap failure shape that caused the
`INSTITUTIONAL_HOLDS`/`EMPLOYED_BY` incident (a table missing from a
hardcoded allowlist silently skipped, not errored). That decision did not
cover the *mechanics* of getting there, and live evidence this session
confirms it's still unimplemented: an in-flight `mdm run` task read DuckDB
shards directly (`silver_shard_hydrated` events against
`s3://.../warehouse/silver/sec/shards/shard-N.duckdb`).

Decide: does `MDMPipeline`'s `SilverReader` protocol get a new
Snowflake-backed implementation alongside the existing
`ShardedSilverReader` during a transition window, or is this a hard
cutover? If a transition window, how is it toggled (env var, config flag,
something else) and what's the removal trigger? Apply the proof standard
from [Decide the Cutover Validation Standard](07-decide-cutover-validation-
standard.md) concretely here: what does "MDM resolution against Snowflake
silver matches MDM resolution against DuckDB silver" actually mean for
company/adviser/person/fund/security resolution specifically — same
resolved entity IDs, same match confidence scores, or a looser bar? Also
confirm the already-provisioned `EDGARTOOLS_PROD_MDM_SILVER_READER` role
(created in the closed migration map's Ticket 05) has the grants this
actually needs, or whether it needs revisiting.

## Deliverable

A decided cutover mechanism for MDM's silver read path (hard cutover vs.
transition window, and how), plus the concrete pass/fail criteria this
consumer's swap must clear per the validation standard.
