# Decide the Replacement Path for Direct Silver Consumers

Type: grilling
Status: claimed
Blocked by: 01

## Question

`edgar_warehouse/serving/gold_models.py`'s ~20+ `_build_*` functions
(`_build_dim_company` etc.) and MDM's `ShardedSilverReader` both query an
embedded DuckDB connection directly via raw SQL today. Once silver lives
natively in Snowflake, what replaces them?

The sharpest candidate: gold already runs entirely as dbt models on top of
Snowflake `SOURCE` — if silver also becomes dbt models (Ticket 01), does
`gold_models.py`'s Python-side table-building logic retire entirely in
favor of pure dbt gold models reading the new dbt silver models directly,
unifying the whole `SOURCE → SILVER → GOLD` chain in one engine? Or does a
real reason remain for `gold_models.py` to exist as a separate Python layer
(e.g. `iter_gold_tables`'s streaming-generator memory-pressure fix from the
gold-build-memory-reliability workstream — confirm whether that concern
still applies once gold tables are dbt-materialized directly from
Snowflake rather than built in Python and streamed to storage one at a
time)? Answer for MDM's `ShardedSilverReader` separately — its
`_TABLES` allowlist has already caused two real production gaps
(`sec_thirteenf_filing`, `sec_employment_event`, see CLAUDE.md's
"INSTITUTIONAL_HOLDS / EMPLOYED_BY" incident) from being an easy-to-forget
manual list; whatever replaces it should not reintroduce that failure
shape.
