# State machine consolidation

## Destination

A locked design for consolidating the platform's 26 deployed Step
Functions state machines (`infra/scripts/deploy-aws-application.sh`,
`infra/aws-prod-application.json`) down to fewer, less-duplicated
definitions -- specifically the repeated `MdmExport -> MdmSync -> MdmVerify`
(often `-> GoldRefresh`) tail that `mdm_gold`, `ownership_mdm_gold`,
`silver_mdm_gold`, `bronze_seed_silver_gold`, and `residual_holds_graph`
each hand-duplicate with a different "head" stage in front of it. Done
when there is a written, evidence-backed decision on the consolidation
mechanism (shared code generating still-separate machines vs. fewer
actually-deployed machines with parameterized entry points) that someone
can implement without further architecture debate. Matches
[pipeline-throughput-architecture](../pipeline-throughput-architecture/map.md)'s
split: this map decides, `release-readiness` tickets implement.

## Notes

- Domain: `infra/scripts/deploy-aws-application.sh` (all Step Functions
  JSON generation, one Python heredoc per factory function),
  `infra/aws-prod-application.json` (deployed state machine ARN registry).
- Real prod execution counts as of 2026-08-04 (`aws stepfunctions
  list-executions --max-results 1000` per machine): 9 of 26 machines have
  **zero executions ever** -- `bootstrap_full`, `full_reconcile`,
  `load_daily_form_index_for_date`, `catch_up_daily_form_index`,
  `bootstrap_batched`, `mdm_gold`, `silver_mdm_gold`, `mdm_seed_universe`,
  `mdm_seed_from_silver`. Zero executions is not proof of deadness by
  itself (see ticket 01) but is the starting evidence.
- CLAUDE.md's user-facing "When to use what" table documents only 5 of the
  26 (`load_history`, `targeted_resync`, `gold_refresh`, `bootstrap`,
  `daily_incremental`). The other 21 are either individual MDM pipeline
  stages exposed standalone (`mdm_run`, `mdm_backfill_relationships`,
  `mdm_sync_graph`, `mdm_verify_graph`, `mdm_counts`, `generation_build`,
  `mdm_migrate`, `mdm_check_connectivity`, `mdm_seed_universe`,
  `mdm_seed_from_silver`) or composed chains of several of those stages
  (`mdm_gold`, `ownership_mdm_gold`, `silver_mdm_gold`,
  `bronze_seed_silver_gold`, `residual_holds_graph`).
- Confirmed live (`describe-state-machine` on all 5 composed machines,
  2026-08-04): `mdm_gold` = `MdmRun, MdmBackfill, MdmExport, MdmSync,
  MdmVerify, GoldRefresh`; `ownership_mdm_gold` = `ParseOwnershipBronze,
  MdmPersons, MdmIsInsider, MdmExport, MdmSync, MdmVerify, GoldRefresh`;
  `silver_mdm_gold` = `SeedUniverse, SeedSilverBatches, BatchSilver,
  MdmRun, MdmBackfill, MdmExport, MdmSync, MdmVerify, GoldRefresh`;
  `bronze_seed_silver_gold` = a much larger strict/release-mode variant of
  the same tail; `residual_holds_graph` = `MdmSecurities, MdmPersons,
  MdmIsInsider, MdmHolds, MdmCompanyHolds, MdmInstitutionalHolds,
  MdmExport, MdmSync, MdmVerify` (no GoldRefresh). Every one of the 5
  re-implements `MdmExport/MdmSync/MdmVerify(/GoldRefresh)` as its own
  literal JSON in its own Python heredoc function -- confirmed duplicated
  state shape, not just similar-looking.
- Parked mid-session (release-readiness ticket 86 was in progress, live
  prod Step Functions had just been touched for ticket 84/86) -- this map
  is charted only through its first two tickets as of 2026-08-04; deeper
  frontier-mapping (grilling through the remaining fog below) is
  explicitly deferred to a dedicated follow-up session, not abandoned.

## Decisions so far

