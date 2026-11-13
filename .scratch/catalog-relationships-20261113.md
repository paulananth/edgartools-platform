# Correct catalog relationship projection

Status: resolved. Implementation and local verification complete; PR #1734 tracks CI and review.

- [x] Classify the original 19 readback differences: 15 description digest mismatches, two inventory mismatches, one task-list mismatch and one table-lineage mismatch (2026-11-13 07:37 ET). The live service digest differs from the checked Rules digest. The extra table and step Pipeline both describe the retired Company name-count step. These are stale catalog projection differences, not an unknown-kind failure.
- [x] Reproduce the independent relationship defect: configuration-only `catalog.plan()` emits 52 domain edges and 23 glossary edges without relationship-fact evidence; an assertion requiring no inferred fact edges failed (2026-11-13 07:37 ET).
- [x] Inspect RDM ownership: pinned `mdm-relationship-types` version 4 already holds 17 relationship types and six capacities, including labels, definitions and endpoint constraints. No vocabulary defect was demonstrated; no RDM version or live database change is justified (2026-11-13 07:37 ET).
- [x] Remove unsupported relationship inference while retaining RDM vocabulary and genuine data lineage: CLI plan smoke preserves 17 type assets, 30 table edges and 115 pipeline edges, with zero domain/glossary fact edges (2026-11-13 07:46 ET).
- [x] Preserve unrelated catalog curation; remove broad relationship cleanup, leaving existing-edge repair to separately reviewed authorization (2026-11-13 07:46 ET).
- [x] Document RDM ownership, generated Mapping Documents and evidence-qualified relationship projection in the owning skills (2026-11-13 07:46 ET).
- [x] Run affected tests and CLI smoke proof; published in PR #1734. Final focused run: 78 passed, 39 deselected by testmon in 194.82 seconds; initial affected run: 117 passed. CLI plan smoke and 107 genericity/path checks passed (2026-11-13 07:48 ET).
- [x] Learning → skill: configuration-only vocabulary publication proceeds without live fact evidence; unknown evidence omits affected fact edges, not unrelated metadata. Updated data-modeling, data-catalog, data-onboarding and OpenMetadata guidance; genericity and guide-path checks: 107 passed (2026-11-13 07:46 ET).

The current main snapshot adds four task-level readback differences to the earlier 19 (23 total): source extract wiring changed after that snapshot. Full private readback evidence is retained outside Git. Readback scope does not cover all business relationship graphs; the 19 differences never diagnosed relationship truth.

No live catalog publication, relationship cleanup, MDM/Postgres access or RDM update is part of this code change.
