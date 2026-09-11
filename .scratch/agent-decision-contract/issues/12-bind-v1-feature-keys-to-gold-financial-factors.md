# Bind v1 feature keys to gold FINANCIAL_FACTORS

Type: task
Status: resolved
Blocked by: 11

## Question

Implement the bind locked in
[Lock v1 As-Of Decision Feature keys against gold](11-lock-v1-feature-keys-against-gold.md).

## Seams

- `build_subject_feature_screen` / `pure_sec_feature_vector` (public
  Python contract vector)
- `build_issuer_subject_bundle` subject_features section (same vector)
- `infra/snowflake/sql/decision_contract/01_subject_feature_screen.sql`
- `infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql`

## Work

1. Alias gold `return_on_equity`/`return_on_assets` onto contract `roe`/`roa`.
2. Pass `ebitda`, `eps_diluted`, `ebitda_margin` through `financial_factors`
   from `financial_derived`.
3. Project the 19 contract keys from SQL 01; coverage = any vector key
   non-null (not the three-column emptiness test). Interim does not require
   FY (ticket 05 Q6).
4. Do not alias `operating_margin` to `ebitda_margin`. No market fields.

## Answer

Implemented on `grok/agent-decision-data-plane-wayfinder`.

- `pure_sec_feature_vector` aliases gold `return_on_equity`/`return_on_assets`
  onto contract `roe`/`roa`; screen and issuer bundle share it.
- `financial_factors.sql` passes through `ebitda`, `eps_diluted`,
  `ebitda_margin` from `financial_derived`.
- SQL 01 projects the 19 keys, aliases roe/roa, coverage is any vector key
  non-null, interim does not require FY. SQL 03 bundle/display views pass
  the same columns through.
- Tests: `test_gold_financial_factors_column_names_bind_to_contract_keys`,
  bundle alias test, architecture SQL assertions. `tests/unit` +
  `tests/architecture`: 1555 passed, 6 skipped.

Prod `FINANCIAL_FACTORS` still needs a dbt `--full-refresh` of
`financial_factors` before live gold has the new columns.
