# Requirements: ER Data Plane (Phase 1)

workstream: er-data-plane  
status: active  
milestone: v1.0 ER data plane phase-1  
updated: 2026-07-24 (scope expand: ERDP-07 EOD)  

**Spec (source of truth for decisions):** `.scratch/er-data-plane/spec.md`  
**Schemas (normative column detail):** `.scratch/er-data-plane/assets/erdp-01-04-schema-sketches.md`  
**Detailed product specs:** `.scratch/er-data-plane/specs/ERDP-0{1,2,3,4,7}-*.md`  
**Coverage gate:** `.scratch/er-data-plane/coverage-matrix.md`  
**Existing surfaces:** `.scratch/er-data-plane/assets/erdp-05-existing-surface-read-map.md`  
**Free-source research:** `.scratch/er-data-plane/assets/free-data-sources-erdp-01-04.md`  
**EOD decision + skill unblock:** `.scratch/er-data-plane/assets/eod-price-source-decision.md`, `assets/er-skills-unblocked-with-eod.md`  
**Wayfinder map:** `.scratch/er-data-plane/map.md`

Consumers: financial-services equity-research skills / agents (Explore Gold + **ERDP-07 yfinance EOD join** + optional Street ERDP-01…04; pure-SEC Agent-Grade unchanged per ADR 0001).

**Sample universe (for acceptance tests):** MDM tracked / Decision Subject Universe active companies (CIKs with tracking_status active). Where a smaller pilot list is used, document it in the test harness README.

**Consumer-path docs location:** Platform docs live under `docs/` (or until promote: `.scratch/er-data-plane/assets/` + detailed specs). financial-services may **link** later; skill body rewrites are out of scope (C-06).

**Normative table names (plural gold):** `CONSENSUS_ESTIMATES`, `GUIDANCE_FACTS`, `EARNINGS_CALENDAR`, `TRANSCRIPT_EVENTS`.

---

## Constraints (non-negotiable)

- **C-01**: ERDP-01…04 products are **Gold Explore** (and object store for transcript bytes). They are **not** pure-SEC Decision Features and must not be injected into `subject_features` or Agent View Mode without a new ADR.
- **C-02**: ADR 0001 stands. Market prices/mcap/beta are **not** pure-SEC Decision Features. Phase-1 delivers them as **ERDP-07 Explore join** (yfinance / `PriceProvider`), not Agent-Grade bundle fields. Optional future **Gold MARKET table** in Snowflake remains phase-2.
- **C-03**: No Neo4j edges for consensus, guidance, calendar, or transcripts in this milestone.
- **C-04**: MDM is optional identity keys only (company/security); not system of record for estimate/calendar/transcript content.
- **C-05**: Schemas are **provider-agnostic** (`source_system` required where noted). Vendor selection is implementation, not a separate product.
- **C-06**: Do not rewrite financial-services ER skill bodies in this milestone (docs/pointers only if needed).
- **C-07**: Schema sketches + detailed product specs are **normative** for columns, keys, and acceptance IDs A0x.*; this file is the checkable milestone backlog.

---

## Suggested delivery order (non-binding)

1. ERDP-06 docs (boundary) + **ERDP-07** PriceProvider/WACC recipes (unblocks valuation-heavy ER skills first)  
2. ERDP-05 doc promote / checklist (include ERDP-07 join)  
3. ERDP-OPS registration patterns (for gold tables 01–04)  
4. ERDP-03 calendar  
5. ERDP-02 guidance (SEC path)  
6. ERDP-01 consensus (needs source choice)  
7. ERDP-04 transcripts (pilot universe)  
8. COV matrix alignment + Partial→Covered as acceptances land  

---

## Milestone Requirements

### ERDP-OPS — Warehouse registration (all new gold products)

