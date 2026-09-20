# Decide S3 path templates and Snowflake native-pull manifests for enrichment evidence

Type: grilling
Status: resolved
Blocked by: none

## Question

The GoF review's Appendix C item 7 asks for S3 path templates and Snowflake
native-pull manifests for normalized enrichment evidence.

The repo already has a validated path catalog boundary
(`edgar_warehouse/infrastructure/dataset_path_catalog.py`, cited directly in
the review's own evidence table) governing existing source families' S3
layout, and the existing Snowflake native-pull bootstrap SQL convention
(`infra/snowflake/sql/bootstrap/`) for how external stages/tables get
declared.

Does GLEIF (and future enrichment sources) simply register new entries in
the existing `dataset_path_catalog.py` and follow the existing bootstrap-SQL
native-pull pattern — reusing both seams rather than inventing a parallel
one — or does the multi-artifact publication-aggregate shape (Level 1 +
Relationship Records + Reporting Exceptions + mappings, one publication with
several member artifacts) need something the existing catalog doesn't
support?

## Comments

- 2026-09-19: operator accepted the recommendation ("keep going with Q2-Q4").

## Answer

Reuse both existing seams: register GLEIF entries in
`edgar_warehouse/infrastructure/dataset_path_catalog.py` and follow the
existing `infra/snowflake/sql/bootstrap/` native-pull pattern. One addition:
a manifest artifact at the *publication* level, enumerating a publication's
member artifacts' catalog entries — the one level today's per-artifact
catalog rows don't cover, needed because a GLEIF publication (ticket 02) is
several artifacts (Level 1 + RR + RE, or one mapping file) that must be
verified complete together, not one payload.
