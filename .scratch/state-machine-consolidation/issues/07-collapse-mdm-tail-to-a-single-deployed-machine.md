Type: grilling
Status: resolved

## Question

Reopens [ticket 02](02-decide-consolidation-mechanism-for-shared-mdm-tail.md)'s
locked "5 MDM Pipeline Machines stay separate, only the sequencing skeleton is
shared via `wire_mdm_tail()`" conclusion, and [ticket 04](04-decide-mdm-seed-machines-fate.md)'s
locked "keep `seed_universe` and `mdm_seed_universe` separate" conclusion.

Fresh evidence found while scoping this reopening (2026-09-03): the
`Mastering → Infer Relationships → Publish → Publish Relationships →
Reconcile → GoldRefresh` tail is **not only** hand-duplicated across the 5
MDM Pipeline Machines ticket 02 already covers — `write_load_history_definition`
(`load_history`) and `write_warehouse_mdm_gold_definition` (`daily_incremental`,
duplicated **twice** inside its own single function) each independently
hand-roll the identical 6-state dict, entirely outside `wire_mdm_tail()`.
Confirmed via direct grep of `infra/scripts/deploy-aws-application.sh` — not
inference. This is the exact drift risk ticket 02's own evidence
(`git log -S"MdmVerify"`, commit `3aa92fe9`) warned about, recurring in
places ticket 02 never touched.

User's request: "one step function for all MDM work; there should be 1 seed
and 1 daily work or history."

## Grilling

Three questions put to the user (AskUserQuestion) to pin the destination:

1. Does "all MDM work" include the MDM-tail portions embedded inside
   `daily_incremental`/`load_history`, or just the 5 already-MDM-only
   machines?
2. Does "1 seed" mean merging `seed_universe` (warehouse-level) with
   `mdm_seed_universe` (MDM-level, kept separate by ticket 04) into one?
3. Does "1 daily work or history" mean literally merging `daily_incremental`
   and `load_history` into one machine, or keeping them separate but sharing
   the MDM tail?

## Answer

1. **The MDM machine is the tail and nothing else.** User: "need to
   understand what is before [the tail] — there should be nothing else."
   The single deployed MDM machine contains exactly `Mastering → Infer
   Relationships → Publish → Publish Relationships → Reconcile →
   GoldRefresh` — no head stage of any kind lives inside it. Every current
   caller of any part of this tail invokes this one machine instead of
   hand-rolling the states.
2. **Seed collapses to 1.** `seed_universe` and `mdm_seed_universe` merge
   into a single seed machine — this **reverses ticket 04's locked "keep
   both separate" call**. The merged seed machine calls the MDM machine
   after seeding ("seed should call this").
3. **`daily_incremental` and `load_history` stay 2 machines**, not 1 — user
   explicitly chose "keep 2 machines, just share the MDM tail" over a full
   merge. Both stop hand-duplicating the tail and instead call the one MDM
   machine as their final step ("daily and history should call this").

**This revises, not deletes, ticket 02 and ticket 04.** Ticket 02's
sequencing-skeleton-sharing (`wire_mdm_tail()`) was a real, already-shipped
improvement but is superseded here: the destination is now a genuinely
separate **deployed** MDM machine invoked via nested Step Functions
execution (`states:startExecution.sync` or equivalent), not just
code-level sharing at generation time. Ticket 04's "keep both seed machines
separate" call is fully reversed by point 2 above.

**Target architecture, once implemented:**
- 1 MDM machine: `Mastering → Infer Relationships → Publish → Publish
  Relationships → Reconcile → GoldRefresh`, callable by any head.
- 1 seed machine: merges `seed_universe` + `mdm_seed_universe`, calls the
  MDM machine after seeding.
- `daily_incremental`: keeps its own head (SEC daily-index-driven bronze/
  silver capture), calls the MDM machine instead of inlining the tail
  (removes 1 of the 2 inline copies found in `write_warehouse_mdm_gold_definition`
  — the other copy's exact purpose, e.g. a second branch within the same
  machine vs. dead leftover code, is unconfirmed and worth checking during
  implementation).
- `load_history`: keeps its own head (windowed MaxConcurrency=1 bronze/
  silver bootstrap), calls the MDM machine instead of inlining the tail.

**Not resolved here — genuinely open, see [ticket 08](08-decide-fate-of-mdm-pipeline-machine-heads.md):**
what happens to the 5 current MDM Pipeline Machines
(`mdm_gold`, `ownership_mdm_gold`, `silver_mdm_gold`,
`bronze_seed_silver_gold`, `residual_holds_graph`) as **standalone deployed
machines**. Each combines a distinct head (e.g. `ownership_mdm_gold`'s
`ParseOwnershipBronze, MdmPersons, MdmIsInsider`; `silver_mdm_gold`'s
`SeedUniverse, SeedSilverBatches, BatchSilver`) with the shared tail. The
target architecture above only names 4 machines total (1 MDM + 1 seed +
daily_incremental + load_history) — it does not say whether these 5
machines' heads get folded into one of those 4, become their own thin
"head + call MDM machine" wrappers, or something else.
