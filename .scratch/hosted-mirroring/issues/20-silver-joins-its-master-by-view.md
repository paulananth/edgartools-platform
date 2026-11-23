# 20: Silver finds its master by a join on a view, not by a written id

Status: open
Type: task

Operator, ticket 16: a join inside the data database on the master id; one view per master kind; the master id is the only id that crosses;
the source's own key is a plain column; "kiss and 7 wastes keep it clean". The rule is in `skills/mdm-engineering/MASTERING-STANDARD.md`.

Today a silver row carries a written text column per link (`mdm_id_column`, in 16 silver specs), filled at landing by `silver_writer/writer.py`
from `mastering/reads.master_ids` and refreshed by `--finish` (`refresh_ids`, `set_ids`, `link_keys`). Gold joins that column to `mdm.mastering_master`.
The mirror carries `mastering_master` and `mastering_identifier` but not `mastering_record`, which holds the binding.

## Checklist

- [ ] Failing test first: a silver row joins its master through the view on `source_code` and `source_key`, and a merged-away id answers with its survivor (the test fails on a store with no view)
- [ ] `mastering_record` gets `source_key` (plain, beside `source_code`), written where the row is inserted (`mastering/store.py`) and carried by the PostgreSQL and MySQL schema files; the init creates it (no DDL at run time)
- [ ] One view per master kind in schema `mdm` (company, security, person, fund_structure): `master_id`, `source_code`, `source_key` and the kind's identifiers; the survivor of a merge, never a merged-away id
- [ ] Silver specs: each link names its `source_code` and `source_key` column; `mdm_id_column` and the written id column leave the 16 specs, the spec checker and the table builder
- [ ] Every silver table joins its master (operator, 2026-11-22: "every silver table should join to the appropriate master"): 15 of 20 specs link today; the other five are `company_line_item_input` and `company_measure_input` (each carries `company_key`: give each the company link), and `relationship`, `relationship_evidence` and `relationship_path` (a relationship's ends are master ids already, and its two child tables carry `relationship_id`: join through it). A unit test fails any silver spec with neither a master link nor a declared way to its master
- [ ] A link that cannot turn empty in Gold (operator, 2026-11-22: "gold must have best data quality fix it create data quality rules using dq rules"): two data quality rules, each failing a test first, each a check that fails the load's readiness, never a silent empty:
      - **One master per identifier:** `<kind>_identifier_conflict` view lists each namespace and value that two masters of the kind hold; the check passes only at zero rows for each namespace an identifier link uses (an identifier that names two masters is the defect in `MASTERING-STANDARD.md`, so it is counted and shown to a steward before Gold reads it)
      - **Every link resolves:** the share of a silver table's rows whose key finds a master is at least the link's declared `inclusion`; the Gold generation writes one test per fact link (`gold/views.py`), and `data-quality` names both rules
- [ ] Gold reads the mirror, and a mirror replicates tables, not views (read from how PostgreSQL replication works, not yet confirmed against Snowflake's documentation): the binding Gold joins must be a table. Operator, 2026-11-22, chose "Narrow binding table". The five places that move a record's master (`bind_record`, `repoint`, `split`, `save_records`, `clear`) make a table kept current by the merge a second copy of `entity_id`; recommended instead is the links pattern: `master_binding` (source_code, source_key, kind, master_id) is a silver table built whole at `--finish` from `mastering_record` (one scan per load), mirrored, joined by Gold and by any in-database reader. The per-kind views in `mdm` then go: nothing reads them
- [ ] Retire `refresh_ids`, `set_ids`, `link_keys`, the landing-time fill and the `--finish` master-id fill, with their tests and the init runbook text
- [ ] The mirror list names the views; Gold's `dim_*` and fact views join on the view's `master_id` (`gold/views.py`, `destination/gold/gold.yaml`); the exposure and gold tests pin it
- [ ] Prove on the cohort: every row's master equals the one the written id gave (0 differences), before the written column is dropped
- [ ] Learning → skill: mdm-engineering (MASTERING-STANDARD.md already holds the rule; add the retired fill to the data-operations finish text), or "none"
