Type: research
Status: resolved

## Question

Does the `edgartools` PyPI package (this platform's dependency, pinned
`>=5.29.0`, used for filing metadata/document fetching per
`edgar.filing`/`edgar.entity`/`edgar.xbrl`) already support parsing Form
N-PORT filings -- structured access to the XML `primary_doc.xml` schema
(fund-level info + `invstOrSecs` holdings array with issuer name/CUSIP/
ISIN/LEI per holding)? If not, what would a from-scratch parser need to
handle (confirmed field names, nesting, any known quirks/edge cases in
real filings)?

## Context

Confirmed via SEC's own Form N-PORT instructions and the 2024 rule
amendments (Willkie Farr summary, Federal Register Feb 2026 proposal) that
N-PORT Part C is a complete line-by-line schedule of portfolio holdings,
each carrying CUSIP (or ISIN/ticker fallback), issuer name, and issuer LEI.
Not yet checked against `edgartools`' actual current capabilities --
this platform's existing parsers (`edgar_warehouse/parsers/ownership.py`,
`adv.py`) each wrap a specific `edgartools` object type
(`edgar.ownership.Ownership`, etc.); need to know whether an equivalent
exists for N-PORT before any silver-schema design ticket can assume how
much parsing work is actually needed here versus already done upstream.

## Answer

