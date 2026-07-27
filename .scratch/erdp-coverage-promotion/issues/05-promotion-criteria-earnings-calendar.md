# 05 — Product-ready promotion criteria for EARNINGS_CALENDAR (ERDP-03)

Type: grilling
Status: resolved
Blocked by: 01, 07

## Question

What is the complete, product-ready set of acceptance criteria that must all pass before `EARNINGS_CALENDAR` is promoted from Partial to Covered — covering every critical requirement surfaced by ticket 01's skill survey (catalyst-calendar's "quarterly earnings date and time (pre/post market)" need, weekly-preview freshness expectations), plus the known ops gate: the `finnhub` path needs a commercial license not yet cleared. This ticket must state whether promotion can happen on the `yahoo`/`firm_manual` pilot paths alone, or whether the Finnhub license is a hard blocking criterion. Write this as the `ERDP-05-04` promotion-checklist entry for this product: a numbered list of criteria, each with a concrete, checkable acceptance query or procedure.

## Answer

**The ticket's own premise needed correcting first (ticket 07 confirmed):** there is no `yahoo` pilot path — the module docstring's claim is unbuilt. The real choice was never "yahoo/firm_manual vs. finnhub license" — it's "firm_manual-only (can't scale to coverage-universe-wide) vs. clearing the finnhub license vs. building a new ToS-clean source." Ticket 07's research found Alpha Vantage `EARNINGS_CALENDAR` is the only free, official, bulk, ToS-clean option (confirmed with the user); date-only (no session timing — no free ToS-clean source has any), accepted as `session="unknown"` (already a legitimate `SESSIONS` enum value, confirmed with the user, not a workaround).

### Build prerequisite (not yet done — blocks all Alpha Vantage-sourced criteria below)

0. **Implement the Alpha Vantage path.** Add `"alphavantage"` to `SOURCE_SYSTEMS` (`earnings_calendar.py:35-37`); implement `fetch_alphavantage_earnings_calendar`/`parse_alphavantage_earnings_calendar` calling `EARNINGS_CALENDAR` with `symbol` omitted (bulk mode, respecting the 25-req/day free-tier ceiling — one or a few pulls per day, not per-ticker); correct the module docstring's inaccurate `yahoo` fallback claim (either remove it or turn it into an explicit future build task, since it doesn't reflect what's implemented today).

### Promotion criteria

1. **Source scope restricted to implemented, ToS-clean sources.** `source_system ∈ {finnhub, firm_manual, alphavantage}` once prerequisite #0 lands. `yahoo`/`fmp`/`other` disqualify — `yahoo` has no implementation despite the docstring, and per ticket 07's research any yfinance-backed implementation would be explicit HTML scraping under a ToS that forbids it; `fmp` has no implementation either.
2. **Universe coverage** — not required at a fixed threshold (unlike `CONSENSUS_ESTIMATES`'s 50% bar): catalyst-calendar and morning-note need the *whole* coverage universe scanned daily (ticket 01 §3), which only the bulk Alpha Vantage/finnhub paths can satisfy at all — `firm_manual` alone cannot pass this criterion by construction, confirmed structurally, not measured. Criterion: at least one bulk source (`finnhub` or `alphavantage`) is active and covers ≥90% of the Decision Subject Universe for the current+next fiscal quarter.
3. **Finnhub rows: format-verified authenticity** — `source_ref` matches `^finnhub:calendar/earnings:[^:]+:[0-9]{4}:Q[1-4]$`, the deterministic format already emitted (`earnings_calendar.py:369`).
4. **Alpha Vantage rows: format-verified authenticity** — once #0 lands, `source_ref` should follow the same deterministic-format convention (e.g. `alphavantage:EARNINGS_CALENDAR:{symbol}:{reportDate}`) so it's equally checkable; specify this in the implementation, don't leave it free-form like `GUIDANCE_FACTS`'s `firm_manual` path had to fall back to.
5. **firm_manual rows: reviewable-artifact provenance** — same procedural analog as tickets 03/04/06: promoted `firm_manual` calendar data traces to a checked-in, git-reviewed CSV, not an ad-hoc row.
6. **Confirmed rows never use `session=unknown`** — already enforced (`normalize_calendar_row`, ERDP-03-03); re-verified live. `status=estimated` rows may legitimately use `session=unknown` (Alpha Vantage-sourced or otherwise), per the confirmed decision above.
7. **Staleness re-verification, not single-fetch-and-trust** — catalyst-calendar's own stated caveat ("dates shift — verify closer to the event," ticket 01 §3): a row whose `as_of` is >X days old and whose `expected_date` is within the next 2 weeks must have been re-confirmed (a fresh row with a newer `as_of` for the same period), not silently served stale. Concrete threshold left to whoever operationalizes this (not gating promotion itself, a freshness-monitoring criterion).
8. **Join integrity, identity-checked** — 100% join to `COMPANY`/`TICKER_REFERENCE` on `cik`, spot-checked against `entity_name` (same pattern as tickets 03/04/06).
9. **Explore-only labeling re-affirmed** (ADR 0001 / ERDP-06-02).

**Explicitly not required** (per ticket 01, no skill needs it): exact time-of-day beyond session bucketing — no skill asks for more precision than pre-market/after-close (and per the confirmed decision, even that is accepted as best-effort/`unknown` given no free ToS-clean source provides it); history — every consumer wants only the *next* occurrence.

**Known residual risk, not closable by any acceptance query:** criterion 7's re-verification requirement is itself dependent on the source actually re-publishing changed dates promptly — if Alpha Vantage or finnhub silently fail to update a shifted date, no acceptance query run against the platform's own data can detect that against ground truth without an independent second source, mirroring tickets 03/04/06's residual-risk framing (promotion reflects demonstrated reliability on what's checkable, not a guarantee against an upstream vendor's own silent staleness).
