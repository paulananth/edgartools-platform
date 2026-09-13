# 11 — Post-Cutover Reconciliation and Human GO/NO-GO Gate

**What to build:** Run [Ticket 08](08-build-table-specific-reconciliation-tooling.md)'s
tooling against the post-cutover state produced by
[Ticket 10](10-atomic-write-path-cutover.md), producing the fail-closed
assertion DuckDB Retirement's Ticket 07 (wayfinder decision) requires, and
route the result to a required human approval before the cutover is
considered final.

Kept as its **own** ticket rather than folded into Ticket 10's deploy step
deliberately: Ticket 07's standard is "automated fail-closed assertion
gating a required human approval" — putting the approval inside the same
ticket as the deploy invites self-certification (the agent that ran the
deploy also signing off on it). A separate ticket makes the human-approval
step a real handoff, matching this repo's `Gate Attestation` /
`Direct-Evidence GO` pattern (`CONTEXT.md`) rather than a rubber-stamp
embedded in the same change.

If reconciliation fails for any table, this ticket's job is to surface that
failure clearly (which table, which check) — not to attempt an automatic
rollback itself. Rollback mechanics, if reconciliation fails, follow Ticket
01's rollback answer (all-or-nothing across the write path + reader
cutovers), executed as a separate, explicit operator action.

**Blocked by:** [Ticket 10](10-atomic-write-path-cutover.md)

**Status:** resolved (2026-09-12) — GO

- [x] Ticket 08's reconciliation tooling runs against the real post-cutover
      state (not a dry run) and produces a PASS/FAIL per table
- [x] `sec_thirteenf_holding`'s large-scale case passes (or a documented,
      understood failure blocks GO)
- [x] A named human operator records an explicit GO/NO-GO decision, bound to
      the specific deploy/reconciliation evidence — not an inferred or
      default approval
- [x] If NO-GO: the specific failing table(s) and check(s) are documented
      clearly enough for the rollback decision to be made without
      re-deriving the failure from scratch

## Deploy-timing discovery (2026-09-12): the cutover was already live before this gate ran

