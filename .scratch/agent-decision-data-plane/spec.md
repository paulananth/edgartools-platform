# Spec: Agent Decision Data Plane (evolve existing platform)

**Status:** ready-for-agent  
**Feature slug:** `agent-decision-data-plane`  
**ADRs:** 0001 (Agent Decision Surface), 0002 (Silver SoE / edgartools-exclusive / optional bronze)  
**Doctrine:** `docs/doctrine-data-plane.md`

---

## Problem Statement

The platform already loads SEC data, builds silver/gold, runs MDM/graph, and serves Snowflake analytics. Operators and future trading agents still face three problems:

1. **Unclear system of engagement** — bronze, silver, edgartools, and raw HTTP all look like sources of truth; re-runs feel like “loading SEC every time,” and doctrine documents contradict the old always-bronze story.
2. **No agent-grade contract** — gold tables and graph edges exist, but there is no versioned, fail-closed Decision Graph Bundle / Subject Feature Screen an automated trading agent can pin, with coverage flags and a composite Decision Watermark.
3. **Incomplete Snowflake surface for agents** — agents must not read silver; several evidence tables needed for the Trading-Relevant Neighborhood never leave silver into Snowflake exports.

We must not rebuild the warehouse from scratch. We must **steer the working product** onto ADR 0001 + 0002.

---

## Solution

Evolve the existing warehouse along two **narrow** change fronts (not a greenfield component library):

### Front A — Ingest doctrine on existing paths

Keep CLI commands, orchestrator, silver store, parsers, Step Functions, and gold/MDM pipelines. Change **behavior at the existing capture boundary**:

- Treat **silver** as the runtime system of engagement (skip keys: accession + form-family + parser_version; catalogs by checkpoint; companyfacts by CIK + facts_parser_version).
- Route **SEC network I/O through edgartools** as the exclusive gateway (hard cutover target, phased behind the existing call sites — `sec_client`, filing artifact fetch, seed/submissions/daily/companyfacts — not a parallel product).
- **Default: no bronze write** for edgartools-sourced SEC objects; bronze only on explicit operator persist **or** for sources edgartools cannot supply (e.g. IAPD ADV bulk).
- Preserve and extend existing idempotency tests (e.g. `network_fetches = 0` on cache/skip) so re-runs do not re-hit SEC when silver already satisfies the skip key.

### Front B — Agent contract on existing Snowflake path

Keep native S3 pull, dbt gold, MDM export, and graph sync. Add:

- Expanded **export** of agent-needed silver evidence (where missing today) into the existing Snowflake export/manifest machinery.
- A **thin Decision Contract** layer in Snowflake (views/procedures over SOURCE/GOLD/MDM/graph tables already there) implementing Subject Bundle Read, Subject Feature Screen, coverage flags, Decision Contract Version, and Decision Watermark rules from ADR 0001.
- Human Audit View **modes** on the existing Streamlit-in-Snowflake app: Agent View (contract only) vs Explore (labeled free gold).

No new agent runtime in AWS. No trading execution. No requirement that agents query DuckDB.

---

## Seams (confirmed framing: evolve, do not greenfield)

**Not** “componentize a new platform.” Prefer **one primary behavioral seam** already in the product, plus **one publish/read seam** for the agent:

| Seam | What it is today | What we change | How we test |
| --- | --- | --- | --- |
| **1. Capture / skip boundary (primary)** | Filing artifact fetch, submissions/daily/reference loaders, fundamentals entity-facts, orchestrator `force` | Silver-once skip before network; edgartools-backed fetch on miss; optional bronze persist; metrics `network_fetches` vs `silver_skips` | Extend `tests/unit/test_loader_idempotency.py`, loader/orchestrator unit tests; architecture tests for “no parallel download path” after cutover |
| **2. Snowflake decision read (secondary)** | Gold export tables, MDM/graph Snowflake tables, Streamlit queries | Contract views + watermark/coverage rules; export list expansion; SiS Agent View | Unit tests for contract SQL builders / watermark validation if in-repo; dbt tests where applicable; architecture tests that agent contract objects only reference allowed schemas |

**Out of seam design:** inventing a third parallel warehouse, replacing MDM, or rewriting Step Functions topology unless a ticket proves a single adapter registration is required.

---

## User Stories

