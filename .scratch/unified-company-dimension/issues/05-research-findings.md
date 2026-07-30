# Research findings — ticket 05 (Implement unified COMPANY dimension), live-state check

Captured 2026-07-29 against `edgartools-prod` (Snowflake account `xcpclkf-kb19989`).
Ticket 05 itself is unclaimed and gated ("Do not start until operator explicitly
claims this ticket") — this is fact-finding only, no implementation.

## What "duplicate" actually means here

There is no row-level duplication *within* either table. This confirms the map's
own framing: the problem is **two parallel tables** for one concept (SEC CIK
identity vs MDM entity identity), not corrupted/duplicated rows in one table.

## Live counts (2026-07-29)

| Check | Result |
|---|---|
| `EDGARTOOLS_GOLD.COMPANY` row count | 32,970 |
| `COMPANY` distinct `COMPANY_KEY` | 32,970 (no internal duplicates) |
| `EDGARTOOLS_GOLD.MDM_COMPANY` row count | 32,970 |
| `MDM_COMPANY` distinct `ENTITY_ID` | 32,970 (no internal duplicates) |
| `MDM_COMPANY` rows with NULL `CIK` | 0 |
| CIKs with >1 distinct `ENTITY_ID` in `MDM_COMPANY` | **0** |
| CIKs in `COMPANY` missing from `MDM_COMPANY` | **0** |
| CIKs in `MDM_COMPANY` missing from `COMPANY` | **0** |

**This is a materially cleaner state than the design assumed.** The map's own
baseline (2026-07-26) recorded a 2-row skew (~32,968 `COMPANY` vs ~32,970
`MDM_COMPANY`) and ticket 02's design explicitly built for a **multi-match**
CIK↔entity_id case ("multi-match single pick + flag"). As of today the join is
a **perfect 1:1**, zero orphans on either side, zero multi-match. The
multi-match/flag logic ticket 02 designed is still worth keeping (it's a
correctness safeguard, not dead code — a future MDM re-run could reintroduce a
multi-match), but there is currently no backlog of disagreement rows to migrate
around.

## Schema reality (grounds ticket 05's scope items)

- **`EDGARTOOLS_GOLD.COMPANY`** is a **dbt-managed dynamic table**
  (`infra/snowflake/dbt/edgartools_gold/models/gold/company.sql`) — a plain
  pass-through select from `source("edgartools_source", "COMPANY")`:
  `company_key, cik, entity_name, entity_type, sic, sic_description,
  state_of_incorporation, fiscal_year_end, last_sync_run_id`. No MDM columns
  today.
- **`EDGARTOOLS_GOLD.MDM_COMPANY`** is **not** dbt-managed — it's written by
  `edgar_warehouse/mdm/export.py`'s MERGE export path
  (`"company": ("mdm_company", "MDM_COMPANY", db.MdmCompany)`, line 24),
  targeting the table declared in
  `infra/snowflake/sql/bootstrap/07_mdm_export_targets.sql`. Columns: `ENTITY_ID,
  CIK, CANONICAL_NAME, EIN, SIC_CODE, SIC_DESCRIPTION, STATE_OF_INCORPORATION,
  FISCAL_YEAR_END, TICKER, PRIMARY_TICKER, PRIMARY_EXCHANGE, TRACKING_STATUS,
  PARENT_COMPANY_ENTITY_ID, VALID_FROM, VALID_TO`.
- Ticket 05 scope item 1 ("enrich `COMPANY` via dbt... left join MDM by CIK")
  is straightforward against this schema: `company.sql` would add a join
  against `MDM_COMPANY` (or the underlying MDM export source) on `CIK`, pulling
  `entity_id`, `display_name` (MDM `CANONICAL_NAME`-preferring per ticket 03),
  `tracking_status`, `parent_company_entity_id`. Given the current perfect 1:1
  join, no `ROW_NUMBER()`/pick-one logic is *required* today, but ticket 02's
  design says to keep it as a safeguard — the dbt model should still guard
  against a future multi-match rather than assume today's clean state holds
  forever.
- Ticket 05 scope item 3 ("stop dual `mdm export` MERGE to `GOLD.MDM_COMPANY`")
  is a one-line change in `export.py`'s target mapping (remove/redirect the
  `"company"` entry) once `MDM_COMPANY` becomes a compat view over the enriched
  `COMPANY`.

## Bottom line

The design (tickets 01–04, all resolved) is still architecturally sound and
nothing in current prod state contradicts it. If anything, live state is
*more* favorable to implementation than when the design was frozen — the
messy multi-match case ticket 02 designed for isn't currently present, so a
first implementation pass can be simpler than the design worst-case, while
still keeping the flag-based safeguard for when it recurs. Ticket 05 remains
correctly gated on an explicit operator claim (`Type: task`, "Do not start
until operator explicitly claims this ticket") — this research doesn't change
that gate, it just confirms there's no new information blocking someone from
claiming it.
