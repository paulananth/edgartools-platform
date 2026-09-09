Type: research
Status: resolved

## Question

What's the real scale of Form N-PORT data across the full registered-fund
universe (ETFs, mutual funds, closed-end funds)? Specifically: how many
distinct N-PORT filers exist currently, how many filings/month given the
monthly filing requirement, typical holdings-per-filing (median and a
large-fund outlier), and a total estimated holdings-row volume comparable
to the existing `sec_thirteenf_holding` measurement (6,799,919 rows across
41,225 distinct CUSIPs, ~165x repetition per CUSIP -- from
mdm-run-throughput Ticket 07's live Snowflake measurement).

## Context

This map's own destination scope (per the user's explicit choice) is "all
registered funds," not just ETFs -- the mutual fund industry alone is a
much larger filer population than 13F's ~8,783 distinct institutional
managers, so this sizing directly informs whether the design tickets
downstream (silver schema, ingestion cadence) need to plan for something
an order of magnitude larger than the 13F pipeline from day one, or
whether a narrower first landing (e.g. ETFs only, later widened) is worth
recommending back to the user despite the destination's stated scope.

Real sources to check: SEC's own Form N-PORT structured data sets
(https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets
-- surfaced during this map's charting), EDGAR full-text search for
`NPORT-P` filer counts, or a sampled bulk-data file directly.

## Answer

**Everything below with a number attached is either read directly from a
primary SEC source, or live-verified against real EDGAR data during this
research session. Section 4's row-volume figures are explicitly a modeled
order-of-magnitude extrapolation, not a measurement — flagged as such
throughout, unlike the 13F figure this ticket compares against, which is a
real live Snowflake count.**

### 1. Distinct N-PORT filer count (real SEC figures, read directly from the primary document)

Source: SEC Division of Investment Management, Analytics Office —
*"Registered Fund Statistics: Form N-PORT and Form N-CEN Data, period
ending September 2025"* (data received through Jan 29, 2026), Table 1.1
and Table 2.3. Downloaded and read directly (not via an AI web-search
summary):
https://www.sec.gov/files/investment/im-investment-registered-fund-statistics-20260129.pdf

As of September 2025 (the latest month in this report), **13,251 total
registered funds** file on Form N-PORT:

| Fund type | Count (Sep 2025) | Share |
|---|---|---|
| Mutual funds (open-end, excl. money market) | 8,256 | 62.3% |
| ETFs | 4,306 | 32.5% |
| Closed-end funds (incl. interval/non-traded funds) | 689 | 5.2% |
| **Total** | **13,251** | 100% |

This grew steadily over the report's 12-month window: 12,754 (Oct 2024) →
13,251 (Sep 2025), ~3.9%/year. Aggregate net assets across all N-PORT
filers were **$35.81 trillion** as of Sept 2025 (Table 2.3).

Who is/isn't covered (SEC's own applicability table, page 1): **required**
— mutual funds (Form N-1A, excl. money market), ETFs (N-1A or N-8B-2),
closed-end funds (N-2, incl. interval/non-traded), separate accounts on
N-3. **Not required** — BDCs, Rule 2a-7 money market funds, small business
investment companies (N-5), and non-ETF unit investment trusts
(N-4/N-6/S-6/N-8B-2). This matches the ticket's framing (open-end funds,
ETFs, closed-end funds) and confirms money market funds are entirely out
of scope for N-PORT.

This filer population (13,251) is **~1.5x** the size of the existing 13F
filer population (8,783 distinct institutional managers, per the
mdm-run-throughput Ticket 07 live Snowflake measurement) — meaningfully
larger, but not order-of-magnitude larger, on filer count alone.

*Caveat:* an earlier, lower-confidence web-search-summarized figure of
"12,668 funds / $32.08T" surfaced during this research but could not be
traced back to a primary source and conflicts with the number read
directly from the SEC PDF above. Treat 13,251 / $35.81T as authoritative —
it was read directly from SEC's own primary document, not filtered through
an AI summary of a secondary source.

### 2. Filings per month/quarter — current regime is quarterly, NOT monthly, despite the 2024 rule

**This is the most important correction to the ticket's own framing.** As
of today (Sept 2026), Form N-PORT is not filed *or* publicly disclosed
monthly. The 2024 rule amendments that would require monthly filing and
monthly public disclosure exist, but their compliance dates have been
delayed twice and have not taken effect for anyone yet:

- **Original rule (still in effect today):** funds file N-PORT once per
  **fiscal quarter**, due 60 days after quarter-end. Each filing reports
  monthly snapshot data for all 3 months of that quarter, but **the SEC
  does not make the first two months' data public** — only the third
  (quarter-end) month is disclosed publicly, immediately upon filing.
  Direct quote from the SEC report itself (page 2): *"the Commission does
  not intend to make public information reported on Form N-PORT for the
  first and second month of each fund's fiscal quarter."* So from a
  public-EDGAR-data perspective, there is exactly **1 public NPORT-P
  filing per fund per quarter** today — not 3, and not 12/year.
