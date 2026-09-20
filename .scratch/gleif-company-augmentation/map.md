# GLEIF MDM enrichment evidence

Label: `wayfinder:map`

## Destination

An implementation-ready `spec.md` for the first Company Legal-Entity Enrichment
consumer, built on the canonical shared-enrichment foundation owned by the
parent program. This map also supplies the evidence and routing decisions the
foundation and later Company, Fund, Security, Branch, and other MDM consumers
need without mixing their semantics. The Company spec must define its source
authority, accepted-link evidence, temporal semantics, cadence, conflicts,
replay, observability, and release gates. It must not implement or deploy the
enrichment.

## Notes

- **Flagged 2026-09-19, not yet propagated below**: legacy MDM is being
  decommissioned; Clean MDM (`mdm_v2`) is the sole MDM target going forward
  — locked on the
  [Shared Enrichment Foundation map](../mdm-enrichment-shared-foundation/map.md),
  which [ticket 17](issues/17-write-and-verify-gleif-mdm-spec.md) is blocked
  on. When `spec.md` is finally written, its identity/relationship contract
  targets Clean MDM's `mdm_v2` schema and Merge Stage
  (`edgar_warehouse/mdm/clean/`), not legacy `edgar_warehouse/mdm/`. The
  decisions already resolved below (source authority, cadence, field
  selection, first delivery slice) are evidence-level and source-side —
  they don't name a target MDM schema — so they likely survive unchanged,
  but this hasn't been re-checked ticket-by-ticket.

- Parent program: [MDM Enrichment Program](../mdm-enrichment-program/map.md).
  This map owns the evidence and first Company consumer; later consumers and
  production delivery remain visible and owned by the parent plan.
- Research and decision only. Production MDM, Snowflake, S3, AWS workflows,
  schedules, and schemas remain read-only.
- Every session uses `/grilling`, `/domain-modeling`, and `/grill-with-docs`.
- `spec.md` is created only after its source-authority, cadence, daily-work,
  conflict, and initial-field decisions are explicit; it does not guess them.
- The earlier 200-row API pass is diagnostic input, not acceptance evidence.
  It returned 25 review-worthy candidates and 8 strongest provisional
  candidates, but it did not adjudicate identity and crossed two Golden Copy
  publications during the run.
- `company-only` reuses the repository's accepted scheduled identity boundary:
  current active tracked CIKs where SEC `entity_type = 'operating'` **or** the
  CIK is present in the captured official SEC ticker snapshot. Do not treat all
  rows in `MDM_COMPANY_ENTITY` as operating companies. Exclude SEC
  `entity_type = 'investment'` unless ticker membership independently makes the
  CIK eligible; exclude the remaining broad `other` population unless ticker
  membership makes it eligible.
- Freeze exactly 1,000 distinct eligible CIKs before examining GLEIF results.
  Preserve CIK and MDM `entity_id` as cohort keys, the selection seed and query
  version, input snapshot identities, canonical row ordering, and SHA-256
  digests.
- Use GLEIF Golden Copy bulk data, not 1,000 sequential queries against the
  moving API. Exhaust the fixed local candidate corpus so a first-page limit
  cannot be mistaken for uniqueness.
- CIK remains the authoritative SEC identifier. LEI is additive evidence. Name
  similarity, including exact normalized name, is never sufficient by itself
  to accept or merge an identity.
- Reuse the field semantics, evidence tiers, and parent/exception distinctions
  in `docs/research/gleif-mdm-comparison-2026-09-11.md`; change them only when
  the new evidence demonstrates a defect.
- A recommendation is decision-ready only when every positive identity
  candidate is adjudicated against retained evidence and an independent replay
  produces the same cohort, candidates, classifications, and aggregates.

## Decisions so far

- CIK authority, additive LEI semantics, and no name-only auto-linking are
  settled by the existing research.
- The 1,000-row rerun uses the existing company-eligible identity boundary,
  not the full 68,949-row exported MDM company table.
- The formal rerun uses one frozen GLEIF bulk publication because the 200-row
  live-API pass crossed publications.
