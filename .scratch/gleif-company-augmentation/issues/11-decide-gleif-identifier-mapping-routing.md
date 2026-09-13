# Decide GLEIF identifier-mapping routing

Type: research
Status: resolved
Blocked by: 09

## Question

Which official GLEIF identifier mappings should the platform ingest, at what
source cadence, and into which MDM domain and authority role?

## Required evidence

- Cover at least ISIN, BIC, MIC, OpenCorporates ID, S&P Capital IQ Company ID,
  QCC code, and Global Energy Monitor entity ID mappings.
- Verify current publication cadence, format, licensing or redistribution
  terms, mapping certification, coverage, and stable source identity.
- Distinguish an entity identifier, a security-to-issuer link, a market or
  branch code, and corroborating match evidence.
- Compare each mapping with current Company, Security, Fund, and Adviser MDM
  schemas and source-reference capabilities.
- Decide whether each mapping belongs in the first specification, a later
  consumer, retained source evidence only, or out of scope.

## Done when

Every mapping has an explicit ingest/defer/reject decision, source cadence,
destination domain, provenance contract, and conflict behavior.

## Answer

Resolved by [`../research/11-gleif-identifier-mapping-routing.md`](../research/11-gleif-identifier-mapping-routing.md).

Only ISIN-to-LEI is a daily feed, and it belongs to the Security-to-issuer
surface rather than daily Company profile enrichment. OpenCorporates is
bi-weekly; BIC, MIC, QCC, and GEM are monthly; S&P CIQ is weekly through LEI
Search while its bulk cross-reference may require a subscription. Each mapping
is routed by identifier semantics and accepted LEI domain, with source-grained
provenance and conflict quarantine.
