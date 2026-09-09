Type: grilling
Status: open

Blocked by: 01, 02

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

(not yet resolved)
