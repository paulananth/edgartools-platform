# ER data plane — wayfinder map

Label: `wayfinder:map`  
Repo: **edgartools-platform** only (financial-services owns ER skills; this effort owns platform requirements).

## Destination

A locked **phase-1 ER data plane plan** for edgartools-platform: requirements live in [`.scratch/er-data-plane/spec.md`](./spec.md), completeness proven by [`.scratch/er-data-plane/coverage-matrix.md`](./coverage-matrix.md) (9/9 ER skills, zero unclassified required inputs). Phase-1 products: consensus, guidance values, earnings calendar, transcript MVP, existing-surface read paths, pure-SEC vs market boundary, **and ERDP-07 yfinance EOD Explore join** (scope expand). REQUIREMENTS at `.planning/workstreams/er-data-plane/REQUIREMENTS.md`. Durable product docs (`docs/…`, ADRs) are promoted **after** decisions land — not before.

**Status: DESTINATION REACHED** (2026-07-24) — REQUIREMENTS published. **Implementation:** ERDP-07 + ERDP-03 + ERDP-02 landed; ERDP-01/04 gold products still open.

## Notes

- **Domain:** SEC warehouse (bronze→silver→gold/MDM/Neo4j/Subject Bundle); consumer is financial-services ER skills / agents.
- **Consult each session:** this map; `docs/agents/issue-tracker.md`; `docs/adr/0001-agent-decision-surface-first.md`; `docs/data-architecture.md`; assets in `./assets/`.
- **Completeness gate:** coverage matrix — Covered requires named product + read path + acceptance criterion; else Partial / External / Gap / N/A. Blank cells = incomplete.
- **Phase-1 in scope:** consensus schema+source policy; guidance values; earnings calendar; transcript store-or-pointer MVP; how ER agents read existing Gold/MDM/Bundle; pure-SEC vs market join boundary.
- **Phase-1 out of execution for this map:** implementing pipelines; rewriting ER skills; thesis/Excel workflow stores; full ratings history; macro calendars (unless graduated later).
- **Tracker:** local markdown `.scratch/er-data-plane/` per issue-tracker.md.
- **Plan, don't build** until destination is reached (spec + matrix complete + REQs generatable).

## Decisions so far

- **Repo of record** — Platform requirements and this map live in **edgartools-platform**, not financial-services.
- **Artifact homes** — Spec: `spec.md`; later milestone REQs: `.planning/workstreams/er-data-plane/REQUIREMENTS.md`; promote to `docs/` after decisions.
- **Completeness method** — Full skill × data-class matrix; phase-1 may mark non-P0 as Out of scope / External without leaving blanks.
- **Phase-1 product focus** — P0 gaps from gap analysis (consensus, guidance values, calendar, transcript MVP) + existing-surface contracts + pure-SEC boundary; prices/mcap productization deferred unless a ticket pulls them in.
- [Seed and freeze coverage matrix](./issues/04-seed-and-freeze-coverage-matrix.md) — Matrix frozen, 0 blanks; no Covered yet (await ERDP-05); Gaps → ERDP-01…04; market/ratings/macro/news → External; footnotes F1–F12 for Partial products. See [coverage-matrix.md](./coverage-matrix.md).
- [Existing-surface ER read map](./issues/05-existing-surface-er-read-map.md) — ERDP-05 draft: Gold + MDM + graph + Subject Bundle read paths, watermark rules, ER limitations. Asset: [erdp-05-existing-surface-read-map.md](./assets/erdp-05-existing-surface-read-map.md); summary in [spec.md](./spec.md) §5.
- [Confirm phase-1 product list](./issues/01-confirm-phase1-product-list.md) — Phase-1 = **ERDP-01…06 only**. Prices/mcap, segment mart, peer comps, ratings/PT, macro, IR decks deferred/External.
- [Pure-SEC vs market boundary for ER](./issues/03-pure-sec-vs-market-boundary.md) — **ERDP-06 locked:** ADR 0001 stands; phase-1 market = External only; optional future Gold MARKET Explore (phase-2) never mixed into pure-SEC features; join by ticker/CIK + as_of.
- [Layer placement for new ER products](./issues/02-layer-placement-new-products.md) — **ERDP-01…04 SoR = Gold Explore** (transcript = object store + gold pointer); MDM keys optional; no graph; no Bundle in phase-1; market still External.
- [Draft phase-1 schemas and acceptance criteria](./issues/06-draft-phase1-schemas-acceptance.md) — Schemas + A01–A06 accepted; asset [erdp-01-04-schema-sketches.md](./assets/erdp-01-04-schema-sketches.md); `spec.md` §6. Unblocks REQUIREMENTS generation.
- [Generate planning REQUIREMENTS.md](./issues/07-generate-planning-requirements.md) — [`.planning/workstreams/er-data-plane/REQUIREMENTS.md`](../../.planning/workstreams/er-data-plane/REQUIREMENTS.md) published; planning destination reached.

