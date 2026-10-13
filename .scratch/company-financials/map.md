# Company financials for analyst fundamentals

> 2026-10-13: this map's open tickets moved to [Rebuild priorities](../rebuild-priorities/map.md), numbered by priority. Each old ticket file holds a one-line pointer.

Labels: wayfinder:map. Charted 2026-10-12 07:48 ET.

## Destination

A local proof that each cohort Company's reported financial facts sit in silver, linked to its MDM Company, as a standard set of line items over every year it reported, enough to compute analyst CAGR and the other fundamental measures the operator names, with every number traceable to the fact and filing it came from.

## Notes

- Goal (operator, 2026-10-12): "It's based on usage and supporting analyst CAGR and other fundamental analytics": metrics come first in the order analysts use them; the data exists to support CAGR and fundamental analytics.
- Source order follows from that: XBRL company facts first (every year reported, structured); iXBRL statements in 10-K and 10-Q, and 8-K earnings text, only where company facts falls short (07c's ruling: iXBRL as Rust configuration, HTML a Python custom step, unconfirmed values never merge).
- Standing rules: zero sec.gov requests without the operator's permission (L8); no prod changes; local proving folder only; repo is public; one branch per ticket; a GoF consult before code; three-axis review; merge on the operator's word.
- Skills: data-profiling (profile any capture), data-onboarding (new feed), domain-modeling and grilling for HITL tickets.
- The rebuild is the only system: the old gold models (`financial_facts`, `financial_derived`, `financial_factors`) are evidence of past usage, not behaviour to preserve.
- Execution is carried in this map (operator, 2026-10-12 08:12 ET: "convert the financial fundamental data requirements to tickets and map and park them for further execution and implementation"): decision tickets first, then build tickets 13 to 16.
- **Parked 2026-10-12 08:14 ET.** Resume at the frontier: tickets 03 and 05 (then 08, 09, 10). The capture and long form are local (`~/.local/share/edgartools/clean-mdm/proving/company-facts/`), not in the repo.
- Program: the profiling map, rows 07 (readers per feed: "XBRL company facts: reader, then profiling") and 07c (iXBRL) are where these feeds sit in the profiling program; this map's build tickets close row 07's company facts line.

## Decisions so far

- [Which measures analysts use, and the reported concepts behind each](issues/01-which-measures-and-concepts.md): 19 line items by usage, concepts chosen per period; years keyed on period end; nine old hazards not to carry over
- [Capture permission and route for company facts](issues/02-capture-permission.md): one bounded capture now, local only (operator, "a")
- [Capture the cohort's company facts](issues/04-capture-the-cohorts-company-facts.md): 329 of 500 have facts (132 none, 39 empty); 773 MB raw, 49 MB stored; 5.1 million facts in long form

## Tickets

| # | Ticket | Type | Blocked by | Status |
|---|---|---|---|---|
| 01 | [Which measures analysts use, and the reported concepts behind each](issues/01-which-measures-and-concepts.md) | research | none | resolved |
| 02 | [Capture permission and route for company facts](issues/02-capture-permission.md) | grilling | none | resolved |
| 03 | [As reported or as restated: the time model](issues/03-time-model-as-reported-or-restated.md) | grilling | 01 | open (frontier) |
| 04 | [Capture the cohort's company facts](issues/04-capture-the-cohorts-company-facts.md) | task | 02 | resolved |
| 05 | [Profile company facts](issues/05-profile-company-facts.md) | task | 04 | open (frontier) |
| 06 | [The standard line items and how concepts map to them](issues/06-standard-line-items-and-concept-mapping.md) | grilling | 03, 05 | open |
| 07 | [Where CAGR and the measures are computed, and their definitions](issues/07-where-cagr-and-measures-are-computed.md) | grilling | 06 | open |
| 08 | [How company facts is read: configured reading or custom step](issues/08-how-company-facts-is-read.md) | grilling | 05 | open |
| 09 | [Profiler gap: objects keyed by data are read as columns](issues/09-profiler-reads-object-keys-as-columns.md) | task | none | open (frontier) |
| 10 | [Currencies, IFRS filers and industry statement shapes](issues/10-currency-ifrs-and-industry-shapes.md) | grilling | 05 | open |
| 11 | [The silver table spec for financial line items](issues/11-silver-table-spec-for-financials.md) | grilling | 03, 06 | open |
| 12 | [A hand-computed answer key for the measures](issues/12-answer-key-for-measures.md) | task | 07 | open |
| 13 | [Build: the company facts reader](issues/13-build-company-facts-reader.md) | task | 08, 09 | open |
| 14 | [Build: standard line items into silver](issues/14-build-line-items-into-silver.md) | task | 06, 10, 11, 13 | open |
| 15 | [Build: CAGR and the fundamental measures](issues/15-build-measures.md) | task | 07, 12, 14 | open |
| 16 | [Proof: the cohort's financials end to end](issues/16-cohort-proof.md) | task | 15 | open |

## Not yet specified

- Quarterly figures: deriving a fourth quarter from the year and nine months, and flows reported only year to date.
- Per-share CAGR across stock splits and share-class changes.
- Segments and other dimensions (company facts carries none; iXBRL does).
- Non-GAAP figures from 8-K earnings releases, behind the cross-check gate.
- How agents read the measures (the `context` command, ticket 05 of the profiling map).

## Out of scope

- Production capture, hosting and deployment (profiling plan decision 37: a later program).
- Analyst consensus estimates and price data (not SEC-reported facts).
