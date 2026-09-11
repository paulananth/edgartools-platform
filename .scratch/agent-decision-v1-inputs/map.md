# v1 Agent-Grade Inputs

Label: `wayfinder:map`

## Destination

An implementation-ready, decision-complete plan for making v1 Agent-Grade
Input Facts live in Snowflake: As-Of Decision Features on gold
`FINANCIAL_FACTORS` (the 19 locked keys, including `ebitda` /
`eps_diluted` / `ebitda_margin`), and current `IS_INSIDER` and
`EMPLOYED_BY` identity usable on the active graph for the Decision Subject
Universe.

## Notes

- Repo: `edgartools-platform`. Planning only unless
  [Lock planning versus execution for v1 inputs](issues/06-lock-planning-vs-execution-for-v1-inputs.md)
  carries implementation into this map. Produce decisions, not PRs, until
  the way is clear.
- AWS-only. Do not introduce another cloud, registry, workflow engine,
  storage target, or secret-management path.
- Skills every session should consult: `/grilling` (one question at a
  time), `/domain-modeling`, ADR 0001, ADR 0006, `CONTEXT.md` Agent
  decision support.
- Destination locked 2026-09-11 as recommended **A** (v1 agent-grade
  inputs only) after searching existing maps: none owns this destination.
  Operator asked to create the map after that search.
- Sibling: [Agent Decision Contract](../agent-decision-contract/map.md)
  owns watermark, READY writer, Feature Screen, issuer bundle, and Agent
  View. This map owns the gold/graph **facts** those objects will read.
  Do not implement contract SQL here. Q13 on that map (which missing data
  first) is held and superseded by this map.
- Predecessor facts are inputs, not questions to reopen:
  - Contract tickets 05 / 11 / 12 / 13: v1 sections, 19 keys, factors bind
    on this branch, live inventory of gaps.
  - [MDM relationship-derivation incremental filters](../mdm-relationship-incremental-filters/map.md)
    Ticket 03: auditor/parent parsers exist; discovery/fetch never built.
  - [Release-readiness](../release-readiness/map.md) tickets 22 / 23:
    subsidiary and auditor parsers resolved; production discovery deferred.
  - [MDM relationship versioning gap](../mdm-relationship-versioning-gap/map.md)
    Ticket 06: 13F security→issuer fuzzy links (live); not a v1 section.
  - [Bring Missing Fundamentals Artifacts Into daily_incremental](../fundamentals-daily-integration/map.md):
    daily Stage 1B freshness; still open.
  - [Artifact usefulness timelines](../artifact-usefulness-timelines/map.md):
    lookback windows locked; execution out of that map.
  - [Incremental Change Propagation](../change-propagation/map.md): do not
    chart a second ingest map.
- Scope locked with destination A:
  - v1 Agent-Grade Input Facts = features + `IS_INSIDER` + `EMPLOYED_BY`.
  - Holders, auditor, and parent stay `unavailable` (contract ticket 05).
  - Manager ADV / `MANAGES_FUND` / `IS_ENTITY_OF` out.
  - Bookkeeping Postgres and bronze S3 are not agent-readable (ADR 0001).
  - Do not widen v1 neighborhood sections.
- Ask the operator one grilling question at a time. Standing preference:
  recommended answers unless the operator overrides.
- Live Snowflake: `snow sql --connection edgartools-prod` against
  `EDGARTOOLS_PROD`. Dev Snowflake is decommissioned.

## Decisions so far

- [Confirm live FINANCIAL_FACTORS bind versus locked 19 keys](issues/01-confirm-live-financial-factors-bind.md) — Prod factors still missing `ebitda`/`eps_diluted`/`ebitda_margin` columns; derived already has them. `--full-refresh` is enough for the column bind. Only 21 CIKs have any factor row. [research](research/01-live-financial-factors-bind.md)
- [Inventory live IS_INSIDER input completeness](issues/02-inventory-is-insider-input-completeness.md) — 902 current graph edges with accession on 87 MDM-active issuers; gold holdings lack person identity (4,577 company keys, accession only). [research](research/02-is-insider-input-completeness.md)
- [Inventory live EMPLOYED_BY input completeness](issues/03-inventory-employed-by-input-completeness.md) — 4,313 graph edges on 1,351 MDM-active issuers; live sources are `item_502_filing`/`proxy_filing`, not ticket 05's `item_5_02`/`proxy_def14a`. Pay gold is sidecar. [research](research/03-employed-by-input-completeness.md)
- [Explain why FINANCIAL_FACTORS has only 21 CIKs](issues/07-why-financial-factors-only-21-ciks.md) — Apple smoke + Ticket 42 20-CIK sample. Same 21 CIKs from landing facts through gold factors. Full-universe entity-facts never published (Stage 1B publish OOM). `--full-refresh` cannot add CIKs. [research](research/07-why-financial-factors-21-ciks.md)
- [Confirm fundamentals wiring and lookback years](issues/09-fundamentals-wiring-and-lookback-years.md) — load_history Stage 1B is live; daily_incremental is not (company-identity only). Fetch default 2 years, not 5. entity-facts unbounded (FY 2009–2026). [research](research/09-fundamentals-wiring-and-lookback.md)

## Not yet specified

- Coverage thresholds for insiders/employment (what share of the Decision
  Subject Universe must have an edge before the input plan calls those
  sections complete). Factor CIK coverage is now ticket 08.
- Whether a graph rebuild is required after any identity work this map
  later specifies.
- Daily versus one-shot factor freshness after the first prod refresh.
- Whether gold `OWNERSHIP_HOLDINGS` should gain person columns, or stay
  accession-only because `IS_INSIDER` is graph-keyed (depends on
  [Lock what usable identity means for v1 insiders and employment](issues/04-lock-v1-insider-employment-usable-identity.md)).

## Out of scope

- Snowflake Decision Contract objects, READY writer, Agent View versus
  Explore ([Agent Decision Contract](../agent-decision-contract/map.md)).
- Auditor / parent discovery and fetch (incremental-filters Ticket 03;
  release-readiness tickets 22 / 23). Those keys stay `unavailable`.
- 13F issuer CIK bind and `holders_of_subject` /
  `subject_as_manager_portfolio` (locked `unavailable`; versioning-gap
  Ticket 06 already did security→issuer fuzzy links).
- Manager ADV / `MANAGES_FUND` / `IS_ENTITY_OF` agent-grade sections.
- Change-propagation ingest redesign, PostgreSQL ledger, edgartools
  gateway cutover.
- Bookkeeping Postgres and bronze S3 as agent-readable data.
- Empty Explore-only gold (consensus, guidance, transcripts, calendar,
  accounting flags).
- Trading execution, market prices, product OAuth, MongoDB/JSON as SoE.
