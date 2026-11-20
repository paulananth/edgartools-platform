# 05: Mirror only the tables Gold reads

Status: resolved

The operator, 2026-11-20: "List out the tables needed for replication from MDM ... merge stage should not be mirrored
only the table required for gold should in the list adjust skills first".

The mirror took all 19 tables of the exposure list. Gold reads 4 of them. Sizes in the data database (counts and sizes
only): the merge stage `mastering_record` 10.5 GB (never mirrored), `mastering_master` 5.0 GB, `nport_holding` 2.7 GB,
`company_fact` 2.1 GB, `mastering_identifier` 1.5 GB; 25.2 GB in all.

Gold's reads (its dbt sources file): `public.mastering_master`, `public.mastering_identifier`, `silver.thirteenf_filing`,
`silver.thirteenf_holding`. The other 15 come out with one `ALTER_MIRROR` remove.

## Checklist

- [x] Skill first: HOSTED-MIRRORING.md "Mirror only what a reader in Snowflake reads" and FINAL-TABLES.md: the mirror is the Gold project's reads, bounded by the exposure list; working tables are never mirrored; skill lints pass 2026-11-20 09:33 ET
- [x] `mirror_sql.py` takes `--reads` (a dbt sources file) and refuses a read not on the exposure list; new `alter` adds and removes the difference; `tests/unit/test_exposure_mirror_sql.py` (the repository's Gold project gives the four tables) 2026-11-20 09:33 ET
- [x] `ALTER_MIRROR('edgartools_mirror', remove_tables => 15 tables)` as the mirror operator (operator: "use ANANP11"; words in the approvals log), then `REFRESH_MIRROR` 2026-11-20 09:35 ET
- [x] Read back: `LIST_MIRRORED_TABLES` showed the four tables `REPLICATING` at 09:36 ET (16, then 4 listed); superseded the same day by ticket 06, which put the silver tables back 2026-11-20 09:36 ET
- [x] Learning → skill: HOSTED-MIRRORING.md, "Mirror only what a reader in Snowflake reads" 2026-11-20 10:34 ET