- [Freeze the 1,000-company cohort and GLEIF snapshot](issues/01-freeze-company-cohort-and-gleif-snapshot.md) froze 1,000 of 8,341 eligible CIKs plus the same-publication 2026-09-11 16:00 UTC Level 1/RR/exception archives; offline replay and all digests/ZIP CRCs pass.
- [Run and adjudicate the exhaustive identity comparison](issues/02-run-exhaustive-identity-comparison.md) found 308 unambiguous accepted company-to-LEI links, 103 companies whose candidates were all rejected, 87 unresolved companies, and 502 with no candidate. Tier B accepted only 90.0% under review, so heuristic matching is candidate evidence rather than unattended link authority.
- [Lock the Company Legal-Entity Enrichment authority boundary](issues/06-lock-company-enrichment-source-authority-boundary.md) — SEC remains authoritative for filings and reported financials; GLEIF legal identity, lifecycle, registration, consolidation, and exception evidence is additive and source-grained in Company MDM.
- [Set the GLEIF source refresh frequency](issues/07-set-gleif-source-refresh-frequency.md) — capture and apply one 24-hour GLEIF delta daily, with a complete Golden Copy reconciliation monthly; do not poll every eight-hour publication.
- [Set the GLEIF MDM processing frequency](issues/08-set-gleif-mdm-processing-frequency.md) — process changed accepted links and new/materially changed entities daily, unresolved or unmatched candidates weekly, and the complete in-scope state monthly.
- [Lock the shared GLEIF Evidence Capture boundary](issues/09-lock-shared-gleif-capture-boundary.md) — capture all Level 1, relationship, and exception source evidence once; route it to explicit MDM domains instead of filtering acquisition to companies or forcing every LEI into Company MDM.
- [Decide GLEIF relationship-type routing](issues/10-decide-gleif-relationship-type-routing.md) — preserve all six directional types; direct and ultimate consolidation require distinct Company relationships, while Branch and Fund types wait for their own domain consumers. Existing `HAS_PARENT_COMPANY` and `MANAGES_FUND` are not semantic substitutes.
- [Decide GLEIF identifier-mapping routing](issues/11-decide-gleif-identifier-mapping-routing.md) — only ISIN is daily and it belongs to Security-to-issuer enrichment; OpenCorporates is bi-weekly, BIC/MIC/QCC/GEM are monthly, and S&P CIQ bulk ingestion is deferred pending access and license approval.
- [Decide the daily Company source portfolio](issues/12-decide-daily-company-source-portfolio.md) — daily Company MDM work is the existing SEC new-filing/impacted-CIK path, one official SEC ticker snapshot, and one 24-hour GLEIF delta. No additional full-universe Company feed is justified; daily ISIN mapping belongs to Security.
- [Measure accounting-parent and exception evidence](issues/04-measure-accounting-parent-evidence.md) — 30/308 accepted companies have direct and/or ultimate consolidation evidence, 262 have typed reporting exceptions, and 23 have neither. Only three typed records currently have accepted local identities at both endpoints.
- [Measure GLEIF attribute lift and conflicts](issues/03-measure-attribute-lift-and-conflicts.md) — all 308 accepted links add legal form and LEI registration evidence; 286 add authority-local IDs, 253 creation dates, 62 legal-event histories, 41 new names, and three successor LEIs. Five comparable jurisdictions disagree with SEC and require review.
- [Decide accepted-link publication policy](issues/13-decide-accepted-link-publication-policy.md) — only approved active links or verified deterministic crosswalks with semantic and uniqueness proof may publish; heuristic tiers remain review-only.
- [Decide GLEIF delta-gap recovery and completeness proof](issues/14-decide-delta-gap-recovery.md) — checkpoint each family independently and reconcile a complete Golden Copy whenever official delta continuity cannot be proven.
- [Decide GLEIF attribute survivorship and conflict handling](issues/15-decide-attribute-survivorship-and-conflicts.md) — retain every field at source grain, project only the accepted first-slice fields, preserve SEC authority, and business-close only from explicit change or full reconciliation.
- [Select the first GLEIF MDM delivery slice](issues/16-select-first-delivery-slice.md) — proceed with a bounded Company tracer bullet using revalidated seed links, OpenCorporates corroboration, selected legal-entity fields, typed consolidation, exceptions, and hard release gates.

## Not yet specified

None. The Company decision frontier is resolved; only specification writing and
verification remain. Later-domain questions are owned by the parent program.

- [Write and verify the GLEIF MDM enrichment specification](issues/17-write-and-verify-gleif-mdm-spec.md) — [`spec.md`](spec.md) written 2026-09-19 against Clean MDM's `mdm_v2`, as the consumer contract that Clean MDM's `company-completion.md` gate implements. Documentation review still to run.

## Decision frontier

None. Destination reached; the spec's own Dependencies table lists what gates implementation.

## Out of scope

- Later Fund, Security, Branch, Adviser/Audit-Firm, government,
  sole-proprietor, and Market/Venue consumer specs, plus the International
  Organization common-entity route in the shared-foundation spec; these are
  owned by the [parent program](../mdm-enrichment-program/map.md).
- Production ingestion, schema migration, backfill execution, deployment,
  scheduling, operations, and physical retention; these are parent-program
  workstreams after this specification.

## Constraints

- CIK remains authoritative for SEC identity; LEI is additive evidence.
- Never merge automatically from exact or fuzzy name similarity.
- Never coerce unsupported GLEIF evidence into Company or a generic entity.
- Never interpret accounting consolidation as legal ownership, beneficial
  ownership, control, or a generic parent relationship.
- Do not change the accepted company-eligible identity universe contract.
