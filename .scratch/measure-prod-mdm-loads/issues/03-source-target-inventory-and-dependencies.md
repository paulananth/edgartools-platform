# What is the exact source/target inventory and dependency order for this checkout?

Type: research
Status: open
Blocked by:

## Question

The plan asserts 13 sequence sources and 16 configured source/target names and names three ordered
targets outside the sequence (`gleif/subfund-pairs`, `iapd.adv/custodians`,
`sec.ownership/security_symbols`). The checkout may have moved. What is the inventory, and what are
the real dependencies?

Re-read, in this checkout:

1. `rules/source-sequence.yaml` — every source entry, its target, and its `requires`/`after`.
2. `rules/` source and target declarations — every configured source/target name, the target's
   declared dataset codes and entity types, and any declared target-to-target ordering.
3. `scripts/run_inputs.py <source>` — the declared facts/files each source needs.
4. The `edgar_warehouse/rules/shape.py` step expansion — the exact step names each target produces
   (needed because the report keeps one interval per exact Bookkeeping step name).

Report:

- The complete list of configured source/target names, with the count.
- Which are sequence sources and which are additional ordered targets, and the evidence for each
  ordering (a declared `requires`, or only a preferred `after`).
- The exact step names per target.
- The declared dataset codes and entity types per target.

Write the findings to `.scratch/measure-prod-mdm-loads/evidence/03-source-target-inventory-and-dependencies.md`.
No source row values, record identifiers or credentials.
