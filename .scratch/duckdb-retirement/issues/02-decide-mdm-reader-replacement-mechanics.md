# Decide MDM's ShardedSilverReader Replacement Mechanics

Type: grilling
Status: resolved
Blocked by: 07 (resolved)

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

## Answer

**Grounding, checked directly before deciding:** `SilverReader`
(`edgar_warehouse/mdm/resolvers/base.py:19`) is already a minimal
one-method Protocol (`fetch(sql, params) -> list[dict]`), its own docstring
anticipating "DuckDB or stub." Only `mdm/cli.py` constructs
`ShardedSilverReader` directly (6 call sites); resolvers never reference it
by name, only through `ResolverContext.silver` — small blast radius.
`EDGARTOOLS_PROD_MDM_SILVER_READER` (provisioned in the closed
silver-snowflake-migration map's Ticket 05) already has correctly
future-proofed grants (`SELECT ON ALL/FUTURE DYNAMIC TABLES`) — nothing to
revisit there. Every `silver.fetch(...)` call site across `pipeline.py`,
`adv_bulk.py`, the resolvers, and `universe.py` was checked for
DuckDB-specific dialect (`QUALIFY`, `EXCLUDE`, `PIVOT`, DuckDB-only
functions) — zero hits; this SQL is already Snowflake-portable as-is,
unlike Ticket 05's SQLite case.

- **Hard cutover, no transition window.** The minimal Protocol, small
  blast radius, and this map's own charting-time Notes (execution timing
  waits for in-flight verification, "not a longer Snowflake-silver soak
  period") all argue against carrying extra toggle-flag state that itself
  needs testing and eventual removal, for a swap this contained.
- **Credential activation: reuse the existing shared credential** — grant
  `EDGARTOOLS_PROD_MDM_SILVER_READER` as a secondary role on
  `EDGARTOOLS_PROD_LOADER`, the same credential MDM's export/sync-graph/
  verify-graph commands already authenticate as. This is the operator's
  explicit choice, made against the alternative (a dedicated secret for
  MDM's read path) that the reader role's own bootstrap SQL had left open.
  Recorded plainly: the bootstrap script's own comment notes this
  "partially reintroduces the write-role read-access overlap Ticket 03
  chose a dedicated role specifically to avoid" — any code already running
  as `EDGARTOOLS_PROD_LOADER` gains read access to `EDGARTOOLS_SILVER`
  incidentally, not just MDM's read path specifically. Chosen anyway for
  credential-provisioning simplicity, consistent with how every other MDM
  Snowflake operation already shares one secret.
- **What "resolution matches" concretely means:** apply Ticket 07's
  digest-based Table-Specific Reconciliation standard to the actual rows
  `silver.fetch(...)` returns (not to raw `entity_id` values, which aren't
  stable across runs by design — they're freshly generated per resolution).
  Given MDM's matching engine is a deterministic function of its input
  rows, proving row-level read equivalence implies resolution-outcome
  equivalence by construction. The concrete pass/fail check on top of that:
  for Ticket 07's bounded case-selected sample, same match decision
  (create-new vs. match-existing, and which existing entity) and same
  confidence score per input row across company/adviser/person/fund/
  security — not identical `entity_id` strings.
