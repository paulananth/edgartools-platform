# 03 — Confirm `mdm run --entity-type company` / `sync-graph --entity-type company` behavior

Type: research
Status: resolved

## Question

`edgar_warehouse/mdm/cli.py` already exposes `--entity-type` on both `mdm run`
(choices: company, adviser, security, person, fund, all) and `mdm sync-graph`.
This pipeline's destination depends on these correctly resolving/syncing
**only** Company entities with no relationship-derivation side effects or
errors when ownership/ADV silver data doesn't exist yet for that CIK scope
(the exact scenario here: a company-only pass that runs *before* any
ownership or ADV data has been captured).

Confirm, by reading `edgar_warehouse/mdm/pipeline.py` and
`edgar_warehouse/mdm/resolvers/company.py`:

1. Does `mdm run --entity-type company` skip all relationship-derivation
   logic (`_derive_is_insider`, `_derive_institutional_holds`, etc.) entirely,
   or does it still attempt some relationship work that would silently
   no-op, warn, or error against missing ownership/ADV silver tables?
2. Does `mdm sync-graph --entity-type company` sync only Company nodes (no
   edges), or does it also attempt to sync edges that don't yet exist for a
   company-only pass?
3. Is there a coverage/completeness check (e.g., a Relationship Coverage
   Record-style classification per CONTEXT.md) that would need a
   company-entity equivalent, or does `--entity-type company` already report
   clean success/failure independent of relationship state?

## Blocked by

None — can start immediately.

## Findings

Full research: `.scratch/company-master-pipeline/research/03-mdm-entity-type-scoping-behavior.md`

`--entity-type company` is safe to use as-is for company-only resolution/graph-sync ahead of ownership/ADV. `mdm run --entity-type company` calls only `MDMPipeline.run_companies()` (never `derive_relationships`/any `_derive_*`), its silver preflight requires only `sec_company` to exist, and `CompanyResolver` never joins ownership/ADV silver tables. `mdm sync-graph --entity-type company` never opens a silver reader at all — it reads MDM's own (empty, at this stage) Snowflake relationship tables, so the edge-sync half of the same script inserts zero rows without erroring; note this "zero edges" outcome is a byproduct of current MDM state, not a guaranteed contract, since `--entity-type` filters only the node query and `--relationship-type` (not `--entity-type`) controls the edge query. No code modification is required to unblock this ticket's use case; a generation-scoped three-state Company Coverage Record (symmetric with the Relationship Coverage Record) doesn't exist but isn't needed — `mdm coverage-report` and `mdm verify-graph`'s `node_parity_company` check already give a relationship-state-independent pass/fail signal.
