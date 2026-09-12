Type: research
Status: resolved

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

**Decisive finding: this is a one-time historical event, not an ongoing write-time bug.** All 140,907 duplicate-active-row groups' active rows share the exact same `created_at` instant — `min(max_created) == max(max_created) == 2026-08-19 15:50:30.731351 UTC` across the entire backlog. Zero of the 140,907 groups have an active duplicate row created after the 2026-08-21 18:06 ET CRD-batching refactor (`869003da`, "fix(mdm): batch MANAGES_FUND priming by adviser CRD instead of loading the whole type"), despite 4,116 new MANAGES_FUND rows being written in the 3+ weeks since (up to 2026-09-08).

(An earlier pass of this same check wrongly reported 3,960 "post-fix" groups — a bug in my own diagnostic query: the outer `max(created_at)` join wasn't re-filtered by `is_active`/`quarantined`/`superseded_by_version_id`, so it picked up a *later, separately-quarantined* conflict attempt on the same `relationship_id` and mistook it for a later *active* duplicate. Corrected query: 0 groups have any active duplicate row after the fix.)

**Contrast with the other 5 types `mdm-relationship-versioning-gap` already covers** (INSTITUTIONAL_HOLDS, COMPANY_HOLDS, EMPLOYED_BY, IS_INSIDER, HOLDS): all five show duplicate-group `created_at` spread across many distinct days through 2026-09-08 — ongoing accumulation, consistent with that map's already-diagnosed (and largely resolved) chain-versioning/quarantine gap. MANAGES_FUND's 100%-single-instant signature is genuinely distinct, confirming this map's original Q3 hypothesis: this is isolated to MANAGES_FUND, not a shared `ensure_relationship`-wide defect, and not the same bug class the other map already fixed.

**Exact mechanism inside the pre-`869003da` code not conclusively pinned down** (the honest gap in this investigation): the old code (`git show 869003da~1`) is structurally almost identical to today's — same `ensure_relationship` call, same properties construction, same identical-evidence merge check it should have hit. What's known: the old `_derive_manages_fund` primed the *whole* `MANAGES_FUND` type unconditionally in one `prime_relationship_type` call and had no per-batch commits (per its own now-superseded design, replaced specifically for an unrelated OOM reason), so its entire single-pass run for the whole universe very plausibly executed inside one long-lived transaction — explaining why every one of that day's ~567K inserted rows (not just the duplicated ones) shares one Postgres `NOW()`-transaction-time value, without requiring the 4 duplicate inserts for one `relationship_id` to have happened back-to-back. Traced batch-slicing (no CRD overlap possible — `sorted_crds` built from a dict's unique keys, sliced via non-overlapping `range()`), the outer dispatcher's self-priming guard (`_SELF_PRIMING_RELATIONSHIP_TYPES` already includes MANAGES_FUND and correctly prevents the outer uniform-prime collision this session initially suspected), and the silver source itself (confirmed exactly 1 row for the sampled filing/fund, both via a narrow query and a broader `GROUP BY ALL` with `COUNT(*)`) — none of these explain it. The proximate mechanism inside the one-time, now-replaced code path remains unconfirmed; further root-causing it would mean debugging dead code with no remaining reproduction path, which is not a good use of further investigation given the practical answer below doesn't depend on it.

**Practical conclusion, load-bearing for Ticket 02/03:** since the write-time bug appears to already be gone (by accident, as a side effect of the OOM-driven CRD-batching refactor) and has not recurred in 3+ weeks of continued production writes, **Ticket 02/03 (decide + implement a write-time fix) may not need new code at all** — only confirmation that the current code path genuinely doesn't reproduce this, which this ticket's live evidence already provides circumstantially (0 new duplicates in 3+ weeks / 4,116 new rows). This reshapes the map: Ticket 02 should decide whether that circumstantial evidence is sufficient to skip a code fix and go straight to Ticket 04's backlog cleanup (with Ticket 03 becoming a no-op or a much smaller confirmation/monitoring task), or whether the user wants a positive reproduction/regression test before accepting "already fixed." That's a decision for Ticket 02 (grilling, needs the user), not resolved here.
