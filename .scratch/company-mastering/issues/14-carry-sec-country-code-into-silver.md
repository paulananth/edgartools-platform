# Carry SEC countryCode into silver Company evidence

Type: task
Status: done (PR #720, merged `843228bd`, 2026-09-26). Production deploy order is in the PR: bootstrap SQL 21, then the dbt full refresh, then both images
Blocked by: none
Blocks: Shell and nine other postcode matches in the Company proving run

## Outcome

Preserve SEC address `countryCode` beside `stateOrCountry` in the approved
silver Company address path and the normalized Company matching evidence.
Do not infer a country from a state code or rewrite existing bronze.

## Checklist

- [x] Verify the source-to-silver-to-MDM mapping on pinned SEC bronze records,
  including Shell (`0001306965`) and records with a missing country code.
- [x] Rebuild the affected silver slice from approved bronze and show the ten
  waiting postcode matches are accounted for without weakening the state veto.
  (Locally; production rows need re-landing after deploy, see below.)
- [x] Keep loader idempotency and the existing SEC capture contract intact:
  no fetch, `--force` or bronze write path changed; old landings read as before.

## Facts found (Claude, 2026-09-26)

- The 10 postcode matches are ticket 08's parity result
  (`research/08-parity.json`): read from bronze, the declared rules bind 3,050
  Companies; read as silver lands the address, 3,040. The 10 are exactly the
  filers whose country is only in `countryCode`: 0000845982 Smith & Nephew,
  0001094324 Sify, 0001123799 Wipro, 0001214816 AXIS Capital, 0001306965
  Shell (`X0`), 0001520504 Volaris, 0001526125 GDS, 0001590560 uniQure,
  0001713923 Jianpu, 0001792267 Burning Rock.
- Over all 76,230 filers in the ticket 08 bronze scan, `stateOrCountry` and
  `countryCode` never both hold a value: 43,269 have only the first, 2,468
  only the second, the rest neither. So "the first, else the second" is the
  same reading the rules were measured on, not a new inference.
- `stage_address_loader` never read `countryCode`; silver's `country`
  column holds `stateOrCountryDescription`, which is empty for these filers.

## Implementation checklist (Claude, 2026-09-26)

- [x] The extractor lands `countryCode` as a new nullable `country_code`
  column; nothing else in the row changes.
- [x] The silver schema carries it everywhere one column must go: the
  `silver_schema.py` snapshot, `11_silver_landing_schema.sql`'s CREATE TABLE,
  a new idempotent `21_silver_landing_company_country_code.sql` for live
  tables, wired into `install.sh` after 20, and the dbt silver model.
- [x] The Company adapter reads the country from `state_or_country`, else
  `country_code`. A landing written before this change has no such column
  and prepares exactly as before.
- [x] Unit tests: the extractor, the adapter (a `countryCode`-only filer, a
  US filer, a filer with neither, an old landing), and one test that all six
  places name the column.
- [x] Real bronze, zero SEC requests: copy the 10 filers' and two controls'
  submissions documents from prod bronze, rebuild their silver slice with
  `bootstrap-batch`, and show Shell's business address lands `X0` and its
  Company record carries country GB. Done 2026-09-26 07:35 ET: S3 reads only,
  the run behind a dead proxy wrote no new bronze object; Shell `X0` → GB,
  the other nine GB, IN, BM, MX, CN, NL; Apple `CA` → US; QVC (no address)
  none.
- [x] Ticket 08 parity re-run with the silver reading done by the production
  adapter: 3,050 bind, 0 differences from bronze, and the state veto
  unchanged. Done 2026-09-26 07:51 ET (`research/14-parity.json`, the same
  census `107c0e04…` as ticket 08): `silver_country_code` binds 3,050 with 0
  only-production and 0 only-research; the old `silver` reading still binds
  3,040 (the 10). No new binding appears, so the state veto holds exactly
  what it held.
- [ ] Full suites, three-axis review, PR, CI green.

## Readings and decisions (Claude, 2026-09-26, from the three-axis review)

- **"Do not infer a country from a state code"** is read as: land SEC's own
  `countryCode` as SEC wrote it, and invent no country SEC did not write.
  It does not remove the ticket 08 rule that a US state code means the
  United States (`names.edgar_jurisdiction`): the measured matching rules
  depend on it, and removing it would drop "US" from 43,269 state-only
  filers and break the 3,050 parity. For the operator to confirm.
- **No mapping version change.** The Dataset Contract's body is unchanged,
  and a landing written before this change prepares the same records. A new
  landing is a new capture with its own publication key (the pinned
  addresses file's digest is in it). Deploy the MDM image with the
  warehouse image: an older MDM image preparing a new landing would give
  one key and revision two different records, which the Stage refuses as a
  contradictory publication (fails closed).
- **The Company address field changes too.** The selected `address`
  field's country comes from the same `business_address`, so Shell's
  master address gains GB, not only its matching evidence.
- **Deploy order.** Apply `21_silver_landing_company_country_code.sql`
  before any warehouse image with this change captures (the landing COPY
  matches by column name and drops a column the table lacks, and does not
  reload those files after the ALTER), then
  `dbt run --select sec_company_address --full-refresh`.
- **Existing production rows** keep `country_code` NULL until each CIK's
  submissions document is landed again. The ten waiting matches bind in a
  Proving Run only if it reads a capture made after deploy (or the ten are
  re-landed from bronze first); tickets 05 and 06 must pin such a capture.

## Found outside this ticket (recorded, not changed)

- `sec_company_ticker.cause_reference` is written by
  `silver_landing_store.py` but is in neither `11_silver_landing_schema.sql`
  nor `silver_schema.py`, and `19_silver_landing_retirement.sql`, which adds
  it to the live table, is run by neither `install.sh` nor
  `deploy-snowflake-stack.sh`. The install coverage test
  (`test_no_bootstrap_sql_file_is_missing_from_the_full_plan`) misses it
  because it matches by number and `19_installer_role.sql` also starts with
  19.
- `infra/scripts/load_local_silver_landing.py` creates a local table from
  the first Parquet it sees and inserts by name, so a local silver database
  whose `sec_company_address` predates this change refuses new Parquet
  ("column country_code does not exist"). Migration 20's columns met the
  same limit.
