# 101 — Automate filing-text capture end-to-end (bronze → silver → Snowflake export)

Type: grilling
Status: open
Blocked by: 30

## Question

Ticket 30 (resolved) found that F3 (Filing/research text) cannot be promoted
from Partial to Covered because `sec_filing_text` has no automated writer at
all — only the manual, single-accession `targeted-resync --include-text`
debug path — and recommended a separate, dedicated ticket to automate
capture before any promotion checklist applies. What is the automation
design: which pipeline stage should call `extract_filing_text()`, for what
scope of filings, and how does the result reach a queryable Snowflake
surface?

## Context (confirmed live, 2026-09-07)

- **The Snowflake table exists now but is empty.** At the time ticket 30 was
  written, `sec_filing_text` didn't exist anywhere in Snowflake at all;
  since then the schema was built (`infra/snowflake/dbt/edgartools_gold/
  models/silver/sec_filing_text.sql`, `infra/snowflake/sql/bootstrap/
  11_silver_landing_schema.sql`, listed in `13_silver_landing_ingest.sql`'s
  COPY list) — but nothing populates it. Live check:
  `SELECT COUNT(*) FROM sec_filing_text` via `SnowflakeSilverReader` →
  **0 rows**. The prerequisite gap ticket 30 named is still fully open.
- **Confirmed single writer, exhaustively traced:** `upsert_filing_text()`
  (`edgar_warehouse/silver_store.py:2781`) is called only from
  `extract_filing_text()` → `edgar_warehouse/infrastructure/
  filing_artifact_service.py` → `_run_accession_resync()`
  (`edgar_warehouse/application/warehouse_orchestrator.py:6432`), reachable
  only via the `targeted-resync` CLI command's `--include-text` flag
  (defaults `True`). Zero other call sites anywhere in the codebase. None
  of `bootstrap-next`/`bootstrap-full`/`daily_incremental`/`load_history`
  ever call this path.
- **`targeted_resync` has run exactly 4 times ever in prod**, all on
  2026-08-04, all for unrelated lease-verification tickets (84/86/87),
  single-CIK scope each, 3 of 4 FAILED — nowhere near enough to populate a
  real dataset even if every write had reached canonical silver and
  Snowflake export cleanly.
- **Ticket 30 already scoped the real consumer need**, per its own ER-skill
  survey (ticket 27): only **one** skill (initiating-coverage, Task 1) has
  a stated need for filing text, and it's narrow — business description /
  risk factors / MD&A from the **latest 10-K only**, single company, no
  historical sweep. Ticket 30's own explicit warning: *"resist
  scope-creeping this into a full-text-search product no skill actually
  asked for."* This ticket should design to that actual need, not a
  broader one.
- Ticket 30's sketch of the eventual shape (unchanged, still the right
  starting point):
  1. A `sec_filing_text` (or equivalent) table fed by an **automated**
     pipeline, not the manual/backfill path.
  2. Scoped to guaranteeing the **latest annual filing's** text on
     request — not full historical coverage.
  3. A documented Subject Bundle section naming the specific text
     sections (business description, risk factors, MD&A), the same
     "documented read path" gate as tickets 28/29.

## Open sub-questions this ticket needs to resolve (not yet decided)

1. **Which pipeline stage triggers text extraction?** — **RESOLVED, see
   Answer below (Q1/Q2 combined with sub-question 2's resolution).**
2. **Trigger condition:** every 10-K as it's captured, or only on-demand
   when a consumer actually requests a company's text (matching the
   narrow, single-company stated need more precisely, avoiding capturing
   text for the ~50K+ tracked companies that never get asked about)? This
   is a real cost/scope tradeoff — extracting text for every company's
   every 10-K is a much bigger and more expensive undertaking than
   extracting on first request and caching thereafter.

   **RESOLVED via `/grilling` session, 2026-09-07 — see Answer below.**
3. **Does the existing `upsert_filing_text`/`sec_filing_text` schema
   (accession_number + text_version, `extracted_at` authority column,
   already in `PROTECTED_TABLE_REGISTRY`/`silver_protection.py`) need any
   changes** to support whichever trigger design is chosen, or is it
   already fit for purpose?
