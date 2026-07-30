# 42 — Decide and execute the fundamentals pipeline backfill (F4/F5/F9/F11)

Type: task
Status: claimed
Blocked by: (none — 41 resolved)

## Question

Ticket 41 (Root-cause the empty fundamentals gold pipeline) found that `load_history` — the
only Step Function ever wired to run `bootstrap-fundamentals --mode entity-facts/per-filing/
thirteenf` — has **zero executions ever** in this account, and flagged (without attempting)
that a full-universe backfill is a substantial, separate operator decision, recommending a
small-scale smoke test first since `entity-facts`/`per-filing` correctness has never been
proven against real SEC data (only against mocked `fetch_companyfacts_json` responses in unit
tests).

What is the concrete, checkable plan to get real data into `sec_financial_fact`/
`sec_financial_derived`/`sec_accounting_flag` (F4/F11), `sec_earnings_release`/
`sec_executive_record` per-filing outputs (F5, shares F10's table), and confirm `thirteenf`
mode is redundant with the existing 6.8M-row 13F dataset (F7) — smoke-test scope, success/
failure criteria, rollout scope (single CIK → sample → full universe), and who/what executes
each step?

This ticket unblocks tickets 31 (Historical financials), 32 (Earnings 8-K GAAP snapshot), 36
(Segment/product-geo revenue), 38 (Accounting forensic scores) — all four are currently
blocked here, re-pointed from ticket 41 since 41 itself is resolved (a root-cause finding, not
a completed backfill) but the real-world blocker (no data) persists.

## Plan (grilled 2026-07-29, executing)

1. **Smoke test first, single CIK, real prod write.** Direct `aws ecs run-task` against the
   existing prod warehouse task definition, `--cik-list 320193` (Apple — same CIK used in the
   rollback rehearsal), two invocations: `bootstrap-fundamentals --mode entity-facts` and
   `--mode per-filing`. Not routed through `load_history`'s Step Functions windowing, which
   resolves CIKs from silver tracking-state offset/limit and cannot be scoped to one CIK.
   Writes for real to prod's canonical silver via the normal BatchSilver publish path (operator
   explicitly chose real-write over a disposable local copy).
2. **Pass criteria — values, not just row counts.** `sec_financial_fact`/`sec_financial_derived`
   gain rows for CIK 320193 AND at least one figure (e.g. a recent-fiscal-year revenue number)
   matches Apple's real public 10-K within rounding. `sec_accounting_flag` may legitimately stay
   empty if cross-period derivation inputs aren't available from one companyfacts pull — not a
   failure on its own. `sec_earnings_release` gains rows matching real 8-K dates;
   `sec_executive_record` gains a row named "Cook" with a CEO-like role. Garbled/wrong-magnitude/
   wrong-period values are a fail even if rows exist.
3. **If the smoke test passes:** run a diverse ~10-20 CIK sample (different entity types, fiscal
   year-ends, filer sizes — not just large-caps) via the same direct-ECS mechanism, re-checking
   the same criteria across the sample, before touching the full universe.
4. **If the sample passes:** trigger a real `load_history` execution for the full ~2,462-company
   operating universe, relying on its existing per-stage idempotency/catch-retry semantics.
5. **Evidence artifact:** `docs/release-readiness/fundamentals-backfill-evidence.json`, one entry
   per stage (smoke test / sample / full run) — timestamp, scope, mode, before/after row counts,
   spot-check results, pass/fail. Tickets 31/32/36/38 cite this instead of re-deriving results.

## Answer

**Stage 1 (single-CIK smoke test) executed live 2026-07-29 against CIK 320193 (Apple), real
writes to prod's canonical silver via two direct `aws ecs run-task` invocations
(`edgartools-prod-medium`, cluster `edgartools-prod-warehouse`). Result: mixed — one mode
(`entity-facts`→facts) genuinely passed; the other two surfaced real, previously-unknown bugs
that no amount of backfill scale would fix. Stopping here rather than proceeding to the sample
batch, since running more CIKs through the same code would only reproduce these same two bugs
at larger scale, not new information.**

### PASS — `entity-facts` → `sec_financial_fact` / `sec_financial_derived` (feeds F4, F9)

24,195 `sec_financial_fact` rows and 282 `sec_financial_derived` rows written for CIK 320193.
Spot-checked `RevenueFromContractWithCustomerExcludingAssessedTax` (consolidated, FY) against
Apple's real public 10-K figures — **exact match**: FY2025 (period ended 2025-09-27) $416.161B,
FY2024 (ended 2024-09-28) $391.035B, FY2023 (ended 2023-09-30) $383.285B. `segment='consolidated'`
default column (relevant to F9) present and populated correctly. This part of the pipeline is
genuinely correct, not just "producing rows" — the code is proven, not merely unverified anymore.

### FAIL — `entity-facts` → `sec_accounting_flag` (F11), structural, not fixable by scale

