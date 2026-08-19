# Decide Cutover/Rollback Mechanics

Type: grilling
Status: resolved
Blocked by: 09
Claimed by Claude on 2026-08-18.

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

## Answer

Specified for MDM's `ShardedSilverReader` cutover only (Ticket 09's named
first consumer) — not a generic policy for gold-building's later cutover,
which gets its own pass at that ticket's own time per this ticket's own
scoping instruction.

**1. Flip mechanism: a toggleable env var,
`MDM_SILVER_READ_TARGET=duckdb|snowflake`**, checked at every
`ShardedSilverReader` call site named in [Ticket 12](12-cutover-mdm-sharded-silver-reader-to-snowflake.md)
(the four sites in `edgar_warehouse/mdm/cli.py`). A deploy flips it — no
image rebuild needed to revert. This is a deliberate, narrow exception to
Ticket 05/07's "committed script over toggleable state" preference: that
preference was about *provisioning* steps (schema/grants — one-time,
should never silently drift), not about a *read-path selector* for a
first migration slice still proving itself. Delete the branch and the env
var entirely once gold-building has also cut over and the write path
retires (Ticket 09's own end state) — tracked as a cleanup item on
whichever ticket implements that retirement, not left as permanent
toggleable state.

**2. Correctness gate: a parity check mirroring `mdm verify-graph`'s
strict SQL comparison.** Before flipping the env var in prod, run MDM's
entity resolution and relationship derivation against both sources for
the same input (a real, already-loaded CIK slice) and diff: row counts
per table, and a full comparison of resolved `entity_id` assignments (not
just counts — two runs could match on count and still resolve different
CIKs to different entities). Land as a new `mdm verify-silver-parity`-
style command, same shape as `verify-graph`'s existing strict-parity
precedent, not an ad-hoc one-off script — this repo's standing preference
per this map's Notes ("every fix ships with real measurements against
real data/infra") and CLAUDE.md's repeated pattern of one-off manual
verification steps getting lost across account rebuilds (see this map's
own Ticket 11 finding the identical failure shape).

**3. Rollback trigger: a new CloudWatch alarm, not operator judgment
alone.** Mirrors ticket 81's `daily_incremental` alarm-coverage pattern
(CLAUDE.md). Concretely: alarm on the parity-check command (item 2) if run
on a recurring post-flip schedule, or on a sudden divergence in MDM's own
downstream row-count metrics (relationship counts per type) versus their
pre-flip baseline — exact metric TBD at implementation time, not
pre-specified here since it depends on what `mdm verify-silver-parity`
actually emits. **Rollback window: not a separate clock — bounded by
Ticket 09's existing 2-week dual-write deadline.** The DuckDB write path
stays alive regardless (gold-building hasn't cut over yet, so
`silver_store.py` keeps writing DuckDB no matter what), so flipping
`MDM_SILVER_READ_TARGET` back to `duckdb` stays cheap for as long as that
write path exists — i.e., for the full 2-week window and beyond, until
gold-building's own cutover retires DuckDB writes entirely. No new cost
estimate needed; this rides Ticket 08's existing figures by construction.

**4. What rollback restores: nothing needs unwinding.** MDM's resolution
*logic* is identical on both paths — only the *read source* changes.
Downstream writes (relationship rows, MDM Postgres state, the Snowflake
mirror/graph export) are produced by the same code regardless of which
silver copy fed it. A bad flip's writes are corrected by the next
resolution pass reading the correct source, under this repo's existing
idempotent-upsert pattern (`run_companies`' CIK-snapshot/resume-filtering
work, task #80 this session) and CLAUDE.md's "SEC data idempotency"
posture — not a manual undo. This assumes DuckDB and Snowflake silver
stay in content parity (guaranteed by Ticket 07's dual-write already being
live) — if the parity check in item 2 ever finds a real divergence, that's
a data bug to fix at the source, not a rollback-mechanics problem.

**5. Alerting: yes, folded into item 3** — no separate alerting decision
needed beyond the new alarm already specified there.

Threaded back into [Ticket 12](12-cutover-mdm-sharded-silver-reader-to-snowflake.md)'s
scope as concrete implementation requirements (env var, parity-check
command, alarm) rather than left as abstract policy.
