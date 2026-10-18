
Priority: 30, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/nport-fund-holdings/issues/07-entity-model-for-fund-complex.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.
Type: grilling
Status: resolved (2026-10-18), by ticket 79's rulings
Blocked by: nport-fund-holdings 01, nport-fund-holdings 02

## Question

What new MDM entity type(s) does the N-PORT registered-fund universe
actually need, and how do they relate to each other and to existing
entity types? Specifically: registrant (Trust/Company, one CIK, may
contain many funds) vs. series (the individual fund itself, own SEC
Series ID + LEI, the thing that files N-PORT holdings) vs. share class
(retail/institutional/ETF shares within a series, each potentially its
own ticker/CUSIP) vs. the fund's own investment adviser vs. the fund
*as a security* (held by other entities, e.g. a 13F filer's SPY position
or a fund-of-funds holding another fund's shares).

## Context

Raised directly by the user, mid-charting: "Do we need additional tables
as etfs and funds have securities, there may be etf issuers and fund
managers." Answer is yes, confirmed via source read -- the existing
`MdmFund` (`edgar_warehouse/mdm/database.py:348`, keyed on
`private_fund_id`) and `MdmAdviser` (`database.py:266`, keyed on
`crd_number`) are both scoped to the **Form ADV private-fund universe**
(hedge funds/PE funds and their advisers) -- a structurally different
regulatory population from N-PORT's '40-Act registered funds (mutual
funds/ETFs/closed-end funds, identified by CIK + SEC Series ID + LEI, not
CRD/private_fund_id). Reusing them as-is would silently conflate two
unrelated datasets.

Confirmed live via SEC's own Form N-PORT instructions
(https://www.sec.gov/files/formn-port.pdf) that the form's Item A.1/A.2
structure is exactly this hierarchy: registrant CIK + registrant LEI
(Item A.1), then EDGAR series identifier + series LEI (Item A.2) -- "one
registrant CIK may map to dozens or hundreds of series IDs," with
share-class-level data (Institutional/Investor/ETF shares etc.) reported
*within* the single series-level filing, not as separate filings.

No existing MDM entity type plays the dual holder/held role a fund needs:
`MdmCompany` is only ever an issuer (held via its `MdmSecurity` rows,
never itself a holder of other securities); `MdmFund`/`MdmAdviser` are
only ever holders (private funds aren't publicly tradeable, nothing else
holds shares of them via a 13F-style relationship). A registered fund is
both -- something INSTITUTIONAL_HOLDS-style relationships can point at
(as a security), and something that N-PORT's own reported constituent
holdings originate from (as a holder), so this ticket's answer directly
shapes both Ticket 03 (schema) and Ticket 04 (relationship design) --
re-wired to block on this ticket too.

Open sub-questions this ticket needs to settle: does the fund's
investment adviser genuinely bridge cleanly onto existing `MdmAdviser`
(most registered-fund advisers also file Form ADV and have a CRD number),
or does that assumption break down often enough to need its own path? Is
share-class-level identity (separate ticker/CUSIP per class) needed for
the fund-as-security representation, or does series-level suffice for a
first landing? Should the registrant (Trust) itself be a first-class
entity at all, or just a foreign-key/attribute on the series?

## Answer

Answered by ticket 79 (2026-10-18 13:35 ET), each from the approved N-PORT findings and the operator's rulings (`.scratch/onboarding/sec.nport/findings-answers.md`):
- registrant (trust, one CIK): a Company, joined by CIK (q16, "Registrant yes, issuer later"); 1,947 in the 2026q2 Proving Run (#1001);
- series (the fund that files holdings): a Fund, kind `fund_structure` with the `fund` profile, joined by series id and LEI (q17, "Series id and LEI join (Recommended)"); 12,937 (#1003); its link to the registrant (IS_SUBFUND_OF) is deferred until a capture states when a series began (operator, 2026-10-16: "Funds now, link later (Recommended)");
- the fund as a security, and every holding's instrument: a Security, joined by CUSIP or ISIN (q19, q20, q23); 423,562 (#999); an ETF share is issued by its umbrella trust (ticket 23, #1038);
- share classes and the investment adviser: not mastered from N-PORT (no ruling asked for them; the adviser comes from Form ADV).

<details><summary>Earlier notes</summary>

(not yet resolved)

</details>
