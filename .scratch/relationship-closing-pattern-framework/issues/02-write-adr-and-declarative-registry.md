Type: task
Status: resolved

Blocked by: 01

## Question

Write the actual deliverable Ticket 01 settled the shape of: an ADR under
`docs/adr/` naming the three closing-pattern families and their selection
criteria (see Ticket 01's Answer for the exact text/framework), plus a
small declarative registry in `edgar_warehouse/mdm/pipeline.py` (or a
nearby module) mapping each of the 11 `RELATIONSHIP_TYPES` to its pattern
name, enforced by a lightweight test that fails if a relationship type is
ever added without a corresponding registry entry.

Notes for whoever picks this up:
- `AUDITED_BY` should map to `property-differs-from-prior` in the
  registry -- but only once `mdm-relationship-versioning-gap`'s Ticket 11
  (its missing chronological guard) is fixed; until then, either wait for
  that fix or register it with an explicit caveat/TODO comment pointing at
  Ticket 11, whichever the implementer judges cleaner at the time.
- `ISSUED_BY` needs a fourth registry value (e.g. `no-versioning-needed`
  or similar) -- it calls `ensure_relationship` with no `properties` at
  all, a pure existence fact with nothing to ever conflict over or close.
  Confirm this is the right characterization rather than assuming it.
- `HAS_PARENT_COMPANY` currently derives zero relationships in prod (a
  separate, already-known bug per an older CLAUDE.md entry) -- register it
  under whichever pattern its *intended* design would use once fixed, not
  "none," so the registry doesn't need revisiting when that bug is
  eventually fixed.
- `IS_ENTITY_OF`/`IS_PERSON_OF` haven't been examined in this map's
  charting session -- check their derive functions before registering
  them, don't assume.

Per CLAUDE.md hard rule: `/gof-refactor-reviewer` before this change,
full 3-axis `/code-review` before committing.

## Answer

`docs/adr/0008-name-relationship-closing-patterns.md` written, matching
this repo's existing terse ADR convention (title + Status + one dense
decision paragraph + Consequences, no elaborate template). Checked the
four not-yet-examined relationship types before registering them (per
this ticket's own notes, not assumed):

- `IS_ENTITY_OF`/`IS_PERSON_OF` (`_derive_is_entity_of`/`_derive_is_person_of`):
  confirmed both call `ensure_relationship` with zero `properties` --
  pure existence facts, same shape as `ISSUED_BY`. Registered
  `no_versioning_needed`.
- `HAS_PARENT_COMPANY` (`_derive_has_parent_company`): its primary,
  evidence-bearing path (`sec_subsidiary_evidence`) DOES pass properties
  (`parent_scope`, `immediate_parent_known`, `jurisdiction`,
  `evidence_fingerprint`) and has no dedicated closing logic yet --
  registered `property_differs_from_prior` (the pattern its properties
  shape implies), per this ticket's own instruction to register under
  intended design rather than "none" while the zero-rows-in-prod bug is
  separately unfixed. A second, no-properties fallback branch
  (`MdmCompany.parent_company_entity_id`-derived) exists in the same
  function but isn't the primary/intended data source.
- `AUDITED_BY`: registered `property_differs_from_prior` now (not
  deferred) with an explicit comment pointing at
  `mdm-relationship-versioning-gap` Ticket 11 -- waiting for that fix
  first would leave the registry incomplete for an indefinite period, and
  the registry's own docstring is explicit this documents intended
  pattern, not implementation correctness.

Registry: `RELATIONSHIP_CLOSING_PATTERNS` (dict, `edgar_warehouse/mdm/
pipeline.py`, right after `RELATIONSHIP_TYPES`) plus
`KNOWN_RELATIONSHIP_CLOSING_PATTERNS` (frozenset of the 4 valid pattern
names). Enforcement: 4 new tests in `tests/mdm/
test_relationship_closing_pattern_registry.py` -- every `RELATIONSHIP_TYPES`
member is classified, no stale entries, every value is a known pattern
name, plus a snapshot test pinning today's actual classification so a
future silent reclassification shows up as a reviewable diff.

`/gof-refactor-reviewer` self-consult before writing (per CLAUDE.md hard
rule): `RELATIONSHIP_TYPES` has grown 3 times in this repo's git history
(one commit per new relationship type, confirmed via `git log -L`), with
no enforcement a new type gets a corresponding closing-pattern decision --
real evidence this registry addresses an actual repeated-change gap, not
a hypothetical one. Purely additive (one dict, one frozenset, one test
file); no existing closing implementation touched. Healthy to proceed
inline, no further structural change needed.

Tests: `tests/mdm/test_relationship_closing_pattern_registry.py` (4
new, all passing) plus `tests/mdm/test_pipeline_relationships.py`/
`test_rules.py` (112 passed, unaffected -- confirms the additive change
didn't touch any derivation logic). Full repo suite green: 3186 passed
(up from 3182), 7 skipped, exit 0.

3-axis `/code-review` (Standards/Spec/GoF), per CLAUDE.md hard rule, all
clean -- no hard findings. Standards flagged two judgement calls, not
acted on: the pattern-name knowledge now lives in three places
(registry, test snapshot, ADR prose -- deliberate, the snapshot test's
own docstring explains this is meant to make a future reclassification
show up as a reviewable diff, not accidental duplication); and the new
ADR adds a "## Patterns" section between its intro paragraph and
Consequences, diverging from the two-file precedent's shape (0006/0007
go straight from one dense paragraph to Consequences) -- accepted as
justified since this ADR's actual content is a taxonomy that doesn't
compress into one paragraph. Spec review independently re-verified
(not just trusted) IS_ENTITY_OF/IS_PERSON_OF's real code (both call
`ensure_relationship` with zero properties) and HAS_PARENT_COMPANY's
real code (its primary `sec_subsidiary_evidence` path does carry
properties, no dedicated closer) -- both match the diff's
classification. GoF review confirmed the 3-commit growth-history
evidence directly via `git log -L` (each commit added relationship
types with zero accompanying closing-pattern decision) and confirmed
the diff is a pure 40-line insertion touching no existing closing
implementation -- registry justified, unification correctly still
deferred per Rule 0.