- [Confirm dead vs. dormant state machines](issues/01-confirm-dead-state-machines.md) — Per-machine verdict on all 9 zero-execution machines: **6 intentionally dormant** (`bootstrap_full`, `full_reconcile`, `load_daily_form_index_for_date`, `catch_up_daily_form_index`, `mdm_gold`, `silver_mdm_gold` — real, current, several actively touched within days of this ticket, one the same day) — none are deletion candidates. **1 dead** (`bootstrap_batched` — `load_history`'s own code comment documents it was built specifically to fix a `silver.duckdb` consistency race in `bootstrap_batched`'s architecture; superseded, safe removal candidate). **2 uncertain** (`mdm_seed_universe`, `mdm_seed_from_silver` — both built solely for since-migrated-off AWS-RDS VPC access; neither has had an explicit keep/retire call). Graduated into tickets 03 and 04.
- [Decide consolidation mechanism for shared MDM tail](issues/02-decide-consolidation-mechanism-for-shared-mdm-tail.md) — First-round lock (named presets over full composability) was **re-grilled after implementation started and found the 5 composed machines' tails are 6 genuinely distinct shapes, not one shape with parameters** (`bronze_seed_silver_gold` alone branches into an entire separate "strict" release-mode tail). Final scope: (1) the 5 **MDM Pipeline Machines** get a sequencing-skeleton-only helper (`wire_mdm_tail()`, ordering only — proven drift risk from `git log -S"MdmVerify"`) and stay 5 separate deployed machines, no collapse; (2) the real uniform group is 7 **MDM Utility Machines** (not 8 — `generation_build` was miscategorized, `mdm_seed_universe` is excluded per ticket 04's own kept-as-is call), collapsed into one consolidated `mdm_utility` machine via `{"mode": "..."}`; (3) `trigger.sh` keeps its short-name UX unchanged. New CONTEXT.md glossary section: "Deployment orchestration (Step Functions)". **Implemented (code-only) 2026-08-10** — full suite green (1974 passed, 4 skipped), not yet committed/deployed.
- [Decide whether to delete `bootstrap_batched`](issues/03-decide-bootstrap-batched-deletion.md) — Delete outright now, no grace period — evidence is already fully determined (zero executions ever, `load_history` supersedes it by design). Found a real landmine while scoping: `tests/architecture/test_mdm_sync_graph_limit_per_type.py` uses the function's name as a text-slice marker for an unrelated test, so deletion requires updating that marker too. Full 8-item checklist written, including the explicit `delete-state-machine` step (not automatic from a routine redeploy) and a rollback snapshot first. **Implemented and closed 2026-08-10** — code in PR #397, live AWS deletion done, rollback snapshot on file.
- [Decide keep-or-retire for `mdm_seed_universe` and `mdm_seed_from_silver`](issues/04-decide-mdm-seed-machines-fate.md) — Split verdict, user-confirmed: **keep** `mdm_seed_universe` (preserves a real, currently-only-here `--tracking-status`/`--limit` override capability, free to generate via the shared single-workflow loop, no code change needed); **retire** `mdm_seed_from_silver` (zero callers of any kind anywhere in the repo, its original AWS-RDS-VPC-access rationale is fully stale post-Snowflake-Postgres-migration; CLI command stays runnable ad hoc). 7-item retirement checklist written, sharing ticket 03's rollback-snapshot-then-explicit-delete pattern. **Implemented and closed 2026-08-10** — code in PR #397, live AWS deletion done, rollback snapshot on file.
- [Delete the 7 orphaned original MDM Utility Machine state machines](issues/05-delete-orphaned-mdm-utility-machine-originals.md) — Opened and resolved same-day, 2026-08-20, after ticket 02's own "orphaned but harmless" call was proven wrong by a real incident: `edgartools-prod-mdm-migrate`/`edgartools-prod-mdm-run` (the pre-consolidation originals, frozen on a 2026-08-09 image) gave a false-positive "SUCCEEDED" and a false-negative "no errors" respectively when invoked to verify the migration-011 schema-drift fix (CLAUDE.md) — neither actually exercised current code, since their frozen task-def revisions predate the very column being tested. The prior "resolved 2026-08-19" claim for that incident was itself never genuinely verified as a direct result. Zero running executions confirmed on all 7, fresh rollback snapshots captured, all 7 deleted live in prod (`edgartools-prod-mdm-run`/`-backfill-relationships`/`-sync-graph`/`-verify-graph`/`-counts`/`-migrate`/`-check-connectivity`), `edgartools-prod-mdm-utility` and the deliberately-kept siblings (`mdm-gold`, `mdm-seed-universe`, `ownership-mdm-gold`, `silver-mdm-gold`) confirmed untouched. One flag left for a separate open ticket (release-readiness 94, `mdm sync-graph`'s `limit_per_type` wiring bug): its discovery notes reference the now-deleted orphaned machine, but the underlying bug lives in shared command-generation code also used by `mdm-utility`'s consolidated mode, so it's unaffected by this deletion — not investigated further here.

## Not yet specified

- Whether ticket 84/86's `sec_fetch_active` cross-command lease wiring
  (release-readiness, a separate concurrent effort) constrains or
  interacts with any consolidation here -- the 5 SEC-fetching machines it
  touches (`daily_incremental`/`bootstrap`/`bootstrap_full`/
  `targeted_resync`/`load_history`) are largely disjoint from this map's
  MDM-tail-duplication focus, but `silver_mdm_gold`/
  `bronze_seed_silver_gold` do call `bootstrap-batch`-adjacent stages --
  worth re-checking once ticket 02 has a concrete mechanism in hand.

## Out of scope

(none yet -- scope has not been narrowed enough to rule anything out)
