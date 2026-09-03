Type: grilling
Status: open

## Question

[Ticket 07](07-collapse-mdm-tail-to-a-single-deployed-machine.md) locked the
target architecture as exactly 4 deployed machines: 1 MDM machine (the pure
`Mastering → ... → GoldRefresh` tail, nothing else), 1 merged seed machine,
`daily_incremental`, and `load_history` — each of the latter 3 calling the
MDM machine instead of inlining its states.

That leaves the fate of today's 5 MDM Pipeline Machines undecided:
`mdm_gold`, `ownership_mdm_gold`, `silver_mdm_gold`,
`bronze_seed_silver_gold`, `residual_holds_graph`. Each is a distinct head
(different upstream stage(s)) plus the shared tail:

| Machine | Head (before the tail) |
|---|---|
| `mdm_gold` | none currently — starts straight at Mastering |
| `ownership_mdm_gold` | `ParseOwnershipBronze, MdmPersons, MdmIsInsider` |
| `silver_mdm_gold` | `SeedUniverse, SeedSilverBatches, BatchSilver, MdmSecurities` (ticket 02's Notes list `SeedUniverse, SeedSilverBatches, BatchSilver, MdmRun, MdmBackfill` for the pre-tail-helper shape — re-verify head boundary during implementation) |
| `bronze_seed_silver_gold` | its own large bronze/seed/silver head, plus a separate "strict" release-mode branch with no equivalent anywhere else |
| `residual_holds_graph` | `MdmSecurities, MdmPersons, MdmIsInsider, MdmHolds, MdmCompanyHolds, MdmInstitutionalHolds` — also runs on `mdm_large`, not `mdm_medium`, and has no `GoldRefresh` at all |

Given the target architecture names only 4 total machines, does each of
these 5 heads become its own standalone deployed machine (5 more machines,
each just its head + a call to the 1 MDM machine — total 9 machines:
1 MDM + 1 seed + daily_incremental + load_history + these 5), or do these
heads get absorbed into one of the 4 named machines (and if so, which —
does the seed machine grow to include ownership-parsing/silver-batching/
residual-holds derivation, or do these become new execution-input variants
of `daily_incremental`/`load_history`)? `mdm_gold` already has no head at
all — is it just deleted outright now that the pure MDM machine subsumes
it entirely?

Also worth surfacing before this is answered: `bronze_seed_silver_gold`'s
strict release-mode branch has no equivalent anywhere else in the system —
whatever this ticket decides needs to account for that branch specifically,
not just the default-path head.

## Answer

(not yet resolved)
