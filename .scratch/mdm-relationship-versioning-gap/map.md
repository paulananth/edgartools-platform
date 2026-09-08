# MDM relationship versioning gap

## Destination

A stateful `mdm_relationship_instance` version (one whose properties can
legitimately change over time on repeated reports from the same source --
share counts, roles/titles, compensation) never gets silently quarantined
just because its predecessor version was never closed. All five affected
relationship types (`COMPANY_HOLDS`, `HOLDS`, `INSTITUTIONAL_HOLDS`,
`EMPLOYED_BY`, `IS_INSIDER`) reliably surface their true current state, the
~199K rows already wrongly quarantined in prod are corrected (not just
future writes), and the fix is deployed + live-verified with real prod
measurements -- matching this session's own standing "real measurements,
not estimates" preference (mdm-run-throughput map). This map carries
execution, not just a decision spec (explicit user choice) -- tickets get
implemented, deployed, and verified as they resolve, the same way
mdm-run-throughput's Tickets 04/06/07 did.

## Notes

- Domain: `edgar_warehouse/mdm/graph.py` (`GraphSyncEngine.ensure_relationship`,
  `close_relationship_version`, `_intervals_overlap`, `_resolve_source_priority`),
  `edgar_warehouse/mdm/pipeline.py` (`_derive_is_insider`, `_derive_employed_by`,
  `_derive_holds`, `_derive_company_holds`, `_derive_institutional_holds*`).
- Directly motivated by, and a natural continuation of, the
  `mdm-relationship-incremental-filters` map -- its
  [Ticket 04](../mdm-relationship-incremental-filters/issues/04-implement-checkpoint-watermarks-and-deactivation.md)
  (PR #568, merged 2026-09-07, already deployed in today's MDM image build)
  already diagnosed this exact root cause and built the fix pattern for
  `HOLDS`/`COMPANY_HOLDS` (zero-shares close) and `INSTITUTIONAL_HOLDS`
  (cross-period diff-and-close) -- but scoped to those 3 types only, and
  its own live effectiveness has not been re-verified since deploy (see
  Ticket 01 below -- today's live data suggests it may not be fully
  working even for the types it targeted).
- `/gof-refactor-reviewer` (CLAUDE.md hard rule) before any code change;
  full 3-axis `/code-review` (Standards/Spec/GoF) before any commit.
- Standing preference from the parent session: real measurements against
  live prod data, not estimates or unit-test-only proof.
- [Ticket 06](issues/06-institutional-holds-securities-never-link-to-issuer.md)
  is filed here despite being a genuinely distinct root cause (entity-
  resolution completeness -- a missing `issuer_entity_id` FK link -- not a
  relationship-instance conflict/quarantine bug) because it surfaced from
  the same investigation thread. Don't assume it shares this map's
  Destination when reading "Decisions so far" once it resolves.

## Decisions so far

- [Ticket 01: root cause + existing-fix effectiveness](issues/01-root-cause-existing-fix-effectiveness.md) — the deeper root cause isn't quarantine logic at all: `_derive_institutional_holds`/`_derive_manages_fund` always restart CIK/CRD-range iteration from the beginning on every capped run, so a stuck watermark can never catch up once backlog exceeds one run's budget. Implemented a persisted, resumable cursor decoupled from the stable watermark (only advances once a sweep covers the *entire* range under one watermark boundary). The mandatory 3-axis `/code-review` found two real bugs in the first draft (a NULL-comparison upsert guard that would have permanently blocked the watermark from ever advancing, and an unstated regression suppressing watermark writes during reconciliation) — both fixed, both covered by new tests, full write-up in CLAUDE.md's own new 5-whys entry. Full `tests/mdm/` suite green (700 passed). Still not committed/deployed; migration 022 not run-verified against real Postgres (none reachable in this sandbox). Surfaced a follow-up, deliberately not fixed here: `reconciliation_pass` shares the identical restart-from-beginning gap, unverified whether it's a live problem in prod.

## Not yet specified

- Whether `reconciliation_pass` (the monthly MDM Reconciliation Backstop)
  ever actually hits its own `target_per_type` cap for INSTITUTIONAL_HOLDS/
  MANAGES_FUND in prod -- if it does, it has the identical restart-from-
  the-beginning coverage gap Ticket 01 just fixed for the ordinary
  incremental pass, since Ticket 01's fix deliberately isolates
  reconciliation from the new cursor state. Needs a live check (does a
  real reconciliation run for either type ever get capped?) before this
  becomes a real ticket rather than a hypothetical.
- Whether the downstream consumers of "current" `mdm_relationship_instance`
  state (Snowflake gold export via `mdm export`, graph sync via
  `mdm sync-graph`/`mdm publish-relationships`, the MDM/graph review
  dashboard) already reflect this stale/quarantined-excluded data as their
  own "current" state, or whether they have some independent correction
  path -- not yet checked. Bears on how urgent/severe the user-facing
  impact already is.
- Root design for how per-period-boundary relationship types (anything
  where the same source reports a new point-in-time snapshot repeatedly --
  13F quarters, executive-compensation fiscal years, insider-status
  filings) SHOULD version and close prior evidence, as a single coherent
  pattern rather than one bespoke closing rule per relationship type. The
  existing `HOLDS`/`COMPANY_HOLDS` zero-shares close and
  `INSTITUTIONAL_HOLDS` cross-period diff-and-close are two structurally
  different bespoke mechanisms already, and `IS_INSIDER`/`EMPLOYED_BY` need
  a third (there is no "shares reach zero" or "latest 13F CUSIP set"
  equivalent for insider-role or executive-compensation evidence -- a role
  change or comp update is signalled purely by the new filing's own
  differing property values on an already-fixed pair).
- Backfill mechanism for the ~199K rows already wrongly quarantined in
  prod -- whether a targeted SQL correction pass (walk each
  `relationship_id`, re-apply the corrected close/supersede logic
  retroactively) is sufficient, or whether a full re-derivation
  (`derive-relationships` for all 5 types, fresh) is needed/safer. Depends
  on Tickets 01-03's design landing first, since backfilling under the
  still-buggy logic would just re-quarantine the same rows.

## Out of scope

- `ISSUED_BY`/`MANAGES_FUND` -- confirmed structurally immune (0%
  quarantined in prod): both call `ensure_relationship` with no
  `properties` argument at all (pure existence facts, nothing to
  conflict over), so this bug class cannot reach them.
- Reducing the underlying MDM Postgres cross-region latency
  (mdm-run-throughput map's own out-of-scope item) -- unrelated to this
  map's root cause.
