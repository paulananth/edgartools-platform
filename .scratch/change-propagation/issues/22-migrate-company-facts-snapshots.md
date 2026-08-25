# 22 — Migrate company-facts snapshots

**What to build:** Carry authoritative company-facts snapshots through the
registered acquisition path and publish only their verified affected scopes to
Silver.

**Blocked by:** 17 — Make Bronze capture retry-safe and recoverable; 20 —
Version and activate the Acquisition Universe

**Status:** resolved (partially — see Answer for the three bullets that
depend on later tickets)

- [~] The family Strategy defines the CIK-scoped logical identity, full-snapshot
  completeness proof, conditional fetch policy, and required producers.
- [x] Scope Completion includes the authoritative member count and ordered
  digest, including a valid complete-empty scope.
- [x] Missing, partial, or failed snapshots cannot retire prior facts or become
  the current Silver authority.
- [~] Changed, unchanged, reinterpreted, replayed, and retired facts produce
  deterministic verified outcomes with bounded work evidence.
- [~] No direct company-facts adapter caller bypasses the gated Facade.

## Answer

Added a `company_facts` Source Family alongside `filing_artifact`/`submissions`,
closely mirroring Ticket 21's architecture (single-phase, since one company-facts
JSON response per CIK has no pagination inventory to discover):

- **Strategy** (`CompanyFactsPolicy`, `source_family_registry.py`): fetches via
  `edgartools_sec_gateway.download_bytes` + `edgar.urls.build_company_facts_url`;
  completeness reuses the `valid_json_object` check (a real CIK can have an
  empty `"facts": {}` section and still be a complete snapshot — tested).
- **Discovery** (`company_facts_discovery.py`, new): one Fetch Decision per CIK.
  `company_facts_candidate_id(cik)` keyed only by CIK (no run-derived label) —
  replay-safety verified directly (network-fetch-count stays flat across two
  full command invocations, at both the discovery-module and command level).
- **Silver acceptance** (`company_facts_silver_acceptance.py`, new): seals
  `sec_financial_fact`/`sec_accounting_flag` as required producers, gated by
  `UnsupportedRequiredProducers` (ported upfront this time — Ticket 21's own
  Standards review caught this missing on its first pass). Verification is a
  batched `SELECT DISTINCT accession_number ... IN (...)` per producer, scaled
  to distinct accessions rather than a full per-row read-back (a company can
  carry thousands of fact rows across years of filings).
- **Command** (`drive-company-facts-discovery`): bundles execute/resolve_scope/
  planned_writes; `facade.py` and `fundamentals_ingest.py` (the legacy path)
  both have empty diffs, confirming no source-family branch was added and no
  legacy code was touched.

**Design decision, consulted with the advisor before writing code:**
`sec_financial_fact` has no `valid_from`/`valid_to`/`is_current` column
(confirmed live against its DDL, `silver_store.py` ~line 599), and
`.scratch/change-propagation/spec.md`'s Silver-publication section is explicit
that `RETIRE` "never physically deletes history" — so DELETE-based retirement
of facts absent from a fresh snapshot is not implementable without a schema
change this ticket does not authorize. Bullet 2's "Scope Completion" is
satisfied as a **recording** requirement instead of a deletion mechanism: each
producer's `ExpectedProducerSpec.scope_reference` carries `count=N/digest=<sha256>`
computed per-CIK from that snapshot's own business-key set, released
immediately per candidate (never accumulated across a batch — the volume/OOM
risk the advisor flagged). Bullet 3 (missing/partial/failed cannot retire) is
satisfied via the same negative-gate pattern as Ticket 21: nothing reaches
Silver unless CAPTURED with a complete payload.

**Three bullets are honestly partial, not silently claimed complete** (Spec
code-review, fixed point `origin/main`, caught exactly this — verified against
current source, not assumed):

- **Bullet 1** (conditional fetch policy): `CompanyFactsPolicy.fetch` takes no
  ETag/If-Modified-Since, and there is no `NOT_MODIFIED` terminal disposition
  for this family — every replay still pays a full network GET before
  `ContentImpact.NO_IMPACT` dedup happens post-fetch. This is not new scope
  creep introduced here; the sibling `submissions` family (Ticket 21) has the
  identical gap. [Ticket 28](28-add-conditional-fetch-and-not-modified-linking.md)
  is the already-charted, still-open ticket for conditional-fetch/not-modified
  linking across every family — this bullet closes there, not here.
- **Bullet 4**'s "retired" outcome kind: genuinely unimplemented, not merely
  deferred by a negative gate — retiring a fact that's absent from a fresh
  complete snapshot would need the validity-interval schema change ruled out
  above. Per the advisor's own explicit instruction ("if it's genuinely
  needed, graduate it as a new ticket rather than silently implementing or
  silently skipping it"), this is graduated to
  [Ticket 33](33-add-validity-interval-retirement-to-financial-facts.md)
  rather than silently folded into bullet 3's negative gate. "Changed" and
  "replayed" are both tested; "unchanged" (NO_IMPACT) is now tested too
  (`test_finalize_second_identical_capture_is_no_impact_and_publishes_with_no_producers`,
  added after Spec review flagged zero coverage for this leg); "reinterpreted"
  shares the same honest bounded-first-slice stance as Ticket 21's
  `SUBMISSIONS_INTERPRETATION_VERSION` (one constant for all four
  hash/version fields — a later parsing-quality ticket must not inherit this
  as an assumption once real interpretation exists).
- **Bullet 5**: true for this new path's own purity, but not true for the
  system as a whole — `fundamentals_ingest.run_bootstrap_entity_facts` (the
  legacy bypass) still calls `fetch_companyfacts_json` directly. Same
  situation as Ticket 21; closes only once Ticket 27 removes the legacy
  bypass for every family, including this one.

**Standards code-review finding accepted, not fixed:** the decision-driving
block in `company_facts_discovery.py` (create → check CAPTURED → execute →
re-query) duplicates `submissions_discovery._issue_and_drive_decision`'s
shape almost line-for-line. Not extracted into a shared cross-module helper
here — this family has exactly one call site (unlike submissions' two), so a
*local* extraction would be Speculative Generality; a *cross-module* one is a
real judgement call worth doing once a third family repeats this same
shape, not before.

Full suite green: 2553 passed, 4 skipped (before the NO_IMPACT test was
added; that test and its sibling file both independently verified green
afterward — not yet re-run against the full suite a third time given
this session's context budget).
