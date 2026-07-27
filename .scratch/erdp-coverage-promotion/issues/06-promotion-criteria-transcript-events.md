# 06 — Product-ready promotion criteria for TRANSCRIPT_EVENTS (ERDP-04)

Type: grilling
Status: resolved
Blocked by: 01

## Question

What is the complete, product-ready set of acceptance criteria that must all pass before `TRANSCRIPT_EVENTS` is promoted from Partial to Covered — covering every critical requirement surfaced by ticket 01's skill survey (earnings-analysis's transcript-with-date checklist item, any date-matching/verification needs), plus the known hard constraint: `PILOT_CIKS = {320193}` (Apple only). This ticket must state whether "Covered" can ever mean "Covered for the pilot CIK only" as a distinct, explicitly-labeled tier, or whether Covered inherently requires coverage-universe breadth (in which case this product cannot be promoted until the pilot list expands, and that dependency should be stated explicitly). Write this as the `ERDP-05-04` promotion-checklist entry for this product: a numbered list of criteria, each with a concrete, checkable acceptance query or procedure.

## Answer

Grounded in `_FACT_TRANSCRIPT_EVENT_SCHEMA`, `transcript_events.py` (`register_ir_pointer`, `store_transcript_text`, `derive_ir_event_id`), and ticket 01's per-skill findings. Confirmed with the user: **Covered status differs by consuming skill**, matching ticket 02's precedent that classification need not be uniform across a row.

### Per-skill promotion tier

- **earnings-analysis**: needs only the latest quarter, date-matched, with real content — structurally satisfiable **Apple-only**. Criteria 1–6 below gate this skill's Covered status.
- **earnings-preview** (needs the *prior* quarter specifically) and **initiating-coverage** (needs 2-3 quarters): structurally blocked regardless of pilot data quality — `PILOT_CIKS={320193}` plus a latest-quarter-only capture pattern cannot satisfy either no matter how well Apple's single row performs. These stay **Partial** until the pilot captures multi-quarter history for at least one CIK; not a quality gate, a coverage-shape gate. Criterion 7 states this explicitly as a blocking dependency, not a checkable query.

### Criteria (earnings-analysis Covered tier)

1. **Source scope restricted to implemented sources** — `source_system ∈ {ir_website, firm_manual}` only; `fmp`/`other` disqualify (enum values with no ingest function, same pattern as tickets 03/04).
2. **`ir_website` rows: format-verified authenticity** — re-derive `derive_ir_event_id(cik, event_date, event_type, source_url)` from the row's own fields and confirm it equals the stored `event_id`. A hand-inserted row with a fabricated `event_id` fails this immediately — this is the exact check that would have caught tonight's incident (I never called the real function, so my row's `event_id` would not have matched its own fields' hash).
3. **Content, not just a pointer, required for this tier** — `content_sha256 IS NOT NULL` and `char_count IS NOT NULL` (i.e. went through `store_transcript_text`, not `register_ir_pointer` alone). A pointer-only row satisfies citation/hyperlink needs but not earnings-analysis's stated need for quotable Q&A excerpts and management-quote content.
4. **Content integrity spot-check** — for a sample of promoted rows, fetch `storage_uri` and confirm `sha256(fetched_text) == content_sha256` — proves the stored hash actually corresponds to the stored bytes, not just an internally-consistent fabrication.
5. **Exact-date-match, ±1 day** — `event_date` within 1 day of the corresponding filing/release date (`FILING_DETAIL`/`EARNINGS_RELEASES` via `accession_number` when present) — earnings-analysis's strictest correctness bar of any of the 4 products (ticket 01 §4), named failure mode "WRONG transcript obtained."
6. **Join integrity, identity-checked** — 100% join to `COMPANY`/`TICKER_REFERENCE` on `cik`, spot-checked against `entity_name` (same pattern as tickets 03/04).

### Blocking dependency (earnings-preview / initiating-coverage tier)

7. **Multi-quarter history capture — content, not code, is the blocker.** **Corrected 2026-07-27** (re-checked as part of the "3 ERDP build prerequisites" follow-on work): the original framing here ("not yet built... needs an expanded `PILOT_CIKS` or an explicit history-backfill ingest mode") was wrong on the code question. `derive_ir_event_id`/`transcript_event_key` hash in `event_date`, and `load_firm_manual_records` loops with no dedup — `register_ir_pointer`/`store_transcript_text` already accept N quarters per CIK with zero collision, and `PILOT_CIKS` is checked nowhere in `transcript_events.py`. Proven by regression test (`tests/unit/test_transcript_events.py::MultiQuarterHistoryTests`, 2026-07-27): two distinct fiscal quarters for CIK 320193, via both `register_ir_pointer` and `store_transcript_text`, produce two distinct non-colliding rows. **There is no ingest-mode fork to pick between — neither option in the original question requires new code.**

   The real blocker is criterion 3 above: earnings-preview and initiating-coverage need transcript **content**, not a dated pointer ("a transcript pointer... would satisfy the citation/hyperlink requirement but not the content-extraction requirement", ticket 01 §4). `register_ir_pointer` can't satisfy them no matter how many quarters are registered — only `store_transcript_text` (which requires the real text) can. Checked live 2026-07-27: Apple's own investor relations site (`apple.com/newsroom/.../apple-reports-second-quarter-results/`, `investor.apple.com`) publishes only a financial-results press release plus a webcast replay available for ~2 weeks (audio/video, not text) — **no first-party transcript text exists**. Every real transcript text source found (Investing.com, Seeking Alpha, Yahoo Finance, Motley Fool, Morningstar) is a third-party licensed re-transcription, not something this platform can legitimately fetch and store. This is now tracked as a separate research question — see [ticket 08](08-free-transcript-content-sources.md) — not a checkable acceptance criterion or a code build item.

**Explicitly not required** (per ticket 01, no skill needs it beyond what's stated above): a coverage-universe-wide transcript sweep — every skill that needs this product is single-company/per-request; `PILOT_CIKS` breadth is a smaller blocker than history depth for the two skills that need more than "latest" (ticket 01 §4).

**Known residual risk, not closable by any acceptance query:** criterion 4's integrity spot-check only proves the *stored* bytes match the *stored* hash — it cannot prove the original fetched text was itself an accurate, unmodified transcript (e.g. a truncated or mid-edit capture would still hash-match itself consistently). This mirrors tickets 03/04's residual-risk framing.
