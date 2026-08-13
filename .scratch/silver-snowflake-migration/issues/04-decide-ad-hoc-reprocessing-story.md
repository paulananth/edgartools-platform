# Decide the Ad-Hoc Reprocessing Story

Type: grilling
Status: open
Blocked by: 01

## Question

CLAUDE.md documents silver as "also used for ad-hoc re-processing" by
operators — today that means running Python/DuckDB code directly against
`silver.duckdb`. What replaces that workflow once silver is Snowflake-native
dbt models: `dbt run` with operator-supplied vars/selectors, a Snowflake
worksheet against the landing zone or silver models directly, a thin CLI
wrapper the warehouse package still exposes, or something else? Whatever is
chosen must preserve the same operator capability (re-derive a subset of
silver from bronze without a full pipeline re-run) without silently
regressing it into "only a full `load_history`/`daily_incremental` re-run
can do this now."
