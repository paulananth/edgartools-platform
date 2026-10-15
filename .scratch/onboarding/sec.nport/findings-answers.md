# N-PORT findings: answers from the operator's rulings (draft, for approval)

Findings: `~/.local/share/edgartools/clean-mdm/profiling/sec.nport-2026q2-final/findings.yaml`
(reused as profiled, operator 2026-10-14: "why cant we reuse the already completed profiling").
Each of its 25 questions is answered below from a ruling already given (2026-10-14, onboarding log),
or, where none applies, by the skill's default for a part the tests did not class: kept in bronze
until a need is ruled. Nothing here is approved until the operator says so.

## Masters (what MDM masters from N-PORT)

| Question | Part | Answer | Ruling it rests on |
|---|---|---|---|
| q19, q20, q23 | the CUSIP columns (`FUND_REPORTED_HOLDING.ISSUER_CUSIP`, `DEBT_SECURITY_REF_INSTRUMENT.CUSIP`, `DESC_REF_OTHER.CUSIP`) | not a new kind: the existing kind `security`, CUSIP its issued identifier (`rules/identifiers/cusip.yaml`) | "CUSIP and ISIN join (Recommended)" |
| q21, q22, q24 | the ISIN columns | not a new kind: `security`, ISIN a second joining identifier (`rules/identifiers/isin.yaml`) | same |
| q17 | `FUND_REPORTED_INFO.SERIES_LEI` | not a new kind: the Fund, kind `fund_structure` with the `fund` profile, joined by series id and LEI | "Series id and LEI join (Recommended)" |
| q16 | `REGISTRANT.CIK` | not a new kind: the registrant is a `company`, joined by CIK; each Fund links to it (IS_SUBFUND_OF) | "Registrant yes, issuer later (Recommended)" |
| q18 | `FUND_REPORTED_HOLDING.ISSUER_LEI` | not mastered now: the issuer's LEI and name stay on the Security until rebuild priority 22 | same |

## Transactions and details (not masters)

| Question | Part | Answer | Ruling it rests on |
|---|---|---|---|
| q5 | `FUND_REPORTED_HOLDING` | transaction data: each quarter's holdings land in silver with the fund's and the security's MDM ids; MDM keeps one HOLDS link per fund and security | "Silver + MDM link (Recommended)" |
| q6 | `IDENTIFIERS` | the holding's identifier list: its ISIN joins the Security; ticker and other ids are cross-references, lookup only | "CUSIP and ISIN join (Recommended)" |
| q4, q9, q12, q13 | `FUND_VAR_INFO`, `DESC_REF_INDEX_BASKET`, `NONFOREIGN_EXCHANGE_SWAP`, `EXPLANATORY_NOTE` | not new master kinds: details of a fund's report or of a holding; bronze until a silver table is ruled | the holdings ruling (report detail is not a master); skill default |
| q1 | `SUBMISSION` | metadata: the filing's own facts (accession, dates), for Bookkeeping | data-onboarding: metadata parts go to Bookkeeping |
| q2, q3, q7, q8, q10, q11 | `MONTHLY_RETURN_CAT_INSTRUMENT`, `DEBT_SECURITY_REF_INSTRUMENT`, `REPURCHASE_AGREEMENT`, `DESC_REF_INDEX_COMPONENT`, `DESC_REF_OTHER` | holding details: bronze until a silver table is ruled; no designed key now | skill default |

## Answered by the 13F findings (approved 2026-10-14 20:54 ET)

| Question | Part | Answer |
|---|---|---|
| q14, q15, q25 | `thirteenf`, `thirteenf.figi` | the 13F information tables, profiled and approved on their own ("yes approve the 13F findings"): no designed key for the holding rows, CUSIP the Security, FIGI a cross-reference |

## The onboarding plan that follows (dependency order)

1. Security from N-PORT holdings: CUSIP and ISIN join; the issuer name and LEI as filed.
2. Company: the registrant by CIK (an existing kind; a new source for it).
3. Fund (`fund_structure`, `fund` profile) by series id and LEI, IS_SUBFUND_OF its registrant.
4. HOLDS from a fund to a Security, with each quarter's holdings in silver.
