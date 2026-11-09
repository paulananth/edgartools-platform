# Close current-identity and cross-store quality evidence gaps

Type: follow-up task
Status: open
Blocked by: a populated, generation-pinned governed MDM snapshot and verified load receipts

## Goal

Close only the quality questions that the 2026-11-08 local audit could not
settle. Preserve the audit's source-of-truth rules: an identifier match alone
is not a source binding, an old MDM identity is not current authority, a
successful HTTP response is not verified publication, and Silver row presence
does not identify its Bookkeeping load. Use aggregate counts and masked or
invented examples in committed artifacts; never write record values or
identifiers.

## Checklist

- [ ] Identify and pin a populated governed MDM identity, current-record, and typed-relationship generation; document why the shared verifier connection was empty and prove which producer populated the selected generation.
- [ ] Compare each configured Silver source link's source key, source binding, kind, null policy, and time basis with the current governed identity; distinguish absent, unmatched, ambiguous, deferred, held, and wrong-pointer cases.
- [ ] Compare each populated Silver relationship by type, direction, endpoint kinds and identities, source evidence, and effective-time/file-date rule. Preserve valid observed file-date fallbacks while authoritative dates remain unknown.
- [ ] Reconcile N-PORT holding Silver rows to a verified Bookkeeping receipt and generation; explain waiting or failed stages from redacted error categories and complete endpoint classification before proposing a holding check.
- [ ] Resolve the recorded Company source/field-generation, international place, Form 4 issuer-edge, 13F manager-coverage, and other held-source candidates against retained evidence and the applicable time basis.
- [ ] Establish private-equity source and pipeline representation from configuration and retained source coverage before assigning a population or proposing checks; do not infer it from fund names or unrelated classifications.
- [ ] For each predicate the existing quality engine supports and the approved contract requires, draft the check in its owning source contract or Silver table spec, measure the pinned population, and show a planted invalid record makes it fire. Do not activate a rule or change data in this evidence task.
- [ ] Route the generic current-MDM cross-store reference capability and typed-relationship read needed for unsupported predicates to their owning engineering work; keep link and relationship checks out of field-only rules.
- [ ] Publish refreshed coverage, confirmed defects, candidates, check measurements, and remaining evidence gaps in the parent audit; do not close it while any required evidence is unavailable.
- [ ] Learning → skill: update `skills/data-quality/SKILL.md` only if new reusable, source-neutral evidence-handling guidance is established.

## Evidence carried forward

The parent audit at
[`01-company-field-and-relationship-quality-checks.md`](01-company-field-and-relationship-quality-checks.md)
records the dated per-store measurements. The governed
`mdm.master_entity`, `mdm.current_record`, and
`mdm.relationship_version` tables still had zero rows at the 19:53 ET
read-only check. A 19:36 ET Bookkeeping status refresh found 360 complete and
30 running records. Both N-PORT security runs were unchanged from the earlier
read: one had 3 verified, 3 reported, 3 waiting, and 9 pending work items; the
other had 14 verified, 1 waiting, and 2 pending, with `merge` in its failed
steps. Each still had one pending `land_holding` item, and no verified holding
landing. The 5,347,869 Silver holding rows measured at 17:54 ET therefore
remain unattributed to a verified run or current MDM generation. Do not inspect run
status again before 20:06 ET. This task does not resume, alter, or clean any
active run.

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
