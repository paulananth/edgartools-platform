# 05: A Person holds a Security and does not issue it

Priority: 25, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/security-mastering/issues/05-a-person-holds-and-does-not-issue.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

**What to build:** A person's reported shares are a Holdings edge from that Person to the Security. The person is not the issuer. `ISSUED_BY` still points at the Company or the Fund Company.

**Blocked by:** security-mastering 01: Publish one Security per 13F CUSIP.

**Status:** ready-for-agent

- [ ] A person holding Class A produces Holdings from that Person to `02079K305`.
- [ ] The same publication does not make the Person the issuer.
- [ ] The Company's `ISSUED_BY` edge is unchanged.
