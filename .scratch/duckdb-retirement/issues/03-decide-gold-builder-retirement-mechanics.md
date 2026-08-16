# Decide Gold's Python-Builder Retirement Mechanics

Type: grilling
Status: open
Blocked by: 07

## Question

The closed silver-snowflake-migration map's Ticket 03 already decided the
*target*: `gold_models.py`'s ~20 Python builders retire entirely in favor
of dbt gold `ref()`-ing dbt silver directly, which also retires
`EDGARTOOLS_SOURCE`'s current gold-mirror purpose and structurally moots
the `iter_gold_tables` OOM-mitigation concern (CLAUDE.md's "Gold-build
memory / daily_incremental OOM 5-whys" — the streaming-generator fix that
concern motivated becomes unnecessary if there's no longer a Python
builder pass over silver at all). Not yet decided: how the cutover from
Python-built gold to dbt-native gold actually happens.

Decide: are new dbt gold models built and validated against the existing
Python-builder output *before* `gold_models.py` is deleted (parallel-run),
or is this a hard swap once dbt silver models are trusted? Per the
validation standard from [Decide the Cutover Validation Standard](
07-decide-cutover-validation-standard.md), what does gold parity mean
concretely — same 8 dynamic tables, same row counts, same aggregation
values, over what data volume/time window? `validate_data_quality.py`'s
separate `build_gold()` call was already flagged by the closed map's
Ticket 03 as becoming "SQL assertions against live Snowflake gold" — does
that conversion happen as part of this ticket's scope or is it a
downstream implementation detail? Also confirm whether any current
consumer of `gold_models.py`'s Python output (beyond
`validate_data_quality.py`) exists and needs its own migration path.

## Deliverable

A decided cutover mechanism (parallel-run-then-swap vs. hard swap, and how
parity is proven per the shared validation standard) for retiring
`gold_models.py` in favor of dbt-native gold.
