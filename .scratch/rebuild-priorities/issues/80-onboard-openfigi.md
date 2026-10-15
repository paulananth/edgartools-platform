# Onboard OpenFIGI with the skills

Priority: 80, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md).

Type: task (onboarding). Status: open. Blocked by: 79 (Onboard funds and securities with the skills: the Security master this source maps onto).

## Why

Operator, 2026-10-14: "create a ticket to onboard figi", after asking whether a FIGI file extract exists and what fields it carries.

Our sources give a Security its CUSIP and ISIN but hardly any tickers: N-PORT names a ticker on about 10% of its identifier rows, some of them junk such as "USD"; the local 13F information tables carry none. OpenFIGI states, for each listing of an instrument, its ticker and exchange, and the instrument's place in a three-level hierarchy. That is how tickers attach to a Security cleanly (operator, 2026-10-14: "Tickers and cusips are attached to securities ie 13F").

## What the source is

- **No bulk file.** OpenFIGI publishes no download of all FIGIs; access is its free API (`api.openfigi.com/v3`), one request at a time. Search and filter stop at 15,000 results a query, so the set cannot be listed whole. A copy is listed on the Snowflake Marketplace as a public-domain source, updated ad hoc.
- **Mapping** (`POST /v3/mapping`) takes identifiers (CUSIP, ISIN, SEDOL, CINS, WKN, ticker, OCC option symbol and about 20 more) and returns, for each match: `figi` (the listing), `compositeFIGI` (the security across one country's exchanges), `shareClassFIGI` (the share class across countries), `ticker`, `exchCode`, `name`, `securityType`, `securityType2`, `marketSector`, `securityDescription`. Filters: exchange or MIC, currency, security type, option type, strike, coupon, expiry, maturity.
- **Limits:** without a key, 25 mapping requests a minute of 10 identifiers each; with a free key (sent in the `X-OPENFIGI-APIKEY` header), 25 requests every 6 seconds of 100 each. Mapping the 385,381 N-PORT CUSIPs is about 3,850 requests with a key (about 15 minutes), about 26 hours without.
- **Licence:** OpenFIGI's site says its tools and metadata are provided under the MIT licence at no cost.
- Sources: [API documentation](https://www.openfigi.com/api/documentation), [Snowflake data docs](https://data-docs.snowflake.com/foundations/sources/openfigi), [Bloomberg 2016 launch](https://www.bloomberg.com/company/press/bloomberg-launches-online-request-utility-and-new-mapping-tools-for-the-financial-instrument-global-identifier-figi).

## Rulings it rests on

- FIGI is a cross-reference on a Security, lookup only; CUSIP and ISIN join Security records (operator, 2026-10-14: "CUSIP and ISIN join (Recommended)").

## Checklist

- [ ] The operator's permission for the capture, and its route: the mapping API with a free key (the key in an environment variable, never printed or typed into the chat), or the Snowflake Marketplace copy read in place
- [ ] Capture: the Security master's CUSIPs and ISINs (ticket 79) sent to the mapping API, each response kept whole with its request, a receipt per file (key, sha256, bytes); counts only in the repo
- [ ] discover: data-profiling over the capture; approved findings
- [ ] plan-parts: the listing (FIGI, ticker, exchange) as a cross-reference and attributes of a Security; the three-level hierarchy (listing, composite, share class) as a master data hierarchy or a relationship, for the operator; `securityType`, `securityType2`, `marketSector`, `exchCode` as code sets for RDM
- [ ] map: the Dataset Contract (source `openfigi`), with FIGI, composite FIGI and share-class FIGI under `cross_references`; how a ticker attaches to a Security when one CUSIP has many listings (per exchange, or the composite's), for the operator
- [ ] quality: checks for FIGI shape and check digit, ticker and exchange present together; set aside a response that names no instrument
- [ ] metadata, test, approve, switch-on, as data-onboarding says
- [ ] Refresh: how often the mapping is re-run for new and changed Securities (Bookkeeping)
- [ ] Every skill gap found on the way: fixed in the skill, on its own branch
- [ ] PR, CI green, merge on the operator's word
- [ ] Learning → skill
