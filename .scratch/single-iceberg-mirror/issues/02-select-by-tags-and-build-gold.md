# Select the mirror's tables by approved tags, and read them from Gold

Status: open
Type: task

Follows [Qualify one Iceberg mirror database from an empty test source](01-qualify-from-empty.md), which proved the
mirror on three tables it named. A hosted run needs the operator's approval of a new test plan.

## Parts

- [ ] Price every bound before create: Postgres compute, the serverless apply, Iceberg storage; keep the create start
  time and a checkpoint every 30 minutes
- [ ] Tables selected by approved mappings and tags, exclusions proved absent
- [ ] OpenMetadata and AutoOntology see the same table set the tags select
- [ ] A read-only consumer denied UPDATE as well as INSERT, and denied the `$CHANGES` companions
- [ ] A Gold model in a separately approved test target reads the mirror, with exact-result checks
- [ ] Learning → skill
