# Silver rows are checked when they land

Priority: 105, tier 2. Map: [Rebuild priorities](../map.md).

Type: task (code, silver writer; data-quality skill). Status: done (#1055 merged 2026-10-17 14:25 ET). Blocked by: none. Raised by: 80 (Onboard OpenFIGI with the skills), 2026-10-17.

## Why

The first silver table from an onboarding (`rules/sources/openfigi/silver-listing.yaml`, ticket 80) has data quality checks that nothing runs:
- profiling's checks for the part, listed in `rules/sources/openfigi/profile.yaml` (a missing key column, codes of the four code sets, and three `hierarchy_invalid` flags on `marketSector`, with 11,870, 10,249 and 340 rows);
- the checks ticket 80 deferred to its silver part: a FIGI's shape and check digit, a ticker and an exchange code present together, and the 6 listing rows whose name differs under one FIGI.

A Dataset Contract's checks run in its reading (`checks` on a mapped table) and `quality.yaml` names only Dataset Contract codes. A silver table spec (`edgar_warehouse/silver_writer/spec.py`) holds no checks, and `edgar-warehouse silver land` runs none. So a silver table's checks show in the Data Catalog but never set a row aside or flag it.

## Question

Where a silver table's checks are declared (the spec, or `quality.yaml` keyed by table), and what `silver land` does with a row that fails one (flag it in a column, or set it aside with its reason), the way the data-quality skill does for a Dataset Contract.

## Checklist

- [x] GoF consult on `edgar_warehouse/silver_writer/`: one commit since it was written (#879), no churn; leave its shape. Checks run where the writer already holds the delivery (`checks.py`, three plain functions in a table), and the `quality` column is added like the MDM id columns (2026-10-17 14:01 ET)
- [x] Ruling: operator, "Flag, land the row (Recommended)" (2026-10-17 14:01 ET): a failing row lands, the check's id in its `quality` column; `exception` keeps a row out. Checks live in the silver spec (`checks`: `identifier`, `in_set`, `one_value`)
- [x] Built: `edgar_warehouse/silver_writer/checks.py`, the spec's `checks`, the `quality` jsonb column with a comment naming each check, the landing report's counts (`quality`, `quality_updated`); `rules/identifiers/figi.yaml` (shape only). Tests: unit (each check, a tie, an empty value, a forged `quality` refused, refused specs) and real PG16 (flags read back as jsonb, an exception's rows kept out, a rerun changes nothing); 271 affected tests pass (2026-10-17 14:12 ET)
- [x] OpenFIGI's listing checks in `silver-listing.yaml`, each measured with the writer's own code on the 2026-10-15 capture: FIGI shape 0, one name per FIGI 0, one market sector per exchange 11,805, per security type 10,249, per second security type 340 (profiling: 11,870, 10,249, 340). "Ticker and exchange together" dropped: 632,078 listings carry a ticker and no exchange code, as OpenFIGI gives them. The OpenFIGI test lands an invented FIGI off its shape flagged (2026-10-17 14:12 ET)
- [ ] ~~FIGI check digit~~ moved to 107 (FIGI's check-digit family): it doubles every second character from the left, which no declared family does (0 failures in 51,623 FIGIs that way; 46,384 under "luhn over letter values")
- [x] Three-axis review (Standards, Spec, GoF); PR, CI green, merged on green: #1055, merged on green 2026-10-17 14:25 ET
- [x] Three-axis review (Standards, Spec, GoF). Fixed: `in_set` reads a text column only, and no check reads a nested column (a number compared as text was refused wrongly, a list crashed); a snapshot table takes no exception check (the row kept out would be deleted); the report counts rows flagged and refused, beside each check's failed rows; the `quality` comment names flag checks only; the FIGI prefix is two consonants; one value per group is documented as per delivery; a test proves flags that move between deliveries leave an append table's row unchanged (a mutation comparing flags fails it). GoF: leave it (three check kinds, no history). 72 tests pass; on the capture, 14,142 rows flagged, none refused (2026-10-17 14:19 ET)
- [ ] ~~`context silver` shows a table's checks~~ deferred to 18 (agent context views): `silver.table_context` (migration 001) shows no checks, so an agent learns them from the `quality` column's comment only; showing them needs a silver migration 002
- [x] Learning → skill: `skills/data-quality/SKILL.md` (a silver part's rules go in the spec's `checks`, measured with the writer's code first; a check that flags what the source gives on purpose is no check), `skills/data-onboarding/SKILL.md` and `docs/specs/profiling/findings.md` section 6 (2026-10-17 14:12 ET)
