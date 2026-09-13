# 19 — `sec_company_ticker`'s DuckDB and Snowflake copies genuinely disagree

**What was found:** Live during [Ticket 11](11-post-cutover-reconciliation-gate.md)'s
post-cutover reconciliation run (2026-09-12), `sec_company_ticker` failed both structural checks
and its semantic-content digest:

- `bronze_to_silver`/`required_parent` integrity: 4,166 cik-orphans against `sec_company`.
- `semantic_content_digest`: `duckdb_key_digest` != `snowflake_key_digest` even though the same
  500 DuckDB-selected keys were requested from both sides (`scope_mode="authority_column"`,
  `out_of_scope_count: 0`) — meaning Snowflake's `sec_company_ticker` is missing or returning
  different rows for some of the exact keys DuckDB has, not just lagging behind on newer rows.

**Why this isn't explained by anything already known:** release-readiness
[Ticket 40](../../release-readiness/issues/40-root-cause-empty-ticker-reference-pipeline.md)
already investigated `sec_company_ticker` directly and found it healthy — "8,056 distinct CIKs
... near-exact match [to SEC's own 8,017]... this pipeline is healthy and essentially complete."
That investigation was about whether the *source data* is correct (yes). This finding is a
different question: whether DuckDB's and Snowflake's independently-populated copies of that
already-correct data actually agree with each other. They don't, for at least some of a 500-key
sample.

**Not yet investigated:**
- Whether the 4,166 cik-orphans and the digest mismatch are the same root cause or two separate
  ones.
- Whether this is a genuine `EDGARTOOLS_SILVER` ingestion gap for this specific table (landing
  buffer never picked it up, a COPY INTO failure, a dbt model bug) or a reconciliation-tool
  artifact specific to this table's shape (e.g. a business-key/authority-column declaration
  mismatch in `contracts.py`).
- Whether this predates [Ticket 10](10-atomic-write-path-cutover.md)'s cutover (like the other
  three tickets 11 found failing) or is itself new.

## Done when

Root cause is found and either fixed, or determined to be a pre-existing gap already covered by
another ticket. A repeat `table-reconcile --tables sec_company_ticker` run passes clean
afterward.

**Blocked by:** none — independent investigation, does not block Ticket 11's GO/NO-GO decision
(which treats this as one open finding among several, not a blocker in itself).
