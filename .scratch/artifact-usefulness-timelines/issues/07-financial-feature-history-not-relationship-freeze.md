# Financial feature history is not relationship freeze

Type: research
Status: resolved
Blocked by: 01
Blocks: 08, 09, 10

## Question

What multi-year history do CAGR / growth / earnings-potential style **As-Of
Decision Features** require, and which pipeline supplies it — proving it must
not drive Ticket 20 relationship document windows?

## Exit criteria

- Feature input lookbacks (3y/5y FY) and pipeline (companyfacts/gold).
- Explicit non-dependency on 13F/8-K bulk-load depth.
- Pointers to ADR 0001 / CONTEXT / decision_contract.

## Answer

**Gist:** CAGR/growth use **3y/5y FY inputs** via **companyfacts → silver → gold `financial_factors` → Decision Contract** (one as-of row at W). They **do not** require deep 13F/8-K bulk-load; Ticket 20 relationship windows stay orthogonal.

Full write-up: [research/07-financial-features-vs-relationship-freeze.md](../research/07-financial-features-vs-relationship-freeze.md)
