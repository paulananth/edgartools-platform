# 40 — Root-cause the empty TICKER_REFERENCE pipeline

Type: research
Status: resolved
Blocked by:

## Question

`EDGARTOOLS_GOLD.TICKER_REFERENCE` and its upstream `EDGARTOOLS_SOURCE.TICKER_REFERENCE` are
both **0 rows in prod** (confirmed live, 2026-07-29), despite `TICKER_REFERENCE`'s comment
literally describing it as "mirrored from the canonical warehouse gold export." This was
discovered while grilling ticket 28 (Identity/ticker-CIK promotion criteria) — every one of the
9 financial-services ER skills surveyed in ticket 27 uses ticker or company name as its primary
input, so an empty ticker reference table is a serious, load-bearing gap, not a cosmetic one.

Initial root-cause investigation (read-only, this session) found:

1. The dbt gold model (`infra/snowflake/dbt/edgartools_gold/models/gold/ticker_reference.sql`)
   is a pure passthrough from `source("edgartools_source", "TICKER_REFERENCE")` — so the gap is
   upstream of dbt, in the warehouse's own export pipeline.
2. `edgar_warehouse/serving/gold_models.py::build_ticker_reference_table` exists and is wired
   into `edgar_warehouse/application/warehouse_orchestrator.py` (~line 648) — but the write path
   is gated: `if (... and command_name == "seed-universe" and ticker_reference_rows is not
   None)`. This means ticker-reference export **only ever fires during the one-time
   `seed-universe` command**, never during `daily-incremental`, `load_history`'s
   `bootstrap-batch`, or `gold-refresh` — the commands that actually run in ongoing operation
   per this map's Phased Pipeline.
3. Within `seed-universe` itself (~line 1440-1460), `ticker_reference_rows` is derived from
   `universe_rows` **after filtering out already-active CIKs** (`skipped_active` in the
   `seed_universe_filtered` event) — so even a CIK that *was* seeded once would only get a
   ticker-reference row from that one seeding pass, never refreshed afterward, and any CIK
   already active before this code path existed would never get one at all.
