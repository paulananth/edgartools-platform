# 21 — Insider-scoped EMPLOYED_BY completeness (Release Owner scope decision, 2026-07-19)

Type: task
Status: open
Blocked by: none
Blocks: 20 (relaunch of the strict bulk-load execution)

## Release Owner decisions (2026-07-19, given verbatim intent: "form 4/5 should
## be tied to 5.02 identification; anyone who has an insider must be identified;
## everyone else is not needed; 13F and other forms are not critical")

1. **13F stays in the freeze but is non-blocking**: keep loading all 101,444
   13F candidates; do not spend launch-gating effort auditing 13F paths;
   fix-forward on 13F issues. (The 13F NULL-period bug is already fixed —
   PR #192.)
2. **EMPLOYED_BY identification is scoped to insiders**: the required
   person-identification universe = people who appear in Form 3/4/5 insider
   filings (already parsed by edgar_warehouse/parsers/ownership.py; MDM
   already derives IS_INSIDER). Item 5.02/proxy events need resolution only
   when the person is an insider; unresolved events for non-insiders are
   not-needed rather than accepted-gap.

## What to build

A revised completeness evaluation for the Ticket 20 gate: instead of "every
Item 5.02 candidate reaches terminal resolution," prove "every insider
(Form 3/4/5 filer) for every in-scope CIK is identified in MDM," with Item
5.02/proxy loaded best-effort under the existing bounded unresolved_accepted
gate. Requires cross-referencing ownership filings against the employment
identification set at evidence time, and revising
docs/release-readiness/required-relationship-bulk-load-completion-gate.md
"Done when" accordingly BEFORE the next strict execution fires.

Note: this reframes (and likely shrinks) the unresolved-Item-5.02 problem —
an ambiguous 8-K only matters if the undisclosed person is an insider, and
insiders are independently identifiable from their own Form 3/4/5 filings.

## Current deployed state (ready, holding)

- Task def `edgartools-prod-medium:29` = warehouse image
  `@sha256:163cfc3b…` (`sha-c2bcd97996cf`): parser v5 + bounded
  unresolved_accepted gate (0.095) + 13F cover-period fix. Smoke-tested.
  SM `edgartools-prod-bronze-seed-silver-gold` references `:29`.
- Freeze `ticket20-agent-20260718T225510Z` (fingerprint `abecbde8…`)
  unchanged, preflight READY_FOR_STRICT_LOAD, execution input on S3.
- Consumed execution names (P3, never reuse): ticket20-strict-agent-20260718T225510Z,
  ticket20-strict-gatev2-20260719T135202Z, plus all earlier ticket20-strict-*.
- Launch requires: this ticket's doctrine revision, then a brand-new
  execution name, then the Release Owner's explicit go.

**Status:** ready-for-agent

- [ ] Spec the insider-scoped completeness check (cross-reference design:
      ownership filings ↔ MDM person identification ↔ Item 5.02 events)
- [ ] Revise the completion-gate doctrine's "Done when" + PASS claim
- [ ] Implement the evidence-time insider-coverage check
- [ ] Relaunch the strict execution (new name, explicit user go)

---

## SPEC (v1, 2026-07-19)

### Definitions

- **Insider** (for this gate): a natural person appearing as a reporting owner
  in a Form 3/4/5 filing for an in-scope CIK — i.e. a row in silver
  `sec_ownership_reporting_owner` (fields: `owner_cik`, `owner_name`,
  `is_director`, `is_officer`, `is_ten_percent_owner`, `is_other`), the same
  source MDM's `_derive_is_insider` already consumes
  (`edgar_warehouse/mdm/pipeline.py`).
- **Identified**: the insider resolves to exactly one MDM person entity
  (by owner_cik primary, owner_name fallback per existing MDM resolution),
  and that person carries an `IS_INSIDER` relationship version to the issuer.

### Completeness invariant (replaces "every Item 5.02 candidate terminal" as
### the EMPLOYED_BY completeness bar)

> For every in-scope CIK, every distinct insider observed in
> `sec_ownership_reporting_owner` within the release windows is Identified
> in MDM at the watermark. Zero unresolved insiders.

Item 5.02 / proxy candidates still load under the existing bounded
`unresolved_accepted` gate (threshold 0.095) — unchanged mechanics — but an
unresolved Item 5.02 event no longer threatens completeness *unless* it can
be shown to conceal an unidentified insider, which the invariant above rules
out independently: insiders self-identify through their own Form 3/4/5
filings regardless of 8-K prose ambiguity.

### Evidence-time check (new, in `build_required_relationship_bulk_load_evidence`
### callers / `reconcile-relationship-release`)

New evidence block `insider_coverage`:
```json
{
  "insider_total": N,          // distinct (owner_cik|owner_name, issuer_cik)
  "insider_identified": N,     // resolved to MDM person + IS_INSIDER version
  "insider_unresolved": 0,     // MUST be zero for PASS
  "source": "sec_ownership_reporting_owner",
  "windows_note": "ownership rows observed in silver at watermark"
}
```
Fail closed (`InventoryError`) if `insider_unresolved > 0`, enumerating the
unresolved (owner, issuer) pairs. 13F/INSTITUTIONAL_HOLDS checks unchanged
but non-blocking per the Release Owner decision — a 13F-side failure is
reported in evidence, does not veto the launch decision (doctrine edit).

### Scope boundary (explicit)

- Form 3/4/5 ARTIFACT COMPLETENESS is NOT this gate: we do not promise every
  ownership filing is loaded — only that insiders observable in the silver
  ownership rows present at the watermark are identified. (The forbidden
  overclaim "Form 3/4/5 complete as Ticket 20" stays forbidden.)
- Non-insider executives named only in proxies/8-Ks: best-effort via the
  existing EMPLOYED_BY path; not a completeness requirement.

### Doctrine edits required (required-relationship-bulk-load-completion-gate.md)

1. "Done when": replace the EMPLOYED_BY completeness bullet with the insider
   invariant; mark 13F bullets non-blocking-but-reported.
2. PASS claim: add an insider-coverage line ("all N observed insiders
   identified"); keep the accepted-unresolved Item 5.02 clause.
3. Ownership section: note Release Owner decision + date.

### Implementation slices (tracer bullets)

1. `insider_inventory(db, ciks) -> [(owner_cik, owner_name, issuer_cik, flags)]`
   in `relationship_bulk_load.py` + unit tests (silver fixture).
2. MDM cross-check: resolve each inventory row against MDM persons +
   IS_INSIDER versions; return identified/unresolved partition (reuse
   `_derive_is_insider`'s resolution, factored to a query helper).
3. Wire into `reconcile-relationship-release` → `insider_coverage` evidence
   block, fail-closed on unresolved > 0.
4. Doctrine edits (PASS phrase + Done-when) — same PR as 3, so the claim
   and the check land atomically.
5. Relaunch (new execution name, explicit user go) — unchanged mechanics.

### Open questions for the Release Owner (non-blocking for slices 1-2)

- Window for "observed insiders": all silver ownership rows at watermark
  (recommended — simplest, matches "anyone who has an insider must be
  identified"), or Form 3/4/5 filed within [W-2y, W] only?
- Should `insider_coverage` failures list ALL unresolved pairs in evidence,
  or cap the enumeration (recommend: all; expected zero).
