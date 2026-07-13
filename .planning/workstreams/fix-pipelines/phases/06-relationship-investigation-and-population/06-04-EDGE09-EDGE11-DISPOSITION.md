# 06-04 Disposition: EDGE-09 (EMPLOYED_BY) and EDGE-11 (INSTITUTIONAL_HOLDS)

**Plan:** 06-04 (Wave 3, fix-pipelines)
**Status:** Both types root-caused. EDGE-11 has a verified, committed code fix (unable to
run the live derive→sync→graph chain from this execution environment — see "Environment
constraints" below). EDGE-09 does not have a confirmed code-level root cause; it is
documented as an unresolved parser-quality investigation, explicitly NOT a source-coverage
exclusion (see EDGE-09 conclusion).

**Re-execution note:** This plan was re-executed from scratch per explicit user direction,
independent of an earlier partial investigation (`06-04-PROGRESS.md`, a leaning hypothesis
about EDGE-09/EDGE-11 that was not read or relied upon while producing this document). The
findings below were derived independently from this plan's own `<read_first>` sources plus
live verification against real SEC EDGAR filings.

## Environment / worktree provenance note

This plan executed in a worktree whose branch base (`main` @ `f2b68e5`) does **not** include
commit `1185942` (`feat(06-03): complete Task 3 coverage evidence...`), which lives on
`claude/consolidate-workstreams` (not yet merged to `main` as of this plan's execution). The
local copy of `06-03-LOAD-COVERAGE-EVIDENCE.md` in this worktree therefore still shows Task 3
as "pending execution #3 outcome" — the completed classification table does not exist on
this branch. The EDGE-09/EDGE-11 classifications below were sourced read-only via
`git show claude/consolidate-workstreams:.../06-03-LOAD-COVERAGE-EVIDENCE.md` (no merge, no
worktree contamination — the committed Task 3 evidence is one of this plan's declared
`<read_first>` sources and this is a legitimate read of it). The orchestrator should be aware
this worktree's base was behind the workstream's actual latest state; it does not affect the
validity of the findings below (all code-level root-causing was done directly against this
worktree's own source tree, which is current).

Also: AWS credentials available in this execution environment resolve to
`arn:aws:iam::077127448006:user/cli-access` — the **decommissioned** account per CLAUDE.md
("Account `077127448006` is DECOMMISSIONED... zero billable resources remaining"), not the
active dev account `690839588395`. No dev Snowflake/MDM/Step Functions/S3 access was
reachable from this environment. Consequently neither type could complete a live
derive → sync-graph → graph-row-count chain in this execution; both dispositions below are
therefore code-level root-causing plus a verified-in-isolation fix (EDGE-11) or a documented
investigation gap (EDGE-09), not a graph-verified populate. This is recorded explicitly rather
than asserting a graph edge count that was never actually run.

---

## EDGE-09: EMPLOYED_BY (DEF 14A → sec_executive_record)

### 06-03 classification (carried forward)

Per `claude/consolidate-workstreams`'s completed 06-03 Task 3 evidence: **ARTIFACT PRESENT,
SILVER EMPTY** — 11 `DEF 14A` + 12 `DEFA14A` attachments present in the loaded dev universe's
`sec_filing_attachment`, but `sec_executive_record` = 0 rows. Classified as a parser gap, not
a missing artifact.

### 5-whys

1. **Symptom:** `sec_executive_record` has 0 rows in the dev canonical silver despite 11 DEF
   14A + 12 DEFA14A bronze attachments being present for the loaded universe.
2. **Why:** `_derive_employed_by` (`edgar_warehouse/mdm/pipeline.py:1119-1217`) reads from
   `sec_executive_record` — if that table is empty, the deriver has nothing to read regardless
   of correctness. The deriver itself is not implicated (07-03/06-01 already established it as
   correct; not touched here).
3. **Why is `sec_executive_record` empty:** it is populated by
   `run_bootstrap_fundamentals_per_filing` (`edgar_warehouse/application/workflows/
   fundamentals_ingest.py:58-162`), which fetches each DEF 14A filing's **primary** attachment
   from `sec_filing_attachment` (`is_primary=True`) and calls `parse_proxy_fundamentals`
   (`edgar_warehouse/parsers/proxy_fundamentals.py`), which wraps edgartools'
   `edgar.proxy.html_extractor.extract_summary_compensation`.
4. **Why would the parser produce zero rows for all 11+12 filings:** tested directly —
   `parse_proxy_fundamentals` was run against a real, live-fetched DEF 14A filing (Apple Inc.,
   accession `0001308179-25-000008`, fetched directly from
   `www.sec.gov/Archives/edgar/data/320193/.../aapl4359751-def14a.htm`) and correctly extracted
   **5 executive compensation rows** (Tim Cook CEO $74.6M total comp, etc.) with plausible
   values. This rules out an import error, a dependency/version break, or a wholesale extractor
   failure — the parser and its edgartools dependency work correctly against real-world proxy
   HTML when a standard Summary Compensation Table is present.
5. **Why then does the loaded dev universe's specific 11+12 filings still show zero:** **not
   conclusively determined in this execution** — the dev universe's actual DEF 14A/DEFA14A
   bronze content was not reachable (see "Environment / worktree provenance note": AWS creds
   here resolve to the decommissioned account, not dev `690839588395`). Two plausible,
   non-exclusive explanations were identified but NOT confirmed against the actual filings:
   - **(a) DEFA14A is not always the annual-meeting proxy.** 12 of the 23 attachments are
     `DEFA14A` ("additional soliciting material") — these are frequently supplemental
     documents (investor presentations, merger/M&A communications) that structurally may
     contain no Summary Compensation Table at all. A `{"sec_executive_record": []}` return for
     these would be a **correct** empty result, not a bug.
   - **(b) Smaller Reporting Company scaled disclosure.** SEC Reg S-K Item 402(l)-(r) permits
     smaller reporting companies to use scaled/narrative executive-compensation disclosure that
     does not require the standard multi-column Summary Compensation Table format the
     extractor's heuristics (`_find_section_table` keyed on the literal phrase "summary
     compensation table"; `_build_column_map(..., min_columns=4)`) are built to recognize. If
     the loaded dev universe (18,034 tracked companies, not limited to large-caps) skews toward
     smaller/micro-cap issuers, this would produce genuine (not-a-bug) misses at scale.

### Conclusion — EDGE-09 disposition

**This is neither "populated-and-graph-verified" nor a "source-coverage exclusion."** The
artifact is present and fetchable (already captured), the deriver is correct, and the parser
demonstrably works on real-world DEF 14A content — so this does not meet the bar for a
source-coverage exclusion (the source is not absent or unfetchable). At the same time, no
code-level bug was found and confirmed against the actual affected filings, so no fix was
applied — applying a speculative fix (e.g., loosening the SCT-detection heuristic) without
being able to verify it against the real failing filings' HTML risked producing a
false-green (a "fix" that looks plausible but does not address the actual failures, or worse,
starts accepting non-SCT tables as SCT data).

**Disposition:** EDGE-09 is root-caused to the extent possible without dev-environment access
and is left as a **documented, scoped follow-up requiring live dev silver access**: pull the
actual bronze HTML for the specific 11 DEF 14A + 12 DEFA14A accessions in the loaded universe
(same read-only method 06-03 Task 3 used: `s3://edgartools-dev-warehouse/warehouse/silver/
sec/silver.duckdb` → `sec_filing_attachment`/`sec_raw_object`) and run
`parse_proxy_fundamentals` against each to determine, per filing, whether (a) it genuinely
lacks an SCT (DEFA14A supplemental material, or SRC scaled disclosure — both are legitimate
empty results, not bugs) or (b) the extractor's heuristic fails against a real, present SCT
table (a genuine parser bug requiring a targeted fix). This is recorded for the 06-06 closure
ledger as an open item, not a false "exclusion" or false "populated" claim.

**No code was fetched or modified for EDGE-09** — no fetch was performed (nothing to fetch
under DEC-009, the artifact is already captured), and no parser change was made without
confirming evidence.

---

## EDGE-11: INSTITUTIONAL_HOLDS (13F-HR → sec_thirteenf_holding)

### 06-03 classification (carried forward)

Per `claude/consolidate-workstreams`'s completed 06-03 Task 3 evidence: **ARTIFACT PRESENT,
SILVER EMPTY** — 61 `13F-HR` filings present in the loaded dev universe's captured-filing
feed, but `sec_thirteenf_holding` = 0 rows. Classified as a parser gap, not a missing
artifact.

### 5-whys

1. **Symptom:** `sec_thirteenf_holding` has 0 rows in the dev canonical silver despite 61
   `13F-HR` filings being present for the loaded universe.
2. **Why:** `_derive_institutional_holds` (`edgar_warehouse/mdm/pipeline.py:1335-1449`, the
   06-01 CIK-range batched deriver) reads from `sec_thirteenf_holding` — if that table is
   empty, the (correct, batched) deriver has nothing to read.
3. **Why is `sec_thirteenf_holding` empty:** it is populated by `run_bootstrap_thirteenf`
   (`edgar_warehouse/application/workflows/fundamentals_ingest.py:248-357`), which locates the
   filing's "INFORMATION TABLE" attachment in `sec_filing_attachment` (matching
   `"INFORMATION TABLE" in description-or-document_type` or `"INFOTABLE" in filename`) and
   calls `parse_thirteenf` (`edgar_warehouse/parsers/thirteenf.py`, wrapping edgartools'
   `edgar.thirteenf.parsers.infotable_xml.parse_infotable_xml`). If no matching attachment is
   found, the filing is skipped (`thirteenf_no_infotable` event) — **every** filing, not some.
4. **Why would every 13F-HR filing be missing its INFORMATION TABLE attachment:** tested the
   parser in isolation first — fetched a real, live 13F-HR filing (Berkshire Hathaway,
   accession `0001193125-26-226661`, period 2026-03-31) and its actual INFORMATION TABLE XML
   attachment (`53405.xml`) directly from SEC EDGAR, and ran `parse_thirteenf` against it: it
   correctly returned **90 holding rows** (e.g. Ally Financial, CUSIP `02005N100`, 12,719,675
   shares, $498,992,850 market value). **The XML parser is not broken.** The gap must therefore
   be upstream, in how (or whether) the INFORMATION TABLE attachment ever gets fetched into
   bronze/silver in the first place.
5. **Root cause found:** `fetch_filing_artifacts` (`edgar_warehouse/bronze_filing_artifacts.py:
   16-100`) has a documented "fast path": whenever a filing's SEC-submissions
   `primary_document` is resolvable (true for essentially all filings, XSLT-prefixed or not —
   `_resolve_raw_document_name` returns the value as-is when there is no XSLT prefix to strip),
   it registers **only that one primary/cover document** as the filing's sole
   `sec_filing_attachment` row and never invokes the full edgartools attachment-enumeration
   fallback that would discover secondary attachments. For 13F-HR, SEC's own filing index
   confirms the *primary* document is `primary_doc.xml` (the cover page XML,
   `document_type = "13F-HR"`) and the holdings live in a **separate, non-primary**
   `INFORMATION TABLE` attachment (`53405.xml` in the tested example, `document_type =
   "INFORMATION TABLE"`). The fast path — written and commented for ownership Form 3/4/5
   filings, where the primary document IS the complete substantive content — was never
   form-type-gated, so it silently applies to 13F-HR too, and the INFORMATION TABLE attachment
   is simply never fetched or registered. `run_bootstrap_thirteenf`'s attachment lookup then
   has nothing to find for any 13F-HR filing, regardless of filing content quality.
   Confirmed live: fetching the same accession's full attachment set via edgartools' `Filing(
   ).attachments` correctly enumerates both `primary_doc.xml` (`is_primary=True`,
   `document_type="13F-HR"`) and `53405.xml` (`is_primary=False`, `document_type="INFORMATION
   TABLE"`, `description="INFORMATION TABLE FOR FORM 13F"`) — the data and the correct
   discovery mechanism both exist; the bronze-fetch fast path is what discards it.

### Fix applied (Rule 1 — bug fix)

`edgar_warehouse/bronze_filing_artifacts.py`: added `_MULTI_ATTACHMENT_FORMS = frozenset({
"13F-HR", "13F-HR/A"})` and gated the fast path (`raw_doc_name and not force and not
_read_cached_index(...)`) on `form_type not in _MULTI_ATTACHMENT_FORMS`. For 13F-HR/13F-HR/A,
`fetch_filing_artifacts` now always takes the full edgartools attachment-discovery fallback
path (`_map_edgartools_attachments`), which correctly enumerates every attachment — including
the INFORMATION TABLE — and sets `is_primary` via membership in `attachments.primary_documents`
(already correct, pre-existing logic; unchanged). Ownership (Form 3/4/5), ADV, DEF 14A, and
8-K fast-path behavior is unchanged — the gate is additive and scoped to exactly the two 13F
form values.

This is a root-cause fix, not a symptom patch: no change was made to `thirteenf.py` (the XML
parser) or to the attachment-matching string logic in `fundamentals_ingest.py` (both are
already correct) — the fix is at the actual defect, the bronze-fetch attachment-discovery
short-circuit.

**Regression tests added** (`tests/unit/test_loader_idempotency.py`):
- `test_13f_hr_bypasses_fast_path_to_discover_information_table` — asserts a 13F-HR filing
  with a known `primary_document` and `force=False` still calls the edgartools fallback
  (`get_filing`), registers both the cover page and the INFORMATION TABLE attachment, and sets
  `is_primary` correctly on each.
- `test_13f_hr_amendment_also_bypasses_fast_path` — same assertion for `13F-HR/A`.

All 9 tests in the file pass (`uv run python -m pytest tests/unit/test_loader_idempotency.py`
— 9 passed). `tests/architecture/test_boundaries.py` (7 tests) also re-verified passing —
no boundary/import-layering regression from the new module-level constant.

### DEC-009 idempotency note

No fetch was performed in this execution (no dev AWS access — see "Environment / worktree
provenance note"). The fix changes behavior for **future** fetches of 13F-HR filings not yet
cached (fresh captures will now correctly discover and fetch the INFORMATION TABLE
attachment alongside the cover page, at normal cost — one additional small XML download per
filing, no `--force`). It does **not** retroactively fix the 61 already-captured dev 13F-HR
filings: those already have a cached `sec_filing_attachment` row (cover page only) from before
this fix, and `fetch_filing_artifacts`'s `existing_rows and not force` branch trusts existing
attachment rows as complete — it will not re-discover the INFORMATION TABLE for
already-captured filings without an explicit operator-approved `--force` re-fetch (per
DEC-009: already-captured filings are skipped by default; `--force` is required to re-fetch,
and that is an explicit, deliberate repair action, not a violation of the idempotency
contract). **This --force re-fetch was not run in this execution** (no dev AWS access) and is
recorded as the concrete next step for whoever has `690839588395` access:
`edgar-warehouse bootstrap-fundamentals --mode thirteenf --cik-list <61 CIKs> --force`
(exact CLI flags to be confirmed against `edgar_warehouse/cli.py`'s current
`bootstrap-fundamentals` subparser before running), followed by `mdm derive-relationships
--relationship-type INSTITUTIONAL_HOLDS` (06-01's batched deriver) → `mdm sync-graph` →
graph-side count confirmation.

### Conclusion — EDGE-11 disposition

**Root-caused with a verified, committed fix; not yet graph-verified populated** (no dev
access in this execution to run the live derive → sync → count chain). This is the closest of
the two types to a full "populate" disposition — the fix is applied, tested, and the specific
mechanism (attachment discovery, not the XML parser) is proven correct in isolation against
real SEC data. It is explicitly **not** a source-coverage exclusion (the artifact is present,
fetchable, and now correctly discoverable going forward). Recorded for the 06-06 closure
ledger as: fix committed and unit-tested; live re-fetch (`--force`, DEC-009-compliant) +
derive + sync + graph-count verification remain as the concrete outstanding step for an
operator/agent with dev (`690839588395`) access.

---

## Summary table

| Type | 06-03 classification | Root cause found? | Fix applied? | Graph-verified? |
|------|----------------------|--------------------|--------------|------------------|
| EDGE-09 EMPLOYED_BY | ARTIFACT PRESENT, SILVER EMPTY | Not confirmed (parser works on live external test; dev-universe-specific cause needs dev silver access) | No (no confirmed target) | No (no dev access) |
| EDGE-11 INSTITUTIONAL_HOLDS | ARTIFACT PRESENT, SILVER EMPTY | **Yes** — bronze-fetch fast path skips the INFORMATION TABLE attachment for 13F-HR | **Yes** — `bronze_filing_artifacts.py` form-type gate + 2 regression tests | No (no dev access; requires `--force` re-fetch of the 61 already-captured filings, then derive→sync→count) |

Neither type ends in "graph-verified nonzero edges" as the plan's must_haves would prefer in
the ideal case — this execution had no reachable dev AWS access (see "Environment / worktree
provenance note"). EDGE-11 is fix-committed and unit-verified; EDGE-09 is an honestly
documented open investigation. Neither is mischaracterized as a source-coverage exclusion,
per the deviation-rules priority (do not dress up an unresolved gap as a false disposition).
