# Decide whether gold compute stays in Python/DuckDB or moves into Snowflake SQL

Type: grilling
Status: resolved
Blocked by: (none)

## Question

[Decide the fate of the dual gold path](05-decide-dual-gold-path-fate.md)
established that today's architecture is not two competing computations —
it's one Python compute engine (`edgar_warehouse/serving/gold_models.py`,
`iter_gold_tables()`) whose output is mirrored into Snowflake via
`EDGARTOOLS_SOURCE` -> dbt -> `EDGARTOOLS_GOLD`, with dbt doing real
transformation in only 3 of ~26 models (`company`, `financial_factors`,
`adv_fund_count_reconciliation`) and MDM writing one table
(`MDM_COMPANY_ENTITY`) directly.

Given the map's async/message-driven destination, decide:

(a) **Formalize the current split as intentional** — Python remains the
sole gold compute engine (reading `silver.duckdb`), Snowflake/dbt stays a
publish/mirror layer, and only the *delivery mechanism* (S3 export +
native-pull ingestion, already partially event-driven via S3->SNS->task)
becomes fully message-driven instead of gated behind the synchronous
`load_history`/`gold-refresh` chain; or

(b) **Move some/all gold computation into Snowflake SQL** — real dbt
transformation reading further upstream (bronze-adjacent tables, if/when
any exist independent of Python's serving export), making gold natively
event-driven inside Snowflake (e.g. dynamic tables refreshing off
object-store-driven ingestion) without requiring a Python compute step for
those tables at all; or

(c) some other split (e.g. per-table, based on transformation complexity —
the 3 dbt models that already do real joins vs. the ~23 pure mirrors).

This determines whether "the gold consumer" in the new architecture is a
Python/ECS process, a Snowflake-native pipeline, or both — which shapes how
[Decide event granularity for bronze-write triggers](04-decide-event-granularity.md),
[Decide MDM's role in the decoupled architecture](06-decide-mdm-role-in-new-architecture.md),
and [Decide the completeness/watermark signal for async silver and gold](07-decide-completeness-watermark-signal.md)
get designed.

## Answer

**(a), sharpened: Python computes gold from silver; Snowflake only
computes when the inputs genuinely only co-exist in Snowflake. Only the
delivery mechanism becomes fully message-driven.** Decided 2026-08-11.

**Why (a), not (b) or an open (c):** every piece of supporting evidence
this map gathered points the same direction, not just this ticket's own
reasoning:
- [Ticket 09](09-decide-silver-write-storage-target.md) decided silver
  stays on DuckDB — (b)'s enabler (bronze-adjacent, silver-shaped data
  landing natively in Snowflake, independent of Python's export) will
  never exist under that decision.
- [Ticket 02](02-research-messaging-substrate-options.md) found Snowpipe
  Streaming — the one mechanism that could make the delivery leg more
  Snowflake-native — isn't worth adopting (cost-equivalent to the current
  path since Dec 2025; would replace, not extend, the write mechanism).
- [Ticket 04](04-decide-event-granularity.md)'s entire async design
  (accession-level events, SQS fan-out to parallel Python/ECS parse
  workers plus a reducer) is built around Python/ECS consumers with
  nothing upstream of gold assuming or needing Snowflake-native compute.

**The precision this ticket adds over the original binary framing:**
`company.sql`, `financial_factors.sql`, and `adv_fund_count_reconciliation.sql`
keep doing genuine Snowflake-side transformation — not as an exception to
patch, but because those specific operations join data that only
co-exists in Snowflake (silver's export + MDM's separate export into
`EDGARTOOLS_GOLD`). Forcing them into Python would mean either duplicating
MDM's export data into the warehouse (recreating the dual-write problem
[ticket 05](05-decide-dual-gold-path-fate.md) already corrected) or losing
a join Snowflake already does cheaply. The governing principle isn't "100%
Python" — it's **compute lives wherever its inputs already co-exist**,
which today means Python for everything sourced purely from silver, and
Snowflake only for the 3 models whose inputs span two independently-written
Snowflake destinations (Python's export and MDM's export).

**What changes under this decision:** only the delivery mechanism — S3
export → SNS → SQS (ticket 02/04's substrate) replacing the
synchronous `load_history`/`gold-refresh` gate. Gold's compute engine,
table count, and per-table transformation split all stay exactly as they
are today.

**This closes the last open grilling ticket on this map.** All eight
elements the Destination named as required before implementation — message
substrate, event granularity, consumer boundaries, silver-write
concurrency model, gold compute location, MDM's role,
completeness/watermark signaling — are now decided. Migration sequencing
from the current live pipeline remains, per the map's own "Not yet
specified" section — now sharp enough to ticket, since it needed the
target shape locked first.