Found while starting this ticket: [Ticket 10](10-atomic-write-path-cutover.md)'s own file still
said "code complete; deploy pending operator" — but the currently-registered prod ECS task
definition (`edgartools-prod-large`, revision 302, registered 2026-09-12) runs image
`warehouse-sha-cffe2a043680`, and `git merge-base --is-ancestor 29612b3d cffe2a04` confirms that
commit descends from Ticket 10's own merge commit (`29612b3d`, 2026-09-06). Canonical
`silver.duckdb`'s S3 `LastModified` independently confirms this: **2026-09-06 10:42:08**, six
days with zero writes as of this reconciliation run. The cutover shipped as an unintentional
side effect of an unrelated deploy (PR #607, an oversized-SEC-document fix) rather than a
deliberate, gated flip — the exact failure mode this ticket exists to catch after the fact. This
gate is therefore retroactive, not pre-emptive, for this cutover.

## Reconciliation run (2026-09-12)

Ran `edgar-warehouse table-reconcile` (Ticket 08's tool) against the real post-cutover state:
canonical `silver.duckdb` hydrated fresh from S3 (1,793,077,248 bytes, matching the frozen
2026-09-06 snapshot) vs. live `EDGARTOOLS_SILVER` via `SnowflakeSilverReader`.

**`sec_thirteenf_holding` (the required large-scale case, ~6.8M rows): PASS.** All four checks
pass — bronze-to-silver, PK uniqueness, required-parent integrity, and semantic-content digest
all clean; `out_of_scope_count: 0`, `duckdb_only_count: 0`, `snowflake_only_count: 0`, digests
match exactly.

**Full run: 30 tables checked, 26 pass, 4 fail.** `report_digest`:
`bd46fb8d503d837435bc7565c4ab4233f239185a091a0d138d0d3509e0e67c09` (reproduce with
`edgar-warehouse table-reconcile --output report.json` against the live environment; this exact
JSON was not committed, ephemeral snapshot of real production data per Ticket 08's own
convention).

Passing (26): `sec_accounting_flag`, `sec_adv_disclosure_event`, `sec_adv_filing`,
`sec_adv_firm_roster`, `sec_adv_office`, `sec_adv_private_fund`, `sec_auditor_report_evidence`,
`sec_company`, `sec_company_address`, `sec_company_former_name`,
`sec_company_submission_file`, `sec_current_filing_feed`, `sec_earnings_release`,
`sec_employment_event`, `sec_executive_record`, `sec_filing_attachment`, `sec_filing_text`,
`sec_guidance_fact`, `sec_ownership_derivative_txn`, `sec_ownership_non_derivative_txn`,
`sec_ownership_reporting_owner`, `sec_pcaob_firm_identity`, `sec_raw_object`,
`sec_subsidiary_evidence`, `sec_thirteenf_filing`, `sec_thirteenf_holding`.

Failing (4), root-caused rather than left as raw numbers:

1. **`sec_financial_fact`** — `required_parent_integrity` orphan_count **67,668** (accessions
   not present in `sec_company_filing`). **Pre-existing, not caused by this cutover**: this is
   the exact same count Ticket 08's own 2026-08-31 dry run already documented ("real orphan/
   digest findings, e.g. ... `sec_financial_fact` 67,668 accession-orphans... logged here as
   real signal the tool correctly surfaced, not fixed in this ticket... a natural follow-up
   ticket"). Identical count, six days apart, spanning the cutover — this gap predates and is
   unrelated to Ticket 10. Never separately ticketed; still open.
2. **`sec_company_filing`** — `bronze_to_silver`/`required_parent` orphan_count 455 (cik-orphans
   against `sec_company`), and `semantic_content_digest` genuinely fails (content differs for
   the same 500 compared keys, not a false positive). **Already known, already fixed, not yet
   deployed**: matches [Ticket 16](16-sec-company-filing-coregistrant-key-collision.md)'s
   already-diagnosed co-registrant/ownership-filing collision (SEC lets one accession cover
   multiple CIKs; this table's one-row-per-accession model silently picks whichever CIK's feed
   lands first, and DuckDB/Snowflake don't necessarily agree on which). Ticket 16's fix is
   implemented and validated live against Snowflake, but its `dbt run --full-refresh` deploy
   step is still pending explicit operator go-ahead — this reconciliation failure is exactly the
   expected, already-understood symptom of that still-pending deploy, not a new problem.
3. **`sec_financial_derived`** — orphan_count 792 against `sec_company_filing`, but
   `semantic_content_digest` itself **passes** (content matches for the compared cohort). Reads
   as a downstream consequence of finding 2 (same parent link, `sec_company_filing`), not an
   independent defect — the orphan check alone doesn't distinguish "genuinely missing parent"
   from "parent row exists but represents a different, colliding CIK" the way Ticket 16
   describes. Expected to clear once Ticket 16 deploys; not separately investigated further.
4. **`sec_company_ticker`** — orphan_count 4,166 against `sec_company`, **and** a genuine
   cross-store content divergence: `duckdb_key_digest` and `snowflake_key_digest` disagree even
   though the same 500 DuckDB-selected keys were requested from both sides, meaning Snowflake's
   `sec_company_ticker` is missing or returning different rows for some of those exact keys.
   **New finding, not explained by anything already on this map** — release-readiness Ticket
   40 already found silver `sec_company_ticker` itself healthy (8,056 distinct CIKs, matches SEC
   ground truth), so this isn't a source-data problem; it's specifically a DuckDB-vs-Snowflake
   disagreement on that already-healthy data. Filed as
   [Ticket 19](19-sec-company-ticker-cross-store-divergence.md) for follow-up investigation —
   not root-caused in this pass.

**Assessment:** of the 4 failing tables, 3 (financial_fact, company_filing, financial_derived)
trace to already-known, already-tracked, pre-cutover data-quality gaps with no evidence the
cutover itself introduced or worsened them. 1 (`sec_company_ticker`) is a new, unexplained
finding that needs its own investigation before it can be judged pre-existing or cutover-caused.
This is evidence for the human GO/NO-GO decision below, not a decision itself.

## GO/NO-GO decision (2026-09-12)

**GO.** Decided by the operator (theananthfamily@gmail.com), bound to this exact reconciliation
run (`report_digest bd46fb8d503d837435bc7565c4ab4233f239185a091a0d138d0d3509e0e67c09`): the
required large-scale case passes clean, 26/30 tables pass overall, and of the 4 failures 3 are
already-tracked pre-existing gaps unrelated to this cutover while the 4th (Ticket 19) is a new
but non-blocking finding, tracked separately rather than gating this decision. The cutover
(Ticket 10) is confirmed final, not subject to rollback. This unblocks
[Ticket 12](12-duckdb-retirement-cleanup.md).
