# Phase 8: Neo4j Native App Verification Gaps - Research

**Researched:** 2026-07-12

## Findings

1. Installed app `NEO4J_GRAPH_ANALYTICS` is listing version `V1_0`, patch `32`; patch 33 exists in
   the current Neo4j changelog but does not advertise fixes for GRAPH_INFO, BFS, or LIST_GRAPHS.
2. Official current algorithm syntax is `CALL app.graph.<algorithm>('CPU_X64_XS', {project,
   compute, write})`. The repository's removed GRAPH_INFO/BFS renderers use an obsolete graph-name
   first argument and snake_case root keys.
3. Official BFS configuration requires `compute.sourceNodeTable`, `compute.sourceNode`, optional
   `maxDepth`, and `write[{'outputTable': ...}]`. It does not use `source_node_id`, `max_depth`, or
   `write_options`.
4. GRAPH_INFO has installed signature `GRAPH_INFO(VARCHAR, OBJECT)`. Live probing accepted the
   current sectioned shape and rejected `compute.consecutiveIds`; GRAPH_INFO therefore needs an
   empty compute object with the same project mapping used by WCC.
5. LIST_GRAPHS exists only as `EXPERIMENTAL.LIST_GRAPHS()`. A correctly located live call fails
   inside the app handler because it attempts an invalid `LIST_FILES` child-job statement. This is
   an external app defect, not a platform SQL naming error.
6. The current verifier intentionally omits GRAPH_INFO/BFS/LIST_GRAPHS and uses WCC alone. It also
   combines all failures into one boolean/status, so a missing compute pool and a parity mismatch
   are not cleanly separated for operators.
7. Current strict verification may stop on parity before giving a clean Native App contract-load
   result. Verification should compute every domain independently and return all domain statuses.

## Recommended Implementation

- Restore GRAPH_INFO and BFS using current config builders shared with WCC project mapping.
- Add LIST_GRAPHS as a non-mutating capability check at its installed EXPERIMENTAL location.
- Add check-level domain metadata and top-level `failure_domains`, `readiness`, `capability`, and
  `parity` summaries. Overall exit remains nonzero when required readiness/parity/capability checks
  fail, while output states exactly which domain failed.
- Treat LIST_GRAPHS as an observed external blocker in live evidence rather than pretending a repo
  change can repair the Marketplace handler.
- Unit-test rendering, error-row handling, and domain classification; then run live dev checks.

## Validation Architecture

- Renderer tests assert current camelCase project/compute/write configuration and exact installed
  schema for LIST_GRAPHS.
- Fake cursor tests cover readiness-only, parity-only, capability-only, and multi-domain failures.
- Live run uses `SNOW_CONNECTION=snowconn`, captures app version/patch, and records each procedure.
- No Phase 6 or canonical relationship data mutation is required. BFS output uses a uniquely named
  smoke table and cleans it after evidence capture.

## Sources

- Neo4j Graph Analytics for Snowflake current operations reference.
- Neo4j Graph Analytics for Snowflake BFS documentation.
- Neo4j Graph Analytics for Snowflake changelog.
- Installed Snowflake `SHOW PROCEDURES ... IN APPLICATION` inventory.

## RESEARCH COMPLETE

