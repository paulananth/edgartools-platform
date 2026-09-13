# Ticket 01 frozen cohort and GLEIF publication

Date: 2026-09-11 America/New_York (source captures continued at 2026-09-12 UTC)
Mode: read-only production Snowflake; public GLEIF HTTPS downloads; no AWS,
Snowflake, MDM, or GLEIF data was mutated.

## Result

Ticket 01 produced a reproducible, ordered cohort of exactly 1,000 distinct
CIKs from 8,341 active current MDM companies that met the settled eligibility
boundary. The cohort was frozen before any entity-level GLEIF records were
examined. A single official 2026-09-11 16:00:00 UTC GLEIF Golden Copy
publication was then pinned across Level 1, Level 2 relationships, and Level 2
reporting exceptions.

The independent offline verifier regenerated the same 1,000 ordered rows and
the same cohort SHA-256, verified every local input digest and row count, and
streamed all three ZIP members through CRC validation without extracting them.

## Frozen Snowflake inputs

The one-statement query
[`01-freeze-company-inputs.sql`](01-freeze-company-inputs.sql) ran through the
configured `edgartools-prod` connection against `EDGARTOOLS_PROD` as a SELECT
only. It captured at `2026-09-12 00:37:45.182 Z`:

- current active `EDGARTOOLS_GOLD.MDM_COMPANY_ENTITY` rows;
- matching `EDGARTOOLS_SILVER.SEC_COMPANY` identity fields;
- all canonical `SEC_COMPANY_TICKER` rows where
  `source_name='company_tickers_exchange'`;
- addresses and former names; and
- the current parent-pointer / SEC subsidiary-evidence presence signal.

Eligibility was applied exactly as specified:

```text
MDM tracking_status = active
AND current MDM row (valid_to IS NULL)
AND SEC_COMPANY row exists
AND (SEC entity_type = operating OR CIK is in canonical ticker snapshot)
```

Input artifacts:

| Artifact | Rows | SHA-256 |
| --- | ---: | --- |
| [`01-sec-company-ticker-snapshot.jsonl`](01-sec-company-ticker-snapshot.jsonl) | 10,473 | `912d2a778032d448190e1fd76ba2189972407391713de5265e0f142ffe7e6ebf` |
| [`01-eligible-universe.jsonl`](01-eligible-universe.jsonl) | 8,341 | `a27f453b8c61c0f243f975536d9da64abd507715e91556428bd8c8281871242d` |
| [`01-company-cohort-1000.jsonl`](01-company-cohort-1000.jsonl) | 1,000 | `33af2a7df8a02a0838bc2b19a72c75dbe7552e7ba73b9004862f1ae3e18f367f` |
| [`01-universe-composition.json`](01-universe-composition.json) | derived | `14dc7a65656943d9468accb3a3f8b21df394dbcb1ab89f66dad4a856e5f31821` |

The query SHA-256 is
`f8a9ab1c4f40eeb5bc51e4adf9155aeec53c35fb7987e67cdcb65f791eb82ce1`;
the selection seed is
`gleif-company-augmentation-2026-09-11-v1`; and the query version is
`gleif-company-cohort-v1`. The complete machine-readable metadata is in
[`01-company-input-manifest.json`](01-company-input-manifest.json).

## Eligible-universe composition

| Dimension | Observed composition |
| --- | --- |
| Eligibility reason | 4,897 operating+ticker; 1,592 operating-only; 1,852 ticker-only non-operating |
| SEC entity type | 6,489 operating; 1,845 other; 7 investment (the latter two are eligible only through ticker membership) |
| Tracking status | 8,341 active |
| Canonical ticker presence | 6,749 present; 1,592 absent |
| SIC presence | 7,626 present; 715 absent |
| Incorporation state | 7,287 present; 1,054 absent; top codes: DE 3,313, E9 654, NV 516, MD 410, A1 172 |
| Address availability | 8,341 present; 0 absent |
| Former-name availability | 3,902 present; 4,439 absent |
| Short/common-name collision risk | 2,362 flagged; definition below |
| Existing relationship-evidence signal | 0 present; 8,341 absent |

The full incorporation-state distribution is retained in
[`01-freeze-verification.json`](01-freeze-verification.json). Collision risk is
defined before GLEIF comparison as a normalized name of at most 12 characters,
a one-token normalized name, or a normalized name shared by more than one row
in the eligible universe.

