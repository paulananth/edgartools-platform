# Company financials for analyst fundamentals

Labels: wayfinder:map. Charted 2026-10-12 07:48 ET.

## Destination

A local proof that each cohort Company's reported financial facts sit in silver, linked to its MDM Company, as a standard set of line items over every year it reported, enough to compute analyst CAGR and the other fundamental measures the operator names, with every number traceable to the fact and filing it came from.

## Notes

- Goal (operator, 2026-10-12): "It's based on usage and supporting analyst CAGR and other fundamental analytics": metrics come first in the order analysts use them; the data exists to support CAGR and fundamental analytics.
- Source order follows from that: XBRL company facts first (every year reported, structured); iXBRL statements in 10-K and 10-Q, and 8-K earnings text, only where company facts falls short (07c's ruling: iXBRL as Rust configuration, HTML a Python custom step, unconfirmed values never merge).
- Standing rules: zero sec.gov requests without the operator's permission (L8); no prod changes; local proving folder only; repo is public; one branch per ticket; a GoF consult before code; three-axis review; merge on the operator's word.
- Skills: data-profiling (profile any capture), data-onboarding (new feed), domain-modeling and grilling for HITL tickets.
- The rebuild is the only system: the old gold models (`financial_facts`, `financial_derived`, `financial_factors`) are evidence of past usage, not behaviour to preserve.
- Program: the profiling map, rows 07 (readers per feed: "XBRL company facts: reader, then profiling") and 07c (iXBRL); build work lands there.

## Decisions so far

## Not yet specified

- Quarterly figures: deriving a fourth quarter from the year and nine months, and flows reported only year to date.
- Per-share CAGR across stock splits and share-class changes.
- Filers that report in IFRS or another currency, and banks and insurers whose statements use other concepts.
- Segments and other dimensions (company facts carries none; iXBRL does).
- Non-GAAP figures from 8-K earnings releases, behind the cross-check gate.
- How agents read the measures (the `context` command, ticket 05 of the profiling map).

## Out of scope

- Production capture, hosting and deployment (profiling plan decision 37: a later program).
- Analyst consensus estimates and price data (not SEC-reported facts).
