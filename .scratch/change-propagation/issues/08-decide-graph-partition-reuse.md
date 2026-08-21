# Decide graph partition reuse and candidate-generation publication

Type: grilling
Status: open
Blocked by: 02, 06

## Question

How should exported MDM changes rebuild only affected graph partitions while
still producing one complete immutable Relationship Generation Snapshot that
can be fully verified and atomically activated?

Decide the stable partition key, content hash independent of generation
watermark, property/evidence hash inputs, unchanged-partition reuse, changed
node/edge rebuild, retirement and eligibility filtering, generation identity
across retries, parity/completeness checks, and pointer activation. Reconcile
the existing Postgres generation-builder lifecycle with physical Snowflake
graph publication and eliminate normal workflow tails that sync one generation
while verifying another.