The relationship-evidence zero is an observed limitation of this specific
current signal: `MDM_COMPANY_ENTITY.parent_company_entity_id` or an SEC
subsidiary-evidence row for the registrant CIK. It is not evidence that a
company has no parent, and it must not be used to infer Level 2 absence.

## Deterministic cohort

Strata are mutually exclusive because they are assigned in the priority order
shown. Rows within each stratum are ordered by
`sha256(seed || ':' || cik)` and CIK. Final rows are ordered by stratum priority
and the same stable key.

| Priority | Stratum | Available | Selected |
| ---: | --- | ---: | ---: |
| 1 | Existing relationship evidence | 0 | 0 |
| 2 | Short/common-name collision risk | 2,362 | 100 |
| 3 | Former-name evidence | 2,572 | 100 |
| 4 | Sparse identity evidence | 782 | 100 |
| 5 | Ticker-only, non-operating | 481 | 150 |
| 6 | Operating and ticker-bearing | 1,378 | 200 |
| 7 | Operating without canonical ticker | 766 | 350 |
|  | **Total** | **8,341** | **1,000** |

The selected cohort's underlying eligibility reasons are 357 operating+ticker,
411 operating-only, and 232 ticker-only non-operating. The zero relationship
stratum was retained explicitly; its planned 100 rows were reassigned as 50
additional ticker-only and 50 additional operating-only rows. No substitute
relationship claim was invented.

## Fixed GLEIF publication

All files came from the same official Golden Copy publication listed by the
[GLEIF download service](https://www.gleif.org/en/lei-data/gleif-golden-copy/download-the-golden-copy):
`2026-09-11 16:00:00 UTC`. The exact immutable URLs are retained in
[`01-gleif-snapshot-manifest.json`](01-gleif-snapshot-manifest.json).

| Family | CDF | Declared records | Compressed bytes | SHA-256 |
| --- | --- | ---: | ---: | --- |
| Level 1 `lei2` | `LEI_3.1` | 3,428,477 | 927,550,946 | `1b6cd9cda3f94269fd406ee481842ea042b699e95eb5b8124b1496d4fda36a6a` |
| Level 2 relationships `rr` | `RR_2.1` | 487,721 | 34,953,042 | `089a2513d2b5d78fc6359c87ef4bc25a56ac7f58d6b3cb740b954e3ecd2bd0c3` |
| Level 2 exceptions `repex` | `REPEX_2.1` | 6,351,397 | 63,719,264 | `f205fd8dfc8dc04587fcd2465b741562bf39af3835916314b96033982023e831` |

The archives were retrieved from `2026-09-12T00:39:01Z` through
`2026-09-12T00:39:56Z`. HEAD and downloaded sizes agreed, content type was
`application/zip`, and ZIP CRC validation passed for all three. The compressed
corpus is 1,026,223,252 bytes. Its expanded size is approximately 15.9 GB, so
the archives were streamed and never extracted. The local `*.json.zip` files
are excluded by the scoped [`.gitignore`](.gitignore); URLs, sizes, ETags,
Last-Modified values, counts, and hashes remain trackable in the manifest.

## Reproduction and verification

1. Regenerate the Snowflake artifacts with
   `uv run python 01-freeze-company-cohort.py` while production remains
   read-only. This produces a new source capture; it is not needed to verify
   the frozen one.
2. Re-download the pinned GLEIF URLs with
   `uv run python 01-fetch-gleif-snapshot.py`. The downloader refuses an
   expected peak above 3 GiB or a result that would leave less than 4 GiB free.
3. Verify all frozen digests and regenerate the cohort solely from local inputs
   with `uv run python 01-verify-freeze.py --zip-crc`.

The recorded verification result is
[`01-freeze-verification.json`](01-freeze-verification.json):
`all_checks_passed=true`, cohort replay is 1,000 rows with SHA-256
`33af2a7df8a02a0838bc2b19a72c75dbe7552e7ba73b9004862f1ae3e18f367f`,
and all archive digests and CRCs passed.

Ticket 01 performs no matching or identity adjudication. Ticket 02 must consume
the frozen cohort and fixed local Level 1 corpus without querying a moving API.
