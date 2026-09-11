# Lock v1 As-Of Decision Feature keys against gold

Type: grilling
Status: resolved
Blocked by: 05

## Question

[Lock issuer v1 agent-grade bundle sections](05-lock-issuer-v1-agent-grade-sections.md)
made As-Of Decision Features agent-grade and locked FY/interim coverage
flags. Python `PURE_SEC_FEATURE_KEYS` is 19 keys (including `ebitda`,
`eps_diluted`, `ebitda_margin`, `roe`, `roa`). Live gold
`FINANCIAL_FACTORS` (5,056 rows) has no `ebitda` / `eps_diluted` /
`ebitda_margin` and names `return_on_equity` / `return_on_assets` /
`operating_margin`. SQL 01 projects a subset and aliases `return_on_equity
AS fy_roe`.

Which keys are on the v1 agent-grade vector, and how do they bind to gold?

Decide:

1. Keep the 19 Python keys (null where gold has no column).
2. Project only columns gold actually has, with aliases (`roe` ←
   `return_on_equity`, …).
3. Wait to add missing gold columns (`ebitda`, diluted EPS) before those
   keys are agent-grade.
4. Something else (explicit allowlist).

This is the feature *schema* bind, not coverage flags (already locked).
It does not reopen market-price fields (`FORBIDDEN_MARKET_FIELDS`).

## Answer

Keep the 19 Python `PURE_SEC_FEATURE_KEYS` as the v1 contract vector.
Bind gold `FINANCIAL_FACTORS` via aliases (`return_on_equity` → `roe`,
`return_on_assets` → `roa`). Pass through `ebitda`, `eps_diluted`, and
`ebitda_margin` from `financial_derived` (they already exist one layer
down; factors currently drop them). Keys still missing after that stay
null on the vector (null ≠ zero). Do not alias `operating_margin` to
`ebitda_margin`. Do not add market-price fields.

Implementation: [Bind v1 feature keys to gold FINANCIAL_FACTORS](12-bind-v1-feature-keys-to-gold-financial-factors.md).