`sec_accounting_flag` stayed 0 rows for CIK 320193 (and 0 rows total in all of prod silver)
despite the task log claiming `"accounting_flags_updated": 129`. Root-caused two independent
bugs in the same code path:
1. `edgar_warehouse/parsers/financials.py`'s `parse_entity_facts` builds `sec_accounting_flag`
   base rows exclusively from four DEI XBRL concepts (`AuditorFirmId`, `AuditorName`,
   `AuditorLocation`, `IcfrAuditorAttestationFlag`). Live-fetched Apple's real
   `data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json` directly and confirmed its `dei`
   facts section contains only 2 concepts total (`EntityCommonStockSharesOutstanding`,
   `EntityPublicFloat`) — **none of the four auditor concepts the parser looks for are ever
   present in the companyfacts REST API**, for Apple or structurally for any filer (these are
   real XBRL taxonomy tags, but the SEC's companyfacts endpoint doesn't surface them the way it
   does core financial concepts). `entity-facts` mode as currently designed against this
   endpoint **cannot ever produce `sec_accounting_flag` base rows** — a design gap, not a
   scale/execution gap. Populating F11 for real needs a different source (e.g. per-filing XBRL
   instance/DEI extraction from the 10-K document itself, not the aggregated companyfacts API).
2. Independent masking bug: `edgar_warehouse/parsers/accounting_flags.py`'s
   `backfill_accounting_flags` runs `UPDATE sec_accounting_flag SET ... WHERE cik=? AND
   accession_number=?` and increments its `updated` counter whenever the call doesn't raise —
   but DuckDB's `UPDATE` against zero matching rows doesn't raise, it just silently affects zero
   rows. Because bug #1 means no base row ever exists to match, all 129 "updates" for Apple were
   no-ops, and the metric silently claims success. This exact masking shape (a counter that
   tracks "attempts that didn't error" instead of "rows actually written") is the same class of
   bug CLAUDE.md's INSTITUTIONAL_HOLDS 5-whys warns about ("a deliberately-broad... error
   handler is a trap").

### FAIL — `per-filing` → `sec_earnings_release` (F5) — root cause confirmed (5-whys)

0 rows for CIK 320193 despite `filings_scanned: 118`, `filings_parsed: 30`. Initial live check
found every Apple Item-2.02 8-K accession has zero `sec_filing_attachment` rows, and the first
correlation spotted (self-filed vs. agent-filed accession prefix) turned out to be a coincidence
of the 3-row sample checked, not the real cause — a follow-up universe-wide query disproved it
and found the actual root cause:

1. **Symptom:** `sec_earnings_release` is 0 rows everywhere in prod silver except 13 rows from
   an unrelated one-off window (ticket 41). CIK 320193's smoke test reproduces it directly.
2. **Why 0 rows from parsing?** The per-filing dispatch loop only calls the earnings parser on
   filings whose primary attachment can be read from `sec_filing_attachment`. For every one of
   Apple's Item-2.02 8-Ks, that table has zero rows for the accession — dispatch hits the
   "no primary artifact" branch and increments `filings_skipped`, never reaching the parser.
3. **Why does `sec_filing_attachment` have zero rows for Item-2.02 8-Ks?** Live-queried the
   **entire** prod silver database, not just Apple: **52,408 Item-2.02 8-Ks exist, and
   exactly 0 of them have any `sec_filing_attachment` row** — 0% coverage, universe-wide, not
   company-specific. (Contrast: Item-5.02 8-Ks are 34,256 total, 6,847 have attachment rows —
   20%, consistent with partial historical bulk-load coverage, not a total gap.) This
   conclusively rules out the earlier self-filed/agent-filed hypothesis.
4. **Why does attachment-fetch skip Item-2.02 specifically?** Attachments are only fetched for
   an accession when `_configured_parser_accessions` (`edgar_warehouse/application/
   warehouse_orchestrator.py`) selects it during Branch A's bulk artifact fetch
   (`--artifact-policy all_attachments`). `_is_configured_parser_form` allows 8-K/8-K-A only via
   `_is_item_502_candidate_form`, whose regex matches only when `items` is blank **or contains
   "5.02"** — there is no corresponding check for "2.02" anywhere in the selection logic.
