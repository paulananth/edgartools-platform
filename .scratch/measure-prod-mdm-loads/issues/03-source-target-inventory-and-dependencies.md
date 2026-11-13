# What is the exact source/target inventory and dependency order for this checkout?

Type: research
Status: resolved
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

## Answer

Evidence: [03-source-target-inventory-and-dependencies.md](../evidence/03-source-target-inventory-and-dependencies.md)
(branch `codex/wayfinder-measure-prod-loads-20261113`, commit `7758ed5b`).

- **The checkout configures 19 source/target names across 13 sources**, not 16. Excluding the two
  capture targets leaves **17 measured names**: `sec.nport.security/mastering_other_keys` is the
  extra one — a real configured target, with its own manifest tree and runs, that is neither a
  capture target nor a sequence entry. The report-shape ticket must rule on it.
- **All 13 sequence sources declare `requires: []`.** No source ordering in
  `rules/source-sequence.yaml` is a hard dependency; `after` is a preference by the file's own
  header.
- **The three ordered targets are prose preferences with partial Rules support.** Only
  `gleif/subfund-pairs` has a Rules-derived wait (it is read inside a pass of its consumer).
  `iapd.adv/custodians` → `iapd.adv/mastering` and `sec.ownership/security_symbols` after OpenFIGI
  have no declared cross-target dependency. The report must state the basis it used for ordering.
- **The entity-kind map has two authorities that differ by exactly one contract.**
  `rules entity-types` — the plan's named authority — was run in this checkout and returns **14
  contracts**: 7 company, 4 security, 2 person, 1 fund_structure. The merge kinds'
  `defaults.sources` lists **13**: 6 company, 4 security, 2 person, 1 fund_structure. The single
  difference is `gleif.reporting_exceptions.v1`, whose Dataset Contract states `company` but which
  maps no field and no rule in the company kind. The entity-model ticket settles which reading the
  report uses.
- Step names per target, and each target's mastered dataset → table, are tabulated in the evidence
  file.
