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

## Not yet specified

- Person feeds 2–5 (Forms 3/4/5 owners, 8-K 5.02, DEF 14A, ADV Schedule
  A/B)
- The one enabled command that runs mastering (review finding 3)
- GLEIF batches sized by bytes (finding 5); the census and missing
  former names (finding 6)
