# Locate issuer neighborhood evidence tables

Type: research
Status: resolved
Blocked by: none

## Question

Where do the issuer Trading-Relevant Neighborhood evidence tables actually
live today — DuckDB silver, Snowflake SOURCE, SILVER, GOLD, or nowhere —
and which of them are already on the Snowflake export/manifest path?

At minimum locate:

- auditor report evidence (SQL sketch reads `EDGARTOOLS_SOURCE.SEC_AUDITOR_REPORT_EVIDENCE`)
- employment events / EMPLOYED_BY sources
- subsidiary / parent evidence
- institutional holdings used for holders_of_subject
- ownership rows used with IS_INSIDER

Cite live objects or in-repo export/dbt models. Save findings at
`.scratch/agent-decision-contract/research/08-issuer-neighborhood-evidence.md`.

Predecessor: [Snowflake export issuer evidence](../../agent-decision-data-plane/issues/08-snowflake-export-issuer-evidence.md)
is closed as intent; this ticket is a live inventory, not a reopening.

## Answer

Live inventory is at
[research/08-issuer-neighborhood-evidence.md](../research/08-issuer-neighborhood-evidence.md)
(prod `EDGARTOOLS_PROD` via `edgartools-prod`, 2026-09-10).

- Auditor, subsidiary, employment-event tables exist on DuckDB silver, SILVER landing/collapse, and SOURCE passthrough (predecessor export intent is wired). **Auditor and subsidiary are 0 rows everywhere.** Employment events are populated (SILVER/SOURCE 7,676). None of the three have a gold model.
- `EMPLOYED_BY` also uses `sec_executive_record` → gold `EXECUTIVE_RECORDS` (14,755). Graph `EMPLOYED_BY` is 3.
- Holdings: gold `INSTITUTIONAL_HOLDINGS` = 6,799,919 from silver `sec_thirteenf_holding` (on export). `sec_thirteenf_filing` is SILVER-only (14,364), not SOURCE. Graph `INSTITUTIONAL_HOLDS` is 0. Sketch `BUNDLE_HOLDERS_OF_SUBJECT` binds `issuer_cik`/`manager_cik`/`shares`, which live gold does not have.
- Insiders: silver owner/txn tables + gold `OWNERSHIP_*` accessions + graph `IS_INSIDER` (1,617). Raw owner tables are not on SOURCE export; gold ownership drops `owner_cik`/`owner_name`.
- `EDGARTOOLS_DECISION` exists and is empty; issuer-bundle SQL is still a sketch.
