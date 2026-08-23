# Decide baseline, migration, cutover, and rollback sequencing

Type: grilling
Status: open
Blocked by: 09

## Question

How should production move from the current full-scan/mutable-key paths to the
Change Propagation Run contract without a full bronze replay, concurrent
canonical writers, lost changes, or an unrollbackable consumer split?

Decide baseline inventory and cursor seeding, read-only reconciliation,
boundary-by-boundary cutover order, treatment of in-flight executions, links to
the open Snowflake-silver/dbt-gold/DuckDB-retirement work, feature-flag or
task-definition revision boundaries, rollback watermark rules, and retention
of superseded DuckDB, mutable landing, and legacy SOURCE artifacts. Every
operator step must be committed, repeatable, and secret-safe.