- [ ] **ERDP-OPS-01**: Each new gold product (`CONSENSUS_ESTIMATES`, `GUIDANCE_FACTS`, `EARNINGS_CALENDAR`, `TRANSCRIPT_EVENTS`) is registered consistently with existing fundamentals tables: gold schema registry entry, Snowflake export path/manifest participation, and dbt `EDGARTOOLS_GOLD` model (or documented equivalent). *(partial: `EARNINGS_CALENDAR` registered 2026-07-24; `GUIDANCE_FACTS` registered 2026-07-26; 01/04 still open)*
- [ ] **ERDP-OPS-02**: Transcript object-store prefix is documented in the warehouse path catalog when platform-held bytes are used.

### ERDP-01 — Consensus estimates

**Pilot sources (locked):** primary `yahoo`; fallback `firm_manual`; optional `fmp`. Detail: `specs/ERDP-01-consensus-estimates.md` §11.1.

Implemented 2026-07-27: gold `_FACT_CONSENSUS_ESTIMATE_SCHEMA`/`CONSENSUS_ESTIMATES`
(Explore-only, no silver table — built directly from vendor/firm rows like
ERDP-03, not extracted from SEC bronze/silver), extractor
`edgar_warehouse.explore.consensus_estimates` (normalize/validate/build,
`yahoo` fetch via optional `[market]` yfinance extra + pure parser,
`firm_manual` CSV loader), dbt model + `sources.yml`/`gold.yml`, export
wiring (`gold_models.py`/`snowflake.py`/`run_manifest_builder.py`),
`REFRESH_AFTER_LOAD` allowlist entry. Docs: `docs/er-consensus-estimates.md`.
Tests: `tests/unit/test_consensus_estimates.py` (15 cases).

