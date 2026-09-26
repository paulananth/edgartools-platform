# Carry SEC countryCode into silver Company evidence

Type: task
Status: claimed (Claude, branch `claude/company-mastering-14-country-code`, 2026-09-26 07:19 ET)
Blocked by: none
Blocks: Shell and nine other postcode matches in the Company proving run

## Outcome

Preserve SEC address `countryCode` beside `stateOrCountry` in the approved
silver Company address path and the normalized Company matching evidence.
Do not infer a country from a state code or rewrite existing bronze.

## Checklist

- [ ] Verify the source-to-silver-to-MDM mapping on pinned SEC bronze records,
  including Shell (`0001306965`) and records with a missing country code.
- [ ] Rebuild the affected silver slice from approved bronze and show the ten
  waiting postcode matches are accounted for without weakening the state veto.
- [ ] Keep loader idempotency and the existing SEC capture contract intact.

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

- [ ] The extractor lands `countryCode` as a new nullable `country_code`
  column; nothing else in the row changes.
- [ ] The silver schema carries it everywhere one column must go: the
  `silver_schema.py` snapshot, `11_silver_landing_schema.sql`'s CREATE TABLE,
  a new idempotent `21_silver_landing_company_country_code.sql` for live
  tables, wired into `install.sh` after 20, and the dbt silver model.
- [ ] The Company adapter reads the country from `state_or_country`, else
  `country_code`. A landing written before this change has no such column
  and prepares exactly as before.
- [ ] Unit tests: the extractor, the adapter (a `countryCode`-only filer, a
  US filer, a filer with neither, an old landing), and one test that all six
  places name the column.
- [ ] Real bronze, zero SEC requests: copy the 10 filers' and two controls'
  submissions documents from prod bronze, rebuild their silver slice with
  `bootstrap-batch`, and show Shell's business address lands `X0` and its
  Company record carries country GB.
- [ ] Ticket 08 parity re-run with the silver reading done by the production
  adapter: 3,050 bind, 0 differences from bronze, and the state veto
  unchanged.
- [ ] Full suites, three-axis review, PR, CI green.