4. The real ticker data that *does* exist lives on `EDGARTOOLS_GOLD.MDM_COMPANY_ENTITY.ticker`/
   `primary_ticker` (populated for 2,713 of 32,970 companies, ~8%) — a completely different
   pipeline (MDM's Postgres-to-Snowflake export, not the warehouse `seed-universe` path) — which
   suggests `TICKER_REFERENCE` may have been effectively superseded/abandoned in practice
   without anyone updating or removing it.

**What this ticket needs to answer:** why is `TICKER_REFERENCE` empty in prod today given
`seed-universe` presumably ran at some point (32,970 companies exist in `COMPANY`) — was
`ticker_reference_rows` actually `None`/empty on that run, or did the export step run and
produce rows that then failed to land in Snowflake, or was `seed-universe` never actually the
command used to build today's 32,970-company universe (e.g., a different bootstrap path)? And:
is `MDM_COMPANY_ENTITY.ticker` the intended long-term ticker source that `TICKER_REFERENCE`
should be retired in favor of, or was `TICKER_REFERENCE` meant to be the canonical one and MDM's
ticker field is the actual gap-filler that was never finished? Investigate git history for both
pipelines, check for any error/skip logs from past `seed-universe` runs, and report a clear
root cause plus a recommended resolution path (not necessarily implemented in this ticket —
this is Type: research; a follow-up task ticket can implement the fix once the cause and
correct target are clear).

This blocks ticket 28 (Identity/ticker-CIK promotion criteria), which cannot write a real
promotion checklist for ticker resolution until the intended canonical source and fix path are
known.

## Additional angle (2026-07-29, operator-directed)

Before assuming this is purely a pipeline/export bug, verify the premise: SEC-active companies
should generally have a ticker (exchange-listed equity), so check whether the ~8% figure on
`MDM_COMPANY_ENTITY.ticker` reflects (a) a broken capture pipeline for genuinely ticker-bearing
companies, or (b) a loaded universe that includes a large share of legitimately non-ticker SEC
filers (private debt issuers, shell/blank-check companies, trusts, foreign private issuers,
delisted/deregistered companies still in the tracked set, etc.) for which a low ticker
percentage is actually correct, not a bug.

Also found a **third** ticker-bearing surface not yet reconciled against the other two
(`EDGARTOOLS_GOLD.TICKER_REFERENCE`, empty; `MDM_COMPANY_ENTITY.ticker`, ~8%): silver itself
carries ticker data via `sec_tracked_universe.current_ticker` and/or a
`sec_company_ticker`/`sec_company_sync_state` join (`edgar_warehouse/mdm/cli.py` ~lines
1128-1191, used by `seed-universe`/`seed-from-silver`'s silver import path) — determine whether
*this* silver-level source is well-populated (i.e., the real capture works fine at the silver
layer and the gap is purely in what gets exported to Snowflake) or is itself sparse (i.e., the
gap originates further upstream, in SEC ingestion itself).

**Concretely:** sample the loaded/tracked-active CIK population (26,300 of 32,970 rows have
`COMPANY.tracking_status = 'active'`) and check it against SEC's own official ticker mapping
(`https://www.sec.gov/files/company_tickers.json` or equivalent primary source — check what
`edgartools` itself uses internally to resolve tickers, since this platform depends on that
library) to establish what fraction of the *tracked/active* universe SEC itself associates with
a ticker. Compare that ground-truth fraction against the ~8% currently visible in
`MDM_COMPANY_ENTITY.ticker` and whatever is found in the three silver-layer candidates above.
Report per-source population rates and a reconciled root cause.

## Answer

### Two separate questions, two separate answers

This ticket bundles two independent questions that must be answered separately: (A) is the
low ~8-10% ticker-population figure a data-capture bug, and (B) is `TICKER_REFERENCE` being
0 rows a bug. **Answer: (A) no — the low percentage is correct, not a bug. (B) yes — 0 rows
is a genuine, isolated export-wiring defect**, unrelated to (A). Evidence for each below.

### (A) The ~8-10% ticker-population figure is correct, not a capture bug

Ground truth: fetched SEC's own official ticker mapping directly
(`https://www.sec.gov/files/company_tickers.json`, the exact source `edgartools` itself uses —
confirmed via `edgar/reference/tickers.py::get_company_tickers()` /
`edgar/urls.py::build_company_tickers_url()`, `edgar/httpclient.py` even special-cases its
cache TTL). That file contains **8,017 unique CIKs** total across all of SEC's history — i.e.
SEC itself only associates a ticker with ~8K CIKs, out of the hundreds of thousands of CIKs
that have ever filed with SEC. Tickers are an equity-listing artifact, not a property of "being
an active SEC filer."

Cross-referenced the platform's 26,300 `tracking_status='active'` CIKs directly against that
SEC file:

| Source | Active CIKs w/ ticker | % of 26,300 active |
|---|---|---|
| SEC's own `company_tickers.json` (ground truth, direct join) | 2,576 | 9.8% |
| Silver `sec_company_ticker` (join on active `sec_company_sync_state`) | 2,585 | 9.8% |
| `EDGARTOOLS_GOLD.MDM_COMPANY_ENTITY.ticker` (join on active `COMPANY`) | 2,574 | 9.8% |

All three numbers agree to within 11 rows (noise/timing) of each other and of the ground
truth. **This is the reconciliation the operator asked for: SEC's own ground truth for this
exact 26,300-CIK population is ~9.8%, and every internal source that actually has data already
matches it almost exactly.** There is no capture bug — silver and MDM are both already correct.

Why is the "true" number so low? Broken down by `COMPANY.entity_type` (from live
`EDGARTOOLS_GOLD.COMPANY`, `WHERE tracking_status='active'`):

| entity_type | count | matched vs SEC | match rate |
|---|---|---|---|
| operating | 2,462 | 1,795 | 72.9% |
| other | 23,395 (88.9% of active universe) | 779 | 3.3% |
| investment | 443 | 2 | 0.5% |

The tracked/active universe is overwhelmingly (89%) `entity_type='other'` — sampling those
rows shows broker-dealers (Cantor Fitzgerald, Cape Securities), investment
advisers/asset-managers (Capital Research & Management, Invesco Advisers, Virtus Investment
Advisers), individual insiders/reporting persons (e.g. "CARSON BENJAMIN SR"), trusts, insurance
companies, and even a foreign sovereign issuer ("REPUBLIC OF CHILE") — none of which are
exchange-listed equity and none of which SEC itself lists in `company_tickers.json`. The
`operating` subset (genuine SEC-registered issuers, 9.4% of the active universe) matches SEC's
ticker file at 72.9% — the residual 27% is explained by legitimately non-ticker operating
filers still in scope (private debt-only issuers, foreign private issuers not using a US
ticker, deregistered/delisted names still marked `active` pending a Form 15 sweep). **Operator
hypothesis (b) confirmed**: the low aggregate percentage is a direct, expected consequence of
this platform's tracked universe including the full population of ownership/13F/ADV-derived
CIKs (insiders, managers, advisers), not a defect in ticker capture for the equity-issuer
subset that should have one.

### The "third source" (`sec_tracked_universe`) does not exist — it's a dead legacy table

Downloaded and queried the live prod silver DuckDB directly
(`s3://edgartools-prod-warehouse-690839588395/warehouse/silver/sec/silver.duckdb`, 994 MB, no
sharding in prod today — single-file silver, not the sharded layout `ShardedSilverReader`
otherwise supports). `sec_tracked_universe` **does not exist as a table** in this live database.
Confirmed this is by design/known, not an oversight discovered this session:
`edgar_warehouse/silver_support/sharded_reader.py:86` lists it in `_TABLES` with the comment
`# legacy table; best-effort`, and `tests/unit/test_silver_store_counts.py` has a standing
regression test (`test_get_table_counts_reports_missing_legacy_tables_as_zero`) that literally
asserts `counts["sec_tracked_universe"] == 0` on a fresh `SilverDatabase`. The
`_seed_mdm_from_silver` code in `edgar_warehouse/mdm/cli.py` (~1128-1191) always hits the
`try/except` fallback path — `SELECT ... FROM sec_tracked_universe` raises, and the code
transparently falls back to `sec_company_ticker t LEFT JOIN sec_company_sync_state s`. So there
are really only **two** independent ticker sources in this platform, not three:

1. **Silver `sec_company_ticker`** (root source) — 21,028 rows, **8,056 distinct CIKs**,
   populated by a dedicated sync job (`source_name='company_tickers'` /
   `'company_tickers_exchange'`, refreshed same-day per `last_synced_at` in the live table).
   8,056 vs SEC's own 8,017 unique CIKs is a near-exact match (small excess plausibly from
   multi-exchange/timing dedup) — **this pipeline is healthy and essentially complete**.
2. **`MDM_COMPANY_ENTITY.ticker`/`primary_ticker`** — populated by `mdm/universe.py`'s
   `bulk_upsert_universe`, which is fed by exactly the `_seed_mdm_from_silver` →
   `sec_company_ticker` fallback path above. It is therefore *derived from* silver
   `sec_company_ticker`, not an independent capture — explaining why its population number
   (2,574/26,300 active) tracks silver's (2,585/26,300) almost exactly.

### (B) `TICKER_REFERENCE` = 0 rows is a real, isolated bug — re-confirmed live

Re-verified live: `EDGARTOOLS_GOLD.TICKER_REFERENCE` and `EDGARTOOLS_SOURCE.TICKER_REFERENCE`
are both still 0 rows. This is **not** explained by the population-rate finding above — even
restricted to the ~10% of the universe that legitimately has a ticker, the export should be
non-zero if it had ever run successfully against the current universe and stayed wired in. It
is 0 because of the structural gating bug the prior investigation (session start, items 1-3 in
the Question section above) already found and this session re-confirmed by reading the code
directly (`edgar_warehouse/application/warehouse_orchestrator.py` lines 642-687 and
1404-1460):

- The export only fires `if command_name == "seed-universe"` (line 645) — never on
  `daily-incremental`, `load_history`'s `bootstrap-batch`, or `gold-refresh`, none of which are
  `seed-universe`.
- `seed-universe` is documented in this repo's own map (`CLAUDE.md`'s Phased Pipeline table) as
  a one-time universe-seeding step, not part of ongoing operation — `load_history` is the
  canonical loader for scale, and it never touches this code path at all.
