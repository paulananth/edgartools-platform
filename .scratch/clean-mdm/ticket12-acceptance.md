# Ticket 12 acceptance

Native GLEIF publication ingestion and accounting are implemented locally. This
report does not authorize a rebuild, production cutover or automatic matching.

## Evidence

- Full retained September 11 JSON ZIP archives: 10,267,595 records across L1/RR/REPEX,
  exact frozen raw hashes and counts verified. Approximately 1.03 GB compressed,
  15.93 GB expanded; peak RSS 37,801,984 bytes. Runtime 1,184.503 seconds total.
  [Machine-readable results](ticket12-native-qualification.json) pin each hash,
  count and measurement. This is archive/parser proof, not a complete 10-million-row
  database mastering run or statistical match qualification.
- Real PostgreSQL 16 targeted run: **74 passed, no skips**, 216.78 seconds. Files:
  `tests/mdm/test_clean_gleif_source.py`,
  `tests/integration/test_clean_native_publications.py`,
  `tests/integration/test_clean_mdm_postgres.py`.
- Final REPEX shape/enum regression: **23 native unit tests passed**. The enum was
  verified against [GLEIF REPEX 2.1](https://www.gleif.org/en/lei-data/access-and-use-lei-data/level-2-data-reporting-exceptions-2-1-format).
- Targeted mypy with `--check-untyped-defs --follow-imports=silent
  --ignore-missing-imports`: seven modified boundary modules passed.
- Ruff and `git diff --check` passed. [Independent reviews](ticket12-review.md): both
  reported issues fixed; no unresolved findings.
- Full repository run: **3,530 passed, 1 failed, 5 skipped**, 613.70 seconds.
  The sole failure was a pre-existing assertion requiring the old Snowflake-only
  error prefix; runtime has supported both local Postgres and Snowflake since #657.
  Updated the test to inject source failure and assert no MDM session opens.
  Final rerun of that complete test file plus final native parser cases:
  **37 passed**, 4.16 seconds. The full suite was not rerun after this test-only
  repair; the final parser fix also has that targeted coverage.
  All five skips are opt-in live SEC/Finnhub/yfinance tests; **zero Clean MDM
  PostgreSQL tests skipped**. [Machine-readable evidence](ticket12-acceptance.json)
  records commands, JUnit hashes, failures/skips and final source hashes.

The focused tests exercised native membership rejection before writes, exact ranges,
partial predecessor rejection, source delta replay, frozen-manifest conflicts,
duplicate delivery, lost export acknowledgements, retained scope exclusions versus
blocking malformed evidence, and SEC + GLEIF fields on one Company with source
provenance. A later RETIRED source correction preserves the SEC Company and name.
Existing core cases cover rollback, lost commit acknowledgements, field correction,
merge reversal, authoritative conflicts and relationship reprojection.

JSON faults include duplicate keys, truncation, trailing/nonfinite values, counts,
hashes and size bounds. XML fixtures cover all three member roots, header agreement,
DTD rejection and simple JSON/XML equivalence. Full real XML archives have not been
qualified. Shared relationship tests cover native direct/ultimate types and cycles.

## Reproduce

```bash
uv run --frozen --extra s3 --extra mdm-runtime --extra mdm pytest \
  tests/mdm/test_clean_gleif_source.py \
  tests/integration/test_clean_native_publications.py \
  tests/integration/test_clean_mdm_postgres.py -q
uv run --frozen --extra s3 --extra mdm-runtime --extra mdm pytest tests -q
```

For full archive qualification, read each file named in
`.scratch/gleif-company-augmentation/research/01-gleif-snapshot-manifest.json` from the
existing local archive cache and call `gleif_source.inspect_archive`. Supply its
frozen `sha256`, `record_count`, `cdf_version`, `json.zip` format, full publication
mode, no delta start, and frozen publisher timestamp `2026-09-11T16:00:00Z`. Consume
through EOF. The report's `canonical_source_hash` and `domain_content_hash` are the
returned values. Capture elapsed monotonic time and `resource.getrusage` peak RSS
(on macOS, bytes). This reads local artifacts only and does not register a source.

## Deliberate limits

The new Source Contract runner/Rules Database, Dataset Contract version migration,
automatic policy interpreter and rule activation remain unimplemented. Full raw
archive re-verification per invocation is too expensive for a production rebuild;
use the future authenticated parsed-partition path. The scoped native fixture does
not approve all-global GLEIF Company creation. Export/graph tests use local contract
sinks; no hosted consumer has been cut over. No persistent source or MDM database
was changed, and original source archives remain retained.
