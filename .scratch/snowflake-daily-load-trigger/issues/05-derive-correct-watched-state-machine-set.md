# Derive the Correct Watched State-Machine Set

Type: grilling
Status: resolved

## Question

Surfaced by the Opus design-review pass (see
[DESIGN-SUMMARY.md](../DESIGN-SUMMARY.md), finding G3), which corrects
map.md's original claim: the watched set is **not** the 7 state machines
matching `GOLD_AFFECTING_COMMANDS` — that hand-mapped a *command*-level set
onto state-machine names, and `gold-refresh` (the command) is also the
terminal ECS state in at least `gold_refresh`, `mdm_gold`,
`ownership_mdm_gold`, and `bronze_seed_silver_gold` (verified in
`infra/scripts/deploy-aws-application.sh` — each deploys a state machine
whose definition contains a `States.Array('gold-refresh', ...)` ECS state),
none of which were in the original 7. `generation_build`,
`residual_holds_graph`, and other remaining machines were not checked
either way.

This is the same failure shape CLAUDE.md's "Gold-build memory / daily_incremental
OOM" 5-whys already documents about `GOLD_AFFECTING_COMMANDS` and
`workflow_profile()`: "two independent collections with no link between
them." The EventBridge watched-ARN list this map is designing would be a
**third** such collection if built the same way — this ticket exists so
that bug doesn't get built in from the start.

Two things to decide:

1. **How should the watched set actually be derived**, so it can't silently
   rot the next time a gold-producing state machine is added?
   - **Explicit enumeration**: list the correct ARNs today (mechanically
     re-derived from "which live SFN definitions contain a `gold-refresh`
     ECS state," not from `GOLD_AFFECTING_COMMANDS`). Precise, but requires
     someone to remember to update the EventBridge pattern whenever a new
     gold-producing machine is added — the exact class of drift that
     created this bug in the first place.
   - **Prefix-match + filter in the command**: match all
     `edgartools-prod-*` state machines in the EventBridge rule, and have
     the new command itself decide (at re-check time) whether the
     triggering/watched executions are gold-affecting — e.g. by checking
     each RUNNING/terminal execution's state machine name against a
     single source of truth. Picks up new machines automatically, but
     fires re-checks (cheap no-ops per ticket 01/02's cost analysis) for
     non-gold machines too, and still needs that "single source of truth"
     defined somewhere.
   - A third option: derive the source of truth mechanically at deploy
     time (e.g. `deploy-aws-application.sh` itself greps its own generated
     definitions for `gold-refresh` states and writes the EventBridge
     pattern from that), so the two collections can't diverge because
     they're generated from the same pass. Worth considering given this
     script already generates all the state machine definitions in one
     place.
2. **Enumerate the actual full correct list** for whichever mechanism is
   chosen — the 4 additional machines found in this review were enough to
   establish the bug exists, not a verified complete list.

## Answer

**Mechanism: derive the watched set mechanically at deploy time from the
generated ASL JSON**, not a hand-maintained list and not broad
prefix-matching.

`deploy-aws-application.sh` is the sole script in this repo that creates
or updates Step Functions state machines (`grep -rl upsert_state_machine
infra/scripts/*.sh` returns only this file) — every one of the 18 state
machines it manages gets its definition written to a JSON file
(`definition_file`/`json_file "sfn-..."`) before `upsert_state_machine`
runs. That means the script can grep each definition file it *just wrote*
for a `gold-refresh` command literal inside any ECS state's `Command`
array, and derive the EventBridge rule's watched-ARN filter (or a small
manifest the trigger reads) from that — by construction it cannot diverge
from what's actually deployed, unlike a second hand-maintained list or
`GOLD_AFFECTING_COMMANDS` (a third, disconnected collection, which is
exactly how this bug was introduced). Rejected explicit enumeration for
repeating the failure mode this ticket exists to fix, and rejected
prefix-match-and-filter-at-runtime for not actually avoiding the
two-collections problem — it just moves the "what counts as gold-affecting"
source of truth into the compute instead of removing it.

**The correct list, mechanically re-derived and verified (11 state
machines, not the originally-claimed 7):**

Traced every `upsert_state_machine` call in `deploy-aws-application.sh`
(12 call sites — 1 loop over 7 single-task workflows, plus 11 individually
named machines — 18 total managed state machines) and checked each one's
generated definition for a `gold-refresh` ECS state. Two distinct
source-code shapes produce the signal:

- **(a) Command-level**: a single-ECS-task workflow whose own command is
  in `GOLD_AFFECTING_COMMANDS` — `bootstrap_full`, `targeted_resync`,
  `full_reconcile` (each builds+exports gold internally as part of that
  one task), plus `gold_refresh` itself.
- **(b) Explicit state**: a multi-stage workflow with a `gold-refresh` ECS
  state appended after other work — `load_history`, `bootstrap`
  ("recent10"), `daily_incremental` (all three via
  `write_warehouse_mdm_gold_definition`), `mdm_gold`, `ownership_mdm_gold`,
  `silver_mdm_gold`, `bronze_seed_silver_gold` (the last has both a
  regular and a `strict_gold` variant).

| Gold-affecting (watch) | Not gold-affecting (correctly excluded, verified no gold reference) |
|---|---|
| `daily_incremental` | `load_daily_form_index_for_date` |
| `load_history` | `catch_up_daily_form_index` |
| `bootstrap` | `seed_universe` |
| `bootstrap_full` | `residual_holds_graph` |
| `targeted_resync` | `generation_build` |
| `full_reconcile` | `mdm_seed_universe` |
| `silver_mdm_gold` | `mdm_utility` |
| `gold_refresh` | |
| `mdm_gold` | |
| `ownership_mdm_gold` | |
| `bronze_seed_silver_gold` | |

This exactly confirms and completes the Opus review's finding (G3) — the
original 7 were all genuinely correct, just incomplete by exactly the 4
machines the review flagged.

**Known limit, not fully closed by this ticket:** `deploy-aws-application.sh`
is confirmed to be the only *current* script managing state machines, but
the ecs-cost-sizing workstream's ticket 11 inventory counted 26 live
`edgartools-prod-*` state machines in the actual AWS account, 8 more than
this script's 18. Those 8 are most likely orphaned/decommissioned machines
this script no longer touches (the state-machine-consolidation map already
deleted at least one such orphan, `bootstrap-batched`), but that wasn't
independently re-verified here via a live `aws stepfunctions
list-state-machines` call. Whoever implements this should cross-check the
mechanically-derived list against a live listing before deploying the
EventBridge rule, to rule out a still-live-but-unmanaged gold-producing
machine outside this script's 18.
