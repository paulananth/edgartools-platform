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

- [Ticket 01: root cause + existing-fix effectiveness](issues/01-root-cause-existing-fix-effectiveness.md) — the deeper root cause isn't quarantine logic at all: `_derive_institutional_holds`/`_derive_manages_fund` always restart CIK/CRD-range iteration from the beginning on every capped run, so a stuck watermark can never catch up once backlog exceeds one run's budget. Implemented a persisted, resumable cursor decoupled from the stable watermark (only advances once a sweep covers the *entire* range under one watermark boundary). The mandatory 3-axis `/code-review` found two real bugs in the first draft (a NULL-comparison upsert guard that would have permanently blocked the watermark from ever advancing, and an unstated regression suppressing watermark writes during reconciliation) — both fixed, both covered by new tests, full write-up in CLAUDE.md's own new 5-whys entry. Full `tests/mdm/` suite green (700 passed). **Committed** (`fc5587e2`); still not deployed, migration 022 not run-verified against real Postgres (none reachable in this sandbox). Surfaced a follow-up, deliberately not fixed here: `reconciliation_pass` shares the identical restart-from-beginning gap, unverified whether it's a live problem in prod.
- [Ticket 02: port deactivation to IS_INSIDER](issues/02-port-deactivation-to-is-insider.md) — a role/title change (e.g. officer→director) now closes the person's prior open IS_INSIDER version before inserting the new one, instead of colliding as an unresolvable same-source conflict and getting silently quarantined — mirrors the existing HOLDS/COMPANY_HOLDS zero-shares-close pattern (`_current_open_versions_by_pair`/`_track_open_version`), with a new chronological guard (found during the pre-code `/gof-refactor-reviewer` consult) so reprocessing an older row can never incorrectly close an already-open newer version. 3-axis `/code-review` came back clean (two trivial doc/test-hygiene fixes only). 4 new tests, `tests/mdm/` suite green (704 passed). **Committed** (`07bd6bf3`); not deployed. Unblocked Ticket 03 (EMPLOYED_BY), which reuses the same new method.
- [Ticket 03: port deactivation to EMPLOYED_BY](issues/03-port-deactivation-to-employed-by.md) — `_derive_employed_by` has two independent source branches; only the exec/DEF-14A branch needed a fix (a new fiscal year's comp record always differs from the prior open version, so every subsequent year quarantined — 97.8% of rows created since PR #568). The event/Item 5.02 branch already had its own separate closing mechanism, untouched. Reused Ticket 02's `_deactivate_if_properties_changed` exactly as designed. 3-axis `/code-review` found the helper's own docstring had gone stale ("not yet wired there") plus two minor hygiene items, all fixed. 3 new tests, `tests/mdm/` suite green (707 passed), full repo suite green (3167 passed, only the 8 pre-existing unrelated Postgres-integration failures). **Committed** (`e0fbcb37`); not deployed.
- [Ticket 04: audit downstream consumers](issues/04-audit-downstream-consumers.md) — worse than hypothesized: the Postgres-native "current" readers and the gold/mirror export paths are clean, but the Snowflake **graph materialization** (`snowflake_graph.py`'s `MDM_GRAPH_EDGES` build) filters only `IS_ACTIVE = TRUE`, never `QUARANTINED = FALSE` — and quarantining never sets `is_active = False`, so a quarantined row and the row it conflicted with both materialize as separate, simultaneously-live, conflicting graph edges. Worse still: the reconcile parity check's own "expected" count has the identical omission, so both sides agree and report a false-clean `MDM_MINUS_GRAPH = 0` — the monitoring built to catch this drift is blind to it, not an independent correction path masking it. Concrete fix identified but deliberately deferred here — implemented in Ticket 07.
- [Ticket 05: backfill already-quarantined rows](issues/05-backfill-existing-quarantined-rows.md) — chose a targeted correction pass over full re-derivation (re-derivation would insert brand-new synthetic rows via `ensure_relationship`, leaving the original ~199K quarantined rows as orphaned duplicates needing separate cleanup anyway). New module (`relationship_quarantine_backfill.py`) walks each quarantined row's own `relationship_id` group and, for each one, retroactively applies the exact same conflict/chronological-guard/priority logic `ensure_relationship` uses at insert time — un-quarantining in place (repurposing the original row, not inserting a new one) only when safe; genuine cross-source conflicts, priority rules configured since quarantine, and chronologically-ambiguous rows are left untouched and counted separately, never force-resolved. 3-axis `/code-review` found real duplication (Standards and GoF independently converged on the same finding) — fixed by extracting two shared predicates (`relationships_conflict`/`confirmed_chronologically_after`) into `graph.py`, now used by `ensure_relationship`, `_deactivate_if_properties_changed`, and this new module alike; also properly integrated `resolve_source_priority` (renamed from private) instead of a hardcoded source-system check, and added an audit trail via `source_evidence` (not `MdmChangeLog`, confirmed that table never tracks relationships at all). 12 new tests, `tests/mdm/` suite green (719 passed), full repo suite green (3179 passed, only the 8 pre-existing unrelated Postgres-integration failures). CLI: `mdm backfill-quarantined-relationships --dry-run`. **Committed** (`76871113`); not deployed. Implemented + tested but deliberately **not executed against real prod** yet — that's a separate, higher-stakes action needing its own explicit go-ahead.
- [Ticket 07: fix Snowflake graph quarantine-blindness](issues/07-fix-snowflake-graph-quarantine-blindness.md) — implemented Ticket 04's identified fix. Ticket 04's own writeup named 3 sites; a full grep found 7 across 7 functions (graph-build, eligible-preflight count, inline validation parity, plus 4 more in the dedicated `mdm verify-graph` functions this session hadn't examined before: `_render_verify_relationship_counts`, `_render_exact_relationship_parity`'s content-hash CTE, `_render_missing_edges`, and `_render_extra_edges` — the last needing the *inverse* `OR RI.QUARANTINED = TRUE` condition since it flags edges that shouldn't exist). All additive filter changes, no schema change needed. 2 new tests, `tests/mdm/` suite green (720 passed). Does not retroactively fix already-materialized duplicate edges in any existing graph generation — needs a fresh `sync-graph` rebuild afterward.
- [Ticket 06: institutional-holds securities never link to issuer](issues/06-institutional-holds-securities-never-link-to-issuer.md) — chose fuzzy-matching `issuer_name` against `MdmCompany.canonical_name` (confirmed with the user; populating CUSIP on Form-4 securities was ruled out — Form 3/4/5 XML carries no CUSIP at all). Reuses the existing `FuzzyNameMatcher`/`('company','fuzzy_name')` threshold rather than new matching infrastructure — this is that matcher's first real multi-candidate production exercise. Write-time fix in `_ensure_security_by_cusip`'s create path plus a dedicated `mdm backfill-security-issuer-links --dry-run` for the 1,718 already-orphaned securities, mirroring Ticket 05's shape. REVIEW-tier candidates are logged only, never written to `mdm_match_review` (its accept path always merges, which would be destructive here). 3-axis review found real issues: duplicated logging (fixed via extraction), an undiscussed backfill-query scope widening (narrowed to match the ticket's own `resolution_method='cusip_stub'` diagnostic exactly), and — most importantly — that fuzzy-match-only was a unilateral scope reduction from the user's original "fuzzy match + real NLP/NER" request; confirmed with the user before proceeding (NER doesn't apply to an already-clean name field). 16 new tests, `tests/mdm/` suite green (739 passed). **Deployed and live-verified 2026-09-09** (same perf-fixed image as PR #575): real prod run examined 12,174 securities, linked 7,294 (60%), logged 3,895 to REVIEW (32%), 985 no-match. Ran end-to-end in ~1h48m. Separately, while executing Ticket 05's real backfill in prod this same session, found and fixed a live bug in `confirmed_chronologically_after` (shared with the already-deployed Ticket 02/03 write path) — see Ticket 05's own file for that correction.
- [Ticket 08: redesign quarantine backfill for multi-version chains](issues/08-redesign-quarantine-backfill-for-multi-version-chains.md) — a live prod dry-run of Ticket 05's backfill found `closed: 0, reopened: 0` — its pairwise "one active vs. one quarantined" design doesn't match reality; 90% of skipped rows (219,247) have 2-353 simultaneously-active same-source rows already conflicting, not a single stuck one. `/domain-modeling` surfaced that `CONTEXT.md`'s "Generation-Eligible Relationship Version" term implicitly assumed at most one current version, an invariant broken at scale. Chose: extend Ticket 05's existing module (same shared `relationships_conflict`/`confirmed_chronologically_after`/`resolve_source_priority` functions) to walk each relationship_id's FULL chronological row history and correct existing rows via UPDATE — explicitly not a call to `ensure_relationship` itself (which only inserts, and would recreate the exact orphaned-duplicate problem Ticket 05 already rejected) and not full re-derivation. Rollout scoped to INSTITUTIONAL_HOLDS first (7,966 relationship_ids) before the other 5 affected types. MANAGES_FUND (a structurally different, larger, previously-hidden bug — see Out of scope) explicitly ruled out of this ticket. Implementation is [Ticket 09](issues/09-implement-chain-aware-backfill-institutional-holds.md), resolved.
- [Ticket 09: implement + run chain-aware backfill for INSTITUTIONAL_HOLDS](issues/09-implement-chain-aware-backfill-institutional-holds.md) — rewrote `backfill_relationship_id` into a chronological, date-grouped chain walk (Ticket 08's design); the mandatory 3-axis `/code-review` caught a real bug the pre-code consult missed (a row still-quarantined after an unresolved same-date tie could get silently selected as a later row's closeable conflict, leaving it permanently stuck quarantined with a closed date). A second, unrelated bug surfaced live during the prod dry-run: `resolve_source_priority` had no caching and re-issued ~9 identical Postgres round trips/sec for 8.5+ hours before being manually stopped — fixed with a run-scoped `priority_cache` (CLAUDE.md's own "Quarantine backfill uncached priority lookup" 5-whys). Real backfill executed against prod 2026-09-10 (exit 0, ~1h46m): 8,525 relationship_ids examined, 84,212 rows closed, 62,947 reopened; live Postgres confirmed INSTITUTIONAL_HOLDS quarantine count dropped 65,778 → 21,704. The remainder (`skipped_ambiguous_order`: 458,139 row-pairs, `skipped_multiple_conflicts`: 62,947) is left for manual review by design, not a bug. Snowflake graph rebuilt same-day (generation `db802e24-...`, exact parity confirmed, activated) — superseded by Ticket 10's own rebuild below.
- [Ticket 10: run chain-aware backfill for the remaining 4 types](issues/10-run-chain-aware-backfill-remaining-four-types.md) — no code change needed (mechanism confirmed type-agnostic). A combined dry-run across all 4 remaining types found `skipped_ambiguous_order` ~16x higher per-relationship_id than INSTITUTIONAL_HOLDS' own dry-run; investigated rather than assumed benign, which surfaced that COMPANY_HOLDS specifically is contaminated by an unrelated, pre-existing bug — ~33K individuals (confirmed: Mark Zuckerberg, Jensen Huang, Javier Olivan, and more) misclassified as `company` entities instead of `person`, driving one relationship_id to 27,849 rows. Split off as its own map ([individual-filer-company-misclassification](../individual-filer-company-misclassification/map.md)) rather than backfilling on top of it. HOLDS/EMPLOYED_BY/IS_INSIDER confirmed clean at normal scale and backfilled for real against prod (exit 0, ~28.8 min): 3,756 relationship_ids examined, 19,756 closed, 19,960 reopened. Graph rebuilt and activated same-day (generation `ae0db138-...`, exact parity confirmed). All 4 types this map's Destination names other than COMPANY_HOLDS are now corrected end-to-end.

## Not yet specified

- Whether `reconciliation_pass` (the monthly MDM Reconciliation Backstop)
  ever actually hits its own `target_per_type` cap for INSTITUTIONAL_HOLDS/
  MANAGES_FUND in prod -- if it does, it has the identical restart-from-
  the-beginning coverage gap Ticket 01 just fixed for the ordinary
  incremental pass, since Ticket 01's fix deliberately isolates
  reconciliation from the new cursor state. Needs a live check (does a
  real reconciliation run for either type ever get capped?) before this
  becomes a real ticket rather than a hypothetical.
- Whether the ~199K already-quarantined rows' duplicate graph edges
  (Ticket 04's finding) need a targeted correction, or whether the next
  ordinary `sync-graph` run's full generation rebuild self-heals once the
  3-line `snowflake_graph.py` quarantine-filter fix (identified but not
  implemented in Ticket 04) lands -- needs its own decision, not yet a
  ticket. Also unresolved: whether Ticket 05's Postgres-side backfill must
  explicitly trigger a `sync-graph` re-run afterward, or whether that's
  implied/automatic.
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

## Out of scope

- `ISSUED_BY` -- confirmed structurally immune (0% quarantined in prod):
  calls `ensure_relationship` with no `properties` argument at all (a pure
  existence fact, nothing to conflict over), so this bug class cannot
  reach it.
- **Correction (2026-09-09, Ticket 08): the identical claim for
  `MANAGES_FUND` was wrong in spirit, even though narrowly true.**
  "Immune to quarantine" was true (0% quarantined) but was read as "immune
  to this bug class" -- it isn't. `MANAGES_FUND` shares `ISSUED_BY`'s
  empty-`properties` call shape, but that means its conflict discriminator
  can *never* fire, so it never even reaches the quarantine check that
  would otherwise catch a conflicting write -- it silently accumulates
  duplicate simultaneously-active rows instead (140,907 relationship_ids
  confirmed live, ~13x this map's own 199K-row destination). This is a
  distinct, larger, previously-hidden bug -- ruled out of scope for *this*
  map (different root cause: write-time conflict-blindness, not a
  backfill-design gap) and needs its own future wayfinder map, not folded
  in here.
- Reducing the underlying MDM Postgres cross-region latency
  (mdm-run-throughput map's own out-of-scope item) -- unrelated to this
  map's root cause.
