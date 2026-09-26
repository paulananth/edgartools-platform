# 05: A Person holds a Security and does not issue it

**What to build:** A person's reported shares are a Holdings edge from that Person to the Security. The person is not the issuer. `ISSUED_BY` still points at the Company or the Fund Company.

**Blocked by:** 01: Publish one Security per 13F CUSIP.

**Status:** ready-for-agent

- [ ] A person holding Class A produces Holdings from that Person to `02079K305`.
- [ ] The same publication does not make the Person the issuer.
- [ ] The Company's `ISSUED_BY` edge is unchanged.
