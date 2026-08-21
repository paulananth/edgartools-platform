# Decide silver delta publication and scope-completion semantics

Type: grilling
Status: open
Blocked by: 01, 02, 04

## Question

How should collision-free producer outputs become one complete, current
Snowflake silver publication while processing only the Change Propagation Run's
Affected-Key Closure?

Decide producer/window/attempt/file identities, immutable landing paths and
checksums, table-specific upsert/retirement/replacement behavior, content-hash
no-op suppression, parser-version reprocessing, concurrent producer ordering,
retry-after-partial-load, and the barrier that proves every expected file was
loaded and every affected dbt silver table reached the run's publication
identity. The answer must eliminate mutable same-key Parquet/manifests and must
not store the source-consumption cursor inside the silver state being produced.
