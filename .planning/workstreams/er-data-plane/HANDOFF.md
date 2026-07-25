# Handoff: ER data plane phase-1

**Date:** 2026-07-25  
**Repo:** `edgartools-platform`  
**Workstream:** `.planning/workstreams/er-data-plane/`  
**Status:** Stopped after **ERDP-07** + **ERDP-03**. Planning complete for full phase-1; implementation partial.

Resume when you have bandwidth for remaining tickets (ERDP-02 guidance, ERDP-01 consensus, ERDP-04 transcripts, OPS finish).

---

## Where things live

| Artifact | Path |
|----------|------|
| Milestone requirements | `.planning/workstreams/er-data-plane/REQUIREMENTS.md` |
| This handoff | `.planning/workstreams/er-data-plane/HANDOFF.md` |
| Planning pack (spec, matrix, detailed specs) | `.scratch/er-data-plane/` |
| Wayfinder map | `.scratch/er-data-plane/map.md` |
| Consumer docs (promoted) | `docs/er-market-eod-join.md`, `docs/er-earnings-calendar.md` |
| Market / EOD code | `edgar_warehouse/market/` (`eod_join.py`, `price_provider.py`, `wacc.py`) |
| Calendar Explore code | `edgar_warehouse/explore/earnings_calendar.py` |
| Gold schema | `edgar_warehouse/config/gold_schemas.yaml` (`_FACT_EARNINGS_CALENDAR_SCHEMA`) |
| dbt | `infra/snowflake/dbt/edgartools_gold/models/gold/earnings_calendar.sql` |
| Tests | `tests/unit/test_market_eod_join.py`, `tests/unit/test_earnings_calendar.py` |

**Related (not this PR):** financial-services skill quality review scratch under `financial-services/.scratch/skill-quality-review/` — planning context only; skill body rewrites out of scope (C-06).

---

## Done (landed)

### Planning (destination reached earlier)

- Coverage matrix, schemas, REQs, free-source locks, ERDP-01…07 product specs under `.scratch/er-data-plane/`.
- Pilot free sources locked:
  - **ERDP-01 consensus:** `yahoo` (+ `firm_manual` / optional `fmp`)
  - **ERDP-02 guidance:** SEC path (`sec_8k` / `sec_10q` / `sec_10k`) + `firm_manual`
  - **ERDP-03 calendar:** `finnhub` primary; `yahoo` / `firm_manual` fallback
  - **ERDP-04 transcript:** `ir_website` + `firm_manual` (small pilot CIK list only)
  - **ERDP-07 EOD:** yfinance / existing `PriceProvider`

### ERDP-07 — Market EOD join (Explore)

- Join helpers: CIK→ticker, EOD snapshot, EV, batch cache guidance.
- Docs + unit tests; live opt-in: `ERDP07_LIVE=1` + `uv run --with yfinance`.
- Explore-only; ADR 0001 / pure-SEC features unchanged.
- REQs **ERDP-07-*** and **ERDP-06-*** checked.

### ERDP-03 — Earnings calendar (Gold Explore)

- Normalize / firm_manual CSV / Finnhub parse+fetch / mark_reported / coverage / next-N-days.
- Gold schema, serving export helper, dbt `EARNINGS_CALENDAR` with `is_current`.
- Docs + unit tests; live Finnhub: `ERDP03_LIVE=1` + `FINNHUB_API_KEY`.
- REQs **ERDP-03-*** checked.
- **Ops gate:** verify Finnhub free-tier license before commercial gold load.

### Partial

- **ERDP-OPS-01:** only `EARNINGS_CALENDAR` registered so far (schema/export/dbt).
- **ERDP-05:** map updated for 03 + 07; full promote of entire read map and Partial→Covered checklist still open.

---

## Not done (resume here)

Suggested order (matches REQUIREMENTS):

1. **ERDP-02** — `GUIDANCE_FACTS` (SEC 8-K/10-Q/K extraction path + firm_manual; prefer numeric low/mid/high).
2. **ERDP-01** — `CONSENSUS_ESTIMATES` (`yahoo` pilot + firm_manual; as_of history; metric min `revenue` + `eps_diluted`).
3. **ERDP-04** — `TRANSCRIPT_EVENTS` + object-store/pointer pilot (small CIK list; no bulk scrape).
4. **ERDP-OPS** — finish registry/export/dbt for 01, 02, 04; transcript path catalog.
5. **ERDP-05** — promotion checklist Partial→Covered; optional promote full read map under `docs/`.
6. **COV** — flip coverage-matrix cells as acceptances land.
7. **financial-services** — optional skill doc *links* only after products exist (no skill body rewrite).

---

## Commands to verify

```bash
cd edgartools-platform
uv run python -m unittest tests.unit.test_market_eod_join tests.unit.test_earnings_calendar -v

# Optional live:
ERDP07_LIVE=1 uv run --with yfinance python -m unittest \
  tests.unit.test_market_eod_join.LiveYfinanceAcceptanceTests -v
ERDP03_LIVE=1 FINNHUB_API_KEY=… uv run python -m unittest \
  tests.unit.test_earnings_calendar.LiveFinnhubTests -v
```

---

## Constraints (do not regress)

- **C-01 / ADR 0001:** ERDP-01…04 and ERDP-07 are **Explore**, not Agent-Grade / not `subject_features`.
- **C-02:** No price/mcap/PE inside pure-SEC Decision Features; no Gold MARKET Snowflake table in this milestone (phase-2 only).
- **C-03:** No Neo4j edges for consensus/guidance/calendar/transcripts this milestone.
- **C-06:** Do not rewrite financial-services ER skill markdown bodies.

---

## Active workstream note

When this handoff was written, `.planning/active-workstream` pointed at **`fix-pipelines`** (unrelated ADV/production work). ER workstream files live under `er-data-plane/` — do not mix commits with ADV pipeline branches. Branch for this land was cut from `main`.

---

## Open ops / legal

- Finnhub free license check before publishing calendar to commercial gold.
- Yahoo / yfinance ToS for consensus + EOD pilot scale (caching guidance in ERDP-07 docs).
- Pilot CIK list for transcripts still to document when ERDP-04 starts.

---

*End handoff — resume at ERDP-02 or ERDP-OPS as preferred.*
