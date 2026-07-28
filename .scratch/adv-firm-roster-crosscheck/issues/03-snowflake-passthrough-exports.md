# 03 — `SEC_ADV_PRIVATE_FUND` + `SEC_ADV_FIRM_ROSTER` Snowflake passthrough exports

**What to build:** Two new Snowflake passthrough source tables, both mirroring the
existing `SEC_SUBSIDIARY_EVIDENCE` "raw silver rows exported straight through" pattern
(not the dimensional `fact_key`/`company_key` modeling `PRIVATE_FUNDS` uses):

- `SEC_ADV_FIRM_ROSTER` — exports ticket 01's new `sec_adv_firm_roster` silver table
  (CRD, `dataset_period`, the ~8 aggregate private-fund columns).
- `SEC_ADV_PRIVATE_FUND` — a raw passthrough export of the *existing* `sec_adv_private_fund`
  silver table (already populated by the shipped `advFilingData` pipeline), carrying
  `adviser_crd_number`, `fund_index`, `private_fund_id`. This is needed because the
  existing gold `PRIVATE_FUNDS` table (`_build_fact_adv_private_fund` in
  `serving/gold_models.py`) is CIK-keyed, not CRD-keyed, so there is otherwise no
  CRD-keyed fund count in Snowflake to reconcile against.

Both need: a `CREATE TABLE` in `01_source_stage.sql`, a merge-key registration in
`03_source_load_wrapper.sql`, and passthrough-style entries in `sources.yml` matching
`SEC_SUBSIDIARY_EVIDENCE`'s existing entry.

**Merge-key correction (found during implementation, 2026-07-28):** the stated
`(adviser_crd_number, dataset_period)` key for BOTH tables is only correct for
`SEC_ADV_FIRM_ROSTER` (its silver PK, set by ticket 01, is literally that pair).
`sec_adv_private_fund` has no `dataset_period` column (only `source_dataset_period`), and
even aliased that pair is not row-unique — one CRD reports many `fund_index` rows per
period, and `03_source_load_wrapper.sql`'s MERGE does no dedup, so this would throw a
Snowflake "Duplicate row detected" error on the first firm with >1 fund. `SEC_ADV_PRIVATE_FUND`
uses its real silver PK, `(accession_number, fund_index)`, as the Snowflake merge key
instead — structurally identical to how `SEC_EMPLOYMENT_EVENT` registers
`(accession_number, event_index)`. `adviser_crd_number`/`source_dataset_period` are still
exported as ordinary passthrough columns (needed by ticket 04's reconciliation), just not
as the merge key. `accession_number` itself must also be in the exported column list
(the original list above omits it; `fund_index` alone isn't a distinguishing identifier
without it). See ticket 04's file for a related, more significant finding this surfaced
about that ticket's own join semantics.

Also note the real registry chain for a Snowflake-exported passthrough table is **6 code
locations plus 3 infra files**, not just the 3 infra files named above:
`edgar_warehouse/config/gold_schemas.yaml` (schema block), `edgar_warehouse/serving/gold_models.py`
(schema binding + `_build_sec_...` function + `build_gold()` registration),
`edgar_warehouse/serving/targets/snowflake.py` (`export_map`), and
`edgar_warehouse/infrastructure/run_manifest_builder.py` (`SNOWFLAKE_EXPORT_TABLES`) — confirmed
against the `SEC_SUBSIDIARY_EVIDENCE` precedent's actual reference chain, in addition to
`01_source_stage.sql`/`03_source_load_wrapper.sql`/`sources.yml`.

**Blocked by:** Ticket 01 (Firm Roster parser + silver table) — `sec_adv_firm_roster` must
exist in silver before it can be exported. (`sec_adv_private_fund` already exists and is
unaffected by ticket 01/02.)

**Status:** ready-for-agent

- [ ] Both tables are created via bootstrap SQL (`01_source_stage.sql`) and registered for
      merge-key-based incremental load in `03_source_load_wrapper.sql`.
- [ ] Both tables have `sources.yml` entries following `SEC_SUBSIDIARY_EVIDENCE`'s existing
      passthrough pattern.
- [ ] A manifest-driven load run (dev) populates both tables from silver and they are
      queryable in Snowflake with the expected CRD-keyed rows.
- [ ] `dbt compile` succeeds referencing both new sources.
