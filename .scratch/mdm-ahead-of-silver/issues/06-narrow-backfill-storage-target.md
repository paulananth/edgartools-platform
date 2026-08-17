# Narrow the Backfill Sweep's Storage Target

Type: grilling
Status: resolved
Blocked by: none (revisits [Ticket 02](02-decide-coupling-mechanism.md)'s "uniformly for both targets" line)

## Question

Surfaced immediately after wiring Phase B into the Stage 2 chain: the sweep
(`edgar_warehouse/mdm_entity_backfill.py`) currently only backfills
`mdm_entity_id` on DuckDB silver shards via `UPDATE`. [Ticket 02](02-decide-coupling-mechanism.md)
originally decided **both** targets get backfilled — DuckDB `UPDATE` plus a
second Snowflake landing-zone `INSERT`, on the assumption that "dbt's
existing latest-`parse_sequence`-wins collapse handles it natively, no new
capability needed."

That assumption doesn't hold as stated. Checked live against the actual
generated dbt models
(`infra/snowflake/dbt/edgartools_gold/models/silver/*.sql`, e.g.
`sec_company.sql`):

```sql
qualify row_number() over (
    partition by cik
    order by parse_sequence desc
) = 1
```

The collapse is **latest-wins per row**, not per column — the highest
`parse_sequence` row for a business key wins **wholesale**, every column.
None of the 6 target tables' generated models currently `SELECT
mdm_entity_id` at all (confirmed: zero matches across all 6). So a **thin**
backfill append (business key + `mdm_entity_id` only, everything else NULL)
would become the "latest" row for that key and **null out every other
column** — `entity_name`, `sic`, etc. — the exact kind of silent-corruption
incident this repo's CLAUDE.md 5-whys sections repeatedly warn about.

The user's follow-up instruction was terse: "Remove Duckdb 6 tables key only
one required." Read literally this could mean several different things, with
very different correctness implications:

1. **Drop DuckDB as a backfill target entirely** — the sweep stops issuing
   `UPDATE`s against silver shards, and Snowflake becomes the *only*
   required target (resolving "which one target" in favor of Snowflake, not
   DuckDB). This would also drop the sweep's `sec_fetch_active`-lease/
   `_hydrate_all_shards`/`_publish_shard_if_remote` machinery entirely — a
   real simplification, and arguably the right direction given DuckDB silver
   is the side already slated for retirement per the closed
   [silver-snowflake-migration](../silver-snowflake-migration/map.md) map.
2. **"Key only"** — does this mean the Snowflake append row carries *only*
   the business key + `mdm_entity_id` (a thin row)? If so, per the collapse
   mechanics above, this **will silently null out every other column** for
   that business key unless something else changes too (e.g. the collapse
   itself becomes column-aware via a `COALESCE`-across-versions read, not a
   single-row-wins `qualify`). A thin append is only safe if the read side
   changes; it is not safe as a drop-in with today's dbt models.
3. **"Only one required"** — confirms exactly one storage target is now the
   contract (superseding Ticket 02's "both"), but doesn't by itself say
   which one, or resolve the thin-vs-full-row question above.

This ticket exists because guessing wrong here has real data-corruption
stakes, not just wasted engineering time.

## Answer

**Snowflake only, both read and write — DuckDB drops out of the sweep
entirely.** Confirmed via two rounds of clarifying questions (the risk of
guessing wrong here was silent column-nulling data corruption, not just
wasted effort):

1. **Target**: Snowflake landing zone is now the sweep's sole target.
   Supersedes [Ticket 02](02-decide-coupling-mechanism.md)'s "uniformly for
   both targets, DuckDB `UPDATE` + Snowflake `INSERT`" — DuckDB is no longer
   a backfill target at all.
2. **Append shape**: full row, not thin. The sweep re-reads every column for
   a business key (not just key + `mdm_entity_id`) and re-emits a complete
   row with `mdm_entity_id` filled in. Required by the dbt collapse being
   latest-`parse_sequence`-wins **per row** (`qualify row_number() over
   (partition by <key> order by parse_sequence desc) = 1`, confirmed live
   against `sec_company.sql` and the other 5 generated models) — a thin
   append would null out every other column for that key.
3. **Read source**: also Snowflake, not DuckDB. The sweep queries the
   landing zone's own latest-per-key view (reproducing the same `qualify
   row_number()...=1` collapse dbt applies) for rows where `mdm_entity_id
   IS NULL`, looks up the resolved `entity_id` from MDM Postgres (unchanged
   — `MdmSourceRef` lookup), and re-INSERTs the full row with `mdm_entity_id`
   filled. This drops `_hydrate_all_shards`/`_publish_shard_if_remote`/
   `PromotionConflictError` handling and the `sec_fetch_active` lease
   requirement entirely — no shard file is read or written, so the
   silent-clobber risk that lease existed to guard against no longer
   applies. **New capability, not previously built**: nothing in the
   warehouse image currently issues an ad-hoc Snowflake `SELECT` for this
   purpose.

**`parse_sequence` checked and confirmed not a blocker**: it's a Snowflake
`SEQUENCE.NEXTVAL` default (`infra/snowflake/sql/bootstrap/
11_silver_landing_schema.sql`), assigned automatically on every `INSERT` —
callers never supply it, and every new row is guaranteed to outrank the row
it supersedes in the collapse. Full-row re-emission cannot silently no-op
for this reason.

**Residual race, accepted, not built around**: the sweep's SELECT (read the
current full row) and its later INSERT (re-emit it) are not atomic — a
genuinely concurrent write to the same business key in that narrow window
could have its data staled-over by the sweep's re-emission (the sweep's row
gets `mdm_entity_id` right but wins the collapse with data read
before the concurrent write). Mitigated narrowly (re-check `mdm_entity_id
IS NULL` immediately before each INSERT, shrinking the window), not solved
with a lock — same "accept a narrow, bounded risk over new distributed
locking infrastructure" reasoning [Ticket 02 of the sibling
snowflake-daily-load-trigger map](../snowflake-daily-load-trigger/issues/02-design-idle-detection-recheck-and-race-safety.md)
already used for a structurally similar problem.

**Consequence for what commit `47fe8fb5` just landed**: most of that
commit's ASL wiring (the `sec_fetch_active` second acquire/release cycle,
`wh_large_arn` sizing, `PromotionConflictError`-era assumptions baked into
its 8 architecture tests) becomes dead weight under this design — the new
sweep touches no shard files, so there's nothing left to protect with that
lease. This is expected rework, not a mistake in that commit; it was a real,
correctly-tested intermediate state before this ticket redrew the target.
Superseding changes land in a follow-up commit, not by reverting `47fe8fb5`.

**Also still required, not yet done by any commit**: add `mdm_entity_id` to
each of the 6 target tables' generated dbt silver model `SELECT` lists
(`infra/snowflake/dbt/edgartools_gold/models/silver/*.sql`) — without this,
a correctly-backfilled landing-zone value is invisible to every downstream
gold-layer consumer regardless of how correctly it was written.

**Addendum — a thin-append detour and a bug it surfaced:** immediately after
this Answer was first recorded, further investigation surfaced
`generate_silver_dbt_models.py`'s `_COALESCE_PRESERVING_COLUMNS` mechanism
(already live for `sec_accounting_flag`'s forensic scores), which appeared to
make a **thin** append (key + `mdm_entity_id` only) safe after all. Asked the
user again with that new information; they picked thin-via-`_COALESCE_PRESERVING_COLUMNS`
(commit `e8e801ec`). Before building the sweep around it, verified the
mechanism empirically (DuckDB reproduction of the exact `QUALIFY`/
`LAST_VALUE` SQL shape) and found it does **not** work as its own docstring
claims — `QUALIFY row_number()=1` still picks one winning row for every
column not itself wrapped in `LAST_VALUE(...IGNORE NULLS)`, so a thin row
still nulls out every other column. This is a live, pre-existing bug in
`sec_accounting_flag`'s own forensic-score backfill, not just a risk for
this feature — tracked separately at
[`.scratch/silver-landing-coalesce-bug/issues/01-thin-backfill-nulls-other-columns.md`](../silver-landing-coalesce-bug/issues/01-thin-backfill-nulls-other-columns.md)
since it predates and is unrelated to this map. Commit `e8e801ec` was
reverted (`ceef4a4d`) and this ticket's Answer stands as originally
recorded above: **full-row re-emission**, confirmed by the user a second
time once the thin-append option was shown to be unsafe. `_COALESCE_PRESERVING_COLUMNS`
was never applied to any of the 6 mdm_entity_id tables in what actually
shipped.
