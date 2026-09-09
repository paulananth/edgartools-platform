# N-PORT fund holdings

## Destination

A locked design for ingesting SEC Form N-PORT (quarterly-public portfolio
holdings reports -- filed quarterly today, with a monthly-filing rule
delayed to no earlier than Nov 2027 and a pending proposal to keep public
disclosure quarterly permanently, per Ticket 02 -- from registered
investment companies: open-end funds, ETFs, and closed-end funds, per
Rule 30b1-9; money market funds are structurally excluded, they file
Form N-MFP instead) as a genuinely new, first-class dataset
in this warehouse: fund constituent holdings become queryable, independent
of any other map's needs. This map is **decision-only** (explicit user
choice) -- it produces a locked design/spec (silver schema shape, MDM
relationship/entity design, ingestion cadence, and how it relates to the
existing 13F/`INSTITUTIONAL_HOLDS` data), not a shipped implementation.
Implementation is a separate future handoff once the design is settled.

## Notes

- Domain: brand-new SEC form type to this codebase -- confirmed via grep,
  zero references to N-PORT/NPORT anywhere in `edgar_warehouse/` as of
  2026-09-08. Nearest existing analog is the 13F pipeline
  (`sec_thirteenf_holding` silver table, `_derive_institutional_holds`
  MDM derivation, `edgar_warehouse/parsers/`) -- same shape of problem
  (a periodic holdings-report form feeding a silver table and an MDM
  relationship type), different filer population and different holder/
  holding direction (13F: a manager's holdings across many issuers;
  N-PORT: a fund's own constituent holdings of its own portfolio).
- Surfaced from a tangent during the `mdm-relationship-versioning-gap`
  map's Ticket 06 investigation (INSTITUTIONAL_HOLDS securities never
  link to their issuer company) -- N-PORT was researched as a candidate
  data source for that gap and found not to directly solve it (issuer
  identified by name + LEI, not CIK, same limitation as 13F's
  `issuer_name`) but worth pursuing as its own capability. That map's
  Ticket 06 remains open and separate; this map does not resolve it.
- `/gof-refactor-reviewer` and full 3-axis `/code-review` (CLAUDE.md hard
  rules) apply once this map hands off to implementation, not during
  this decision-only phase.
- Standing preference from the parent session: real measurements against
  live data (SEC EDGAR filer counts/filing volume), not estimates.

## Decisions so far

1. [Does edgartools already support N-PORT parsing](issues/01-edgartools-nport-parsing-support.md) — resolved: yes, full first-class support via `edgar.FundReport` (same dispatch pattern as `Ownership`/`ThirteenF`), live-verified against real filings including a derivatives-heavy fund. No from-scratch parser needed; a new `edgar_warehouse/parsers/nport.py` would be a thin adapter like `ownership.py`. Real quirks found: `form="N-PORT"` (literal) silently returns zero results (must use `"NPORT-P"`), one registrant CIK mixes all its series' filings together (must filter by `series_id`), a None-guard bug in the derivative `options_data()` accessor, and no built-in amendment-supersession logic (warehouse-side work, same as other multi-amendment forms).
2. [N-PORT filer and volume sizing](issues/02-nport-filer-and-volume-sizing.md) — resolved: 13,251 real N-PORT filers as of Sep 2025 (SEC's own Registered Fund Statistics report) — only ~1.5x 13F's 8,783 filer population, not order-of-magnitude larger on filer count alone. **Correction to this map's own earlier framing: N-PORT is currently filed and publicly disclosed quarterly, not monthly** — the 2024 monthly-filing rule has been delayed twice (now Nov 2027/May 2028) and a Feb 2026 SEC proposal would make quarterly-only public disclosure permanent; live-verified against real EDGAR filing dates. Current public volume ≈52,000 filings/year. Row-volume estimate (modeled, not measured, explicitly flagged as such): ~10-26M holdings-rows/year, ~65M-175M cumulative since 2019 — roughly **10x-25x** 13F's live 6.8M-row count, driven by holdings-per-filing (bond funds report every CUSIP; a single large bond fund's one filing ≈35 typical equity-fund filings) not filer count. Confirms money market funds are entirely out of scope for N-PORT (SEC's own applicability table). Flags that narrowing to ETFs-only would cut filer count ~2/3 but should not be assumed to cut row volume proportionally, since broad-market/bond ETFs sit in the same "ETF" bucket as narrow sector ETFs.

## Not yet specified

- Whether/how this dataset should eventually resolve N-PORT's issuer LEI
  to an MDM company entity (the same class of problem
  `mdm-relationship-versioning-gap` Ticket 06 has for 13F CUSIPs, one
  level removed -- LEI-to-CIK resolution has no established mechanism in
  this codebase either). Not sharp enough to ticket until the schema/
  entity design tickets below land and clarify whether issuer resolution
  is even in this map's own scope or a follow-on.
- Whether a gold-layer model (dbt) for fund holdings is part of this
  map's destination or a separate future map -- the destination as
  currently scoped stops at "queryable in the warehouse," which could
  mean silver-only for a first landing.

## Out of scope

- Implementing/deploying the ingestion pipeline itself -- decision-only
  per this map's explicit scope; a future map or direct implementation
  session picks this up once the design is locked.
- Resolving `mdm-relationship-versioning-gap` Ticket 06 (13F CUSIP-stub
  securities never linking to their issuer `MdmCompany` row) -- that
  ticket remains in its own map; N-PORT was investigated as a candidate
  fix and ruled out as a direct solution (see Notes above).
- Money market funds / Form N-MFP -- structurally excluded from N-PORT
  by SEC's own applicability rules (confirmed in Ticket 02: money market
  funds file Form N-MFP, not N-PORT, and never will), not a scoping
  choice this map made. Ingesting N-MFP data would be a separate future
  effort, not a widening of this map.
