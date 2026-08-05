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

### F5 follow-up — Apple Exhibit 99.1 selection fixed and live-validated (2026-08-01)

Ticket 56's byte-exact capture boundary registered the preserved Apple artifacts, but the
per-filing reader still always handed the primary 8-K document to the earnings parser.  For
Item 2.02 filings the earnings release is the `EX-99.1` attachment, so the parser was receiving
the cover 8-K rather than the release.  The workflow now selects `EX-99.1` (also accepting the
equivalent `EX-99.01` type) only for explicit Item 2.02 8-K earnings parsing; Item 5.02 parsing
continues to use the primary document.  A focused unit regression uses Apple accession
`0000320193-19-000073` and proves that the exhibit bytes, not the primary bytes, reach the
earnings parser.

The immutable warehouse image
`sha256:70cdc1c710d1a334a28e7c894f41db61a024baf61a3ddaa76029a937b2ea5e57` was deployed as
`edgartools-prod-medium:104`.  Direct ECS run
`84eeed611ba64bc7a0cefbe92c5e826b` (`bootstrap-fundamentals --mode per-filing --cik-list
320193`) exited 0: 118 filings scanned, 75 parsed, 43 skipped, and **44
`sec_earnings_release` rows written**.  The fresh canonical production `silver.duckdb` upload
(2026-08-01 11:47:40 UTC) contains the known Apple release row:

`0000320193-19-000073 | FY2019 Q2 | 2019-06-29 | revenue_gaap=53,809,000,000 |
net_income_gaap=10,044,000,000 | eps_gaap_diluted=2.18`.

F5's Apple smoke-test criterion is now met.  Ticket 42 remains claimed because the sample/full
backfill rollout decision and the independent F11 source-design gap remain unresolved.

### Rollout + F11 decisions resolved via grilling (2026-08-04)

Re-verified live state unchanged since 2026-08-01 (`sec_financial_fact`=36,809 rows/2 CIKs,
`sec_financial_derived`=450 rows/2 CIKs, `sec_accounting_flag`=0 rows, `sec_earnings_release`=57
rows/14 CIKs, `sec_executive_record`=13,457 rows/893 CIKs) before deciding anything, confirming
the 2026-08-01 findings still hold.

Decided (operator, via `AskUserQuestion`): (1) proceed with the sample then full-universe
backfill for F4/F9/F5 now, independent of F11 -- F11's gap won't be fixed by scale or time; (2)
for F11, fix the masking bug now (real correctness bug, independent of the data-source
question) and defer the data-source redesign to its own ticket rather than deciding it inline.

**Masking bug fixed.** `SilverDatabase.update_accounting_flag_scores` (`silver_store.py`) now
returns `True`/`False` via `UPDATE ... RETURNING cik` instead of `None` -- DuckDB's `UPDATE`
against zero matching rows doesn't raise, so "the call didn't error" was never a valid proxy for
"a row was actually updated." `backfill_accounting_flags` (`accounting_flags.py`) now only
increments its `updated` counter when a real match occurred. 4 new tests
(`tests/unit/test_accounting_flags_update_masking.py`), including one that reproduces the exact
live scenario (derived-metric rows exist, no base `sec_accounting_flag` rows do) and asserts
`updated == 0` -- confirmed to fail pre-fix (counted 2 no-op "updates") and pass post-fix. Full
suite green: 1325 passed, 4 skipped, only the pre-existing unrelated `test_go_live_wizard.py`
failure. Not yet deployed to prod.

**F11 data-source redesign split off** as [ticket 92](92-decide-f11-accounting-flag-data-source.md)
-- deliberately not decided here.

**Next:** sample backfill (10-20 diverse CIKs) for F4/F9/F5, then full-universe `load_history`
if the sample passes. See below for results.

### Sample backfill: PASS 2026-08-05 (4th attempt, after tickets 96 and 97)

