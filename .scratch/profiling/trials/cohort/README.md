# Recreation proof cohort (profiling ticket 08)

`cohort.json` is the fixed cohort: 500 entities, filing in the 2 years
2024-07-01 to 2026-06-30, chosen by `select.py` from the feeds on this
machine (operator, 2026-10-07: "Local feeds only (Recommended)"). Each
stratum is drawn in a fixed order (sha256 of the seed and the CIK), so a
rerun gives the same list.

| Stratum | Entities | Why it is there |
|---|---|---|
| named | 4 | Apple, Microsoft, Shell, ASML: the examples every trial follows |
| company_bound_to_gleif | 171 | a name rule binds the company to its GLEIF record |
| company_deferred | 75 | a name rule holds it for a steward; all 8 hold-back reasons are present (29 no agreement, 20 several GLEIF entities, 9 conflicting jurisdictions, 8 another entity's other name, 6 several SEC filers, 1 each FUND, INACTIVE, government) |
| company_no_gleif | 75 | no GLEIF record of its name |
| investment | 75 | an investment company |
| other_filer | 100 | any other filer: people and other entities |

222 of the 500 have an LEI.

## Size and time

| Feed | What is sliced | Size | Time |
|---|---|---|---|
| SEC submissions | the 500 filers' captured files | 46 MB | seconds (a file copy) |
| GLEIF Level 1 | the 222 LEIs, plus their parents and successors | under 1 MB | one pass of the Golden Copy: about 5 minutes (measured, ticket 04c) |
| GLEIF relationships and reporting exceptions | records naming those LEIs | a few MB | one pass each: about 5 to 10 minutes |
| 13F information tables | those of the 999 on this machine filed by a cohort filer | unknown until sliced | under a minute |
| Every other feed (Forms 3/4/5, Form ADV, XBRL facts, 8-K, proxy) | not on this machine | none | not covered; DIFF.md lists each |

Mastering the cohort: about a minute (ticket 02's counts run mastered 7,000
Companies in 8 minutes). The proof itself (a cold agent regenerating MDM, RDM
and relationships with the skills) is the long part: hours, estimated when it
starts.
