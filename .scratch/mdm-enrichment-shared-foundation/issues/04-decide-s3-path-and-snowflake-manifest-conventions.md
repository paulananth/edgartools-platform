# Decide S3 path templates and Snowflake native-pull manifests for enrichment evidence

Type: grilling
Status: open
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