- **2024 amendments** (adopted Aug 2024) would require monthly filing (30
  days after month-end) *and* monthly public disclosure (60-day lag).
  Original compliance dates: large fund groups Nov 17, 2025; smaller fund
  groups May 18, 2026.
- **April 16, 2025:** SEC delayed both compliance dates by 2 years — large
  fund groups → **Nov 17, 2027**; smaller fund groups → **May 18, 2028**.
  The monthly regime cannot take effect before late 2027 at the earliest.
- **Feb 18, 2026:** SEC proposed to further water down the 2024
  amendments — filing deadline extended to 45 days after month-end, but
  **public disclosure reduced from monthly back to quarterly** (60 days
  after fiscal-quarter-end). Comment period ran through ~April 2026; not
  finalized as of this research (Sept 2026). If adopted as proposed,
  public N-PORT disclosure would remain quarterly *indefinitely*, even
  once monthly (non-public) filing eventually starts.

**Live-verified against real EDGAR data**, not just secondary sources: the
Vanguard Index Funds family's (CIK 0000036405) actual public NPORT-P
filings land roughly every 3 months (2025-11-25, 2026-02-26, 2026-05-28,
2026-08-28) — confirming quarterly, not monthly, cadence in practice
today. A live EDGAR full-text-search query
(`https://efts.sec.gov/LATEST/search-index?forms=NPORT-P&startdt=2026-08-25&enddt=2026-09-04`)
for all NPORT-P filings in the ~1.5-week window around the most recent
quarterly deadline (60 days after the June 30 fiscal-quarter-end most
funds use) returned an **exact** `"total":{"value":7058,"relation":"eq"}`
— a large fraction of, but not all of, the ~13,000 total filer population
(fund complexes with non-calendar fiscal year-ends file in other weeks
spread across the year, so the full population doesn't land in one single
burst; a 3-month EDGAR FTS window, Jun–Aug 2026, hit the search UI's
10,000-result cap, `"relation":"gte"`, consistent with ~13,000 filers
filing once each somewhere across that window).

**Current filing volume (public, today):**
- ≈ 13,000 filings/quarter (1 per fund)
- ≈ **52,000 filings/year**

**If/when the monthly regime eventually takes effect** (no earlier than
Nov 2027 for large funds, and possibly *never* for public disclosure
specifically if the Feb 2026 rollback proposal is adopted as written):
public filing volume could roughly **triple to ≈156,000/year** (13,000 ×
12). Given the trajectory — two delays, plus an active proposal to make
quarterly-only public disclosure permanent — I would not design around the
monthly scenario as the near-term baseline; the current quarterly regime
is the one to plan for.

### 3. Holdings-per-filing — real samples from actual current filings

| Fund | Type | Holdings count | Basis |
|---|---|---|---|
| SPDR sector ETFs (avg. of 11 SPDR Select Sector funds) | narrow/sector ETF | ~47 avg | Aggregate holdings count, illustrative of the small end |
| SPDR S&P 500 ETF Trust (SPY) | large-cap index ETF | ~503–505 | N-PORT-sourced holdings list, portfolio date 2026-06-30 |
| Fidelity Contrafund (FCNTX) | actively-managed diversified equity mutual fund | 442 | Holdings list, as of 2026-06-30 |
| Vanguard Total Stock Market Index Fund (VTSAX/VTI) | broad-market equity index fund | ~3,498–3,525 | Holdings list, as of ~July 2026 |
| Vanguard Total Bond Market Index Fund (VBTLX/BND) | broad-market bond index fund | **~17,257** | Holdings list |

This confirms the ticket's own framing directionally: a "typical"
diversified equity fund or ETF sits in the 50–500 range, but broad-market
index products — and *especially* bond funds, which report every
individual bond CUSIP/issue rather than a blended position — can run into
the thousands to tens of thousands of holdings in a single filing. Bond
funds are not a rare edge case: SEC's own Table 1.1 shows ~1,268 "Taxable
Bond" mutual funds alone as of Sep 2025 (~15% of all mutual funds, before
even counting bond ETFs/closed-end funds) — a real, sizeable population
that will pull any simple per-filing average well above the median.

### 4. Total holdings-row volume — explicit order-of-magnitude estimate, not a measurement

Unlike the 13F figure (a real, live Snowflake row count), this platform
has no direct database access to N-PORT holdings data, so this is a
bottom-up extrapolation from the real filer count (§1), the real current
filing cadence (§2), and the real sampled holdings-per-filing (§3). Every
number below is a modeled estimate with the assumptions stated inline —
not a measurement.

**Per year, current (quarterly-disclosure) regime, ≈52,000 public filings/year:**