## Not yet specified

- Consensus **provider** choice (vendor vs firm feed vs multi-source) — implementation detail under A01 source_system
- Transcript: how much text is retained vs pointer-only in ops (schema allows both)
- Exact Subject Bundle section additions for ER (optional later)
- How financial-services skills document platform contracts — after REQUIREMENTS / build
- Phase-2 Gold MARKET schema details (only if/when that effort is charted)
- Pilot EOD source decided: **Yahoo / yfinance** (External Explore) — [assets/eod-price-source-decision.md](./assets/eod-price-source-decision.md)
- **Scope expand:** **ERDP-07** market EOD join in phase-1 (not gold table); unblocks valuation-heavy ER skills — [assets/er-skills-unblocked-with-eod.md](./assets/er-skills-unblocked-with-eod.md); [specs/ERDP-07-market-eod-join.md](./specs/ERDP-07-market-eod-join.md); REQUIREMENTS updated
- **Pilot free sources locked:** consensus=`yahoo` (+firm_manual); calendar=`finnhub` (+yahoo/firm_manual); transcript=`ir_website`+`firm_manual` — [assets/free-sources-consensus-calendar-transcript.md](./assets/free-sources-consensus-calendar-transcript.md)
- **ERDP-07 implemented (Explore):** `edgar_warehouse/market/eod_join.py` + `docs/er-market-eod-join.md` + `tests/unit/test_market_eod_join.py`; ERDP-06 boundary docs done; REQs ERDP-07-* checked.
- **ERDP-03 implemented (Explore gold):** `edgar_warehouse/explore/earnings_calendar.py` + dbt `EARNINGS_CALENDAR` + `docs/er-earnings-calendar.md` + unit tests; REQs ERDP-03-* checked; Finnhub commercial license still ops gate.
- **ERDP-02 implemented (Explore gold, 2026-07-26):** `edgar_warehouse/explore/guidance_facts.py` (SEC extractor over `EarningsRelease.guidance` + `firm_manual` CSV loader) + silver `sec_guidance_fact`/`sec_guidance_fact_reject` + dbt `GUIDANCE_FACTS` + `docs/er-guidance-facts.md` + 51 unit tests; REQs ERDP-02-01/02/04/05/06/07 checked, ERDP-02-03 (live Snowflake join) and dbt compile still open — no warehouse creds available in-session. A02.1 verified via synthetic FinancialTable fixtures, not a live curated accession set (D5 backfill also not yet run).



## Out of scope

- Implementing Gold/MDM/Neo4j code in this planning map
- Rewriting financial-services ER skill bodies
- Firm thesis store / model file registry as platform products
- Macro event calendars (unless destination redrawn)
- Non-AWS architecture paths
- **Phase-1 build scope excludes:** productized gold market prices/mcap/beta; segment revenue mart; peer comps pack; Street ratings/PT history; IR decks as first-class gold products (reaffirmed by ticket 01)

