# Platform validation and clean-up

## Destination

The rebuilt platform's core is validated with evidence and runs on one
design. That means:
- Bookkeeping, the Change Journal, Company mastering and the operator skills
  are validated with evidence;
- legacy tables and code are gone;
- Clean MDM lives in schema `mdm`, and every table explains itself;
- the rules skill is split into Data Onboarding and Refining Rules, written
  for agents;
- Person feed 1 is onboarded through Data Onboarding as that skill's real
  test.

## Notes

- The operator asked for this on 2026-09-30: "validate bookkeeping, change
  journal, company mastering, and all skills and review current database
  design"; "remove all legacy tables, make mdm_v2 to mdm"; Data Onboarding
  and Refining Rules as separate skills, "super clear for agents"; "onboard
  another domain like person"; "make the table self explainable".
- Standing ruling: "Rebuild is the only system … don't preserve old
  behaviour".
- Each slice gets its own branch and PR. CI must be green. Merge only on the
  operator's word.
- No local test run over 5 minutes.
- A hosted database is dropped only on the operator's word for that
  database.

## Tickets

1. [Validate the core and review the database design](issues/01-validate-core-and-db-design.md): done
2. Remove legacy tables and their code: 2a legacy MDM, 2b legacy
   Bookkeeping and the run coordinator, 2c migrations 001–022
3. Re-baseline Clean MDM under schema `mdm`, commented, with the names the
   operator rules on
4. Split the rules skill into Data Onboarding and Refining Rules, written
   for agents, with cold trials
5. Onboard Person feed 1 (SEC individual filers) with Data Onboarding
6. [Relationship rules for Companies and People](issues/06-relationship-rules.md):
   the operator ruled relationships are mastered with MDM (2026-10-01). 06a,
   the GLEIF accounting parent, is merged and approved; next is the
   relationship rules document, then 06b (Forms 3/4/5)

## Not yet specified

- Person feeds 2–5 (Forms 3/4/5 owners, 8-K 5.02, DEF 14A, ADV Schedule
  A/B)
- The one enabled command that runs mastering (review finding 3)
- GLEIF batches sized by bytes (finding 5); the census and missing
  former names (finding 6)

## Decisions so far

- Table names (2026-09-30). Asked to rename the unclear MDM tables in the
  rebuild, the operator chose **"Rename all as proposed"**:
  - `mdm_v2` → `mdm`
  - `assertion` → `source_reading`
  - `identity` → `master_entity`
  - `projection` → `current_record`
  - `observation` → `run_batch`
  - `assessment(_event)` → `match_proposal(_event)`
  - `deferred_record` → `set_aside_record`
  - `publication(_event)` → `outbox(_event)`
  - `commit_batch_core` + `commit_batch` → `save_batch`
  Applied in slice 3.
- Mode names (2026-09-30). The operator chose **"Adopt as proposed"**:
  - **Bookkeeping**: init, migrate, plan, validate, run, status, recover. It
    owns running a feed, and mastering too (`run` with target `mdm`).
  - **Change Journal**: init, migrate, plan, validate, deploy, status,
    recover-delivery.
  - **Data Onboarding**: init, migrate, identify, profile, map, quality,
    metadata, test, approve, switch-on.
  - **Refining Rules**: change-mapping, change-quality, change-matching,
    test, approve, switch-on.
  - The command `rules migrate` becomes `rules load` / `rules unload`.
  Applied in slice 4.
- Legacy scope (2026-09-30). Asked how far slice 2 should go, the operator
  chose **"Everything not reachable"**: delete every module the enabled
  commands cannot reach. That is 214 files and about 57,500 lines, plus
  their tests, and includes the warehouse orchestrator, parsers, serving
  exports, explore and market. A parser needed later (e.g. ownership for
  Person) is re-added through Data Onboarding. The AWS deploy script and
  dbt gold are rebuilt afterwards. Slices:
  - 2a: CLI entry points and legacy MDM;
  - 2b: the rest of the unreachable code and its tests;
  - 2c: deploy scripts, installers, dbt.