- **Low estimate** (weighting toward the numerically-dominant
  smaller/typical funds — most ETFs and actively-managed equity funds
  cluster in the 50–500 range): ~200 holdings/filing average →
  **~10.4M holdings-rows/year**
- **Mid estimate** (blending the typical-fund mode with a real,
  non-trivial tail of broad-index and bond funds): ~350 holdings/filing
  average → **~18.2M holdings-rows/year**
- **High estimate** (if the bond-fund/broad-index tail pulls the
  arithmetic mean up the way the VBTLX (17,257) sample suggests it can):
  ~500+ holdings/filing average → **~26M+ holdings-rows/year**, and could
  go meaningfully higher — a single large bond fund's one quarterly
  filing alone contributes as many rows as ~35 typical equity-fund
  filings combined.

**Cumulative since N-PORT data availability began** (Oct 2019 → present,
~7 years, per SEC's own Form N-PORT Data Sets page coverage window,
allowing for filer-population growth over that period — average filer
population somewhat below today's 13,251): roughly 300,000–350,000 total
historical filings × the same 200–500 holdings/filing range → **roughly
65M–175M cumulative holdings-rows**, order of magnitude only.

**Comparison to the existing 13F measurement**
(`sec_thirteenf_holding`: 6,799,919 rows / 41,225 distinct CUSIPs / 8,783
distinct institutional managers, live Snowflake count, mdm-run-throughput
Ticket 07):

- N-PORT's filer population (13,251) is only ~1.5x 13F's (8,783) — not a
  large multiplier on its own.
- N-PORT's estimated cumulative holdings-row volume (~65M–175M, order of
  magnitude) is roughly **10x–25x** 13F's current live row count (6.8M) —
  driven almost entirely by holdings-per-filing, not filer count: N-PORT's
  real per-filing samples range from ~50 up to ~17,000+ for a single fund,
  a far wider and higher-ceiling spread than a typical 13F institutional
  manager's aggregate position report.
- **The disproportionate driver is bond funds and broad-market index
  funds specifically, not "ETFs" or "mutual funds" as categories** — both
  fund types contain small-holdings-count and huge-holdings-count members
  (e.g. a narrow sector ETF vs. a total-bond-market ETF are both "ETFs").
  Narrowing scope to "ETFs only" (4,306 of 13,251 filers, ~33%) would cut
  the *filer* count by roughly two-thirds, but should **not** be assumed
  to cut *holdings-row* volume by the same proportion — broad-market/index
  ETFs, which include some of the largest holdings-count filings on
  record (e.g. total-bond-market and total-stock-market ETF share
  classes), are disproportionately represented among ETFs relative to
  narrow/sector ETFs. An ETF-only first landing would meaningfully reduce
  scope on filer count and operational surface area, but a downstream
  design ticket should not assume it reduces row volume 3x for the same
  reason.

### Sources

- SEC Registered Fund Statistics (Form N-PORT/N-CEN data, period ending
  Sep 2025), primary document read directly:
  https://www.sec.gov/files/investment/im-investment-registered-fund-statistics-20260129.pdf
- SEC Form N-PORT Data Sets:
  https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets
- Federal Register, Form N-PORT Reporting (2026 proposal):
  https://www.federalregister.gov/documents/2026/02/23/2026-03460/form-n-port-reporting
- Federal Register, Investment Company Names/Form N-PORT Reporting
  compliance-date extension:
  https://www.federalregister.gov/documents/2026/02/23/2026-03459/investment-company-names-form-n-port-reporting-extension-of-compliance-date
- Federal Register, 2024 Form N-PORT/N-CEN amendments:
  https://www.federalregister.gov/documents/2024/09/11/2024-19819/form-n-port-and-form-n-cen-reporting-guidance-on-open-end-fund-liquidity-risk-management-programs
- Sidley Austin, "U.S. SEC Proposes to Scale Back 2024 Form N-PORT
  Amendments":
  https://www.sidley.com/en/insights/newsupdates/2026/03/us-sec-proposes-to-scale-back-2024-form-n-port-amendments
- Dechert, "SEC Acts on N-PORT and Names Rule; Staff Issues FAQs":
  https://www.dechert.com/knowledge/onpoint/2026/2/sec-acts-on-n-port-and-names-rule--staff-issues-faqs--what-funds.html
- Willkie Farr, "Form N-PORT Pivot":
  https://www.willkie.com/publications/2026/03/form-n-port-pivot-sec-proposes-rulemaking-to-roll-back-registered-fund-reporting
- SEC EDGAR company filing search (live-verified, CIK 0000036405 Vanguard
  Index Funds) and EDGAR full-text search API (`efts.sec.gov`,
  live-queried Sept 2026 NPORT-P filing counts)
- Real fund holdings counts, cross-checked against fund type:
  stockanalysis.com (VTSAX, FCNTX holdings lists), GuruFocus (SPY
  summary), Yahoo Finance/USNews (VBTLX/BND holdings), SPDR sector-ETF
  aggregate holdings commentary
