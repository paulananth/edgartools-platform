# Hosted ADV Private-Fund Ingestion

## Destination

Provide one supported, current Bookkeeping path that loads retained IAPD Schedule D 7.B(1)/(2) records into the current Fund Structure and Adviser-profile model, writes to hosted Snowflake Silver/MDM, and verifies the resulting adviser-to-fund relationships in the hosted graph.

## Notes

- Use the current domain language and identity rules in [`CONTEXT.md`](../../CONTEXT.md), the current source files under `rules/sources/iapd.adv/`, and the [`data-operations`](../../skills/data-operations/SKILL.md), [`bookkeeping`](../../skills/bookkeeping/SKILL.md), and [`AWS/Snowflake operations`](../../skills/aws-snowflake-operations/SKILL.md) skills.
- Current hosted targets: Snowflake `EDGARTOOLS_SILVER` for Silver and Snowflake-hosted Postgres for MDM. A load uses the configured hosted connections; a local test store is not a hosted substitute.
- A hosted reload starts from a complete captured delivery with its real receipts and producer run identity. Do not manufacture capture evidence or request new IAPD data without separate operator permission.
- Do not run the retired `load_history` Step Function or its legacy `ingest-relationship-sources` path for this work.

## Decisions so far

(none)

## Not yet specified

The current Adviser/Fund source contract must be reconciled with the current Company/Person Adviser-profile, Fund Structure, and `INVESTMENT_ADVISER_TO` model; the child ticket resolves this in the implementation.

## Out of scope

- Automatic recurring acquisition or wiring to a retired daily/history state machine.
- Pre-2025 ADV history, Firm Roster cross-checks, and unrelated MDM/Gold refresh work.
- Any new public IAPD request without explicit operator authorization.
