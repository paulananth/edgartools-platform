# Ticket 08, step 1: does either source already join SEC to GLEIF?

Measured 2026-09-24 22:23 ET. Zero SEC requests: bronze S3 (newest `submissions.json` per CIK)
and the pinned local GLEIF Level 1 Golden Copy (2026-09-11 16:00 UTC, sha256
`1b6cd9cd…a36a6a`, re-hashed before use). Scripts:
[`08-scan-sec-lei-and-address.py`](08-scan-sec-lei-and-address.py),
[`08-extract-gleif-ra000665.py`](08-extract-gleif-ra000665.py). Outputs are
kept outside the repo (about 90 MB).

## 1. SEC's own `lei` field

Every one of the 76,230 bronze submissions files has the `lei` key; it is
populated in **392** (0.5%), and **356** of those pass the ISO 17442 check
digit (one value is a 12-digit number, one is `N/A`, one has a letter O/0
typo against GLEIF).

| SEC entity type | Filers | LEI stated | LEI valid |
| --- | ---: | ---: | ---: |
| operating | 7,016 | 5 | 4 |
| other | 67,421 | 372 | 337 |
| investment | 1,793 | 15 | 15 |

Over the Company population (rule `2026-09-24.8`, 7,130 Company verdicts)
it covers almost nothing. Consequence: SEC's own LEI is not an identifier path
for Companies. It would also break ticket 11's rule that a record adds only
identifiers its own source issues (SEC does not issue LEIs). At most it is
supporting evidence inside the matching rule, after the check-digit test.

## 2. GLEIF registration authority `RA000665`

On two of the 308 accepted seed links, GLEIF's registration-authority entity ID
equals the CIK, under authority `RA000665`. The whole Golden Copy has
**32,093** records under it (27,933 as registration authority, 4,160 as
validation authority only):

- 31,670 are GLEIF category **FUND**, 419 GENERAL;
- 22,951 IDs are SEC fund **series** IDs (`S0000…`), 8,998 are 10-digit CIKs;
- 8,951 distinct numeric IDs; 49 carry more than one LEI;
- against the 7,130 Company verdicts: **57** step-2 Companies (one LEI each),
  **0** step-4 Companies; Microsoft, Shell and ASML have none;
- where SEC also states an LEI: 17 agree, 3 disagree.

`RA000665` is SEC's registration authority for registered funds. It is no
route for Companies (0.8% of them), and joining on it would treat a GLEIF value
as a CIK crosswalk, which Q14 leaves to the operator. It is recorded for the
later Fund kind.

## 3. What this means for ticket 08

Neither source joins SEC to GLEIF for Companies, so the matching rule on
name, country and address must carry nearly all of it. The earlier measurement
of that shape (gleif-company-augmentation research 02, Tier B: names plus
address and jurisdiction) accepted 224 of 249, a Wilson interval of
85.6–93.1%, below the 95% bar. So ticket 08 has to find a **stricter** rule,
not build that one. Candidate levers, to be tuned on the 883 reviewed pairs
(development data) and qualified on a fresh held-out draw from the Company
population:

- uniqueness both ways: one GLEIF candidate for the CIK, and that LEI a
  candidate for no other CIK;
- GLEIF category GENERAL only (no branches, no funds);
- legal form compatible, postal code and street number agree, jurisdiction
  compatible.
