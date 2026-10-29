# 15 Build: CAGR and the fundamental measures

Priority: 47, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/company-financials/issues/15-build-measures.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task. Status: open. Blocked by: 39, 44, 46. Map: [map](../../company-financials/map.md).

## Question

Implement the measures where ticket 07 decides, each with its "not meaningful" reasons; tests against the answer key of ticket 12.

## Checklist

Started 2026-10-29 16:52 ET on `claude/t47-measures` (operator, 2026-10-29: "Yes", to starting 47 while ticket 120's loads run).

- [x] The measure definitions as rules configuration: `rules/sources/sec.company-facts/measures.yaml` (ticket 39: ratios, returns in both forms, CAGR over 1, 3, 5 and 10 years; the financial-services list of ticket 42), a descriptive version name: `measures-2026-10-29.first-build`; 10 ratios, 3 returns in two forms, 6 growth series over 4 windows (40 measures a year); its grammar refused whole on a bad entry (unit tests) (2026-10-29 17:28 ET)
- [x] The SQL over silver (`edgar_warehouse/financials/measures.py`), run as counted temporary-table steps like the line items: reads `company_line_item`, and `company_fact` only for each year's annual periods ("fiscal year changed": a gap where the year end moved or a year held two annual periods, ticket 35); its literals, inline rows and counted steps shared with the line items in `financials/sql.py` (GoF consult, below); a growth rate worked at 40 places (one cohort rate differed in its last digit at PostgreSQL's default 16) (2026-10-29 17:28 ET)
- [x] Each filer's statement format and country read from the Company master (ticket 46: "read from Company"), passed to the SQL as rows; ROIC's statutory rate from the pinned `corporate-tax-rates`, the country through `sec-place-codes`' ISO crosswalk; `measures.from_company` reads `sic` and `state_of_incorporation` through the master-id lookup and the consumer contract; the command passes it to `build` as a function, tests pass invented filers (2026-10-29 17:28 ET)
- [x] Decided from the rulings: one vocabulary of null reasons across the spec, the skill, the answer key and the code ("denominator zero or negative", as ticket 43's spec and the skill word it; the key said "zero or less"); the oracle changed and the local key regenerated: exactly 5 null reasons change wording, no value or line item moves; key sha256 `f81ca4500d84ba3397b8642dca79d23751c083c0e1b5ec05d0f2c48915f41530` (the previous key kept beside it) (2026-10-29 17:28 ET)
- [x] Decided from the rulings: a filer with no Company master has no statement format ("unknown until Company is mastered", skill), so a measure that depends on the format is null, "statement format unknown"; every other measure is computed (integration test) (2026-10-29 17:28 ET)
- [x] The silver spec `silver-company-measure.yaml` (ticket 43's `company_measure`, keyed on `company_key` as ticket 46 corrected) and the command `edgar-warehouse silver measures`; as-at is the writer's `loaded_at` (the spec requires a named as-at) (2026-10-29 17:28 ET)
- [x] Tests with invented data: one per measure kind and per null reason (ticket 39, answer 5): 7 integration tests on PG16 cover every measure kind and all 10 null reasons, with both "fiscal year changed" cases (the year end moved; a year held two annual periods); 11 unit tests; with ticket 46's, 70 pass in 16 s (2026-10-29 17:28 ET)
- [x] The cohort against the answer key (ticket 44): every measure's value (at 10 places) and null reason equal, rows counted; the filers' SIC and place fed as the key reads them (mastering the cohort's Companies is ticket 48's proof: `company-on` holds 30 of the 368): 368 files, 168,360 measures on both sides and no row on one side only, 168,360 equal (value at 10 places and null reason), 86,487 with a value; the measure query 19 s, the whole run 6.7 min (`.scratch/company-financials/measures/compare_key.py`) (2026-10-29 17:28 ET)
- [x] The wording of "no statutory rate for the country and year" (deferred from 133): the cohort never meets it (0 of 168,360), so not asked; the words stand as the key had them, and an invented filer tests them (2026-10-29 17:28 ET)
- [x] GoF consult before code (2026-10-29 17:28 ET): leave it (`line_items.py` changed twice since written); one extraction only, the shared SQL text (`financials/sql.py`), now with two callers
- [ ] Three-axis review (Standards, Spec, GoF), findings fixed
- [ ] PR, CI green, merge
- [x] Learning → skill: `skills/company-financials/SKILL.md`, "Measures": built as SQL over the line items; one list of null reasons and their order; format and country from the Company master; a growth rate at 40 places, and an answer key rounded once (2026-10-29 17:28 ET)
