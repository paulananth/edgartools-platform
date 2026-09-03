Type: task
Status: open

## Question

Implement a real incremental/diff filter for each relationship type in
`MDMPipeline.derive_relationships()` (`edgar_warehouse/mdm/pipeline.py`),
so each `_derive_*` method only reads source rows that are new or changed
since that type's last successful derivation, instead of scanning the full
source table every invocation.

Confirmed evidence (this session, both read directly in code, not
measured against live prod):

- `_derive_institutional_holds` (`pipeline.py:3017`) joins the full
  `sec_thirteenf_holding` table every run, batched by CIK range only to
  avoid OOM — not to skip already-processed rows. `target_per_type` bounds
  how many new relationship rows get **written**, not what gets **read**.
  Its own docstring: "bounded today only because this type currently has
  0 active rows in prod, not because the code path is actually safe at
  scale." Source table is 6.8M rows
  (`EDGARTOOLS_PROD.EDGARTOOLS_SOURCE.SEC_THIRTEENF_HOLDING`).
- `_derive_holds` (`pipeline.py:1180`) has the identical shape against
  `sec_ownership_non_derivative_txn`/`sec_ownership_derivative_txn`:
  `self.silver.fetch(self._bounded_relationship_sql(sql, remaining, existing))`
  bounds on write count only.
- The other 9 `_derive_*` methods (`_derive_is_insider`,
  `_derive_company_holds`, `_derive_is_entity_of`,
  `_derive_has_parent_company`, `_derive_is_person_of`,
  `_derive_manages_fund`/`_derive_manages_fund_batch`, `_derive_issued_by`,
  `_derive_employed_by`, `_derive_audited_by`) were not individually
  re-verified this session but share the same `_bounded_relationship_sql`
  pattern — confirm each rather than assuming before scoping the fix.

Why this matters now: this gap is what blocked folding `IS_INSIDER`/
`HOLDS`/`COMPANY_HOLDS`/`INSTITUTIONAL_HOLDS` derivation into the new
single MDM machine's automatic tail
([state-machine-consolidation ticket 08](../../state-machine-consolidation/issues/08-decide-fate-of-mdm-pipeline-machine-heads.md)) —
baking a full-table-scan operation into something scheduled as "daily
incremental" would be architecturally inconsistent with the rest of the
platform (see CLAUDE.md's "SEC data idempotency" and "Daily
accession-expansion" sections for the precedent this should follow:
`sec_daily_index_checkpoint`-style high-water-marks, not re-scanning
source state each run).

## Answer

(not yet resolved)