- [x] **ERDP-01-01**: Platform exposes Gold Explore table **`CONSENSUS_ESTIMATES`** with columns per normative schema sketch (at minimum: `cik`, `ticker`, `metric`, `period_type`, `fiscal_year`, `fiscal_quarter`, `period_end`, `estimate_value`, `unit`, `currency`, `statistic`, `as_of`, `source_system`, `source_ref`, `ingested_at`, `fact_key`).
- [x] **ERDP-01-02**: **A01.2** — Natural key retains history across `as_of`: two snapshots on different `as_of` dates for the same period are both retained (no silent overwrite). Free pilot may document best-effort/waiver for deep as_of history.
- [x] **ERDP-01-03**: **A01.1** — For a CIK in the **sample universe**, ≥1 row for `metric=eps_diluted` and ≥1 for `metric=revenue` for the latest completed fiscal quarter with non-null `as_of` (via pilot `yahoo` or `firm_manual`).
- [x] **ERDP-01-04**: **A01.4** — Sample rows join to `COMPANY` or `TICKER_REFERENCE` on `cik`.
- [x] **ERDP-01-05**: **A01.3 / A01.5** — Platform docs (see consumer-path location above) label Explore-only; beat/miss path vs `EARNINGS_RELEASES`/actuals with `as_of` ≤ print date is documented.
- [x] **ERDP-01-06**: Phase-1 **metric vocabulary minimum** accepted by ingest: at least `revenue`, `eps_diluted` (unknown metrics rejected or quarantined).
- [x] **ERDP-01-07**: `firm_manual` load path works for ≥1 test CIK (CSV/Parquet → gold).
- [x] **ERDP-01-08**: Pilot ingest implements at least one automated path with `source_system=yahoo` (or documents blocker + firm_manual-only pilot). *(parser implemented + tested; live network fetch is opt-in like ERDP-03's `ERDP03_LIVE` pattern — not exercised in CI)*

### ERDP-02 — Guidance facts

Implemented 2026-07-26: silver `sec_guidance_fact` (+ `sec_guidance_fact_reject`
quarantine), gold `_FACT_GUIDANCE_SCHEMA`/`GUIDANCE_FACTS`, extractor
`edgar_warehouse.explore.guidance_facts`, dbt model + `sources.yml`, export
wiring (`gold_models.py`/`snowflake.py`/`run_manifest_builder.py`). Docs:
`docs/er-guidance-facts.md`. Tests: `tests/unit/test_guidance_facts.py` (48
cases), `tests/unit/test_earnings_release_guidance_wiring.py` (3 cases).

- [x] **ERDP-02-01**: Platform exposes Gold Explore **`GUIDANCE_FACTS`** with columns per normative schema / detailed spec (including `value_low` / `value_mid` / `value_high`, `as_of`, optional `accession_number`, `is_non_gaap`, `source_system`, units). *(schema + gold builder + dbt + export registration; dbt compile not run — no Snowflake creds in this session)*
- [x] **ERDP-02-02**: **A02.1** — Sample 8-K with numeric guidance yields ≥1 row with at least one of low/mid/high non-null and `accession_number` set. *(verified via 5 synthetic FinancialTable-shaped fixtures covering range/point/non-GAAP/multi-metric/unrecognized-row shapes, same testing style as ERDP-03 — not yet run against a live curated set of real accessions; see D5 backfill note)*
- [ ] **ERDP-02-03**: **A02.2** — When `accession_number` present, row joins to `EARNINGS_RELEASES` or `FILING_DETAIL` on `(cik, accession_number)`. *(join query documented and accession_number correctness unit-tested; the actual Snowflake join has not been run — no warehouse access this session)*
- [x] **ERDP-02-04**: **A02.3** — Documented path for model-update prior-guide vs actual using period keys + `as_of`. *(docs/er-guidance-facts.md §5.2)*
- [x] **ERDP-02-05**: Prefer SEC-derived rows (`sec_8k` / `sec_10q` / `sec_10k`); allow `source_system=firm_manual` overrides (coexist by key including `source_system`). *(natural key includes source_system; both paths write through the same merge_guidance_facts into one gold builder)*
- [x] **ERDP-02-06**: Every published row has ≥1 of low/mid/high non-null (constraint check). *(enforced in normalize_guidance_row; violations quarantined to sec_guidance_fact_reject, not silently dropped)*
- [x] **ERDP-02-07**: Phase-1 metric minimum for SEC path: support at least `revenue` and `eps_diluted`. *(map_metric classifies both; unit-tested)*

### ERDP-03 — Earnings calendar

**Pilot sources (locked):** primary `finnhub`; fallback `yahoo` / `firm_manual`. Map bmo→`pre_market`, amc→`after_close`. Detail: `specs/ERDP-03-earnings-calendar.md` §11.1. **Verify Finnhub free license** before commercial gold load. Consumer docs: `docs/er-earnings-calendar.md`. Code: `edgar_warehouse.explore.earnings_calendar`.

- [x] **ERDP-03-01**: Platform exposes Gold Explore **`EARNINGS_CALENDAR`** with `cik`, `fiscal_year`, `fiscal_quarter`, `expected_date`, **`expected_time`** (nullable), **`timezone`** (nullable), `session` (`pre_market` | `after_close` | `during_session` | `unknown`), `status` (`estimated` | `confirmed` | `reported` | `cancelled`), `as_of`, `source_system` (full columns per schema sketch). *(schema + dbt + builder)*
- [x] **ERDP-03-02**: **A03.1** — For a sample of ≥10 CIKs from the **sample universe**, ≥80% have a forward quarter row (`expected_date` ≥ today) or a just-completed quarter with `status=reported`. If provider coverage is lower, record measured coverage and explicit waiver. *(`coverage_for_universe` unit-tested; live rate at ops load)*
- [x] **ERDP-03-03**: **A03.2** — Confirmed rows do not use `session=unknown` (estimated may). *(enforced in `normalize_calendar_row`)*
- [x] **ERDP-03-04**: **A03.3** — Documented that catalyst-calendar can list next 2 weeks of earnings from this table for tracked CIKs. *(`docs/er-earnings-calendar.md` §3; `next_n_days`)*
- [x] **ERDP-03-05**: Calendar is forward-looking; not a substitute for reactive `filing_date` on 8-K. *(docs + dbt header)*
- [x] **ERDP-03-06**: `firm_manual` load works for ≥3 CIKs. *(`load_firm_manual_csv` + unit test)*
- [x] **ERDP-03-07**: Pilot ingest implements automated path with `source_system=finnhub` (or documents license blocker + yahoo/firm_manual pilot). *(`parse_finnhub_earnings_calendar` / `fetch_finnhub_earnings_calendar`; live opt-in `ERDP03_LIVE=1`)*

### ERDP-04 — Transcript MVP

**Pilot sources (locked):** `ir_website` + `firm_manual` only; **small pilot CIK list** (not full-universe free scrape). Detail: `specs/ERDP-04-transcript-mvp.md` §10.1.

- [ ] **ERDP-04-01**: Platform exposes Gold Explore **`TRANSCRIPT_EVENTS`** with `cik`, `event_id`, `event_type`, `event_date`, `storage_uri`, `source_system`, `as_of` (full columns per detailed spec).
- [ ] **ERDP-04-02**: Text bytes live in object store **or** documented external URL referenced by `storage_uri`.
- [ ] **ERDP-04-03**: **A04.1 / A04.2** — Sample event has resolvable URI and non-empty text (or HTTP 200 external in test env).
- [ ] **ERDP-04-04**: **A04.3** — Documented path for earnings-analysis to use transcript without web search when URI present (platform docs location above).
- [ ] **ERDP-04-05**: Transcript content is not required in pure-SEC feature vectors.
- [ ] **ERDP-04-06**: Pilot supports both `firm_manual` (S3 copy) and `ir_website` (pointer-only) for ≥1 CIK each.
- [ ] **ERDP-04-07**: Pilot CIK list documented; no bulk third-party web scrape as default ingest.

### ERDP-05 — Existing-surface ER read map

- [x] **ERDP-05-01**: Maintain `.scratch/er-data-plane/assets/erdp-05-existing-surface-read-map.md` and/or promoted `docs/` copy listing Gold/MDM/graph/Bundle surfaces with grain, Explore vs Agent-Grade, watermark rules. *(ERDP-07 §9b + `docs/er-market-eod-join.md` linked; full docs/ promote of entire map may follow.)*
- [x] **ERDP-05-02**: **A05.1** — Map covers coverage-matrix footnotes F1–F12 Partial products.
- [x] **ERDP-05-03**: **A05.2** — Fail-closed Agent-Grade rules (Decision Watermark) documented.
- [ ] **ERDP-05-04**: **A05.3** — Partial → Covered promotion checklist exists per product (acceptance query); may trail implementation of ERDP-01…04.
- [x] **ERDP-05-05**: Document read paths for new Explore tables (01–04) once published (same docs home). *(partial: 03 + 07 documented; 01/02/04 when published)*

### ERDP-06 — Pure-SEC vs market boundary

- [x] **ERDP-06-01**: **A06.1** — No ERDP-01…04 schema includes price, mcap, PE, or EV columns. *(schemas in assets; market is ERDP-07 only)*
- [x] **ERDP-06-02**: **A06.2** — Serving/docs state Agent-Grade features remain pure-SEC (ADR 0001). *(`docs/er-market-eod-join.md` §1; ADR 0001)*
- [x] **ERDP-06-03**: **A06.3** — Market fields join only via **ERDP-07** (or later Gold MARKET Explore); join keys ticker|CIK + `as_of` documented for ER valuation/PT paths.
- [x] **ERDP-06-04**: Phase-2 Gold MARKET **Snowflake table** is allowed only as a separate surface outside pure-SEC features (not this milestone). *(documented non-goal)*

### ERDP-07 — Market EOD join (yfinance Explore)

**Scope expansion:** Free EOD prices unblock valuation-heavy ER skills (initiating Task 3, model-update PT, idea/sector multiples, earnings valuation sections). Pilot source: **Yahoo / yfinance**. Detail: `specs/ERDP-07-market-eod-join.md`. Consumer docs: `docs/er-market-eod-join.md`.

- [x] **ERDP-07-01**: Document Explore market join contract: resolve CIK→ticker via `TICKER_REFERENCE`/MDM; fetch EOD close/mcap/beta via `PriceProvider` (`source_system=yahoo`); join with gold fundamentals on ticker|CIK + `as_of`.
- [x] **ERDP-07-02**: **A07.1** — Sample ≥5 liquid US tickers: non-null close for a recent trading day. *(unit mock path always; live via `ERDP07_LIVE=1`)*
- [x] **ERDP-07-03**: **A07.2** — CIK→ticker→price works for ≥5 sample-universe CIKs. *(unit + opt-in live)*
- [x] **ERDP-07-04**: **A07.3** — `compute_wacc` succeeds for ≥1 CIK using gold debt/tax inputs + yfinance mcap/beta (or documented overrides).
- [x] **ERDP-07-05**: **A07.4 / A07.5** — Docs: Explore-only; forbidden in pure-SEC features; ER recipes for model-update PT, initiation comps/DCF, idea value screen, sector multiples.
- [x] **ERDP-07-06**: **A07.6** — Caching / batch guidance documented (no unbounded Yahoo calls).
- [x] **ERDP-07-07**: Optional helper: document EV = mcap + total_debt − cash using gold DERIVED + EOD mcap. *(`enterprise_value` + docs)*

### Coverage / planning integrity

- [ ] **ERDP-COV-01**: Coverage matrix remains 9 ER skills × data classes with zero blank cells.
- [ ] **ERDP-COV-02**: Every Gap cell maps to an ERDP-* requirement or explicit Out of Scope below (including non-GAAP **values** disposition).
- [ ] **ERDP-COV-03**: Spec `.scratch/er-data-plane/spec.md` stays aligned when requirements change.

---

## Out of Scope (this milestone)

- Productized **Snowflake Gold MARKET table** of daily prices (phase-2 option only) — **ERDP-07 yfinance join is in scope**.
- **Street** ratings / sell-side PT **history** (model-derived PT via ERDP-07 is in scope).
- Turnkey “peer comps pack” gold product (ad hoc comps via gold peers + ERDP-07 prices are in scope as recipes).
- Macro event calendars; IR decks as first-class Gold products.
- Segment / product-geo revenue mart (beyond raw XBRL `segment` on facts).
- **Non-GAAP metric values as a separate actuals product** (beyond `is_non_gaap` on guidance rows and any values stored on `GUIDANCE_FACTS`). Full non-GAAP actuals extraction is future work — clears prior matrix Gap for phase-1.
- Neo4j edges for estimates/calendar/transcripts.
- Subject Bundle new sections (`latest_guidance`, `upcoming_earnings`, etc.) — optional later.
- Rewriting financial-services ER skill markdown (links only, post-build).
- Thesis store, Excel model registry, order execution.
- Non-AWS architecture paths.
- Choosing a single commercial consensus/transcript vendor as a formal product decision (implementation under `source_system`; free pilots per free-data research).

## Future Requirements

- Phase-2 Gold MARKET Explore (if charted) with strict separation from pure-SEC features.
- Optional Subject Bundle ER sections with explicit grade rules.
- Non-GAAP **actuals** value extraction product (beyond guidance flags/rows).
- Promote frozen contracts into `docs/` and optional ADR addendum for ER Explore surfaces.
- financial-services skill docs linking to platform read paths after build.
- Deeper multi-`as_of` institutional consensus history (paid feed).

## Traceability

| Requirement family | Spec / asset |
|--------------------|--------------|
| ERDP-01 | `specs/ERDP-01-consensus-estimates.md` + schema sketch |
| ERDP-02 | `specs/ERDP-02-guidance-facts.md` + schema sketch |
| ERDP-03 | `specs/ERDP-03-earnings-calendar.md` + schema sketch |
| ERDP-04 | `specs/ERDP-04-transcript-mvp.md` + schema sketch |
| ERDP-05 | `assets/erdp-05-existing-surface-read-map.md` |
| ERDP-06 | `spec.md` §3.1; ADR 0001 |
| ERDP-07 | `specs/ERDP-07-market-eod-join.md`; `assets/er-skills-unblocked-with-eod.md` |
| Completeness | `coverage-matrix.md` |
| Wayfinder decisions | `.scratch/er-data-plane/map.md` Decisions so far |
| Free sources | `assets/free-data-sources-erdp-01-04.md`; `assets/eod-price-source-decision.md` |
