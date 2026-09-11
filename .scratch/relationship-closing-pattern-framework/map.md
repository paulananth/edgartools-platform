# Relationship-closing pattern framework

## Destination

A locked ADR under `docs/adr/` names the real, recurring pattern families
behind every existing "close a prior `mdm_relationship_instance` version
when a new fact arrives" mechanism in this codebase, with a clear
selection criterion for each -- not a code refactor, no existing closing
implementation is touched or unified. Backed by a small declarative
registry (`RELATIONSHIP_TYPES` -> pattern name) enforced by a lightweight
test that every relationship type is classified, so the mapping can't
silently drift once a new type lands. Validated against a concrete,
near-term consumer -- N-PORT's upcoming `FUND_HOLDS` relationship type
(`nport-fund-holdings` map) -- as the test of whether the framework
actually answers "which pattern does the next type use," not just an
abstract taxonomy exercise.

## Notes

- Domain: `edgar_warehouse/mdm/pipeline.py` (`_deactivate_if_zero_shares`,
  `_deactivate_if_properties_changed`, `_derive_institutional_holds_batch`/
  `_derive_manages_fund_batch`'s expected-targets-diff, `_derive_audited_by`'s
  own inline duplicate of the property-change concept),
  `edgar_warehouse/mdm/graph.py` (`close_relationship_version`,
  `confirmed_chronologically_after`).
- This map carries light execution, not just a decision spec (explicit
  user choice, same override `mdm-relationship-versioning-gap` used) --
  the ADR + registry + test IS the deliverable.
- `/gof-refactor-reviewer` (CLAUDE.md hard rule) before any code change;
  full 3-axis `/code-review` (Standards/Spec/GoF) before any commit --
  applies to the registry+test change (Ticket 02), not the ADR itself.
- `/domain-modeling`'s own ADR criteria apply directly here: hard to
  reverse (future relationship types get built against this), surprising
  without context (four independently-written closing mechanisms already
  exist with no documented reason to pick one over another), result of a
  real trade-off (framework vs. refactor, confirmed via grilling below).
- Surfaced from `mdm-relationship-versioning-gap`'s own "Not yet
  specified" fog item #3 (root design for how per-period-boundary types
  should version/close prior evidence).
- **A real, separate bug was found while charting this map**: `_derive_audited_by`'s
  inline closing logic lacks the `confirmed_chronologically_after` guard
  that `_deactivate_if_properties_changed` already has, meaning a
  late-filed/reprocessed older AUDITED_BY row could incorrectly close an
  already-correct newer version. Explicitly ruled **out of this map's
  scope** (a correctness bug, not a design question) and filed instead as
  [`mdm-relationship-versioning-gap`'s Ticket 11](../mdm-relationship-versioning-gap/issues/11-audited-by-closing-lacks-chronological-guard.md).
  When that ticket's fix lands (most likely by routing AUDITED_BY through
  the shared `_deactivate_if_properties_changed` helper instead of its own
  inline copy), it trivially becomes Pattern 2 in this map's registry --
  no separate registry-update ticket needed here for that.
- Cross-reference: `nport-fund-holdings`'s own
  [Ticket 04](../nport-fund-holdings/issues/04-mdm-relationship-entity-design.md)
  is blocked on that map's own Tickets 01/02/03/07 (entity design), not on
  anything here. This map's Ticket 03 produces the closing-pattern answer
  for `FUND_HOLDS` as a validation exercise and cross-links it there for
  whoever resolves that ticket once unblocked -- it does not resolve
  Ticket 04 itself.

## Decisions so far

- [Name the pattern taxonomy and selection criteria](issues/01-name-pattern-taxonomy-and-selection-criteria.md) — three real families confirmed via grilling: **value-signals-disposal** (the new row's own value encodes "this ended" -- HOLDS/COMPANY_HOLDS), **property-differs-from-prior** (a point-in-time status snapshot for an already-fixed pair, differing value implies staleness -- IS_INSIDER/EMPLOYED_BY, and AUDITED_BY once its own bug is fixed), and **periodic-snapshot-diff** (the source periodically reports its full current target set; absent targets close, present-but-changed targets roll forward -- INSTITUTIONAL_HOLDS/MANAGES_FUND). Framework will be enforced via a small declarative registry (not a refactor of the closing implementations) and written up as an ADR.

- [Write ADR and declarative registry](issues/02-write-adr-and-declarative-registry.md) — [ADR 0008](../../docs/adr/0008-name-relationship-closing-patterns.md) written, matching this repo's existing terse ADR convention. `RELATIONSHIP_CLOSING_PATTERNS` registry added to `edgar_warehouse/mdm/pipeline.py`, classifying all 11 `RELATIONSHIP_TYPES` (checked the 4 not-yet-examined types rather than assuming: `IS_ENTITY_OF`/`IS_PERSON_OF` are pure existence facts (`no_versioning_needed`); `HAS_PARENT_COMPANY`'s primary evidence path carries properties with no closer yet (`property_differs_from_prior`, registered under intended design per this ticket's own instruction, not "none"); `AUDITED_BY` registered now rather than deferred, with an explicit comment pointing at Ticket 11). 4 new enforcement tests (every type classified, no stale entries, only known pattern names, a snapshot pin). `/gof-refactor-reviewer` self-consult found real evidence (3 prior growth commits) the registry addresses, confirmed purely additive/low-risk. Full repo suite green (3186 passed). 3-axis `/code-review` clean, no hard findings.

- [Validate against N-PORT FUND_HOLDS](issues/03-validate-against-nport-fund-holds.md) — confirmed `FUND_HOLDS` fits `periodic_snapshot_diff`, the same pattern `INSTITUTIONAL_HOLDS`/`MANAGES_FUND` already use (N-PORT reports a fund's full current holdings each quarter, the same reporting shape as 13F). Surfaced one real ADR gap, now fixed: the pattern description didn't distinguish its own roll-forward/close logic from the amendment-supersession dedup a caller must separately provide (13F's own `base_sql` already does this via a `NOT EXISTS`/restatement filter) — a future `FUND_HOLDS` implementer would need N-PORT's own equivalent dedup, not get one free from adopting the pattern. ADR 0008 sharpened accordingly. Confirmed the double-representation risk (same security via both `INSTITUTIONAL_HOLDS` and `FUND_HOLDS`) doesn't affect pattern selection -- correctly stays `nport-fund-holdings` Ticket 04's own problem. Cross-linked there. Docs-only, no code changed by this ticket.

## Not yet specified

(none -- the destination-shaping and frontier-mapping grilling settled the
open questions; remaining work is the two tickets below)

## Out of scope

- Unifying/refactoring the existing closing implementations behind one
  shared abstraction -- explicit user choice (documentation + a
  declarative registry, not a code unification); Rule 0 (`/gof-refactor-reviewer`)
  default applies: three to four small, independently-working,
  low-churn implementations don't yet justify the migration risk of
  collapsing them.
- `_derive_audited_by`'s missing chronological guard -- a correctness
  bug, not a design question; filed as `mdm-relationship-versioning-gap`
  Ticket 11 instead (see Notes above).
- Resolving `nport-fund-holdings`'s own Ticket 04 -- that ticket is
  blocked on that map's own entity-design tickets (01/02/03/07), not on
  anything decided here; this map only produces the input it will need.