1. As a **platform operator**, I want re-runs of bootstrap over an already-loaded CIK to skip SEC network for accessions already parsed at the current parser_version, so that jobs finish quickly and respect rate limits.
2. As a **platform operator**, I want discovery (daily index / submissions) to only fetch what is needed to find **new** filings, so that catalogs stay current without full history re-download.
3. As a **platform operator**, I want `--force` (or equivalent) to re-fetch via edgartools and overwrite silver for a scope, so that I can repair bad parses deliberately.
4. As a **platform operator**, I want bronze raw archive **off by default**, so that we do not store a second copy of SEC data without reason.
5. As a **platform operator**, I want `--persist-bronze` (or env/job) to archive raw payloads when I explicitly ask, so that audit/replay of bytes is available on demand.
6. As a **platform operator**, I want non-edgartools sources (e.g. IAPD ADV bulk) to still land in immutable storage (bronze-equivalent), so that those pipelines remain reproducible.
7. As a **developer**, I want all SEC network access to go through edgartools-backed adapters, so that we do not maintain two HTTP stacks for the same objects.
8. As a **developer**, I want a phased cutover from `sec_client` downloads without stopping the live product, so that production keeps working during migration.
9. As a **developer**, I want parser_version (and facts_parser_version) to control skip vs re-fetch, so that library or parser upgrades can intentionally refresh silver.
10. As a **developer**, I want metrics for network_fetches vs silver_skips on each command, so that “we loaded SEC again” is observable and false.
11. As a **trading agent**, I want a versioned Snowflake Decision Contract, so that I can pin Decision Contract Version and trust field semantics.
12. As a **trading agent**, I want a Subject Bundle Read by CIK at a Decision Watermark, so that I get a Trading-Relevant Neighborhood plus features in one contract.
13. As a **trading agent**, I want a Subject Feature Screen over the Decision Subject Universe, so that I can rank/filter many issuers without loading full neighborhoods.
14. As a **trading agent**, I want Bundle Coverage Flags (present / empty / unavailable / not_applicable), so that I can abstain instead of treating missing data as zero.
15. As a **trading agent**, I want fail-closed Agent-Grade Reads when watermark components disagree, so that I do not trade on mismatched graph vs features.
16. As a **trading agent**, I want pure-SEC Decision Features only, so that market prices are joined outside this platform.
17. As a **trading agent**, I want issuer bundles without requiring ADV, so that equity subjects are not blocked on IAPD lag.
18. As a **trading agent**, I want manager bundles to require bulk-IAPD-backed ADV/fund data when that subject type is in scope, so that private-fund graph is trustworthy.
19. As a **trading agent**, I want 13F exposed as holders_of_subject and subject_as_manager_portfolio separately, so that I do not confuse who owns the issuer with the issuer’s own 13F book.
20. As a **trading agent**, I want holdings “current” defined as Latest Complete Holdings Period with lag metadata, so that I do not treat 13F as same-day positions.
21. As a **trading agent**, I want Current Neighborhood edges by default and optional history only when requested, so that ended relationships are not mistaken for live.
22. As a **trading agent**, I want As-Of Decision Features as Primary Annual FY plus Latest Interim if newer, so that factors are up to date while still using multi-year history as inputs.
23. As a **trading agent**, I want graph IS_INSIDER/HOLDS plus gold ownership rows for source accessions, so that I get resolved entities and transaction detail.
24. As a **trading agent**, I want EMPLOYED_BY from proxy and Item 5.02 with distinguished source_system, and pay detail from gold executive records, so that employment is current and compensation is explicit.
25. As a **trading agent**, I want AUDITED_BY preferred from auditor evidence with PCAOB id, so that firm identity is reliable.
26. As a **trading agent**, I want optional HAS_PARENT only when subsidiary evidence inventory is complete for that claim, so that registrant_disclosed scope is honest.
27. As a **trading agent**, I want IS_ENTITY_OF when adviser and company CIKs both resolve on manager subjects, so that 13F/ADV/corporate identity can join.
28. As a **trading agent**, I want dual security provenance (CUSIP stubs vs Form 4 titles) documented in the contract, so that I do not assume a single security master.
29. As a **trading agent**, I want Decision Subject Universe = warehouse active ∩ MDM active, so that thin or untracked CIKs are out.
30. As a **platform operator**, I want warehouse seed to be the single writer for tickers and MDM seed to import from silver sync state, so that dual ticker clients stop diverging.
31. As a **platform operator**, I want agent-needed evidence tables exported to Snowflake, so that agents never depend on silver.
32. As a **platform operator**, I want verify-graph (or equivalent parity) required before Agent-Grade Reads, so that graph drift cannot silently pass.
33. As a **platform operator**, I want open high-severity reconcile findings to block Agent-Grade Reads until repaired or waived on the watermark, so that known drift is visible.
34. As a **platform operator**, I want post-run silver reconciliation proof before export that feeds agent-grade, so that shard races do not publish bad agent inputs.
35. As a **research analyst**, I want Streamlit-in-Snowflake Agent View Mode over the same contract the agent uses, so that I can audit what the agent would see.
36. As a **research analyst**, I want Explore Mode clearly labeled not-for-agent, so that free gold queries do not look like the contract.
37. As a **research analyst**, I want optional earnings release section on the bundle with coverage flags, so that 8-K GAAP snapshots are available without blocking agent-grade.
38. As a **research analyst**, I want filing text out of the agent contract in v1, so that unstructured noise is not treated as Decision Features.
39. As a **release owner**, I want Deferred Access Control (no product OAuth in v1) with a contract that can sit behind OAuth later, so that go-live is not blocked on auth productization.
40. As a **developer**, I want architecture tests that fail if a new direct SEC download path bypasses the approved gateway after cutover, so that dual stacks do not return.
41. As a **developer**, I want companyfacts re-runs to skip when silver facts exist for the current facts_parser_version, so that entity-facts does not hammer SEC by default.
42. As a **developer**, I want documentation (doctrine + ADR) to match runtime behavior after implementation, so that agents and operators are not misled by always-bronze docs.