- Live silver evidence supports "ran at most once, long ago, for a small batch": the live
  `pipeline_run` table has exactly 1 row total (`parse-adv-bronze`) and `sec_sync_run` (303
  rows) shows only `sync_mode='bootstrap'` entries — no `seed_universe`-mode run is visible in
  the current silver snapshot's own tracking tables. This is consistent with (not conclusive
  proof of) `seed-universe` having last run, if ever, before or outside the window these
  tracking tables currently retain — plausible given 32,970 companies already existed before
  this session and no `seed-universe` executions appear in accessible history.
- The schema of `build_ticker_reference_table()` (`edgar_warehouse/serving/gold_models.py:1329`)
  — `cik, ticker, exchange, last_sync_run_id` — is *identical in shape* to silver's
  `sec_company_ticker` table, confirming `TICKER_REFERENCE` was designed as a straight export of
  that same data, just wired to the wrong (one-time) trigger.

No evidence of a failed export attempt (no error rows, no partial manifest) was found — the
simplest explanation consistent with all evidence is that the gate itself has simply never
fired under real operating conditions since `load_history`/`bootstrap-batch` became the
standard loading path, not that an export ran and silently failed.

### Reconciliation (direct answer to the ticket's core question)

**`MDM_COMPANY_ENTITY.ticker` is not "the gap-filler that was never finished" and
`TICKER_REFERENCE` was not secretly correct all along — both readings in the original Question
section are partially right.** `TICKER_REFERENCE` genuinely is broken (gating bug, confirmed).
But the *data it should contain* already exists, essentially completely and correctly, in two
other places (silver `sec_company_ticker`, and downstream `MDM_COMPANY_ENTITY.ticker`) — this
is not a data-recovery problem, it is a plumbing problem. The apparent "~8%" alarm is a red
herring caused by conflating two unrelated facts (empty export table; low ticker % on the
active universe) that happen to have surfaced in the same grilling session.