The same 20-CIK sample (`1800,8818,10329,14177,15615,16160,22701,23194,25895,27093,27996,60519,
75288,77543,82020,277638,764180,875355,1064728,1603978`) had failed 3 prior times — attempts 1-2
were the pre-ticket-96 edgartools whole-market-scan timeouts; attempt 3
(`ticket42-sample-artifacts-retry3-postticket96-1785887896`) got past the fetch phase but exited
2 on 147 `sec_filing_attachment.raw_object_id` conflicts, root-caused and fixed as
[ticket 97](97-fix-filing-attachment-raw-object-id-conflicts.md). Re-ran the identical CIK list
(`ticket42-sample-artifacts-retry4-postticket97-1785894075`, ECS task
`20a3e448c6ae4a91940234a761c5eb90`) against the ticket-97-fixed image: **exited 0**, first clean
end-to-end pass. 3,149 accessions processed (221 known immutable-object-conflict skips, circuit
breaker stayed closed), all 31 protected tables merged without ambiguous conflicts, canonical
silver published, run manifest written. F4/F9/F5 sample criteria (real row counts + spot-check
values, per this ticket's original pass criteria) not yet re-verified against the freshly
published canonical — that check plus the full-universe `load_history` decision are the
remaining open items.

### F4/F9/F5 re-verification against fresh canonical (2026-08-05)

Downloaded the freshly-published canonical `silver.duckdb` (post-attempt-4,
`2026-08-04 22:28:59`) and queried directly (not trusting log row counts alone).

**F4/F9 (`sec_financial_fact`/`sec_financial_derived`): PASS.** Real data present for all 20
sample CIKs; spot-checked Abbott Laboratories' (CIK 1800) FY2024 revenue against known public
figures — correct.

**F5 (`sec_earnings_release`): initially FAIL — empty.** 0 rows for all 20 sample CIKs. 5-whys:
all 4 prior retries ran `bootstrap-batch` (the ownership/ADV/13F artifact pipeline), never
`bootstrap-fundamentals --mode per-filing` (the command that actually populates
`sec_earnings_release`) — a conflated-command gap, not a code defect. Confirmed both F5-specific
prerequisites still held before re-running: Item 2.02 8-K attachment coverage across the 20 CIKs
(97.8%/87.3%), and both previously-fixed F5 bugs (`_is_item_202_candidate_form` item-selection,
EX-99.1-vs-primary-document exhibit selection) present via grep in the currently-deployed image's
source commit.

Ran `bootstrap-fundamentals --mode per-filing --cik-list <same 20 CIKs>`
(ECS `bc905b97cab2402e8a0f04335a416f59`, RUN_ID `ticket42-perfiling-sample-1785924446`): exited 0
in 636s. `bootstrap_fundamentals_completed`: 3,334 filings scanned, 1,773 parsed, 861
`sec_earnings_release` rows written (plus 1,915 `sec_executive_record`, 71
`sec_employment_event`), silver re-published to S3.

Re-downloaded the freshly-published canonical and queried again: all 20/20 sample CIKs now have
`sec_earnings_release` rows (9–83 rows each, 861 total matching the log). Spot-checked Abbott
Laboratories (CIK 1800, 30 rows spanning 2018–2026): quarterly revenue/net-income/EPS values
match Abbott's known real public earnings figures and dates line up with its actual quarterly
release cadence (mid-Jan/mid-Apr/mid-Jul/mid-Oct) — correct.

**New defect found — wrong-magnitude values, ~15% of sample rows.** Per this ticket's own pass
bar ("wrong-magnitude values are a fail even if rows exist"), scanned all 861 sample rows for
implausibly small `revenue_gaap`/`net_income_gaap` given each company's real scale. **128 of 861
rows (15%), across 15 of the 20 sample CIKs** have values that were clearly reported "in
millions"/"in thousands" in the source document but never scaled to whole dollars.
`edgar_warehouse/parsers/earnings_release.py` does no scaling of its own by design (see the
file's own "WHY-STUB" comment) — it delegates entirely to edgartools' `EarningsRelease`/
`FinancialTable` classes. Investigated edgartools' actual behavior directly (installed 5.30.0,
`.venv/.../edgar/earnings.py`), not guessed — re-ran `EarningsRelease` against the real cached
exhibit bytes for two failing accessions, pulled straight from bronze S3. This surfaced **two
distinct upstream edgartools defects**, both live in 5.30.0 and, per a full changelog review
through the current latest (5.45.1, PyPI `edgartools`, checked 2026-08-05), **neither has been
fixed in any release since** — no changelog entry after 5.23.3 (2026-03-15, the release that
introduced the current parenthetical-pattern regex) touches `EarningsRelease` scale or row-type
logic at all:

1. **Row-type misclassification** (Avery Dennison, CIK 8818, accession `0000008818-26-000075`).
   Table-level scale *is* correctly detected as `MILLIONS` (`inc.scale == Scale.MILLIONS`,
   confirmed live). But `get_key_metrics()` only scales a row when
   `get_row_type(label, position) == RowType.AMOUNT`; the "Net sales" row (revenue, position 0)
   comes back `RowType.PERCENTAGE` instead of `AMOUNT`, so it's skipped while the very next
   `AMOUNT`-classified row (net income) in the same table scales correctly — reproduced exactly
   this shape live: `revenue_gaap=2298.5` (unscaled) next to correctly-scaled
   `net_income_gaap=168100000.0` in one row. `_classify_row_type("Net sales", "")` called
   directly returns `AMOUNT` as expected — the label text itself doesn't match any PERCENTAGE
   pattern (`margin`, `as a percentage`, etc.) — so the bug is upstream of that function, in how
   `_extract_tables()` builds the positional `row_types` list: it pulls per-row
   `parent_contexts` from `df.attrs['_row_parent_contexts']` (set by `_extract_clean_dataframe`,
   a separate table-hierarchy-detection routine), and this document's row-hierarchy detection
   appears to mis-assign a nearby percentage row's parent context onto the revenue row.

2. **Scale-detection miss** (Louisiana-Pacific Corp, CIK 60519, ticker `LPX` — mislabeled "L.B.
   Foster" earlier; this CIK had the most suspicious rows, 32/55). The source document states
   `"(dollar amounts in millions, except per share amounts)"` directly above the income
   statement table (confirmed by grepping the raw cached HTML) — but LPX's table-level
   `inc.scale` still resolves to `Scale.UNITS`, so *every* AMOUNT row in the table is wrong, not
   just revenue (explaining why this CIK has far more bad rows than Avery Dennison's single-row
   miss). Root cause: the document-level `detected_scale` regex
   (`\((?:dollars |amounts |figures )?in\s+millions`) requires exactly one of three literal
   prefix words directly after `"("` — `"(dollar amounts in millions"` has *two* words
   ("dollar" + "amounts") before "in millions", and "dollar" (singular) isn't one of the three
   allowed prefixes anyway, so it doesn't match. The table-level `_detect_table_scale()` has a
   looser fallback (substring `"in millions"` in up-to-3 preceding sibling nodes), which should
   catch this phrasing — but evidently the caption paragraph isn't within that 3-sibling/DOM-
   proximity window for this document's actual markup structure, so it falls through to the
   equally-blind document-level regex and lands on `UNITS`. This is the same brittle-regex defect
   *class* edgartools itself fixed for a different class (`ConceptReport.currency_scaling`,
   changelog 5.31.2, GH #807 — "narrow text match... silently fell through to the default of 1"
   for phrasing like `"Dollars in Millions"`) — but that fix was never applied to
   `EarningsRelease`.

Both are genuine, reproducible defects in the third-party `edgartools` package we depend on via
PyPI (`edgartools>=5.29.0`, CLAUDE.md) — not in this repo's parser or orchestrator code, and not
fixable by upgrading (no release since 5.23.3 touches this path).

**Not yet decided:** whether this blocks the full-universe `load_history` run (Task #35), needs
a corrective heuristic in this repo's parser layer (e.g. a plausibility check comparing
`revenue_gaap` against the company's own other filings, or against `net_income_gaap` magnitude in
the same row, to catch an unscaled outlier), an upstream edgartools issue report (both defects are
precisely reproducible with a two-line repro against real cached bytes — worth filing regardless
of what we decide to do locally), or is accepted as a known, tracked limitation of F5 for now.
Needs a decision before Task #35/#36 proceed.

### Fix implemented for defect #1 (row-classification mismatch) — 2026-08-05

Decision: build a repo-side correction for defect #1 only (mechanically well-understood and
safely correctable — edgartools already tells us the document's real scale via `metrics['scale']`,
it just fails to apply it to one misclassified row). Explicitly **not** attempting to fix defect
#2 (scale-detection-miss, LPX-shaped) — that requires an independent secondary scale-detection
pass with no reliable in-row signal to correct from, materially bigger scope and higher
false-positive risk than reapplying a scale edgartools already detected. Filing an upstream
edgartools issue for both defects is still worthwhile (two-line repros in hand) but not done as
part of this pass.

`edgar_warehouse/parsers/earnings_release.py`: added `_correct_scale_mismatch()`, applied to
`revenue_gaap` and `net_income_gaap`. When `metrics['scale']` is a real non-UNITS scale (meaning
edgartools *did* detect the table's scale) and a value's magnitude is implausibly below that
scale's unit (e.g. `2298.5` when scale is MILLIONS), it's corrected by reapplying the same
multiplier edgartools itself determined for the table — not a guessed/independent scale. A
correction is logged (`earnings_release_magnitude_corrected`, includes accession/field/raw/scale/
corrected) so every correction stays auditable. When `scale` is UNITS or absent (defect #2's
shape, or older/test metrics dicts without a `scale` key), values are left untouched — no
signal to safely correct from, and guessing would risk introducing new wrong values.

**Validation:**
- `tests/unit/test_earnings_release_scale_correction.py` (4 new tests): reproduces the exact live
  Avery Dennison shape (revenue unscaled, net_income scaled, same row) → revenue corrected,
  net_income untouched; already-correctly-scaled values → untouched (no double-scaling); LPX's
  scale-UNITS shape → untouched (defect #2 correctly left alone, not guessed at); missing
  `scale` key (matches this repo's existing `test_earnings_release_guidance_wiring.py` mock
  shape) → untouched, backward compatible. Confirmed via `git stash` that the first test fails
  with the exact expected pre-fix value (`2298.5 != 2298500000.0`) before the fix and passes
  after.
- Full suite (`tests/unit tests/application`): 1015 passed, 4 skipped, no failures, no
  regressions.

Not yet committed/PR'd/deployed/re-verified against a live re-run — awaiting go-ahead.
