# 119: One set of code for every database engine

Status: parked (2026-10-19 13:30 ET, operator: "Park this for now"). Claimed 2026-10-19 13:23 ET, Claude. Takes over the
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
- [ ] Design: one way to write a store's tables, checks and atomic operations once for every engine, extending the skill adapter's approach; GoF consult; each database-enforced check classified (a grant, a constraint, or an atomic operation), with how it is tested per engine
- [ ] Engine test servers for this work (the shared ones stay untouched): isolated MySQL 8 and SQL Server 2022 stores beside the PostgreSQL ones
- [ ] Slice 1: Rules on the one code, all three engines, its checks tested per engine; three-axis review; PR
- [ ] Slice 2: Change Journal
- [ ] Slice 3: Bookkeeping
- [ ] Slice 4: MDM (the Company tables first)
- [ ] Slice 5: RDM and Silver
- [ ] Company switched on in a MySQL store and a SQL Server store from the same rules and captured inputs as `company-on`; the three hold the same Companies
- [ ] Learning → skill
