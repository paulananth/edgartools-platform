Type: grilling
Status: claimed

## Question

[Ticket 07](07-collapse-mdm-tail-to-a-single-deployed-machine.md) locked the
target architecture: 1 MDM machine (exactly `Mastering → Infer
Relationships → Publish → Publish Relationships → Reconcile`, nothing
before or after — `GoldRefresh`, renamed `FactPublishtoGold`, is explicitly
excluded and stays its own separate machine), 1 merged seed machine,
`daily_incremental`, and `load_history` — each of the latter 3 calling the
MDM machine instead of inlining its states. Ticket 07 also settled
`mdm_gold`'s fate directly (**deleted outright** — it already has no head,
so it's fully redundant with the new MDM machine) and
`bronze_seed_silver_gold`'s strict release-mode branch (**left embedded and
untouched**, no equivalent built elsewhere) — neither is part of this
ticket's remaining question.

That leaves the fate of the **remaining 4** MDM Pipeline Machines
undecided: `ownership_mdm_gold`, `silver_mdm_gold`,
`bronze_seed_silver_gold`'s **default path** (its strict path is already
settled — untouched), and `residual_holds_graph`. Each is a distinct head
(different upstream stage(s)) plus the shared tail:

| Machine | Head (before the tail) |
|---|---|
| `ownership_mdm_gold` | `ParseOwnershipBronze, MdmPersons, MdmIsInsider` |
| `silver_mdm_gold` | `SeedUniverse, SeedSilverBatches, BatchSilver, MdmSecurities` (ticket 02's Notes list `SeedUniverse, SeedSilverBatches, BatchSilver, MdmRun, MdmBackfill` for the pre-tail-helper shape — re-verify head boundary during implementation) |
| `bronze_seed_silver_gold` (default path only) | its own large bronze/seed/silver head |
| `residual_holds_graph` | `MdmSecurities, MdmPersons, MdmIsInsider, MdmHolds, MdmCompanyHolds, MdmInstitutionalHolds` — also runs on `mdm_large`, not `mdm_medium`, and already correctly skips `FactPublishtoGold`/`GoldRefresh` today (ticket 07 confirmed why: no new bronze/silver capture happens in its own run, so there's nothing new for a gold rebuild to pick up) |

Given the target architecture names only 4 total machines (plus the
untouched `FactPublishtoGold`), does each of these 4 remaining heads become
its own standalone deployed machine (4 more machines, each just its head +
a call to the 1 MDM machine — total 8 machines: 1 MDM + 1 seed +
`daily_incremental` + `load_history` + `FactPublishtoGold` + these 4), or
do these heads get absorbed into one of the named machines (and if so,
which — does the seed machine grow to include ownership-parsing/
silver-batching/residual-holds derivation, or do these become new
execution-input variants of `daily_incremental`/`load_history`)?

## Answer

(not yet resolved)