4. **Snowflake export path:** confirm `13_silver_landing_ingest.sql`'s
   existing COPY INTO wiring for `sec_filing_text` is correct and
   sufficient once rows exist locally, or whether it has its own gap
   (unverified — no rows have ever existed to test it against).

   **RESOLVED, 2026-09-07 — no gap found. See Answer below.**
5. **BeautifulSoup/text-extraction correctness at scale:** `filing_text_
   projection.py`'s extraction logic has only ever run against a handful
   of manually-resynced accessions; running it against a real cross-section
   of 10-K HTML/XBRL variety (different filer agents, different form
   sub-types) for the first time may surface parsing gaps not visible from
   the current tiny sample.

   **RESOLVED, 2026-09-07 — real defect found and fix validated live. See
   Answer below.**

## Answer

### Sub-questions 1 and 2 (trigger condition / pipeline stage) — resolved via `/grilling`, 2026-09-07

**The motivating need is not a live consumer.** Checked the one stated
consumer's actual documented workflow directly
(`initiating-coverage/references/task1-company-research.md`, read-only
per standing instruction): it says, verbatim, "Download latest 10-K from
SEC EDGAR" — it fetches from SEC directly and never touches this
platform's data. There is no existing call path a live "on-demand" design
would hook into; building one means building new request-serving
infrastructure from scratch for a consumer that doesn't ask for it today.

**The real driver, per the operator:** a system of record for which
artifacts are *required* vs. already *processed*, so unneeded
already-captured artifacts can be identified for cleanup. This reframes
the whole question away from "serve a request cheaply" toward "keep an
accurate, self-correcting ledger."

**Decision: ledger-driven background sweep, folded into `daily_incremental`
as a new stage after silver publish** — not blind bulk-extraction for
every tracked CIK, and not live/on-demand extraction. Rationale for
`daily_incremental` specifically over a new standalone Step Functions
machine: it already runs daily and already touches the full tracked-CIK
universe for company-identity/tracking-status purposes; a new standalone
machine is one more thing that can silently stop being scheduled (this
repo's CLAUDE.md documents that exact failure mode recurring for other
machines) for no cadence benefit, since nothing here needs a different
schedule than daily.

**`required` for filing-text, computed fresh at every sweep (no explicit
state/transition tracking — recomputing is cheap, reusing joins the sweep
already needs):**

1. CIK is a genuine periodic-reporting company — i.e. **not** an
   individual reporting owner, using Ticket 01's validated discriminator
   (`exclude_individual_reporting_owners_sql`) — and has ever filed a real
   periodic disclosure form (`10-K`/`10-K405`/`10-KSB`).
2. That CIK's most recent such filing's `filing_date` is within the
   **trailing 2 years** of "now" at sweep time. This ages a company out of
   `required` automatically once it stops filing annual reports
   (delisted, acquired, went private, bankrupt) — no manual status flip
   needed, matching the "computed fresh" design.
3. CIK has a real ticker in `sec_company_ticker` — tighter than
   periodic-filing history alone; excludes a company that still nominally
   files but has lost its listing.

**`processed`** = a `sec_filing_text` row already exists for that CIK's
current latest qualifying accession (existing schema — `accession_number`
+ `text_version`, `extracted_at` authority column — needs no change for
this).

