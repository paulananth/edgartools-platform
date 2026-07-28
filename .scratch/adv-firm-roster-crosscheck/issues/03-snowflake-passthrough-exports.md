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
`03_source_load_wrapper.sql` (merge key `(adviser_crd_number, dataset_period)` for both,
matching how other composite-key passthrough tables like `SEC_EMPLOYMENT_EVENT` are
registered), and passthrough-style entries in `sources.yml` matching
`SEC_SUBSIDIARY_EVIDENCE`'s existing entry.

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