---

## Implementation Decisions

### Product / doctrine (locked — implement, do not re-argue)

1. Follow ADR 0001 and ADR 0002 and `docs/doctrine-data-plane.md`.
2. Three SoEs: runtime silver; agent Snowflake; human Explore labeled.
3. Bronze default off for edgartools-sourced SEC; explicit persist or non-edgartools mandatory archive.
4. Agent-grade watermark: silver parse/completeness + graph generation + gold run_id + business date; bronze sha only if persist used.
5. No trading execution; pure-SEC features; OAuth deferred.

### Evolve existing modules (no greenfield product)

6. **Do not** replace the CLI surface (`edgar-warehouse …`) or Step Functions product names; change internals and add contract objects.
7. Capture boundary: extend existing filing artifact service / loaders / fundamentals paths so that **before network**, silver skip keys are checked; on miss, prefer edgartools-mediated fetch; record network vs skip metrics.
8. Submissions, daily index, and ticker seed: keep commands; change skip semantics to silver catalog/checkpoint SoE; only fetch for novelty unless force.
9. Companyfacts / entity-facts: versioned silver skip; optional persist-bronze; remove any requirement that agent-grade needs companyfacts bronze by default.
10. edgartools hard cutover: inventory every SEC download call site; migrate in ordered phases; end state forbids parallel download clients for the same object classes; keep a transition window only as tickets require.
11. Parser version: use existing PARSER_VERSION / parser constants and edgartools version pinning; bump policy documented in contract when semantics change.
12. Gold export: extend existing export table registry and gold builders for agent-needed evidence (subsidiary evidence, auditor report evidence, employment events, and other tables required by the neighborhood — minimum set for issuer v1 first).
13. MDM/graph: keep export + sync-graph + verify-graph; Agent-Grade Read requires parity proof (change ops gate for agent publish, not necessarily block all gold-refresh for non-agent analytics if product needs split — prefer single fail-closed agent publish path).
14. Decision Contract: Snowflake views/procedures over existing SOURCE/GOLD/graph schemas; Decision Contract Version field; IssuerBundle vs ManagerBundle (or equivalent section set with not_applicable).
15. Subject Feature Screen: flat relation from gold factors + universe flags + watermark columns; not full graph.
16. Streamlit-in-Snowflake: add mode toggle Agent View vs Explore; Agent View only queries contract objects.
17. Universe: implement warehouse seed as single writer; MDM seed-universe consumes silver tracking/tickers, not a second live edgartools ticker pull as source of truth.
18. ADV: heuristic parse remains non-agent-grade; bulk IAPD path remains authoritative for manager MANAGES_FUND; issuer agent-grade does not require ADV.
19. 13F: contract documents two sections; lag metadata mandatory.
20. Filing text: out of agent contract v1.
21. Reconcile: open high-severity findings block agent-grade until repair or explicit watermark waiver metadata.