**Short answer: yes — `edgartools` has full first-class N-PORT support, exactly
analogous to `edgar.ownership.Ownership` for Form 3/4/5.** A from-scratch
parser is NOT needed. This is confirmed both by reading the package source
(installed locally, `edgartools==5.30.0`, in this repo's `uv` venv) and by
live-fetching and parsing real prod SEC filings against it during this
research.

### 1. First-class object model exists: `edgar.funds.reports.FundReport`

Repo: `dgunning/edgartools` (confirmed via `gh repo view` — 2,681 stars, MIT,
description literally lists "10-K, 8-K, XBRL financials, Form 3/4/5, 13F, ADV").
Source file: `edgar/funds/reports.py` (1,652 lines) plus
`edgar/funds/models/derivatives.py` (602 lines) for the derivative sub-schema.

- `FundReport` is exported at the top level: `from edgar import FundReport`
  (`edgar/__init__.py:53`), and via `edgar.funds` (`edgar/funds/__init__.py:45`).
- **The generic filing-dispatch table wires N-PORT in exactly the same way
  Form 3/4/5/13F/ADV are wired** (`edgar/__init__.py`):
  ```python
  'NPORT-P': ('FundReport', 'fund portfolio holdings'),
  'NPORT-EX': ('FundReport', 'fund portfolio holdings'),
  ...
  elif matches_form(sec_filing, ["NPORT-P", "NPORT-EX"]):
      return FundReport.from_filing(sec_filing)
  ```
  So `filing.obj()` on any NPORT-P/NPORT-EX filing returns a `FundReport`,
  the same pattern this codebase's `edgar_warehouse/parsers/ownership.py`
  already relies on for `Ownership.from_xml(content)` — a new N-PORT parser
  could follow the **same adapter pattern as `ownership.py`**, not the
  regex/BeautifulSoup fallback pattern `adv.py` uses (ADV has no first-class
  edgartools object; N-PORT does).
- A dedicated constant `NPORT_FORMS = ["NPORT-P", "NPORT-EX", "N-PORT",
  "N-PORT/A"]` and a `get_fund_portfolio_filings` convenience
  (`partial(get_filings, form=NPORT_FORMS)`) also exist at the top level.
  **Caveat (see quirks below): `"N-PORT"` as a literal `form=` filter value
  does NOT work** — only `"NPORT-P"`/`"NPORT-EX"` are real SEC form strings.

`FundReport.from_filing(filing)` calls `filing.xml()` (a generic method on
`Filing`, not N-PORT-specific — same method any XML-bearing filing type
uses) to get `primary_doc.xml`'s content, then
`FundReport.parse_fund_xml(xml)` parses it with `lxml` (rewritten from
BeautifulSoup for ~10x speedup, commit `038c6602`, 2026-02-01).

**Live-verified end-to-end** (fetched real prod SEC data during this research,
no code written, just `uv run python -c "..."` against the installed package):

```python
from edgar import get_filings
filings = get_filings(year=2026, quarter=2, form='NPORT-P')  # 14,407 filings that quarter alone
f = filings[0]  # Trust for Professional Managers / Bright Rock Mid Cap Growth Fund
obj = f.obj()
type(obj)  # <class 'edgar.funds.reports.FundReport'>
```
Produced real, correct field values (see section 3) and a second live fetch
against a derivatives-heavy fund (Guggenheim Strategic Opportunities Fund /
GOF, CIK 1380936) returned 1,942 holdings including 126 real derivative
positions (FX forwards, swaps, etc.) parsed cleanly through the same object.

### 2. Generic document access (moot here, but confirmed)

Since first-class support exists, this platform doesn't need to reach
`primary_doc.xml` as a raw attachment — but confirming it's reachable
either way: `Filing.xml()` (`edgar/_filings.py:1638`) is a **generic**
method (works via SGML parsing of the primary document, with a homepage
`primary_xml_document` attachment fallback) used by every XML-bearing
filing type, not something N-PORT-specific. If a from-scratch parser were
ever wanted instead, the raw XML is fully reachable via `filing.xml()` or
`filing.attachments`, same as any other filing.

### 3. Real field structure (live-fetched, accession `0001193125-26-290095`)

**Header / general info** (`FundReport.header`, `.general_info` —
Pydantic `GeneralInfo` model):

```
name: Trust for Professional Managers
cik: 0001141819
file_number: 811-10401
reg_lei: 549300O1N816L3GGRD45          # registrant-level LEI
series_name: Bright Rock Mid Cap Growth Fund
series_id: S000029035
series_lei: 254900DE03HYL0GM1264       # series-level LEI (distinct from registrant LEI)
fiscal_year_end: 2027-02-28
rep_period_date: 2026-05-31            # the actual "as of" reporting date
is_final_filing: False
```

**Fund-level financials** (`FundReport.fund_info` — Pydantic `FundInfo`
model, ~25 fields including borrowings, liquidity prefs, interest-rate-risk
metrics per currency, monthly flows/returns):

```
total_assets: 95552448.24
total_liabilities: 97844.75
net_assets: 95454603.49
```

**Per-holding fields** (`FundReport.investments` — list of
`InvestmentOrSecurity`, maps 1:1 to each `<invstOrSec>` under
`formData/invstOrSecs`), 3 real example rows:

```
name: Chipotle Mexican Grill Inc      | Arthur J Gallagher & Co   | AMETEK Inc
title: (same as name here)
lei: 529900REP5VGTPCP1J71              | 54930049QLLMPART6V29      | 549300WZDEF9KKE40E98
cusip: 169656105                       | 363576109                 | 031100100
isin: US1696561059                     | US3635761097              | US0311001004
ticker: CMG                            | AJG                       | AME
balance: 30000.0                       | 7500.0                    | 17500.0
units: NS  (number of shares)
value_usd: 955800.0                    | 1508325.0                 | 3952375.0
pct_value: 1.0013%                     | 1.5801%                   | 4.1406%   (% of NAV)
asset_category: EC (equity-common)
issuer_category: CORP
investment_country: US
is_restricted_security: False
fair_value_level: 1                    (fair-value hierarchy level, 1/2/3)
is_derivative: False
```

Full `InvestmentOrSecurity` schema (all confirmed real fields, not just the
above): `name`, `lei`, `title`, `cusip`, `identifiers` (nested: `ticker`,
`isin`, `other` — a dict for non-CUSIP/ISIN/ticker ids like an internal
identifier), `balance`, `units`, `desc_other_units`, `currency_code`,
`currency_conditional_code` + `exchange_rate` (only present for
non-reporting-currency positions), `value_usd`, `pct_value`,
`payoff_profile`, `asset_category`, `issuer_category`, `investment_country`,
`is_restricted_security`, `fair_value_level`, plus three optional nested
sub-models: `debt_security` (maturity date, coupon, default/PIK flags —
bonds only), `security_lending` (cash/non-cash collateral flags), and
`derivative_info` (only populated when `is_derivative` is true).

**Derivatives** (`derivative_info`, only when populated) has its own full
sub-schema in `edgar/funds/models/derivatives.py`: `ForwardDerivative`,
`SwapDerivative` (with directional receive/pay legs, floating-rate index,
tenor, reset dates), `FutureDerivative`, `SwaptionDerivative` (wraps a
nested nested swap), `OptionDerivative` (wraps a nested forward/future/swap
as the underlying). Live-confirmed real example: a EUR/USD FX forward
against The Toronto-Dominion Bank, `asset_category=DFE`,
`derivative_type=FWD`. `FundReport` exposes purpose-built accessors —
`.derivatives_data()`, `.swaps_data()`, `.swaptions_data()`,
`.options_data()`, `.forwards_data()`, `.futures_data()` — each returning a
flattened `pandas.DataFrame`, in addition to `.investment_data()` for the
full holdings table and `.securities_data()` for non-derivatives only.

### 4. Known parsing quirks / edge cases (from real issue history, `gh issue list --repo dgunning/edgartools --search nport`)

- **`form="N-PORT"` (literal, hyphenated) silently returns zero results** —
  only `"NPORT-P"` / `"NPORT-EX"` (and their `/A` amendment suffixes) are
  real SEC form strings; `"N-PORT"` is not indexed and the query fails
  silently rather than erroring (issue #843, confirmed by a maintainer:
  "Form filtering is exact-match against the index... the same
  silent-empty footgun pattern we've been cleaning up elsewhere"). An
  alias-normalization fix shipped in edgartools **5.36.0** — this repo's
  installed version (5.30.0) predates that fix, so **always filter with
  `form="NPORT-P"` explicitly**, not the `"N-PORT"` string, until/unless
  the pin is bumped past 5.36.0.
- **One registrant CIK can file many NPORT-P filings per quarter, one per
  series/fund** — `Company.get_filings(form="NPORT-P")` (or
  `FundSeries.get_filings()`, which just delegates to the parent company)
  returns every sibling series' filings mixed together under one CIK, not
  just the one series you asked for (issue #1143, still-open-pattern
  confirmed live: Vanguard's trust, CIK 36405, returns the identical
  325-filing list and identical "latest" accession number for two
  different series/tickers, VEXMX and VFINX). **A parser/loader must
  filter by `general_info.series_id` (or use `report.matches_ticker(...)`)
  after fetching, not assume company-level filings are already
  series-scoped.**
- **A null/missing nested-derivative amount can crash the built-in
  `options_data()` DataFrame accessor** — `abs()` called directly on an
  optional forward-derivative amount without a None-guard (issue #811,
  `TypeError: bad operand type for abs(): 'NoneType'`, reproduced against a
  real Guggenheim (GOF) NPORT-P options position). Fixed in commit
  `d6ccfab6` (2026-05-15); **this repo's pinned floor (`>=5.29.0`) does not
  guarantee that fix is present** — worth pinning to a version at or after
  it (need to confirm exact release number) if `options_data()` specifically
  is used, though `.investments`/`.investment_data()` (the two accessors a
  holdings-only warehouse pipeline would actually use) are unaffected —
  only the derivative-specific convenience DataFrames hit this path.
- **Historical ISIN-collision bug (old, appears fixed)**: issue #15
  (filed 2023, against edgartools 3.12.1) reported every holding row
  getting the *same* ISIN. Not reproducible against the current version —
  this research's own live fetch (section 3 above) shows correctly
  distinct ISINs per holding (`US1696561059`, `US3635761097`,
  `US0311001004`, ...). Likely fixed by the `Identifiers.from_xml` /
  `lxml` rewrite (2026-02-01) or an earlier refactor; flagging as
  historical, not a live concern, but a from-scratch design should still
  assert ISIN uniqueness within a filing as a sanity check.
- **Amendments/restatements**: `NPORT_FORMS` and the entity-categorization
  constants both explicitly include `"N-PORT/A"` as a distinct amendment
  form alongside the base form — confirmed present in
  `edgar/entity/constants.py` and `edgar/funds/reports.py`. No specific
  amendment-supersession logic was found in `FundReport` itself (it parses
  whatever single filing you hand it) — an amendment is just another
  filing with a later `filing_date`/same accession family; this warehouse
  would need its own supersession logic (comparable to how
  `sec_ownership_*`/`sec_adv_*` already handle amendments elsewhere in this
  codebase), same as it does for other multi-amendment SEC form types.
- **Multiple share classes per filer**: `series_class_info`
  (`FilerInfo.series_class_info`, a `SeriesClassInfo` with `series_id` +
  `class_id`) is parsed from the header but is **not currently exposed** as
  a first-class field on `FundReport.general_info` (only `series_id`/
  `series_name`/`series_lei` are) — a filing genuinely reports at the
  series level (one filing can cover multiple share classes of the same
  series), so per-class breakdowns are not separately itemized in the
  parsed object as far as this research found; would need direct XML
  access (`filing.xml()`) if per-class granularity is ever required.

### What a warehouse-side parser would need to do (design implication for a later ticket)

Given `edgartools` already fully parses the XML into typed Pydantic models,
a new `edgar_warehouse/parsers/nport.py` would look like
`edgar_warehouse/parsers/ownership.py` (adapter over an edgartools object,
not `adv.py`'s raw-XML/regex fallback): call
`FundReport.from_filing(filing)` (or construct directly from `filing.xml()`
via `FundReport.parse_fund_xml(xml)` to avoid a second network round trip if
the warehouse already has the XML bytes cached from bronze), then map
`general_info`/`fund_info`/`investments` onto warehouse row dicts — same
shape as `ownership.py`'s `owner_rows`/`non_derivative_rows`/
`derivative_rows` split, likely a `nport_filer_row` +
`nport_holding_rows` (+ optionally `nport_derivative_rows` for the
richer derivative sub-schema) split here. Genuinely new work is schema
design (silver table shapes, series-scoping/dedup logic per the quirk
above, amendment-supersession policy) — not XML parsing itself, which
`edgartools` already does completely.

### Sources

- `edgar/funds/reports.py`, `edgar/funds/models/derivatives.py`,
  `edgar/funds/__init__.py`, `edgar/__init__.py`, `edgar/_filings.py`,
  `edgar/entity/constants.py`, `edgar/entity/categorization.py`,
  `edgar/forms.py` — read directly from the installed
  `edgartools==5.30.0` package in this repo's `.venv`
  (`site-packages/edgar/`).
- Live SEC EDGAR fetches via the installed package (this research session,
  2026-09-08): `get_filings(year=2026, quarter=2, form='NPORT-P')`
  (14,407 results), accession `0001193125-26-290095` (Trust for
  Professional Managers / Bright Rock Mid Cap Growth Fund), and
  `Company('GOF').get_filings(form='NPORT-P')` (Guggenheim Strategic
  Opportunities Fund, 126 live derivative positions).
- GitHub repo `dgunning/edgartools` (confirmed correct repo via
  `gh repo view`, 2,681 stars) — commit history for
  `edgar/funds/reports.py` (`gh api repos/dgunning/edgartools/commits`),
  and issues #843, #1143, #811, #15, #237 (`gh issue list --search nport`,
  `gh issue view <n>`).
- README.md (`dgunning/edgartools`, fetched via `gh api
  repos/.../contents/README.md`): N-PORT listed as a headline-supported
  form type ("13F holdings, N-PORT, N-MFP, N-CSR/N-CEN fund reports").
