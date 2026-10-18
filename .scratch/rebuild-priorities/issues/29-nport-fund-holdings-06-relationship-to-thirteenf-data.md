
Priority: 29, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/nport-fund-holdings/issues/06-relationship-to-thirteenf-data.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.
Type: grilling
Status: closed (2026-10-18): the Securities are shared; the holdings question moved to ticket 79
Blocked by: nport-fund-holdings 02, 26

## Question

13F reports an institutional manager's holdings across many issuers (the
manager's own perspective); N-PORT reports a fund's own constituent
holdings of its own portfolio (the fund's own perspective). Where a fund
files both (a large fund complex is often both a 13F filer and an N-PORT
filer for its own series), how should this warehouse treat the overlap --
two independent, uncorrelated silver datasets that happen to describe
related real-world facts, or something that should be explicitly
cross-referenced/deduplicated at the MDM layer? Depends on Ticket 03's
schema answer and Ticket 02's real overlap-rate measurement (how many
N-PORT filers are also 13F filers, and by how much do their reported
holdings actually differ for the same fund/period).

## Answer

Answered for the instruments (2026-10-18 13:35 ET): 13F and N-PORT describe the same Securities, and both bind to one Security per CUSIP (13F's `security-cusip`, N-PORT's `nport-security-cusip`, both switched on, #984 and #1075); 0 CUSIPs on two Securities in the part 1 Proving Run, which read 13F first, then N-PORT. The holdings stay two facts from two filers (a manager's 13F position, a fund's N-PORT holding), not deduplicated; how a fund's holdings relate to its manager's is part of ticket 79's "Funds hold securities: HOLDS".

<details><summary>Earlier notes</summary>

(not yet resolved)

</details>
