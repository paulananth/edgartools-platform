# Name-only Person sources: what can bind deterministically

Ticket: [01](../issues/01-measure-name-only-source-overlap.md). Run 2026-09-19.
Read-only. Full results: [`01-results.json`](01-results.json),
[`01-results-quality.json`](01-results-quality.json).

## What was and wasn't reachable

Prod Snowflake (`EDGARTOOLS_PROD.EDGARTOOLS_SILVER`) refused every query:
*"Your free trial has ended and all of your virtual warehouses have been
suspended."* The S3 silver landing prefix
(`s3://edgartools-prod-snowflake-export-690839588395/warehouse/silver_landing/`)
is empty — landing rows are consumed into Snowflake. So
**`sec_ownership_reporting_owner` (the only source with `owner_cik`) was
not readable.** The source-layer exports carry only a surrogate `party_key`
(`infra/snowflake/dbt/edgartools_gold/models/gold/ownership_holdings.sql`
line 80 hashes `'cik:' || owner_cik` or `'name:' || owner_name_norm`),
which cannot be joined back to a name.

What *was* readable: the latest full-snapshot source-layer exports for the
two name-only sources, plus the ownership fact exports for counts.

| Dataset | S3 key under `s3://edgartools-prod-snowflake-export-690839588395/` | sha256 (prefix) |
| --- | --- | --- |
| `executive_record` | `warehouse/artifacts/snowflake_exports/executive_record/business_date=2026-09-06/run_id=50c0407f-…/executive_record.parquet` | see `01-results.json` |
| `sec_employment_event` | `warehouse/artifacts/snowflake_exports/sec_employment_event/business_date=2026-09-14/run_id=daily-incremental-ticket17-verify-1789514832/sec_employment_event.parquet` | see `01-results.json` |
| `ownership_holdings` | `warehouse/artifacts/snowflake_exports/ownership_holdings/business_date=2026-09-06/run_id=50c0407f-…/ownership_holdings.parquet` | see `01-results.json` |
| `ownership_activity` | `warehouse/artifacts/snowflake_exports/ownership_activity/business_date=2026-09-06/run_id=50c0407f-…/ownership_activity.parquet` | see `01-results.json` |

Full keys and full sha256 digests are in `01-results.json` under `inputs`.
Queries: DuckDB over those four files (`uv run --with duckdb`); name
normalization = lowercase, strip `.` and `,`, collapse whitespace;
"plausible person name" = no role vocabulary in the field and at least two
tokens.

## Findings

**F1 — the proxy name field is half role text.** Of 14,755
`executive_record` rows, 6,889 (47%) carry role vocabulary *inside*
`exec_name` ("Chairman of the", "President and Chief", "Executive Officer",
"Finance and Chief"), and 987 are single tokens. Only 7,600 (51.5%) look
like a person's name — and those still carry trailing commas and footnote
markers ("Brian B. Yoor,(1)"). The most frequent "names" appearing under
many issuers are "chief financial officer" (203 issuers), "chief executive
officer" (182), "president and" (140), "former" (129), "executive vice"
(84). **The DEF 14A parser (`edgar_warehouse/parsers/proxy_fundamentals.py`)
leaks the role column into the name column.** Any binding rule for proxy
names is meaningless until that is fixed upstream; this is a parser
defect, not a matching question.

**F2 — the 8-K Item 5.02 name field is clean.** 97.7% of 7,878
`sec_employment_event` rows are plausible person names; 4,695
appointments and 3,181 departures across 1,742 issuers. `exec_role` is
inconsistent ("Director" 2,661; null 2,637; "a member" 246; "directors"
84), so role can corroborate but cannot key.

**F3 — same name under different issuers is common enough to forbid
name-only binding across issuers.** Among 10,042 plausible distinct names
across both sources, 398 appear under more than one issuer CIK. Without
the reporting-owner CIK we cannot say how many are one person on several
boards versus different people; either way a name alone does not identify.

**F4 — cross-source deterministic context matching is small but real.**
Of 6,834 plausible 8-K `(issuer CIK, name)` pairs, 204 also appear in the
proxy export for the **same** issuer. Low because the two sources cover
different issuer sets (903 proxy issuers vs 1,742 8-K issuers) and
different years — not because the key is weak. `(issuer CIK, normalized
name)` is the only deterministic handle a name-only source has.

**F5 — reporting-owner scale, from hashes only.** 8,944 distinct
`party_key`s across 4,364 issuers in the holdings export; 81,455 activity
rows. How many are natural persons versus 10% entity owners, and how many
proxy/8-K names match a reporting owner on the same issuer (the ticket's
questions 1 and 3 proper), **remain unmeasured** until Snowflake is
reachable.

## What this settles for ticket 02

- `owner_cik` (Form 3/4/5) and CRD (Form ADV) are the only identifiers;
  everything else is a name under an issuer context.
- The proxy source cannot participate in *any* binding rule until its
  parser stops leaking role text into `exec_name`. That is a code fix,
  outside this map's planning scope — raised as
  [ticket 10](../issues/10-fix-proxy-executive-name-parser-leak.md) (task,
  hands to whoever owns the parser).
- For 8-K names, the strongest deterministic key is
  `(issuer CIK, normalized name)` matched against a reporting-owner row
  with a consistent officer/director flag. Its hit rate is unknown (F5).
- A name alone never binds, and never across issuers (F3) — consistent
  with the repo rule.

## Still blocked

Questions 1 and 3 of the ticket need `sec_ownership_reporting_owner`.
Re-run when Snowflake billing is restored: a three-way join on
`(cik, normalized name)` plus a flag breakdown by `owner_cik`. Tracked as
[ticket 09](../issues/09-measure-reporting-owner-overlap-when-snowflake-returns.md).
