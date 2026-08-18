# Decide Cutover/Rollback Mechanics

Type: grilling
Status: open
Blocked by: 09

## Question

[Decide Consumer Cutover Order](09-decide-consumer-cutover-order.md) names
which consumer (MDM's `ShardedSilverReader` or `gold_models.py`'s Python
builders) moves off DuckDB first. This ticket specifies how that specific
cutover actually happens and unwinds if it goes wrong — the map's
previously-identified fog item ("how an in-flight execution's understanding
of 'silver' transitions across the cutover boundary," moved here from
Ticket 06's cross-reference) made concrete for the consumer Ticket 09 named.

Specify:

1. **Flip mechanism.** Is the migrated consumer's data source chosen by a
   feature flag/env var (e.g. `SILVER_READ_TARGET=duckdb|snowflake`) that a
   deploy can toggle without a code rollback, or does the code itself
   change to read Snowflake unconditionally (rollback = redeploy the prior
   image)? The former is safer for a first slice but adds a branch to
   delete later; the latter matches this map's existing preference (Ticket
   05/07) for committed, re-runnable scripts over toggleable state.
2. **Correctness gate before flipping.** What proves the Snowflake-native
   read path produces the same answer as the DuckDB path it replaces, for
   real prod data, before the flip is trusted? (e.g. a parity check
   comparable to `mdm verify-graph`'s strict SQL parity checks, or
   `--skip-native-app`'s candidate-vs-active generation pattern already
   used elsewhere in this pipeline.)
3. **Rollback trigger and window.** What observable signal (a specific
   alarm, a specific verify-step failure, an operator judgment call) says
   "revert," and how long after the flip is rollback still cheap — bounded
   by Ticket 08's dual-write cost estimate, since keeping both paths
   write-live longer costs more but keeps rollback cheap longer.
4. **What "rolled back" actually restores.** If the migrated consumer wrote
   anything downstream while on the Snowflake path (e.g. MDM relationship
   rows, if MDM goes first per Ticket 09) that DuckDB-path code wouldn't
   have produced identically, does rollback need to also unwind those
   writes, or is downstream state considered append-only/reconcilable on
   the next full pass (matching this repo's existing SEC-data-idempotency
   posture from CLAUDE.md)?
5. Whether this cutover needs its own alerting (mirroring ticket 81's
   `daily_incremental` alarm-coverage pattern, cited elsewhere in
   CLAUDE.md) for "the flip happened but the new path is silently wrong,"
   not just "the new path crashed."

Resolve with a concrete mechanism and rollback runbook for the Ticket
09-named consumer specifically — not a generic policy for all three
consumers, since MDM and gold-building have different downstream blast
radii.
