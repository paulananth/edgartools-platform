Type: research
Status: open

## Question

`GraphSyncEngine.ensure_relationship` is supposed to merge a new insert
into an existing "current" version when properties + validity window are
byte-identical (`_merge_source_evidence`, returns `created=False`, no new
row). Live evidence (this map's charting session, see map.md's Notes)
shows this merge is failing for `MANAGES_FUND`: sampled `relationship_id`s
each have 2-4 rows with byte-identical properties/dates/source_system/
source_accession, all sharing one transaction's `created_at`, while the
corresponding silver source (`sec_adv_private_fund`) has exactly 1 row for
the same filing/fund. So `_derive_manages_fund_batch`'s row loop is
somehow calling `ensure_relationship` more than once for the same
(adviser, fund) pair with the same evidence, within what looks like one
run — and each call inserts a fresh row instead of the 2nd+ merging into
the 1st.

Investigate:

1. Trace `_derive_manages_fund`'s CRD-batching (`_MANAGES_FUND_CRD_BATCH_SIZE`,
   `sorted_crds`/`batch_crds`) — can the same CRD end up processed by more
   than one batch within a single call (an off-by-one in batch slicing, a
   duplicate entry in `adviser_ids_by_crd`, or the resumable-cursor logic
   from `mdm-relationship-versioning-gap` Ticket 01 re-processing a range
   it already covered)?
2. Trace `GraphSyncEngine.prime_relationship_type`/`unprime_relationship_type`'s
   lifecycle across one CRD-batch — does priming genuinely load the
   already-primed-type's cache from the DB fresh per batch, and could
   `_current_by_relationship_id` fail to contain a row this exact session
   already inserted earlier in the same batch (e.g., a race between
   `defer_flush=True` and the primed-cache read path in
   `ensure_relationship`)?
3. Check whether `source_rows` (the `sec_adv_private_fund` query result,
   filtered to `active_accessions`) can itself contain the same logical
   row more than once — even though this session's one sample showed
   exactly 1 silver row, confirm this holds generally (e.g., could a JOIN
   or the schedule_section grouping produce a fan-out for some fund
   shapes not covered by the single sample checked so far)?
4. Check whether `derive_relationships()`'s outer dispatch could call
   `_derive_manages_fund` more than once within what looks like "one run"
   (e.g., both an ordinary incremental pass and a reconciliation pass in
   the same execution, or a retry after a transient failure that
   re-attempts the same batch without the first attempt's inserts having
   rolled back).
5. Once the mechanism is found, check live whether any of the other 5
   relationship types affected by `mdm-relationship-versioning-gap`
   (INSTITUTIONAL_HOLDS/COMPANY_HOLDS/EMPLOYED_BY/IS_INSIDER/HOLDS) show
   the same clean-duplicate signature for any of their own duplicated
   `relationship_id`s, or whether this genuinely looks isolated to
   MANAGES_FUND's own batching code.

Live evidence already gathered (reusable, don't re-derive):
[map.md](../map.md)'s Notes section — empty-properties fallback ruled
out (17 rows only), full properties dict confirmed live in the real code
path since commit `869003da`, 5 sample `relationship_id`s' full row
dumps showing byte-identical duplicates, and the one cross-checked silver
source row confirming no source-side duplication.

Read-only investigation — no code changes. Use `/research` per this
map's workflow; MDM Postgres access via `edgartools-prod/mdm/postgres_dsn`
(pipe the secret straight into a script, never print the DSN).

## Answer

_(pending)_