**Sweep logic:** for every CIK in `required`, if not yet `processed` for
its current latest qualifying accession, extract (reuses the existing
`extract_filing_text()`/`upsert_filing_text()` machinery, currently only
invoked via `targeted-resync`, now also invoked from this new
`daily_incremental` stage — no new extraction code needed, only a new
caller + the `required` query). If a CIK is `processed` but **not** in
`required` (aged out past 2 years, lost its ticker, or turns out to be an
individual per Ticket 01's ongoing cleanup) — surface as a cleanup
candidate. **Do not delete.** Matches this repo's established
identify-then-decide-separately split (Tickets 70/71's binary-attachment
precedent) — deletion is explicitly out of scope for this ticket, to be
its own follow-on once there's a real candidate list to decide over.

**Explicitly not built by this design:**
- No live/on-demand request-time serving — no stated consumer needs it.
- No explicit tracking of *why* a CIK's required-status changed — only
  *whether* it currently is, recomputed each sweep.
- No proactive real-time re-extraction the instant a newer 10-K lands —
  the daily sweep cadence is the freshness guarantee; nothing stated
  needs tighter than that.

### New follow-on surfaced, not resolved here

The `required`/`processed` concept generalizes beyond filing-text: this
codebase already tracks a same-shaped `artifact_required` boolean for
ownership/13F/ADV artifacts (`relationship_bulk_load.py` →
`daily_artifact_resume.py`'s outcome ledger, Ticket 63), and the
binary-attachment cleanup need (Tickets 70/71) is the identical problem
one artifact type over. Whether to build one shared, general-purpose
artifact ledger across all artifact types, or keep each type's tracking
narrow and separate (as designed here for text), is a real, undecided
question — deliberately not resolved in this session to avoid scope
creep. See Ticket 102.

### Sub-question 4 (Snowflake export path) — resolved, 2026-09-07: no gap found

Traced the full chain and confirmed each link, ending in a real local
end-to-end test (not code-reading alone):

1. **Row shape matches the DDL exactly.** `upsert_filing_text`'s row dict
   (`accession_number`, `text_version`, `source_document_name`,
   `text_storage_path`, `text_sha256`, `char_count`, `extracted_at`) has
   the identical 7 field names, in the identical order, as
   `11_silver_landing_schema.sql`'s `sec_filing_text` DDL
   (TEXT/TEXT/TEXT/TEXT/TEXT/INTEGER/TIMESTAMP_TZ).
2. **The landing-buffer mechanism is generic and already proven live.**
   `@track_landing_row("sec_filing_text")` (already present on
   `upsert_filing_text`) records the exact row dict passed in, keyed by
   table name, into `LandingExportBuffer` — the same opt-in mechanism
   already used by 29 other tables. `SILVER_LANDING_EXPORT_ROOT` is
   confirmed set in prod (`deploy-aws-application.sh:1546`), so this isn't
   dead/unconfigured — it's live and running for every other table today.
3. **`sec_filing_text` is genuinely in the COPY INTO procedure's hardcoded
   table list** (`13_silver_landing_ingest.sql`'s `LOAD_SILVER_LANDING()`,
   confirmed by direct read, not assumed from the file's own header
   comment) — using the same `MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE`
   COPY + parse_sequence-backfill pattern the file's own comments say was
   "verified LIVE... before this procedure was trusted with the full
   table list." No per-table special-casing exists or is needed — plain
   TEXT/INTEGER/TIMESTAMP_TZ columns, same shape as most of the other 29
   tables.
4. **The dbt silver model has no unmet prerequisite.** `sec_filing_text.sql`
   reads from `source('edgartools_silver_landing', 'SEC_FILING_TEXT')`,
   dedupes via `qualify row_number() ... order by parse_sequence desc = 1`,
   and calls the generic `silver_not_retired()` macro — which reads a
   single shared `SILVER_LANDING_RETIREMENT` table filtered by
   `target_table` name, needing no separate per-table registration.
5. **Real local end-to-end test** (`upsert_filing_text` → `LandingExportBuffer`
   → `write_landing_export` → real Parquet file on disk, no AWS/Snowflake
   writes): produced `sec_filing_text/business_date=.../run_id=.../
   sec_filing_text.parquet` whose **native embedded schema** (checked via
   `pq.ParquetFile(...).schema_arrow`, not `pq.read_table`, which turned
   out to inject two Hive-partition-inferred `business_date`/`run_id`
   columns as a read-time artifact — caught and ruled out before trusting
   the result) is exactly the 7 expected columns, correctly typed
   (`char_count` as `int64`, `extracted_at` as `timestamp[us, tz=UTC]`),
   with no extra or missing fields.

**No fix needed for this sub-question** — the export path is correct and
already proven at scale for 29 sibling tables; `sec_filing_text` was
always going to flow through it the same way once real rows exist upstream
from Ticket 101's sweep. Nothing here blocks implementation.

### Sub-question 5 (parsing correctness at scale) — resolved, 2026-09-07: real defect found, fix validated

**Also surfaced along the way, more fundamental than sub-question 5 itself:**
of 68,412 `10-K`/`10-K405`/`10KSB`/`10KSB40` filings, **zero** have any
`sec_filing_attachment` row, and a direct S3 check confirmed zero bronze
content for a random sample too — primary documents for periodic-disclosure
filings have essentially never been captured into bronze at all (the
existing artifact-fetch pipeline is scoped to ownership/ADV/13F forms
only; this repo's own "Artifact-throttle" 5-whys entry already documents
`_configured_parser_accessions` this way). This means the sweep's first
run for any given company is a genuine SEC fetch — `extract_text_for_
accession`'s existing self-heal path (calling `refresh_filing_artifacts`
when no cached primary document exists) already handles this correctly,
but it's a real, non-trivial first-touch cost across the ~7,505-company
population (roughly 7,505 real document downloads, rate-limited), not the
near-free operation implied earlier in this ticket's discussion — worth
budgeting for, not a blocker.

**Test method:** fetched 21 real primary documents live from SEC EDGAR
(read-only, respecting the platform's normal rate limit), spanning recent
iXBRL 10-Ks (2025-2026), pre-iXBRL 10-Ks (2010-2011), `10-K405` (1997-2002),
`10KSB`/`10KSB40` (1997-2006) — chosen specifically to cross the iXBRL
mandate boundary and the plain-text/plain-HTML/modern-HTML eras. Ran
`filing_text_projection._normalize_text` (the real extraction function)
against each real document's actual bytes.

**Result: 21/21 succeeded with no exceptions, but a real, systematic defect
was found in exactly the population this feature cares about most.** All
5 recent (iXBRL-tagged) 10-Ks produced text starting with raw XBRL
metadata noise instead of readable prose — e.g. `weav-20251231 | 0001609151
| false | 2025 | FY | P5Y | 1 | 1 | iso4217:USD | xbrli:shares | ...` —
instead of business description/risk-factors/MD&A content. All 16
pre-iXBRL filings (`10-K` older, `10-K405`, `10KSB`, `10KSB40`) extracted
cleanly, starting with real prose (`UNITED STATES | SECURITIES AND
EXCHANGE COMMISSION | Washington, D.C. 20549 | FORM 10-K | ...`).

**Root cause, confirmed:** modern EDGAR filings embed an `<ix:header>`
block (containing `<ix:hidden>`, non-rendered XBRL facts required by the
iXBRL 1.1 spec) plus, in the sampled filing, 826 `display:none`-styled
elements — both invisible in a browser, but `BeautifulSoup.get_text()` has
no CSS engine and no XBRL-tag awareness, so it walks and extracts them
like any other text node. SEC's iXBRL convention places `<ix:header>`
early in document order, so the noise lands at the *start* of the
extracted text — exactly what "latest 10-K" business-description
extraction would read first. Since this affects only iXBRL-tagged filings
(SEC-mandated for all filers since ~2019), and "latest 10-K" is
structurally biased toward recent filings, this defect would hit the
*majority* of what this feature is actually meant to produce — not an
edge case.

**Fix, validated live against the same real filing:** strip `<ix:header>`
and any element with a `display:none`-containing inline style, before
calling `.get_text()`. Confirmed on `weav-20251231.htm` (accession
`0001609151-26-000016`): head text changed from the XBRL-noise example
above to `UNITED STATES | SECURITIES AND EXCHANGE COMMISSION | Washington,
D.C. 20549 | ... FORM 10-K | ANNUAL REPORT PURSUANT TO SECTION 13 or
15(d)...`, char_count essentially unchanged (422,098 vs. 435,425 —
confirms the fix removes contamination, not real content). Provably a
no-op on pre-iXBRL filings (no `<ix:header>`/`display:none` elements exist
in them at all — confirmed: the legacy-era samples in the same test batch
were already clean before this fix).

**Not yet implemented** — this is a validated finding + fix direction, not
a shipped code change. Implementing it means editing
`filing_text_projection.py`'s `_normalize_text` (a small, well-scoped
change: two `.find_all(...).decompose()` calls before the existing
`soup.get_text("\n")` line), needs `/gof-refactor-reviewer` per this
repo's hard rule before editing production code, and a regression test
pinning both the iXBRL-noise-removed case and the legacy-no-op case using
real captured filing content (not synthetic HTML — this defect is
convention-specific enough that a hand-written test fixture could
accidentally not reproduce the real shape).

Sub-question 3 (schema changes — none needed, confirmed above) is the
only remaining open item; all others (1, 2, 4, 5) are now resolved.
