# Silver rows are checked when they land

Priority: 105, tier 2. Map: [Rebuild priorities](../map.md).

Type: task (code, silver writer; data-quality skill). Status: open. Blocked by: none. Raised by: 80 (Onboard OpenFIGI with the skills), 2026-10-17.

## Why

The first silver table from an onboarding (`rules/sources/openfigi/silver-listing.yaml`, ticket 80) has data quality checks that nothing runs:
- profiling's checks for the part, listed in `rules/sources/openfigi/profile.yaml` (a missing key column, codes of the four code sets, and three `hierarchy_invalid` flags on `marketSector`, with 11,870, 10,249 and 340 rows);
- the checks ticket 80 deferred to its silver part: a FIGI's shape and check digit, a ticker and an exchange code present together, and the 6 listing rows whose name differs under one FIGI.

A Dataset Contract's checks run in its reading (`checks` on a mapped table) and `quality.yaml` names only Dataset Contract codes. A silver table spec (`edgar_warehouse/silver_writer/spec.py`) holds no checks, and `edgar-warehouse silver land` runs none. So a silver table's checks show in the Data Catalog but never set a row aside or flag it.

## Question

Where a silver table's checks are declared (the spec, or `quality.yaml` keyed by table), and what `silver land` does with a row that fails one (flag it in a column, or set it aside with its reason), the way the data-quality skill does for a Dataset Contract.

## Checklist

- [ ] GoF consult on `edgar_warehouse/silver_writer/` (spec, writer, sink)
- [ ] Where a silver table's checks live, and what a failed check does (flag or set aside), following the data-quality skill
- [ ] Build it; a test per check family on real PG16
- [ ] OpenFIGI's listing checks declared and run on its table
- [ ] Three-axis review (Standards, Spec, GoF); PR, CI green, merged on green
- [ ] Learning → skill
