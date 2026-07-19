# Phase 9 — edgartools crosscheck (EDGX-01..03) — DISPOSITION

Completed 2026-07-19. Scope set by the Release Owner per-form:
ownership **standard** rigor (~50 filings, identification fields blocking),
ADV **deferred entirely**, financials **small comparison** (10 companies),
API audit **fix-deprecated-now**.

## EDGX-01 — sample-filing comparison: PASS, zero discrepancies

- **Ownership (Forms 3/4/5), 50 live filings** (`edgx01-sample-results.jsonl`):
  50/50 agree, 0 identification diffs, 0 other diffs, 0 errors. Fields
  compared per owner row: owner_cik, owner_name, is_director, is_officer,
  is_ten_percent_owner (blocking — these feed Ticket 21's insider gate) and
  officer_title (non-blocking). Platform rows come from
  `parse_ownership()`; reference values from raw
  `edgar.ownership.Ownership.from_xml` objects on identical XML.
- **Financials, 10 companies** (AAPL MSFT JNJ XOM JPM PG KO CAT T GE):
  10/10 agree on headline-concept presence (Revenues /
  RevenueFromContractWithCustomer... / NetIncomeLoss latest-FY) between
  `parse_entity_facts()` output and the raw companyfacts payload. Small
  comparison by scope decision (fundamental-factors workstream owns depth).
- **ADV: deferred** — Release Owner decision 2026-07-19 ("13F and other
  forms are not critical"); ADV is not on the insider-critical path.

## EDGX-02 — replace-or-justify per hand-built parser

| Parser | Verdict | Reason |
|---|---|---|
| ownership | **Keep (already edgartools-backed)** | `parse_ownership` is a thin adapter over `Ownership.from_xml` (the CLAUDE.md-documented pattern); EDGX-01 shows exact agreement. Nothing to replace. |
| adv | **Deferred, documented** | Release Owner deprioritized ADV (2026-07-19). Revisit only if ADV joins a release-critical path. |
| financials | **Keep** | `parse_entity_facts` consumes the raw SEC companyfacts JSON directly (not an edgartools duplicate); EDGX-01 sample shows no missing headline concepts. Depth owned by fundamental-factors workstream. |

## EDGX-03 — API usage audit vs pinned version: CLEAN

Installed: edgartools **5.30.0** (pin `>=5.29.0`). All 11 distinct runtime
import surfaces verified present. Zero deprecated usages in platform code —
the `edgar.files.*` DeprecationWarnings visible in CI originate INSIDE
edgartools' own modules, not from this repo. Two private-surface uses are
deliberate with documented justification (do not "fix" them):

- `edgar._filings.get_filing_by_accession` — imported solely to call
  `.cache_clear()` after TransientFilingContentError; the public
  `edgar.get_by_accession_number` wrapper does not expose the cache
  (see `_reset_edgartools_filing_cache_after_transient_content_error`).
- `edgar.earnings._parse_period_header` — reuses edgartools' period parsing
  instead of duplicating it; fragile-by-design, guarded by the version pin.

Batch scripts under `scripts/batch/` use broad `from edgar import *`
surfaces — smoke-test scripts, exercised on version bumps per CLAUDE.md,
not runtime code; excluded from the runtime audit verdict.
