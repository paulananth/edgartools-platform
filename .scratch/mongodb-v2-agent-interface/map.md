# MongoDB v2 Agent Interface

Label: `wayfinder:map`

## Destination

An implementation-ready, decision-complete plan for a **v2 Agent Decision
Surface** on MongoDB: documents that project issuer v1 Agent-Grade Input
Facts (As-Of Decision Features, current `IS_INSIDER`, current
`EMPLOYED_BY`, Decision Watermark / READY rules) so an internet agent can
read them from Atlas, **without** replacing the Snowflake Decision
Contract as v1 SoE.

## Notes

- Repo: `edgartools-platform`. Planning only unless a later Notes override
  carries implementation. Produce decisions, not PRs, until the way is
  clear.
- Skills: `/grilling` (one question at a time), `/domain-modeling`,
  ADR 0001, ADR 0006, `CONTEXT.md` Agent decision support,
  official `mongodb-atlas` plugin + `mongodb-schema-design`.
- Destination locked 2026-09-11 from this `/wayfinder` ask plus prior
  research: Atlas Free is the only perpetually free public store of the
  three vendors; ADR 0001 / contract ticket 10 keep Snowflake as v1.
- v2 is **additive**. Snowflake remains the Agent System of Engagement
  for v1. MongoDB is a later public-internet serving layer (the ADR 0001
  “S3/API optional later” door), not a second warehouse, not bronze,
  not silver.
- Predecessors (inputs, do not reopen):
  - [Inventory JSON and MongoDB as an end-user agentic data plane](../agent-decision-contract/issues/10-json-mongodb-as-agentic-data-plane.md)
    — JSON is the Python bundle *shape*; no Mongo in repo or Terraform.
  - [v1 Agent-Grade Inputs](../agent-decision-v1-inputs/map.md) and
    [v1 Agent-Grade Feature Inputs](../v1-agent-grade-feature-inputs/spec.md)
    — what v1 facts are; 21-CIK factor coverage; load_history vs daily.
  - [Free + public-network databases](../agent-decision-v1-inputs/research/10-free-public-agentic-databases.md)
    — Atlas M0 never expires; public hostname; IP allowlist / `0.0.0.0/0`;
    512 MB; 500 connections. Snowflake trial is not free. Databricks Free
    Edition is non-commercial.
- AWS-only for warehouse ingest. Atlas is a **serving target**, not a new
  cloud for SEC capture. Do not chart a second ingest map
  ([Incremental Change Propagation](../change-propagation/map.md)).
- Ask the operator one grilling question at a time. Standing preference:
  recommended answers unless the operator overrides.
- Ownership: Grok's `grok/mongodb-v2-agent-interface` branch merged to
  `main` via PR #606 (2026-09-12); the branch no longer exists. The prior
  Grok-worktree isolation note above no longer applies — confirmed live
  2026-09-19 (`gh pr list --head grok/mongodb-v2-agent-interface` shows
  `MERGED`, no matching local or remote branch). Claude now stewards this
  map, including its 4 open `v2-mongo-decision-projection` implementation
  tickets (01-04). Do not implement v1 factor tickets (Claude's own,
  unrelated map).
- Reopened 2026-09-19 at operator request: whether SPARQL/RDF should serve
  some or all of this v2 layer instead of, or alongside, MongoDB is back
  under active grilling — the "decision-complete" state below predates
  this. ADR 0009 stays accepted until/unless that grilling produces a
  supersession; MongoDB implementation tickets 01-04 are not blocked by
  it in the meantime. See `.scratch/agent-contract-query-interface-options/`
  for the SPARQL-hosting research feeding this.

## Decisions so far

- [Inventory Atlas Free limits versus Decision Graph Bundle size](issues/01-inventory-atlas-free-vs-bundle-size.md) — M0 holds 21-CIK and sparse ~63k one-doc-per-issuer v2; dense-Apple 63k and a one-document Feature Screen do not (16 MiB).
- [Inventory bundle JSON as MongoDB documents](issues/02-inventory-bundle-json-as-mongo-documents.md) — v2 would project the Python bundle dict; no JSON SoE today; Feature Screen must not be one universe document; collection shape unchosen.
- [Lock how v2 Mongo relates to the Snowflake Decision Contract](issues/03-lock-v2-mongo-vs-snowflake-soe.md) — Projection of READY Snowflake; publisher fail-closed (v2 agent abstains; Mongo never wins); full Agent-Grade watermark + READY marker on every agent-grade document.
- [Lock what v2 Mongo publishes](issues/04-lock-v2-published-collections.md) — Two collections: nested issuer bundle per CIK (unavailable stubs kept) + Feature Screen per CIK; not Explore gold; not per-edge; not SQL-flat.
- [Lock Atlas tier and public network for v2 agents](issues/05-lock-atlas-tier-and-network.md) — M0 now; paid only if needed later; public `mongodb+srv` with `0.0.0.0/0` + TLS + DB user.
- Mongo Decision Projection data contract — database `edgartools_decision`; collections `issuer_subject_bundle` and `subject_feature_screen`; `_id` = int CIK; full watermark + READY; [data-contract.md](data-contract.md).
- [Lock who writes v2 Mongo and when](issues/06-lock-mongo-writer-and-ready-timing.md) — Separate publisher after READY; in-place fail-closed hide (`not_ready` + `agent_grade=false`); no delete; no pointer collection.
- [Lock how v2 agents authenticate to Atlas](issues/07-lock-v2-agent-auth.md) — One read-only SCRAM user for internet agents; separate publisher write user; product OAuth later; plugin OAuth is operator-only.
- [Lock how the v2 publisher is tested](issues/08-lock-v2-publisher-test-strategy.md) — Mock Mongo driver in unit tests; optional operator M0 smoke; no Atlas secrets in CI.
- [ADR 0009 Mongo Decision Projection](../../docs/adr/0009-mongo-decision-projection.md) — v2 Atlas projection; v1 Snowflake SoE unchanged.

## Not yet specified

<!-- MongoDB implementation is decision-complete (tickets 01-08); the
     SPARQL/RDF reopening below is not yet ticketed pending grilling -->

- Operator: provision M0, apply `$jsonSchema`, create read-only agent user
  + publisher write user, set `0.0.0.0/0`.
- Implementation: separate publisher after READY (not this map unless a
  later Notes override). Use `/to-tickets` to slice that work.
- Scope locked 2026-09-19: SPARQL/RDF evaluated for the relationship-edge
  half only (`IS_INSIDER`/`EMPLOYED_BY`), not the tabular features; open
  survey, not SPARQL-only; fail-closed *outcome* required, mechanism may
  be RDF-native. See
  [Survey free/public serving options for the v2 relationship-edge layer](issues/09-survey-relationship-edge-serving-options.md)
  (claimed, in progress).
  Which option wins, and whether that reopens ADR 0009, is a follow-on
  grilling ticket once that survey lands — not yet sharp enough to
  ticket.

## Out of scope

- Replacing Snowflake as v1 Agent SoE (ADR 0001; contract ticket 10).
- Ingest, bronze, PostgreSQL ledger, edgartools gateway.
- Manager ADV / `MANAGES_FUND` agent-grade sections.
- Auditor / parent / 13F holders becoming agent-grade (still
  `unavailable` on issuer v1).
- Trading execution, market prices.
- Databricks as v2 (non-commercial Free Edition; not requested).
- Making Mongo the warehouse or silver store.
