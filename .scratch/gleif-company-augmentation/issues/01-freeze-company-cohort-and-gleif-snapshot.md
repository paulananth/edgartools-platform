# Freeze the 1,000-company cohort and GLEIF snapshot

Type: research
Status: resolved
Blocked by: (none)

## Question

What exact frozen MDM, SEC ticker, SEC company, address, former-name, and GLEIF
Golden Copy inputs produce a reproducible cohort of exactly 1,000 current
company-eligible CIKs for the formal comparison?

## Required evidence

- Apply the settled eligibility rule to active current MDM rows:
  `SEC_COMPANY.ENTITY_TYPE = 'operating'` or membership in the captured
  official SEC ticker snapshot.
- Report the full eligible-universe count and composition by eligibility reason,
  tracking status, ticker presence, SIC presence, incorporation state, address
  availability, former-name availability, short/common-name collision risk,
  and existing relationship evidence.
- Select exactly 1,000 distinct CIKs using declared non-overlapping strata and a
  deterministic seed before examining GLEIF outcomes.
- Obtain one official GLEIF Level 1 Golden Copy bulk publication and the
  corresponding Level 2 relationship and reporting-exception publications.
- Record source URLs, publication timestamps, extraction timestamps, row
  counts, file sizes, hashes, query text/version, seed, and canonical cohort
  hash in a run manifest.
- Keep all artifacts local and read-only with respect to production systems.

## Done when

A second process can regenerate the same ordered 1,000 CIKs and verify every
input digest without consulting a moving API endpoint.

## Answer

Resolved by [`../research/01-freeze-results.md`](../research/01-freeze-results.md).

The read-only Snowflake freeze found 8,341 eligible active current MDM CIKs:
4,897 operating+ticker, 1,592 operating-only, and 1,852 ticker-only
non-operating. Query version `gleif-company-cohort-v1` and seed
`gleif-company-augmentation-2026-09-11-v1` selected exactly 1,000 distinct CIKs
before entity-level GLEIF inspection. The ordered cohort SHA-256 is
`33af2a7df8a02a0838bc2b19a72c75dbe7552e7ba73b9004862f1ae3e18f367f`.

The matching GLEIF 2026-09-11 16:00:00 UTC Level 1, relationship, and
reporting-exception JSON archives were downloaded from their official pinned
URLs, retained compressed, and hashed. Their declared record counts are
3,428,477, 487,721, and 6,351,397; compressed sizes are 927,550,946,
34,953,042, and 63,719,264 bytes. SHA-256 and ZIP CRC verification passed for
all three. The scoped research `.gitignore` excludes the approximately 979 MiB
local archive corpus while the URLs, sizes, counts, and hashes remain in
`01-gleif-snapshot-manifest.json`.

`uv run python ../research/01-verify-freeze.py --zip-crc` independently
reproduces the ordered 1,000-row cohort from the frozen local universe and
verifies every recorded input digest. Production MDM, Snowflake, AWS, and S3
were never written.
