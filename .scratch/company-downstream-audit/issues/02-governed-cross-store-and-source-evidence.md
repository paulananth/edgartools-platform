# Close current-identity and cross-store quality evidence gaps

Type: follow-up task
Status: open
Blocked by: lineage and source-binding qualification for the populated generic MDM store, and verified N-PORT holding receipts

## Goal

Close only the quality questions that the 2026-11-08 local audit could not
settle. Preserve the audit's source-of-truth rules: an identifier match alone
is not a source binding, an old MDM identity is not current authority, a
successful HTTP response is not verified publication, and Silver row presence
does not identify its Bookkeeping load. Use aggregate counts and masked or
invented examples in committed artifacts; never write record values or
identifiers.

## Checklist

- [x] Trace the active Bookkeeping source worker and refresh the current MDM store snapshot. At 20:12 ET, `mastering.merge` called `edgar_warehouse.mastering.merge.merge_file` through `edgar_warehouse.mastering.store.open_store`, writing legacy `mastering_master`; this worker does not call `edgar_warehouse.mdm.merge.MergeStage`. At 20:38 ET, the MDM CLI's separate governed `public.mdm_store_current` contained 435,836 entities and 13,442 relationships at generation 2619. The records are real and the store is populated, but available code-path evidence does not tie them to a Bookkeeping source run, batch receipt, or current source policy. Do not call this store empty or assume it is the active Bookkeeping projection.
- [x] Pin the producer and batch lineage of `public.mdm_store_current` (read-only counts, 2026-11-09 07:02 ET; Claude took this ticket over from Codex on the operator's word). The store is written through the `mdm_store` storage adapter (`mdm/assessment.py`, `mdm/prepared.py`), which is the old Merge Stage path, not `mastering.merge`. `mdm_store_batch` holds 2,619 batches, one per generation 1 to 2,619, from 327 distinct run keys and 325 scope keys (all 64-character hashes, every batch with a lease owner; 2,526 changed records). The 604,247 current rows point at 2,406 of those batches and none points at a missing batch. The run keys match no Bookkeeping run id (the schema `mdm.run` and `mdm.batch` tables are empty) and `mdm_store_run` keeps its run body as binary, so the producing source run is not readable from the database alone. Reconciled: `mastering.merge` writes `mastering_master`, the old path wrote this store, and the old path's workers were deleted with ticket 199 stage 5, so the store is a frozen historic projection, not a live one. Left open under the next part: the registered policy of those runs, which the run body would hold.
- [ ] Read the registered policy of the 327 runs from the binary run body, through the adapter's own reader, to finish the lineage.
- [ ] Compare each configured Silver source link's source key, source binding, kind, null policy, and time basis with the populated generic MDM identity after its producer and source generation are pinned; distinguish absent, unmatched, ambiguous, deferred, held, and wrong-pointer cases. The active legacy comparison across 16 link contracts is recorded in the parent audit.
- [ ] Compare each populated Silver relationship with generic MDM endpoint identities, source evidence and effective-time/file-date rules after the generic store's source lineage is pinned. The active legacy pair comparisons and observed file-date fallbacks are recorded in the parent audit.
- [ ] Reconcile N-PORT holding Silver rows to a verified Bookkeeping receipt and generation; explain waiting or failed stages from redacted error categories and complete endpoint classification before proposing a holding check. At 20:08 ET, a listing of up to 1,000 complete runs found zero completed `sec.nport.security` runs; both matching runs remained active with one `land_holding` unit pending each. The existing 5,347,869 Silver rows therefore lack a verified Bookkeeping producer/receipt. The failed-step summary identifies `merge`, but its redacted cause remains `other`.
- [ ] Resolve the recorded Company source/field-generation, international place, Form 4 issuer-edge, 13F manager-coverage, and other held-source candidates against retained evidence and the applicable time basis. The audit confirmed that `sec.ownership.security.v2` declares period-of-report effective time, but `ownership-security-sgml.yaml` does not read it and `prepare_security` omits `effective_column`; all 5,273 v2 assertions have null `effective_at`. Its contract declares only a ticker cross-reference, not `ISSUED_BY`. Keep the six differing and 1,531 absent CIK/edge comparisons as candidates until the time mapping and relationship authority are resolved.
- [ ] Route the generic current-MDM cross-store reference capability and typed-relationship read needed for unsupported predicates to their owning engineering work; keep link and relationship checks out of field-only rules.
- [x] Establish whether current configuration and retained coverage represent private-equity records. The audit found no separate PE kind or active private-fund mastering path, so there is no current PE cohort or quality denominator; details and limits are recorded in the parent audit. Do not infer PE from names or unrelated classifications.
- [x] Decide whether this audit supports new row-local checks. Existing predicates are already covered by Dataset Contract validation or configured Silver checks; unsupported pointer and relationship predicates require cross-store capabilities. No new check is justified by the measured evidence, and none was activated.
- [x] Publish refreshed coverage, confirmed findings, candidates, check measurements, and remaining evidence gaps in the parent audit. The parent audit remains in progress because the populated generic MDM source lineage and N-PORT receipt are not yet verified; the limitations and next evidence are recorded here.
- [x] Learning → skill: extended `skills/data-quality/SKILL.md` → **Existing master projections** to compare effective time, source claim, operation, winner/projected value, and clear state in one repeatable-read, key-paged audit; genericity check (99 passed) and skill validator passed (2026-11-08 20:12 ET).

## Evidence carried forward

The parent audit at
[`01-company-field-and-relationship-quality-checks.md`](01-company-field-and-relationship-quality-checks.md)
records the dated per-store measurements. The 19:53 ET read found zero rows in
schema-native `mdm.master_entity`, `mdm.current_record`, and
`mdm.relationship_version`. At 20:38 ET, a repeatable-read query through the
MDM CLI's governed adapter found 435,836 entities and 13,442 relationships in
`public.mdm_store_current`, at global generation 2619, plus 154,969 reviews.
Entity counts were Company 8,361, fund structure 12,937, Person 31,097, and
Security 383,441. Relationship counts were 12,937 `IS_SUBFUND_OF` and 505
`ISSUED_BY`. Their source-run, batch, and policy provenance remain unidentified;
this is not proof that Bookkeeping's active mastering worker wrote them.

At 20:38 ET, two `sec.nport.security` runs remained `running` and none of up
to 1,000 complete runs matched that pipeline. Both had one pending
`land_holding` item. One had waiting `holding`, `holding_rows`, and `record`
items plus three pending deliveries; the other had `merge` waiting,
`processed` pending, and 14 pending deliveries. No run was resumed or changed.
The 5,347,869 Silver holding rows measured at 17:54 ET remain unattributed to a
verified landing receipt and source generation. The next run-state check is no
earlier than 21:08 ET.

The 19:53 ET repeatable-read field audit traversed 461,455 legacy master rows
and compared all 4,036,273 populated accepted field projections to their
retained winning assertions. It found zero source, record-key, time, claim,
operation, winner-value, projection-value, or clear-state mismatches. This
establishes legacy field provenance and value agreement; it does not replace
generic-store identity or relationship checks, or prove that today's
configured authority selected the right business value.

The data-quality engine currently supports row-local predicates only. The
parent audit defines the exact minimum cross-store link and typed-edge
predicates; this ticket is the evidence and implementation handoff, not an
authorization to add engine code or activate rules.
