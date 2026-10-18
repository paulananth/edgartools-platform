
Priority: 26, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/nport-fund-holdings/issues/03-silver-schema-design.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.
Type: grilling
Status: closed, moved to ticket 79 (2026-10-18)
Blocked by: nport-fund-holdings 01, nport-fund-holdings 02, 30

## Question

Design the silver-layer schema for N-PORT fund holdings -- table shape(s)
(mirroring `sec_thirteenf_holding`'s pattern, or a genuinely different
shape given N-PORT's richer per-holding fields), column set, and how a
fund's own identity (its own CIK as filer, its series/class LEI structure
-- N-PORT filers are often umbrella trusts with multiple fund series
sharing one CIK) gets represented alongside each holding row.

## Answer

Answered in part by ticket 79's onboarding (2026-10-18 13:35 ET): N-PORT is profiled and its findings approved (`.scratch/onboarding/sec.nport/findings-answers.md`); the fund's own identity is mastered, not carried on each holding row: the registrant is a Company by CIK (q16), the series a Fund (kind `fund_structure`) by series id and LEI (q17), the holding's instrument a Security by CUSIP or ISIN (q19, q20, q23). The holding rows themselves (their silver table, one row per holding, linked to the Fund and the Security) are ticket 79's open part "Funds hold securities: HOLDS", where this question now lives.

<details><summary>Earlier notes</summary>

(not yet resolved)

</details>
