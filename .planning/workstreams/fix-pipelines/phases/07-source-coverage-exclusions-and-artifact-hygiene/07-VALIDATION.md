---
phase: 07
slug: source-coverage-exclusions-and-artifact-hygiene
date: 2026-07-12
status: draft
---

# Phase 07 Validation Strategy

## Test Layers

| Layer | Scope | Required evidence |
| --- | --- | --- |
| Unit | Temporal intervals, IDs, conflict rules, coverage fingerprints, manifests, silver policies | Focused `uv run pytest` targets pass |
| Integration | PostgreSQL outbox/migrations, Snowflake SQL executor, semantic DuckDB merge, artifact cache | Real database fixtures and connector doubles prove state transitions |
| Architecture | AWS-only orchestration and passive Terraform boundary | `tests/architecture` pass; Step Functions definition assertions pass |
| Live dev | Complete staged generation, parallel retry/reuse, activation, temporal traversal, rollback | Dated evidence captured with generation IDs and hashes |

## Per-Plan Verification Gates

- 07-00: live Native App contract loading, typed dates, supported GRAPH_INFO/BFS/multi-hop operations, semantic MDM↔graph parity, and stable-view generation switch produce a GO verdict or block Phase 7. The platform registry verifies discovery; experimental LIST_GRAPHS is diagnostic only.
- 07-01: additive migrations; interval/conflict/version tests; no physical deletion path in ordinary APIs.
- 07-02: exhaustive coverage manifest; EDGE-07/08 categories; stale fingerprint and undocumented type fail closed.
- 07-03: transactional outbox atomicity; claim/retry lifecycle; 5/15 minute health thresholds.
- 07-04: complete fan-out manifest; content-addressed reuse; failed shard retry; no overlapping activation.
- 07-05: identity/property parity; same-generation endpoints; single pointer activation; rollback retention; temporal queries.
- 07-06: partial merge preserves keys; ambiguous conflicts abort; ETag/version conflict prevents promotion; cache hit makes zero SEC calls; repair audit complete.
- 07-07: all mandatory phase-exit evidence passes in dev with `SNOW_CONNECTION=snowconn`.

## Commands

```bash
uv sync --extra s3 --extra snowflake --extra mdm-runtime
uv run pytest tests/mdm tests/application tests/unit tests/architecture
SNOW_CONNECTION=snowconn uv run pytest tests/integration -k 'graph or mdm or silver'
```

Live DDL and verification commands must use `SNOW_CONNECTION=snowconn`. Deployment changes must be
made through `infra/scripts/deploy-aws-application.sh`, never passive Terraform.

## Failure Injection Matrix

| Injection | Expected result |
| --- | --- |
| One relationship partition fails | Generation remains inactive; successful immutable partitions remain reusable |
| Canonical S3 object changes after localization | Promotion aborts as retryable conflict |
| Same business key has ambiguous payload | Silver merge aborts with row-level report |
| Coverage exclusion fingerprint changes | Verification and generation activation fail |
| Graph property differs from MDM | Identity may match, but property parity fails activation |
| Entity merge remaps endpoint | Canonical traversal succeeds and original identity remains in provenance |
| Rollback requested | Pointer returns to retained verified predecessor; node/edge views switch together |

## Phase Exit

Phase 7 passes only when all automated suites are green and the bounded dev rehearsal captures every
mandatory criterion from `07-CONTEXT.md`. A warning-only exclusion, count-only parity, partial graph
activation, or silver `--force` bypass is a hard failure.