### Recommendation (research only — not implemented here)

1. **Canonical source going forward: silver `sec_company_ticker`.** It is the actual root
   capture (fed from `edgartools`'s own SEC `company_tickers.json`/`company_tickers_exchange`
   fetch), already continuously refreshed, and already verified to match SEC ground truth to
   within noise. `MDM_COMPANY_ENTITY.ticker` should be treated as a derived/denormalized copy
   of it (which it already structurally is), not a second source of truth.
2. **Concrete fix for `TICKER_REFERENCE`:** stop deriving it from `seed-universe`'s
   in-memory `universe_rows`/`ticker_reference_rows` entirely. Rewire `build_ticker_reference_table`
   to read directly from silver `sec_company_ticker` (same schema already: `cik, ticker,
   exchange, last_sync_run_id`) and fire the export from **`gold-refresh`** — the one command
   this repo's own Phased Pipeline names as "the sole gold builder" and which already runs on
   every load. This both fixes the 0-row bug and gives `TICKER_REFERENCE` a live, ongoing
   refresh cadence instead of a one-time snapshot.
3. **For ticket 28 (Identity/ticker-CIK promotion criteria):** do not write acceptance
   criteria assuming full-universe ticker coverage is the target. The correct target
   population for "ticker coverage" criteria is the ticker-*eligible* subset (SEC-listed
   equity issuers — roughly `entity_type='operating'` plus any others that appear in SEC's own
   `company_tickers.json`), not the full 26,300-row active/tracked universe, which by design
   includes non-equity filers (insiders, advisers, broker-dealers, trusts). A criterion like
   "100% of active companies have a ticker" would be unachievable and wrong; a criterion like
   "≥X% of SEC-ticker-eligible active companies (cross-checked against SEC's own
   `company_tickers.json`) have a ticker in the canonical source" is the correct shape.

## Addendum (2026-07-29, CUSIP cross-check)

Operator asked for a fourth cross-reference dimension — CUSIP — to further verify that missing
tickers really do correspond to non-trading companies, not just infer it from `entity_type`.
`MDM_SECURITY.cusip` turned out to be unpopulated (0 of 97 rows) — not a usable source. Found
and used instead: `EDGARTOOLS_GOLD.INSTITUTIONAL_HOLDINGS` (6.8M 13F holding rows, CUSIP +
`issuer_name` populated for all rows, 41,225 distinct CUSIPs). 13F only covers Section 13(f)
securities (common stock and a narrow set of equity-like instruments), so a company's name
appearing there is a real signal of being an actively-held tradeable security — independent of
whether our ticker source has it.

