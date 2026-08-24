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

**Status:** ready-for-agent

- [ ] Decide what `acquisition_mode`/`completeness_policy`/`discovery_policy`
  actually change about runtime behavior for `filing_artifact` (today the
  only covered family) — or, if none of the three currently have a
  meaningful effect on this one family, decide and document that
  explicitly rather than leaving them silently unread. `required_producers`
  should very likely gate `ProcessingLedger.seal_expected_producers`'s
  expected-producer set instead of (or in addition to) wherever that set is
  constructed today — confirm and wire it, or explain why not.
- [ ] Either enforce `coverage_end_date` (acquisition genuinely continues
  until that date, then stops) or narrow the spec bullet's own language/this
  repo's understanding of "explicit boundary" to mean "recorded, not
  time-gated" — whichever is decided, make the code and a test agree with
  it explicitly (today they're silently mismatched).
- [ ] Ship a real, committed, re-runnable bootstrap path (a script or a
  `mdm` CLI invocation sequence documented in this repo, not inline test
  fixture logic) that opens and activates the first Source Family Registry
  version for `filing_artifact` in prod, and wire it into whichever
  deploy/install script currently applies migration 014.
