# Lock the Company Legal-Entity Enrichment authority boundary

Type: grilling
Status: resolved
Blocked by: (none)

## Question

Should the specification add GLEIF legal-entity identity, lifecycle, and
accounting-consolidation evidence to Company MDM while SEC remains authoritative
for company filings and reported financials?

## Answer

Yes. The user accepted `Company Legal-Entity Enrichment` as an additive MDM
domain. SEC remains the Source Authority for SEC filings and reported
financials. GLEIF is the Source Authority for published Global LEI Index
identity, lifecycle, registration, direct and ultimate accounting-consolidation
relationships, and reporting-exception evidence. CIK remains the authoritative
SEC identifier; LEI is additive. Fund, Branch, Adviser, Person, Security,
market-price, and financial-calculation domains are outside this enrichment
boundary.

The term and its avoid-list are recorded in root `CONTEXT.md`.
