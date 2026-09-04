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
- **1 MDM machine**: exactly `Mastering → Infer Relationships → Publish →
  Publish Relationships → Reconcile`. Nothing before it, nothing after —
  `GoldRefresh` is explicitly **not** part of this machine (see "GoldRefresh
  is not Publish" below). Takes one small, optional-fields execution-input
  contract (`generation_id`, `limit_per_type`, `skip_native_app`, plus
  whatever else surfaces from `daily_incremental`/`load_history`/ticket 08's
  heads during implementation) — **the same contract shape for every
  caller**, not a bespoke shape per caller. Reached via a real nested Step
  Functions execution (`states:startExecution.sync2` or equivalent), not
  code-level sharing at generation time.
- **`GoldRefresh` renamed to `FactPublishtoGold`**, stays its own separate
  deployed machine (unaffected in count — it already exists today as the
  standalone `gold_refresh` machine, just renamed), not folded into the MDM
  machine. Every caller decides on its own whether to chain into it
  afterward. Confirmed via code reading
  (`edgar_warehouse/mdm/export.py`'s `DOMAIN_TO_TABLE`, `warehouse_orchestrator.py`'s
  `gold-refresh` handler) that `Publish` and `FactPublishtoGold` are
  genuinely different jobs, not two names for the same step: `Publish`
  (`mdm export`) writes MDM's own Postgres entities directly into exactly 5
  gold tables (`MDM_COMPANY_ENTITY`, `MDM_ADVISER`, `MDM_PERSON`,
  `MDM_SECURITY`, `MDM_FUND`); `FactPublishtoGold` (`gold-refresh`) rebuilds
  the other ~18 dbt-managed gold tables (`company`, `filing_activity`,
  `ownership_holdings`, `financial_facts`, etc.), almost all derived from the
  **silver** layer, independent of MDM entirely. This is exactly why
  `residual_holds_graph` already skips it today — no new bronze/silver
  capture happens in that machine's own run, so there's nothing new for a
  gold rebuild to pick up.
- **1 seed machine**: merges `seed_universe` + `mdm_seed_universe`. No
  pipeline calls it — it exists purely as an ad-hoc operator tool (scoped
  re-seed/backfill/test), matching the real, still-used
  `--tracking-status`/`--limit` override capability ticket 04 originally
  found value in. Chains `seed-universe` (CIK/ticker discovery) → `mdm
  seed-universe` (MDM enrollment) in sequence — confirmed via code reading
  that `mdm seed-universe --source silver` (the default) reads the
  tracking-status rows warehouse `seed-universe` already wrote, not an
  independent fetch, so this is a genuine 2-stage pipeline, not two
  alternatives. Mirrors what `load_history`'s own inline `SeedUniverse →
  MdmSeedUniverse` states already do — `load_history`'s inline seeding
  stays untouched by this change, since it isn't duplicating anything (one
  caller of two tasks was never the problem this map is solving).
- `daily_incremental`: keeps its own head (SEC daily-index-driven bronze/
  silver capture), calls the MDM machine instead of inlining the tail
  (removes 1 of the 2 inline copies found in `write_warehouse_mdm_gold_definition`
  — the other copy is confirmed **dead code** left over from the retired
  `bootstrap` caller, this function's `if workflow_name == "daily_incremental"`
  branch vs. its `else` branch; falls away naturally once this function is
  rewritten to call the new MDM machine, no separate cleanup ticket needed).
- `load_history`: keeps its own head (windowed MaxConcurrency=1 bronze/
  silver bootstrap), calls the MDM machine instead of inlining the tail.
- **`mdm_gold` deleted outright.** It already has no head today — it's
  literally just the tail with nothing in front — so it's a 100% redundant
  duplicate of the new MDM machine the moment that machine exists. Anyone
  who wants "just run the MDM tail standalone" runs the new machine
  directly; zero capability lost.
- **`bronze_seed_silver_gold`'s separate strict release-mode branch**
  (`StrictMdmExport → StrictMdmSync → StrictMdmSyncIdempotency →
  StrictMdmVerifyCandidate → StrictMdmVerify → StrictGoldRefresh`, no
  equivalent anywhere else) stays embedded and bespoke, untouched by this
  consolidation. Folding it into the shared MDM machine would just recreate
  the "6 distinct shapes" problem ticket 02 already found, inside the one
  machine meant to eliminate exactly that.

**Not resolved here — genuinely open, see [ticket 08](08-decide-fate-of-mdm-pipeline-machine-heads.md):**
what happens to the remaining 4 MDM Pipeline Machines
(`ownership_mdm_gold`, `silver_mdm_gold`, `bronze_seed_silver_gold`'s
default path, `residual_holds_graph`) as **standalone deployed machines**
(`mdm_gold` is settled above — deleted; not part of ticket 08's remaining
question). Each combines a distinct head (e.g. `ownership_mdm_gold`'s
`ParseOwnershipBronze, MdmPersons, MdmIsInsider`; `silver_mdm_gold`'s
`SeedUniverse, SeedSilverBatches, BatchSilver`) with the shared tail. The
target architecture above only names 4 machines total (1 MDM + 1 seed +
daily_incremental + load_history) plus the untouched `FactPublishtoGold` —
it does not say whether these 4 remaining machines' heads get folded into
one of the named machines, become their own thin "head + call MDM machine"
wrappers, or something else.