### Phasing (recommended ticket order)

22. **Phase 0 — Observability + silver skip on existing paths** without full edgartools cutover: metrics and skip keys for ownership/artifacts/companyfacts where cheapest.
23. **Phase 1 — edgartools cutover by object class** (filings, then catalogs, then companyfacts).
24. **Phase 2 — bronze default-off + persist flag**; mandatory bronze only for non-edgartools sources (verify ADV bulk still archives).
25. **Phase 3 — Snowflake export expansion** for issuer neighborhood evidence.
26. **Phase 4 — Decision Contract objects + watermark validation**.
27. **Phase 5 — SiS Agent View / Explore** + universe single-writer if not done earlier.
28. Phases may be tickets with explicit Blocked by edges; do not require all phases in one PR.

### Non-goals of structure

29. No new microservice, no new cloud region, no replacement of DuckDB silver store, no Graph rewrite off Snowflake-hosted graph.

---

## Testing Decisions

### What makes a good test

- Assert **external behavior**: network not called when silver skip key satisfied; force calls network; contract returns coverage flags; watermark mismatch rejects agent-grade.
- Do **not** assert private function names, call order inside edgartools, or exact S3 key formatting unless that formatting is the published contract.
- Prefer existing test styles: unit tests with fakes/mocks for HTTP and edgartools; architecture tests for forbidden imports/call patterns.

### Modules / areas to test

1. **Capture skip / force / metrics** — extend `test_loader_idempotency` patterns; loader and artifact fetch behavior.
2. **Companyfacts skip by facts_parser_version** — fundamentals path.
3. **Export registry** — new tables appear in export manifest planning; schemas stable.
4. **Decision Contract / watermark** — pure functions or SQL fixtures: valid vs invalid watermark; empty vs unavailable; issuer ADV not_applicable.
5. **Architecture** — after cutover milestones: no disallowed direct SEC download entry points for migrated object classes; agent contract docs/objects do not reference silver paths.
6. **Streamlit** — if testable without Snowflake, mode gating pure functions; otherwise document manual SiS check.

### Prior art

- `tests/unit/test_loader_idempotency.py` — network_fetches on cache hit  
- `tests/unit/test_sec_client.py` — SEC client behavior  
- `tests/unit/test_gold_*` — gold export shapes  
- `tests/architecture/*` — deploy and boundary contracts  
- `tests/mdm/*` — relationship and graph-adjacent behavior  

---

## Out of Scope

- Building a live trading / order execution system  
- Market prices, market cap, PE inside the Decision Contract  
- Product OAuth / customer multi-tenant auth (Deferred Access Control)  
- Making filing text / NLP Decision Features  
- Full ADV heuristic deprecation for Explore/debug  
- Rewriting Step Functions topology or passive Terraform model  
- External Neo4j (graph remains Snowflake-hosted)  
- Replacing silver DuckDB with another OLTP/OLAP engine  
- Public launch / customer-facing SaaS packaging  
- Wayfinder-scale re-opening of ADR 0001/0002 product choices  
- Greenfield “component platform” rewrite unrelated to doctrine  

---

## Further Notes

### Working product constraint

This effort **extends a working system**. Tickets must prefer:

- adapter swaps and skip checks at existing boundaries  
- additive Snowflake views and export tables  
- feature flags or phased command behavior where cutover is risky  

Avoid PRs that rename the whole package or stop production loaders without a dual-run plan.

### Supersession

Stale requirements that must not drive tickets:

- Always write bronze first  
- Companyfacts bronze required for agent-grade  
- Artifact-in-bronze as the only completeness proof  
- Dual permanent SEC HTTP stacks  

### Clarity still allowed inside tickets (not open product doctrine)

- Exact flag names (`--persist-bronze` vs env)  
- Ordered list of call sites for edgartools cutover  
- Minimum export table set for issuer v1 vs manager v1  
- Whether verify-graph blocks all gold-refresh or only agent-grade publish  

### References

- `docs/adr/0001-agent-decision-surface-first.md`  
- `docs/adr/0002-silver-soe-edgartools-exclusive.md`  
- `docs/doctrine-data-plane.md`  
- `docs/product-questions-and-dashboards.md`  
- `CONTEXT.md` (Agent decision support + Data plane)  

### Next skill

`/to-tickets` — tracer-bullet issues under `.scratch/agent-decision-data-plane/issues/` with `Blocked by:` edges, Status and ready-for-agent where fully specified.
