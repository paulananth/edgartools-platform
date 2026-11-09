# Close current-identity and cross-store quality evidence gaps

Type: follow-up task
Status: open
Blocked by: a Bookkeeping source-merge path into governed MDM and verified N-PORT holding receipts

## Goal

Close only the quality questions that the 2026-11-08 local audit could not
settle. Preserve the audit's source-of-truth rules: an identifier match alone
is not a source binding, an old MDM identity is not current authority, a
successful HTTP response is not verified publication, and Silver row presence
does not identify its Bookkeeping load. Use aggregate counts and masked or
invented examples in committed artifacts; never write record values or
identifiers.

## Checklist

- [x] Identify the active source producer and explain the empty governed snapshot (read-only code-path trace, 2026-11-08 20:12 ET). Bookkeeping `mastering.merge` calls `edgar_warehouse.mastering.merge.merge_file` through `edgar_warehouse.mastering.store.open_store`; `Store.write_masters` writes the legacy `mastering_master` family. The worker does not call `edgar_warehouse.mdm.merge.MergeStage`; repository search found its only caller in `mdm.steward.split`. The 19:53 ET empty governed tables therefore have no active Bookkeeping source writer in this path. No populated governed generation can be pinned until that merge path is wired and verified.
- [ ] After a governed source-merge path is wired, pin its identity, current-record and typed-relationship generation and compare the configured links and edges against it. The current audit uses the active legacy source bindings and records this unimplemented path as a migration/qualification gap; do not mislabel the empty new tables as a failed load.
- [ ] Compare each configured Silver source link's source key, source binding, kind, null policy, and time basis with the governed identity after that path is active; distinguish absent, unmatched, ambiguous, deferred, held, and wrong-pointer cases. The active legacy comparison across 16 link contracts is recorded in the parent audit.
- [ ] Compare each populated Silver relationship with governed endpoint identities, source evidence and effective-time/file-date rules after that path is active. The active legacy pair comparisons and observed file-date fallbacks are recorded in the parent audit.
- [ ] Reconcile N-PORT holding Silver rows to a verified Bookkeeping receipt and generation; explain waiting or failed stages from redacted error categories and complete endpoint classification before proposing a holding check. At 20:08 ET, a listing of up to 1,000 complete runs found zero completed `sec.nport.security` runs; both matching runs remained active with one `land_holding` unit pending each. The existing 5,347,869 Silver rows therefore lack a verified Bookkeeping producer/receipt. The failed-step summary identifies `merge`, but its redacted cause remains `other`.
- [ ] Resolve the recorded Company source/field-generation, international place, Form 4 issuer-edge, 13F manager-coverage, and other held-source candidates against retained evidence and the applicable time basis. The audit confirmed that `sec.ownership.security.v2` declares period-of-report effective time, but `ownership-security-sgml.yaml` does not read it and `prepare_security` omits `effective_column`; all 5,273 v2 assertions have null `effective_at`. Its contract declares only a ticker cross-reference, not `ISSUED_BY`. Keep the six differing and 1,531 absent CIK/edge comparisons as candidates until the time mapping and relationship authority are resolved.
- [ ] Route the generic current-MDM cross-store reference capability and typed-relationship read needed for unsupported predicates to their owning engineering work; keep link and relationship checks out of field-only rules.
- [x] Establish whether current configuration and retained coverage represent private-equity records. The audit found no separate PE kind or active private-fund mastering path, so there is no current PE cohort or quality denominator; details and limits are recorded in the parent audit. Do not infer PE from names or unrelated classifications.
- [x] Decide whether this audit supports new row-local checks. Existing predicates are already covered by Dataset Contract validation or configured Silver checks; unsupported pointer and relationship predicates require cross-store capabilities. No new check is justified by the measured evidence, and none was activated.
- [x] Publish refreshed coverage, confirmed findings, candidates, check measurements, and remaining evidence gaps in the parent audit. The parent audit is complete as a current evidence snapshot; future governed-MDM and N-PORT receipt work remains open here.
- [x] Learning → skill: extended `skills/data-quality/SKILL.md` → **Existing master projections** to compare effective time, source claim, operation, winner/projected value, and clear state in one repeatable-read, key-paged audit; genericity check (99 passed) and skill validator passed (2026-11-08 20:12 ET).

## Evidence carried forward

The parent audit at
[`01-company-field-and-relationship-quality-checks.md`](01-company-field-and-relationship-quality-checks.md)
records the dated per-store measurements. The governed
`mdm.master_entity`, `mdm.current_record`, and
`mdm.relationship_version` tables still had zero rows at the 19:53 ET
read-only check. Code-path review at 20:12 ET found that active Bookkeeping
`mastering.merge` writes the legacy `mastering_master` family; no worker invokes
the separate governed `mdm.MergeStage`. The empty governed tables have no
active source writer in this path. A 19:36 ET Bookkeeping status refresh found 360 complete and
30 running records. At 20:08 ET, the two N-PORT security runs remained
`running`: one had 3 verified, 3 reported, 3 waiting and 9 pending work items,
with 3 pending deliveries; the other had 14 verified, 1 waiting and 2 pending,
with 14 pending deliveries and `merge` in `failed_steps`. Each had one pending
`land_holding` item. The safe status summary classified the recorded error only
as `other`; its cause remains unknown. No run was resumed or changed. The
5,347,869 Silver holding rows measured at 17:54 ET therefore remain
unattributed to a verified run or current MDM generation. Do not inspect run
status again before 20:38 ET.

The 19:53 ET repeatable-read field audit traversed 461,455 legacy master rows
and compared all 4,036,273 populated accepted field projections to their
retained winning assertions. It found zero source, record-key, time, claim,
operation, winner-value, projection-value, or clear-state mismatches. This
establishes legacy field provenance and value agreement; it does not replace
current governed identity or relationship checks, or prove that today's
configured authority selected the right business value.

The data-quality engine currently supports row-local predicates only. The
parent audit defines the exact minimum cross-store link and typed-edge
predicates; this ticket is the evidence and implementation handoff, not an
authorization to add engine code or activate rules.
