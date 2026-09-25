# SEC Company classification proof, rule 2026-09-24.8

Ticket 12, second measurement on 2026-09-24. The retained bronze summary has
76,230 CIKs and SHA-256
`395b7db4cfeb5ab0d4816ee4c0e68ca078b548fce3b8337c0ab671f0e0668600`.
The script made no SEC, S3, or other network requests. Version .7's sample
shaped this change, so the .8 draw uses the fresh seed `20260924.8`.

## Result

| Company step | Hand-confirmed Companies | Drawn | One-sided 95% Wilson lower bound | Bar |
| --- | ---: | ---: | ---: | ---: |
| 2: SEC `operating` | 300 | 299 | 0.98520 | 0.95, clears |
| 4: SEC `other`, industry code, filer category and company name word | 300 | 300 | 0.99106 | 0.95, clears |

The separately hand-labeled adversarial fixture has 483 records and **zero**
non-Company violations. It uses the same name-blind arm selection as .7, with
new seed-dependent draws in the two 100-record arms. Among category-bearing
adversarial records, Texas Precious Metals Trust and iShares Bitcoin Premium
Income ETF are deferred by step 1's excluded industry code `6221`; the others
are Company issuers on name and filing evidence.

One error in 600 (Claude's recheck, 21:50 ET): "Stonepeak-Plus
Infrastructure Fund LP", step 2, a private fund with no BDC election; it is a
Fund on the standard used for the seed-.6 sample. This is a precision
measurement of the two Company verdict paths, not a recall measurement of all
SEC filers. The .7 step-4 failure, 258/300 with 33 adversarial violations,
remains in the earlier commit `476003cd` and does not measure .8.

## Method and scope

`12-classify.py` passes `entity_type`, `sic`, `category` and `entity_name` to
the same `fired` function the real SEC adapter uses. The SEC Company landing
extractor supplies `category` from the bronze `submissions.json` filer field;
the normalizer passes the landing row unchanged to `fired`. The script draws
300 separately from each Company step and verifies each sampled record still
fires at its recorded step before scoring.

Draft labels read filing forms, tickers and exchanges before name. They never
read the SEC category, industry code or entity type used by the rule. I read
the sampled names and filing sets. `12-label-reviewed.py` records judgments;
every fund-, trust- or partnership-looking name has a note. The operator's
decision that a business development company is a Company governs the BDCs
filing 10-K/10-Q plus N-2 or 40-APP. The adversarial rows each carry a final
label and a hand-read note. Labels are judgments from retained summary data,
not an external registry check.

Version .8 calls 7,130 of the 76,230 filers Company: 5,980 at step 2 and
1,150 at step 4. It defers 69,100. The added category gate removes 1,119
previous step-4 calls. Among these are 88 annual reporters with empty
category that would otherwise match step 4. There are 96 `other` filers with
an industry code, an empty category and a 10-K, 20-F or 40-F in the summary;
ROYAL BANK OF CANADA is one of them. They wait for review rather than being
treated as classification failures.

`12-summary.json` gives exact counts and SHA-256s of the sample, adversarial
fixture, population metadata, classifier and review script. `PROOF` in
`company_source.py` pins those hashes and the per-step numbers. The standard
policy is still inactive: `automatic_rules` is empty; `PENDING_ACTIVATION`
contains the proposed entry with `approved_by` and `approved_at` unset. The
policy validator refuses the proposal as an activation until a real approval
is recorded.

This proof does not establish SEC-to-GLEIF binding, Company master creation,
production reach or operator approval.
