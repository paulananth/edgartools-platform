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

(none yet)

## Not yet specified

- Whether any of the 9 zero-execution machines are provisioned-for-a-
  future-use-not-yet-triggered (e.g. `bootstrap_full`/`full_reconcile`/
  the two `daily_form_index` machines might be intentional disaster-
  recovery/backfill tooling nobody has needed yet) versus genuinely
  obsolete leftovers -- ticket 01 investigates before any deletion
  decision is made.
- The actual consolidation mechanism for the composed-machine family
  (`mdm_gold`/`ownership_mdm_gold`/`silver_mdm_gold`/
  `bronze_seed_silver_gold`/`residual_holds_graph`): shared Python helper
  functions generating still-5-separate deployed machines (lower risk,
  fixes the code-duplication half of the problem but not the count) vs.
  collapsing to fewer actually-deployed machines with a parameterized
  entry stage (bigger change: touches how operators/EventBridge/other
  automation currently target these ARNs by name) -- ticket 02 grills this.
- Whether the 8 standalone single-stage MDM machines (`mdm_run`,
  `mdm_backfill_relationships`, `mdm_sync_graph`, `mdm_verify_graph`,
  `mdm_counts`, `generation_build`, `mdm_migrate`,
  `mdm_check_connectivity`) should keep existing independently once the
  composed machines are consolidated -- they may be legitimate operator
  debugging/rerun tools (run just one stage without the rest), a genuine
  redundancy with the composed machines, or both depending on the stage.
  Not yet specifiable as a sharp ticket until ticket 02 resolves the
  consolidation mechanism.
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
