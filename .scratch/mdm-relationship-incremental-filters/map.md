# MDM relationship-derivation incremental filters

## Destination

Every `_derive_*` method in `MDMPipeline.derive_relationships()`
(`edgar_warehouse/mdm/pipeline.py`) reads its source table with a real
incremental/diff filter — only rows new or changed since that
relationship type's last successful derivation — instead of the current
full-source-table scan bounded only by how many new relationship rows to
write. Done when `mdm derive-relationships`/`mdm infer-relationships` can
be folded into a genuinely daily-scoped pipeline (e.g. the single MDM
machine's automatic tail, state-machine-consolidation map) without paying
a full-table-scan cost on every run.

## Notes

- Domain: `edgar_warehouse/mdm/pipeline.py`, `MDMPipeline.derive_relationships`
  and its 11 `_derive_*` methods.
- Discovered while grilling
  [state-machine-consolidation ticket 08](../state-machine-consolidation/issues/08-decide-fate-of-mdm-pipeline-machine-heads.md):
  the user asked whether `IS_INSIDER`/`HOLDS`/`COMPANY_HOLDS`/
  `INSTITUTIONAL_HOLDS` derivation should fold into the new single MDM
  machine's automatic tail (would then run on every `daily_incremental`/
  `load_history` execution). Investigation found the gap this map exists
  to close, and ticket 08 stayed with the conservative answer (leave all 4
  relationship types operator-triggered-only) specifically because of it —
  see that ticket's Answer once resolved for the full reasoning.
- Confirmed live in code (not measured in prod) for 2 of 11 types:
  - `_derive_institutional_holds` (`pipeline.py:3017`): joins the full
    `sec_thirteenf_holding` table (CIK-range batched only for OOM
    avoidance, not incrementality). Own docstring: "bounded today only
    because this type currently has 0 active rows in prod, not because
    the code path is actually safe at scale." Source table has 6.8M rows
    (`EDGARTOOLS_PROD.EDGARTOOLS_SOURCE.SEC_THIRTEENF_HOLDING`, CLAUDE.md).
  - `_derive_holds` (`pipeline.py:1180`): same shape against
    `sec_ownership_non_derivative_txn`/`sec_ownership_derivative_txn` —
    `self.silver.fetch(self._bounded_relationship_sql(sql, remaining, existing))`,
    where the bound is on write count (`remaining`/`existing` = current
    active-relationship count vs. `target_per_type`), not on which source
    rows are new.
  - The other 9 (`_derive_is_insider`, `_derive_company_holds`,
    `_derive_is_entity_of`, `_derive_has_parent_company`,
    `_derive_is_person_of`, `_derive_manages_fund`(`_batch`),
    `_derive_issued_by`, `_derive_employed_by`, `_derive_audited_by`) were
    not individually re-checked this session — presumed same shape given
    they share `_bounded_relationship_sql`'s pattern, but confirm each
    before assuming.
- Existing incremental/diff precedent elsewhere in the platform worth
  modeling this on: `sec_daily_index_checkpoint` (daily-index-driven
  discovery, CLAUDE.md's "SEC data idempotency" section) and the
  accession-union/digest carried through `daily-incremental`'s recurring
  window (CLAUDE.md's "Daily accession-expansion 5-whys"). Both use an
  explicit checkpoint/high-water-mark rather than re-scanning source state
  each run.

## Decisions so far

(none yet)

## Not yet specified

- What the checkpoint/filter mechanism should actually be per type —
  options include an accession-number or `ingested_at` high-water-mark per
  relationship type, a dedicated checkpoint table mirroring
  `sec_daily_index_checkpoint`'s shape, or filtering by source-row
  timestamps already present on the underlying silver tables. Needs
  investigation per type since source tables differ (13F holdings vs.
  Form 3/4/5 ownership transactions vs. ADV data for MANAGES_FUND, etc.).
- Whether all 11 types need this, or only the ones with real data-volume
  risk (`INSTITUTIONAL_HOLDS` clearly; `HOLDS`/`COMPANY_HOLDS`/
  `IS_INSIDER` are much smaller-volume but not yet measured).

## Out of scope

(none yet)
