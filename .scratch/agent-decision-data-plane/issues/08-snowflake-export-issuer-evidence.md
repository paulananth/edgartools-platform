# 08 — Snowflake export expansion for issuer neighborhood evidence

**What to build:** Agent-needed issuer evidence that today lives only in silver (minimum set: auditor report evidence, subsidiary evidence, employment events — adjust only if a table is not yet populated on main) is included in the Snowflake export/manifest path so agents never depend on DuckDB silver.

**Blocked by:** None for starting once evidence tables exist on main (prefer after Ticket 20 ingest implementations already landed). Not blocked by 01–07.

**Status:** resolved

- [x] Export registry/planning includes the minimum issuer evidence tables required for Trading-Relevant Neighborhood
- [x] A gold/export run produces those tables for Snowflake SOURCE consumption
- [x] Schemas are stable enough for dbt or contract views to bind
- [x] Agents still have no requirement to read silver for those facts