**Method:** built a CUSIP→issuer-name lookup from `INSTITUTIONAL_HOLDINGS` (one representative
name per CUSIP), normalized both that and `COMPANY.entity_name` (uppercase, strip punctuation
and common corporate suffixes — INC/CORP/LLC/LP/CLASS A/etc.), and joined on normalized name
against the 26,300 active CIKs.

**Crosstab (active universe, N=26,300):**

| | has_ticker | no_ticker |
|---|---|---|
| **matched a 13F CUSIP by name** | 1,478 | **149** |
| **no 13F match** | 1,096 | 23,577 |

The bottom-right cell (23,577, 89.6% of the active universe) has no ticker **and** no 13F
evidence of being an actively-held security — strongly reinforces the original finding: these
are the non-equity filer types (insiders, advisers, broker-dealers, trusts) already identified
via `entity_type`.

**The top-right cell (149 CIKs) is the one worth real scrutiny** — no ticker, but the name
matches a CUSIP that institutional managers actually hold. Manually reviewed a random sample of
25 of these 149 (not the full set — this is a spot-check, not an exhaustive audit):

- **Genuine capture gaps** (currently-traded companies missing from the ticker source) —
  roughly 5-6 of 25: e.g. NKGen Biotech (Nasdaq NKGN), Soleno Therapeutics (Nasdaq SLNO),
  Canna-Global Acquisition Corp, Signing Day Sports — real misses worth fixing once ticket 40's
  export pipeline is rewired.
- **Legitimately non-ticker for reasons the CUSIP match doesn't capture** — the majority,
  roughly 16-18 of 25:
  - Gone private / acquired, CIK still exists with historical filings (Dell Inc's pre-2013 CIK,
    General Re Corp post-Berkshire acquisition, Yahoo Inc post-Verizon/Apollo).
  - Debt-only or structured-finance CUSIPs, not equity (Burlington Northern Santa Fe LLC —
    Berkshire-owned since 2010, issues public bonds; CIFC Funding 2019-VI Ltd and CrossCountry
    Intermediate Holdco LLC — CLO/SPV note issuers).
  - Foreign-exchange-listed only, no US ticker (Kioxia Holdings Corp — Tokyo Stock Exchange).
  - Non-traded REIT/BDC (Cottonwood Communities Inc).
  - Fund-complex trusts (Thrive Series Trust, Build Funds Trust, Putnam ETF Trust, ARK Venture
    Fund, Harris Oakmark ETF Trust) — these CIKs are trust wrappers containing multiple
    series/share classes, each with its own ticker; a single trust-level CIK correctly has no
    single ticker of its own.
  - **A real limitation of the name-matching method, not a data gap**: at least 2-3 samples
    (Charter Communications Holdings LLC, GCM Grosvenor Holdings LLC, Scilex Inc) matched a
    CUSIP that actually belongs to a *related but distinct, separately-traded* parent/affiliate
    entity (Charter Communications Inc/CHTR, GCM Grosvenor Inc/GCMG, Scilex Holding
    Company/SCLX) — the subsidiary/operating-entity CIK correctly has no ticker of its own, but
    normalized-name matching conflated it with its publicly-traded parent's CUSIP.

**Conclusion:** the CUSIP cross-check confirms the original finding rather than overturning it
— the large majority of "missing ticker" cases are correctly non-ticker (non-equity filer
types, gone-private, foreign-listed, structured debt, or parent/subsidiary name-matching
artifacts), consistent with entity_type alone. But it also surfaces a small, real, non-zero set
(a low-single-digit percentage of the 149, so a small fraction of a percent of the full 26,300
active universe) of genuine capture gaps worth fixing — this refines rather than replaces the
recommendation above: once `TICKER_REFERENCE` is rewired onto silver `sec_company_ticker`
(recommendation above), spot-check that these specific sampled companies (NKGen Biotech, Soleno
Therapeutics, etc.) actually pick up a ticker as a smoke test that the fix closes real gaps, not
just the already-healthy 9.8%.

**Caveat on precision:** the 25-sample categorization above is manual/eyeballed from company
names and general knowledge, not independently verified per-company against a live listing
check — treat the "5-6 genuine gaps out of 25" split as an informative order-of-magnitude
estimate, not an audited count.
