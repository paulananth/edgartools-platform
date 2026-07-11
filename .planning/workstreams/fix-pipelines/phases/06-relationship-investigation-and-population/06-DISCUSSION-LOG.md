# Phase 6: Relationship Investigation And Population - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-08
**Phase:** 6-relationship-investigation-and-population
**Areas discussed:** Real-data prerequisite, INSTITUTIONAL_HOLDS batching, Adviser-link closure
bar, Neo4j relationship counting (advisor mode — all 4 areas researched via parallel
`gsd-advisor-researcher` agents before user selection; calibration tier `minimal_decisive`)

---

## Real-data prerequisite

Grounding fact surfaced before discussion: `load_history` (canonical 10+-company loader) has
**zero executions ever** in dev (`690839588395`), confirmed via
`aws stepfunctions list-executions`. Only single-CIK smoke tests (CIK 320193/Apple, via
`targeted_resync`) have succeeded; a plain `bootstrap` run failed once on 2026-07-06.

| Option | Description | Selected |
|--------|-------------|----------|
| Investigate with existing data | Stay code/design-only; root-cause against dev's existing ~15,285-node/1,117-edge MDM dataset; document a bounded `load_history` proving-run as a follow-on operator action, mirroring Phase 5's EDGARTOOLS_PRODB precedent. **Advisor research recommendation.** | |
| Bounded load first | Phase 6's first plan triggers a ~100-300 company `load_history` run before investigation. | ✓ |

**User's choice:** Bounded load first, scaled to ~100-200 companies (follow-up question)
— **Recommended** option in that follow-up, matching CLAUDE.md's documented example scale.

**Notes:** This overrides the advisor-research recommendation, which had found that Phase 5
already established a structurally identical precedent (treat prodb replication as a follow-on,
not a plan) and that 3 of 5 target relationship types don't strictly need more data (EDGE-05/06
are pure resolver logic; EDGE-10 is gated on Codex-coordination regardless). User chose to load
real data now rather than defer. Claude additionally proposed investigating the unexplained
2026-07-06 `bootstrap` failure first (5-whys, per CLAUDE.md's debugging discipline) before
running `load_history` — user did not push back, so this stands as agreed sequencing, folded
into CONTEXT.md D-01.

---

## INSTITUTIONAL_HOLDS batching

| Option | Description | Selected |
|--------|-------------|----------|
| Bounded/sample-safe now | Use the existing `remaining`/limit param (already wired in `_derive_institutional_holds`); defer TODOS.md's CIK-range batching until a real full-universe run is planned. **Advisor research recommendation.** | |
| Batch now | Implement the CIK-range chunked-read strategy today (per TODOS.md's existing design) so a full-universe run is safe from day one. | ✓ |

**User's choice:** Batch now.

**Notes:** Also overrides the advisor-research recommendation. Consistent with the
Real-data-prerequisite pick — since D-02 puts a real `load_history` run in this phase, the
documented OOM risk becomes live rather than hypothetical, so building the fix now (rather than
deferring) is coherent with the other override, not an isolated risk-tolerance swing.

---

## Adviser-link closure bar

| Option | Description | Selected |
|--------|-------------|----------|
| SQL zero-overlap check | Query `MdmCompany.cik`/`MdmPerson.owner_cik` overlap against `MdmAdviser.cik` in the loaded universe — same join logic the resolver already runs. **Advisor research recommendation.** | ✓ |
| Manual EDGAR audit | Spot-check specific adviser CIKs against SEC EDGAR full-text search for company-type filings under other form families. | |

**User's choice:** SQL zero-overlap check.

**Notes:** Followed the advisor research's recommendation without modification.

---

## Neo4j relationship counting

*(User-added area — not one of Claude's original 3 proposed gray areas; added via "Other" on
the initial area-selection question.)*

| Option | Description | Selected |
|--------|-------------|----------|
| Extend verify-graph | Add each newly-populated type to `POPULATED_RELATIONSHIP_TYPES` + a named parity check, mirroring 05-03 exactly — keeps `verify-graph` the single gate. **Advisor research recommendation.** | ✓ |
| Ad-hoc query | One-off manual graph count during investigation, not wired into the permanent `verify-graph` gate. | |

**User's choice:** Extend verify-graph.

**Notes:** Followed the advisor research's recommendation without modification. Research
flagged a sequencing risk to carry into planning: derive → `mdm sync-graph` → `verify-graph`
must run in that order per newly-populated type, or the new named check will (correctly) fail
closed before sync has run — expected behavior, not a bug to chase.

---

## Claude's Discretion

- Exact CIK-range batch size for INSTITUTIONAL_HOLDS batching — tune based on real
  `sec_thirteenf_holding` row density once the bounded load lands data.
- Whether the bounded `load_history` run uses `--tracking-status-filter active` or a specific
  `--cik-list`/limit flag.
- Ordering of investigation within Phase 6's plan waves.

## Deferred Ideas

None — discussion stayed within Phase 6 scope.
