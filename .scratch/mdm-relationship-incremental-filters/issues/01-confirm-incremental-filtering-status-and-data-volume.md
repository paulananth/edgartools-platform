Type: research
Status: open

**Spawned by:** the map's own charting session — 2 of 11 `_derive_*` types were confirmed live in code (`_derive_institutional_holds`, `_derive_holds`), the other 9 were presumed to share the same `_bounded_relationship_sql` write-count-bound-not-recency shape but never individually checked.

## Question

For every one of `MDMPipeline.derive_relationships()`'s 11 `_derive_*` methods (`_derive_is_insider`, `_derive_holds`, `_derive_company_holds`, `_derive_institutional_holds`, `_derive_is_entity_of`, `_derive_has_parent_company`, `_derive_is_person_of`, `_derive_manages_fund`(`_batch`), `_derive_issued_by`, `_derive_employed_by`, `_derive_audited_by`):

1. **Confirm the actual filtering shape in code** — does it genuinely scan the full source table bounded only by write-count (`_bounded_relationship_sql`'s `remaining`/`existing` pattern), or does at least one of the "presumed same shape" 9 already have some real incremental/diff mechanism this map's charting session missed? Read each method directly; don't extrapolate from the 2 already confirmed.
2. **Confirm real data-volume risk per type** — for each type's source table(s), get the live row count (Snowflake `EDGARTOOLS_PROD.EDGARTOOLS_SOURCE`/`EDGARTOOLS_SILVER`, whichever this method's `self.silver.fetch(...)` call actually reads) and, where available, growth rate. `INSTITUTIONAL_HOLDS` is already known at 6.8M rows (`sec_thirteenf_holding`); this ticket should produce the equivalent number (or a credible estimate) for the other 10.
3. **Note what source-table timestamp/versioning columns exist per type** — this doesn't need to design the checkpoint mechanism (that's the next ticket), just inventory what's available (an `ingested_at`-equivalent column, a natural accession-number ordering, nothing usable, etc.) per source table, since the next ticket's mechanism choice depends on this.

Read-only investigation — no code changes, no decisions. Use `/research` per this map's own workflow.

## Answer

_(pending)_
