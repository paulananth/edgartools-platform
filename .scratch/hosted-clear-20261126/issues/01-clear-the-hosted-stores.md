# Clear the hosted stores for a fresh load

Status: open
Type: task
Owner: claude (operator, 2026-11-26: "using skills clear out the hosted postgress")

Operator, 2026-11-26: "using skills clear out the hosted postgress". Scope: the hosted Snowflake Postgres `EDGARTOOLS_PROD_MDM` holds six stores in three databases. The data database (MDM, RDM, Silver) and the control database (Bookkeeping, Change Journal) are cleared table by table; the config database (Rules) is kept whole. The databases, schemas, roles and logins stay in place.

## Checklist

- [x] Drain: no load running (`load_jobs.py --status`: 0 running, 30 of 30 done; the container holds only the activity worker and the exporter), no Bookkeeping runs in `running`, `waiting` or `blocked`, no client sessions on the data database (only the two Snowflake-managed `pg base extension worker` sessions, which hold no state and no transaction), no replication slots and no WAL senders. The instance is READY, `LIST_MIRRORS` names no mirror and the mirror target database is absent. 2026-11-26 11:16 ET
- [x] Back up the control stores and RDM before the clear: `pg_dump` (PostgreSQL 17 client) of the control database (33 MB, all six control tables) and of the `rdm` schema (488 KB, all ten RDM tables); both dumps listed with `pg_restore --list` and are readable. The dumps and the manifests are in the private stores folder. 2026-11-26 11:16 ET
- [x] Plan and apply the reset for the five stores with one reviewed plan digest each: MDM 13 tables, RDM 10, Silver 21, Bookkeeping 5, Change Journal 1; every action TRUNCATE, `--require-all-tables` on each, the two retention triggers named (`rdm.code_set_version.no_truncate_version`, `journal.event.immutable_event`) and restored enabled after the truncate. Each store's apply is one transaction with the approval receipt in the private stores folder. 2026-11-26 11:16 ET
- [x] Restore the published RDM code sets from git: 11 code sets, 11 versions, 7,272 published codes, every pin ok. The RDM store holds 7,272 codes, 7,272 labels, 7,272 paths, 11 code sets, 11 versions, 1,110 crosswalk rows and 8 levels. 2026-11-26 11:16 ET
- [x] Verify the clear: every resettable table of MDM, Silver, Bookkeeping and Change Journal reads 0 rows; `mdm.migration` 1 and `silver.table_spec` 21 stay; the config database is untouched (2 policies, 21 dataset readings, 21 rules used, 0 drafts); both retention triggers read enabled (`O`). 2026-11-26 11:16 ET
- [x] Set the run's state files aside: `chain-fresh-v1.log` and `chain-hosted-lanes-20261125.log` named the store's old generation and were renamed, never deleted. The next load starts a fresh state file. 2026-11-26 11:16 ET
- [x] `readiness.py` full pass: READY on all eleven checks (CODE, DOCTOR, GUARDS, REFERENCE, CAPTURES, QUIET, ROOM, AUDIT, LOGINS, STATE, REGISTERED). 2026-11-26 11:16 ET
- [x] Learning → skill: `data-operations/HOSTED-LOADS.md` records that a table reset leaves the run's state file naming the old generation, which the next load must set aside, and that the RDM backup is a schema-scoped `pg_dump`. 2026-11-26 11:20 ET

## Comments

2026-11-26: The reset is the same one the reset ticket ran on 2026-11-25, before the hosted load `hosted-lanes-20261125` filled the stores again. This run clears them once more, on the operator's words, and leaves the store READY for the next load. The Change Journal held 257,580 events and Bookkeeping 531 pipeline runs before the clear; the captures on this machine are untouched, so the next load reads the same files again.
