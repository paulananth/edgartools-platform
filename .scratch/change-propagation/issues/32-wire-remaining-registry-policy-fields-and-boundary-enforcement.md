# 32 — Wire Ticket 20's remaining registry policy fields, enforce the removal boundary, and bootstrap the first active version

**What to build:** Close three gaps Ticket 20's `/code-review` Spec pass
found in the merged implementation (`SourceRegistryLedger`,
`edgar_warehouse/mdm/migrations/014_source_registry.sql`) — each is a real,
evidenced partial-completion of Ticket 20's own acceptance bullets, not a
new idea:

1. **Bullet 1 ("versions ... as executable policy data") is only partially
   true.** `active_in_scope_forms` reads `in_scope_forms` and actually gates
   `drive_filing_discovery.py`'s scope filter — that part is executable. But
   `acquisition_mode`, `completeness_policy`, `discovery_policy`, and
   `required_producers` are captured by `CoverageSpec`, persisted to
   `source_registry_coverage`, and round-tripped by the CLI, yet **nothing
   ever reads them back** — `build_active_source_family_registry` ignores
   all four when constructing a `SourceFamilyPolicy`, and
   `facade.SourceFamilyPolicy`'s own Protocol has no fields for any of
   them. They are inert audit metadata today, not policy that drives
   behavior.
2. **Bullet 2's "ends future acquisition at an explicit boundary" is not
   enforced.** `coverage_end_date` is stored (and required non-null by
   `ck_source_registry_coverage_remove_end_date` for `'remove'` rows) but
   never compared against any date anywhere in `edgar_warehouse/`. A
   `'remove'`d family is excluded from `build_active_source_family_registry`
   and `active_in_scope_forms` immediately upon the version activating,
   regardless of how far in the future `coverage_end_date` is —
   `test_removed_family_excluded_from_active_registry` sets
   `coverage_end_date=date(2026,2,1)` and asserts exclusion right after
   `activate()`, confirming the field is currently decorative.
3. **No bootstrap path exists to actually go live.** `drive_filing_discovery.py`
   and `capture_filing_artifact.py` now hard-require an active registry
   version (`NoActiveRegistryVersion` / empty `in_scope_forms` otherwise) —
   but nothing in `runtime.py`'s `seed_defaults`, migration
   `014_source_registry.sql`, or `bootstrap-prod-mdm.sh` ever opens and
   activates a first version. The only place that logic exists is
   duplicated inline in two test fixtures
   (`tests/application/test_capture_filing_artifact_command.py`'s and
   `tests/application/test_drive_filing_discovery_command.py`'s
   `_activate_filing_artifact_registry` helper), whose own comment admits
   it's "mirroring the real bootstrap a fresh deployment needs" — i.e. a
   needed deliverable that was never actually shipped. Until this exists,
   applying migration 014 to prod and redeploying would make both commands
   fail closed in production, not just in tests.

**Blocked by:** 20 — Version and activate the Acquisition Universe (this
ticket only exists because 20 is otherwise merged and working)

**Status:** resolved

- [x] Decide what `acquisition_mode`/`completeness_policy`/`discovery_policy`
  actually change about runtime behavior for `filing_artifact` (today the
  only covered family) — or, if none of the three currently have a
  meaningful effect on this one family, decide and document that
  explicitly rather than leaving them silently unread. `required_producers`
  should very likely gate `ProcessingLedger.seal_expected_producers`'s
  expected-producer set instead of (or in addition to) wherever that set is
  constructed today — confirm and wire it, or explain why not.
- [x] Either enforce `coverage_end_date` (acquisition genuinely continues
  until that date, then stops) or narrow the spec bullet's own language/this
  repo's understanding of "explicit boundary" to mean "recorded, not
  time-gated" — whichever is decided, make the code and a test agree with
  it explicitly (today they're silently mismatched).
- [x] Ship a real, committed, re-runnable bootstrap path (a script or a
  `mdm` CLI invocation sequence documented in this repo, not inline test
  fixture logic) that opens and activates the first Source Family Registry
  version for `filing_artifact` in prod, and wire it into whichever
  deploy/install script currently applies migration 014.

## Answer

All three gaps closed (commit `e3db9bbd`, branch
`claude/change-propagation-ticket32-registry-policy-bootstrap`).

1. **User decision:** put to the user as an explicit either/or (per
   wayfinder's HITL rule for a genuine design fork); they chose the broader
   "wire all four fields now" option over "wire `required_producers` only."
   Each field became a *validate-against-the-one-known-value* gate rather
   than generic dispatch machinery for hypothetical modes nothing yet
   needs (confirmed sound via a `/gof-refactor-reviewer` pass before
   implementing, given exactly one source family exists today):
   `acquisition_mode` gates which Strategy factory may serve a family
   (`registry_ledger.py`'s `_POLICY_FACTORIES`); `completeness_policy`
   dispatches `FilingArtifactPolicy.is_complete` via a one-entry check map;
   `discovery_policy` is validated in `drive_filing_discovery.py` against
   the one mechanism that module implements; `required_producers` is
   validated against the one producer `filing_artifact`'s Silver-write body
   can actually serve (`silver_acceptance.py`) rather than generalized to
   arbitrary N producers with different write bodies.
2. **User decision:** delegated to the agent ("you decide"); chose "enforce
   the date." `coverage_end_date` now genuinely gates future acquisition
   (`registry_ledger.py`'s new `_coverage_in_effect`). This surfaced a
   non-obvious follow-on requirement: a `'remove'` `CoverageSpec` now
   inherits its operational fields from the family's currently-active
   coverage row in `SourceRegistryLedger.open_draft`, since an operator
   scheduling a removal naturally wouldn't redeclare policy just to stop
   it later — without this, a removed family would report zero in-scope
   forms immediately despite still being "in effect." `/code-review`'s
   Spec pass then found a second, real bug in the first draft of this fix:
   every production call site defaulted the new `as_of_date` parameter to
   server wall-clock `date.today()` instead of the command's own
   `business_date` — wrong for a per-business-date driver that can replay
   historical dates. Fixed by threading `business_date_value` through every
   registry read in `drive_filing_discovery.py`; a regression test proves
   it (reproduced red before the fix, confirmed green after).
3. Shipped `infra/scripts/bootstrap-source-family-registry.sh` (idempotent
   once a version is active; documented non-idempotent edge case on a
   mid-sequence crash — leaves a harmless orphaned draft) plus a new `mdm
   registry-record-catchup` CLI subcommand (previously had no CLI surface
   at all). Wired into `install.sh` right after `mdm migrate`. Smoke-tested
   end-to-end — including the idempotent re-run — against a real throwaway
   Postgres 16 container, not just unit tests.

Both `/code-review` axes ran against the full diff: Standards found no hard
violations (a few minor duplicated-validation-shape smells noted, not
fixed); Spec's one real finding (the wall-clock boundary bug above) is
fixed and regression-tested. Full suite green: 2484 passed, 4 skipped, plus
the real-Postgres integration suite (4 passed).

Ticket 20 can now be marked fully resolved — its own bullets 1 and 2 were
the only partial pieces, and both are closed by this ticket.
