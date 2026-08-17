# 01 — Establish Snowflake-Native Surrogate Keys for Gold's Hash-Keyed Dimensions

**What to build:** A single, uniformly-applied key-generation pattern (dbt
macro or equivalent) for every gold model whose surrogate key is currently
derived from DuckDB's `hash()` SQL function or Python's `hashlib.sha256` —
neither of which has a drop-in Snowflake equivalent that reproduces the same
bit values. Every later ticket in this batch (02-05) calls this one macro
instead of re-deriving a key strategy per table. Also decides and documents
whether existing key values are preserved or intentionally reset during
cutover, and who downstream (dashboard queries, MDM export joins, any
external consumer) currently depends on today's literal key values.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] A macro exists that deterministically derives a BIGINT surrogate key
      from one or more natural-key columns, usable identically across every
      affected model (`form_key`, `filing_key`, `fact_key`, `party_key`,
      `security_key`, `private_fund_key`, and any other hash-derived key)
- [ ] Decision recorded on whether key values change during cutover, with an
      inventory of every known consumer of today's key values
- [ ] The macro has a dbt unit test (or equivalent) against a representative
      natural key, confirming deterministic output
- [ ] Applied end-to-end on one pilot column (e.g. `filing_activity`'s
      `filing_key`) to prove the pattern before Tickets 02-05 apply it broadly