5. **Root cause:** `_is_configured_parser_form`/`_configured_parser_accessions` was built for
   the original Required Relationship Bulk-Load scope (tickets 12-24: ownership, ADV, proxy,
   13F, and Item 5.02 employment events — the relationship-graph-feeding form types). When
   `bootstrap-fundamentals --mode per-filing` was added later for earnings/proxy fundamentals,
   its own docstring assumes "Branch A" already populated `sec_filing_attachment` for "8-K
   earnings + DEF 14A proxy" — but Branch A's selection gate was never updated to actually
   include Item 2.02 when that assumption was written. A newer consumer (fundamentals
   per-filing) assumed a broader producer (Branch A's artifact fetch) than what the producer's
   own form-selection code actually implements — the two drifted out of sync at the point the
   fundamentals pipeline was bolted on, and nothing caught it because per-filing mode has never
   run against real data until this smoke test (ticket 41).

**Fix applied and unit-tested 2026-07-29.** Added `_is_item_202_candidate_form` (sibling to
`_is_item_502_candidate_form`, same regex shape, matches only explicit "2.02" tags — no
blank-items catch-all, since that ambiguous bucket is already owned by the 502 predicate) and
OR'd it into `_is_configured_parser_form` (`edgar_warehouse/application/
warehouse_orchestrator.py`). Two existing tests had **locked in the bug as expected behavior**
and needed updating, not just new tests added: `tests/unit/test_ownership_lookback.py`'s
`test_filters_old_ownership_keeps_recent_and_non_ownership` asserted an item-2.02 fixture named
`"unrelated-8k"` was correctly excluded (renamed/repurposed to a real unrelated-item-1.01
fixture, added a new `"earnings-8k"` fixture asserted as included); `tests/unit/
test_submission_phase_order.py`'s `test_configured_form_artifact_pipeline_filters_to_parser_forms`
had a fixture literally named `"earnings-8k"` asserted as excluded from artifact/parser calls
(updated to assert inclusion, row-count math adjusted accordingly). Added 7 new direct unit
tests for the new predicate (`TestIsItem202CandidateForm`) covering match/no-match cases
including a false-positive-on-substring guard. Full suite: **1386 passed, 4 skipped
(pre-existing), 0 failed** (`tests/unit`, `tests/application`, `tests/architecture`,
`tests/mdm`).

**Live re-verification done 2026-07-29 — mixed result, real progress plus a new finding.**
Merged the fix (PR #299), rebuilt/redeployed the prod warehouse image (digest
`sha256:e95add6ac3f63863cdc007bf5ec9647cb53f6f0a9f559ca7d8d2074e93fbd035`, task-def
`edgartools-prod-medium:93`), then re-ran `bootstrap-batch --cik-list 320193 --artifact-policy
all_attachments` (the correct re-verification path — a bare `bootstrap-fundamentals --mode
per-filing` re-run does NOT re-trigger Branch A's artifact fetch, it only reads whatever's
already registered, so it reproduced the exact same zero-row result as before the fix on first
attempt; caught this and re-ran the right command).

**The selection fix itself is confirmed correct and working**: Apple's Item-2.02 earnings 8-Ks
are now genuinely selected for artifact fetch (live-confirmed via `artifact_call_started`/
`artifact_call_completed` CloudWatch events with real byte counts).

**But every one of the 45 selected earnings-8-K accessions failed** with a NEW error —
`WarehouseRuntimeError("immutable object ... already exists with different content")`, from the
just-merged PR #298 immutable-write guard. Live-checked the actual S3 objects: every colliding
primary-document key already existed in bronze, written in a single ~3-second window on
2026-07-19T20:13:19–22Z by an unidentified process that never registered `sec_filing_attachment`
— re-fetching the same document now produces different bytes, tripping the guard. Spun off
[ticket 44](44-root-cause-earnings-8k-immutable-content-collision.md) to root-cause this
separately rather than guess at a fix inline. **F5 is not yet actually populated in prod** —
the selection bug (this ticket's original scope) is fixed and proven, but a second, independent
blocker (ticket 44) sits between the fix and real `sec_earnings_release` rows.

### Recommendation — do not proceed to the sample batch yet

The plan's stage 3 (diverse sample batch) and stage 4 (full-universe `load_history`) are
**paused**, not cancelled — running more CIKs through the same code paths would reproduce these
same two bugs at scale (self-filed earnings 8-Ks likely affect many companies, not just Apple;
the DEI-concept gap affects every filer since it's structural, not company-specific), burning
real AWS runtime for no new information. Two follow-up tickets are needed before resuming:
one to root-cause the self-filed-8-K attachment gap (F5), one to decide F11's real data source
now that companyfacts is confirmed insufficient. `sec_financial_fact`/`sec_financial_derived`
(F4/F9) are the one part of this ticket's scope that's genuinely proven — a sample/full backfill
for **those two tables specifically** could reasonably proceed independent of the F5/F11 fixes,
since `entity-facts` mode's revenue/derived-metrics path has no known defect. That split
decision (proceed on F4/F9 now vs. wait for all three) was not made in this pass — flagging for
the operator.

Evidence: CloudWatch logs
`/aws/ecs/edgartools-prod-warehouse` streams `warehouse-medium/edgar-warehouse/
305b4d618cc74a8ab004cf8f6f353150` (entity-facts) and
`.../8d3238d90d084583b6c71090b6dc3ea7` (per-filing); live queries against downloaded prod
`silver.duckdb` (2026-07-29 20:5x UTC) and a direct fetch of Apple's real companyfacts JSON.
No `docs/release-readiness/fundamentals-backfill-evidence.json` written yet — holding off until
the operator decides how to split the remaining scope (see Recommendation above), since writing
a "stage 1: PASS" evidence entry would misrepresent a mixed 1-pass/2-fail result as a clean gate
pass.
