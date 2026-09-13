# Inventory bundle JSON as MongoDB documents

Type: research
Status: resolved
Blocked by: none

## Question

What would a v2 Mongo document be, given the in-repo bundle is already a
nested Python dict and there is no Mongo in the repo?

Determine:

1. Fields and nesting of `build_issuer_subject_bundle` / watermark /
   coverage flags / feature vector (19 keys). What is one document vs
   many collections (subject, features, edges).
2. Whether any existing JSON writer (`JsonAlignmentStore`, serving
   targets, Streamlit) is a seed for a Mongo writer, or is Snowflake-only
   alignment.
3. Identity keys (CIK, contract version, READY, graph generation id) that
   a unique index would need.
4. What ADR 0001 / CONTEXT would have to add for a **v2** Mongo surface
   while keeping v1 Snowflake (do not propose replacing v1).

Cite code and ADRs. Reuse contract research 10; do not reopen its v1
verdict. Do not implement.

Save findings at
`.scratch/mongodb-v2-agent-interface/research/02-bundle-json-as-mongo-documents.md`.

## Answer

**A v2 Mongo document would be a BSON projection of
`build_issuer_subject_bundle` (CIK envelope, eight `sections`,
coverage, `agent_grade`, four-field watermark identity), optionally
split so Feature Screen rows and edges are their own documents. It is
not a second warehouse and not v1 SoE.**

No persisted JSON agent SoE exists. `JsonAlignmentStore` is local
cause-alignment scratch. `SnowflakeTarget` writes Parquet.
Streamlit Agent View reads Snowflake display views. No `pymongo` /
Mongo / DocumentDB in `pyproject.toml`, `uv.lock`, or Terraform.

Feature Screen is one Python return with `rows[]` for the universe —
that return cannot be one BSON document (~70–82 MiB vs 16 MiB).
Collection shapes left unchosen for grilling 04: (A) nested issuer
bundle, (B) envelope + per-CIK screen rows + edge docs, (C)
SQL-sketch relational-mirror collections.

Identity dimensions (not picked): CIK, contract version `"1"`,
`agent_grade` vs Snowflake READY (READY is absent from the Python
dict), `graph_generation_id`, `business_date`, `gold_run_id`. The
Python identity pin omits bronze hashes.

ADR 0001 stays “Delivery = Snowflake Decision Contract.” Product
table “S3/API optional later” is the v2 door. A new additive ADR
would be required; v1 Snowflake is not rewritten. Atlas must not
become warehouse ingest.

Findings:
[research/02-bundle-json-as-mongo-documents.md](../research/02-bundle-json-as-mongo-documents.md)
