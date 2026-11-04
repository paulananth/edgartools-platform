# 119: One set of code for every database engine

Status: resolved (2026-11-03 20:39 ET, operator: "yes" to a review against the merged work; the ruling was carried out by the storage-layer tickets below). It was parked 2026-10-19 13:30 ET (operator: "Park this for now"). Claimed 2026-10-19 13:23 ET, Claude. Takes over the
open parts of `.scratch/company-native-three-engines/issues/01` and
`.scratch/company-three-engine-readiness/issues/01`.

## The operator's ruling

2026-10-19, asked how to switch Company on for MySQL and SQL Server: "No
porting all must be config driven this is a disaster one set of code for all
components and skills".

What follows from it:

- The database engine is configuration: a store's connection names its
  engine, and nothing else changes between PostgreSQL, MySQL and SQL Server.
- No second copy of any store for another engine. Each store's logic is
  written once and the same code runs on all three, PostgreSQL included.
  Today's PostgreSQL-only functions are retired, not kept beside the new
  code.
- Every check the database enforces today (append-only rows, approval
  before activation, leases and fences, generation gates) keeps being
  enforced, and each one is tested on each engine.

## What is PostgreSQL-only today (measured 2026-10-19 13:23 ET, origin/main)

| Store | Migration SQL lines | Functions, procedures, triggers | Python text SQL with PostgreSQL operators |
|---|---|---|---|
| Rules | 251 | 4 | 14 |
| Change Journal | 132 | 9 | 1 |
| Bookkeeping | 851 | 27 | 4 |
| MDM | 4,521 | 36 | 68 |
| RDM | 403 | 12 | 3 |
| Silver | 49 | 0 | 3 |

On MySQL and SQL Server every store refuses with "requires PostgreSQL 16".
Only the mdm-engineering skill's storage adapter
(`skills/mdm-engineering/scripts/database_adapter.py`) runs on all three: it
writes each capability once and compiles it for the engine.

## Checklist

- [x] Inventory of the PostgreSQL-only code, by store (2026-10-19 13:23 ET, table above)
- [x] (2026-11-03 20:39 ET) Design: one way to write a store's tables, checks and atomic operations once for every engine, extending the skill adapter's approach; GoF consult; each database-enforced check classified (a grant, a constraint, or an atomic operation), with how it is tested per engine: done by the storage-layer work: a shared facade and native core (Rust `control-contract`, `source-contract`) with durable storage chosen by engine; the PostgreSQL migration history is kept immutable, so the old PostgreSQL SQL stays in the tree as history (#1237)
- [x] (2026-11-03 20:39 ET) Engine test servers for this work (the shared ones stay untouched): isolated MySQL 8 and SQL Server 2022 stores beside the PostgreSQL ones: CI starts an isolated container per engine (`tests/storage_adapters/conftest.py`, the `ci.yml` matrix `postgresql, mysql, mssql` for the skill adapter, `postgresql, mysql` for the stores)
- [x] (2026-11-03 20:39 ET) Slice 1: Rules on the one code, all three engines, its checks tested per engine; three-axis review; PR: Rules on PostgreSQL and MySQL (#1235, 2026-10-30; SQL Server deferred)
- [x] (2026-11-03 20:39 ET) Slice 2: Change Journal: `edgar_warehouse/change_journal/storage.py` names its table per engine (#1121, 2026-10-22)
- [x] (2026-11-03 20:39 ET) Slice 3: Bookkeeping: normal Bookkeeping storage on PostgreSQL and MySQL (#1237, 2026-10-30; control qualification #1241)
- [x] (2026-11-03 20:39 ET) Slice 4: MDM (the Company tables first): the MDM store runs on PostgreSQL and MySQL (#1121, #1212 closes the qualified MySQL MDM completion records, 2026-10-28); the installed MDM workflow runs on both in CI
- [x] (2026-11-03 20:39 ET) Carry ticket 120's merge changes, which land first (operator, 2026-10-20 17:42 ET: "Ship 120 first (Recommended)"): the detail-list selection in `survivorship.select_details` and its use in `merge.py`, MDM migration 022 (`mdm.detail_version`, its triggers and `detail_rows()`), Bookkeeping migration 007 (a run another live run reads is not compacted) and `verified_units`' newest capture; their tests (`tests/mdm/test_clean_details.py`, `tests/integration/test_clean_detail_rows_postgres.py`, `test_configured_bookkeeping_postgres.py`) pass on every engine
- [x] (2026-11-03 20:39 ET) Slice 5: RDM and Silver: RDM search parity and PostgreSQL/MySQL callers (#1147, 2026-10-23); Silver indexes and exact transport (#1231, 2026-10-29); SQL Server Silver stays deferred (`skills/data-operations/SKILL.md`)
- [ ] ~~Company switched on in a MySQL store and a SQL Server store from the same rules and captured inputs as `company-on`; the three hold the same Companies~~ deferred: MySQL is qualified by the installed MDM workflow in CI (every PR); the SQL Server stores are deferred (`skills/data-operations/SKILL.md`: "SQL Server Silver remains deferred"), and a Company comparison across engines has no owner
- [x] (2026-11-03 20:39 ET) Learning → skill: none new; `skills/data-operations/SKILL.md` already says what runs on PostgreSQL, MySQL and SQL Server
