# GLEIF identifier-mapping routing decision

Date: 2026-09-12
Scope: current official GLEIF mapping catalog and current repository MDM model;
research only.

## Decision matrix

Use each mapping at its native publication cadence. Do not force every mapping
through the daily GLEIF Level 1 refresh and do not treat all mapped values as
Company identifiers.

| Mapping | Official cadence/access | Semantic route | Decision |
| --- | --- | --- | --- |
| ISIN -> LEI | Daily open-source ZIP/CSV; participating NNAs and newly issued ISINs, not complete legacy coverage | Security identifier linked to issuer legal entity | Ingest daily in a later Security consumer; populate/prove `mdm_security.isin` and `ISSUED_BY` only when both identities are accepted |
| BIC -> LEI | Monthly open-source ZIP/CSV; SWIFT mapping certified by GLEIF | Financial-institution/organization identifier; may include branch semantics | Ingest monthly as source-grained identifier evidence; route by accepted LEI category, never assume Company |
| MIC -> LEI | Monthly full ZIP/CSV, with extra publications when the MIC source changes | Trading venue/market code linked to its operating organization | Retain monthly evidence; defer publication until a Market/Venue domain exists; do not store MIC as a Company identifier |
| OpenCorporates ID -> LEI | Bi-weekly open-source ZIP/CSV | Legal-entity registry/database identifier | Include in the first Company consumer as deterministic corroborating source evidence, subject to accepted LEI routing and license metadata |
| S&P CIQ Company ID -> LEI | Weekly in LEI Search; full cross-reference file is an S&P service and may require subscription | Commercial company identifier | Defer bulk ingestion; permit bounded review evidence only until access, license, immutable capture, and replay are approved |
| QCC Code -> LEI | Monthly full open-source ZIP/CSV; mapping certified by GLEIF | Global-enterprise identifier with strong China coverage | Later Company consumer; source reference/corroboration, not SEC authority |
| GEM Entity ID -> LEI | Monthly open-source ZIP/CSV; mapping certified by GLEIF | Organization identity in the Global Energy Monitor ownership ecosystem | Later Company/government consumer; do not infer energy-asset ownership from the identifier pair itself |

Only ISIN has a native daily cadence. That daily feed is additional
Security-to-issuer evidence, not additional daily Company profile data. The
Company Legal-Entity Enrichment daily job therefore consumes GLEIF's 24-hour
Level 1, relationship, and reporting-exception deltas only. OpenCorporates,
BIC, MIC, QCC, and GEM run on their native periodic schedules; S&P CIQ remains
deferred unless licensed bulk access is separately approved.

## Provenance and conflict contract

Every mapping capture records mapping family, source publisher and partner,
publication identity/date, download URL, content hash, file format, mapping
certification status, license document/version, parser version, and run ID.
Files that publish a full current table rather than a delta require snapshot
diffing; disappearance closes the mapping only after a complete verified load.

A certified mapping is authoritative for the published identifier/LEI pair,
but not for SEC facts and not automatically for the local CIK/MDM identity. A
pair becomes a local source reference or relationship only after the LEI has an
accepted local entity link and the mapped identifier's semantics match that
domain. Conflicting pairs are quarantined; they do not overwrite SEC CIK,
security identifiers, or an existing source reference silently.

The current schema can represent ISIN on `mdm_security` and generic external
identities in `mdm_source_ref`, but it lacks a Market/Trading Venue entity type.
Its composite `mdm_source_ref` primary key also does not by itself prevent one
external identifier from binding to multiple MDM entities, so the first
implementation needs a uniqueness invariant for each source-system/source-ID
pair before publishing mappings.

## Sources

- [GLEIF LEI Mapping catalog](https://www.gleif.org/en/lei-data/lei-mapping)
- [ISIN-to-LEI files](https://www.gleif.org/en/lei-data/lei-mapping/download-isin-to-lei-relationship-files)
- [BIC-to-LEI files](https://www.gleif.org/en/lei-data/lei-mapping/download-bic-to-lei-relationship-files)
- [MIC-to-LEI files](https://www.gleif.org/en/lei-data/lei-mapping/download-mic-to-lei-relationship-files)
- [OpenCorporates-to-LEI files](https://www.gleif.org/en/lei-data/lei-mapping/download-oc-to-lei-relationship-files)
- [QCC-to-LEI files](https://www.gleif.org/en/lei-data/lei-mapping/download-qcc-to-lei-relationship-files)
- [GEM-to-LEI files](https://www.gleif.org/en/lei-data/lei-mapping/download-gem-to-lei-relationship-files)
- [S&P CIQ-to-LEI factsheet](https://www.gleif.org/lei-data/lei-mapping/s-and-p-c-i-q-company-id-to-lei-relationship/2025-06-12_s_and_p-ciq-company-id-to-lei-factsheet_v2.1.pdf)
- Repository `edgar_warehouse/mdm/database.py`
