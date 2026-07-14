# Phase 6 Closure Ledger — Relationship Investigation And Population

**Phase:** 06-relationship-investigation-and-population
**Success Criterion 6:** no relationship type this phase investigated exits in an undocumented
zero state — every one of EDGE-05, EDGE-06, EDGE-09, EDGE-10, EDGE-11 below ends in exactly one
evidenced disposition, cross-referenced to the disposition doc that proves it.

## Disposition categories

The 06-06 plan's `must_haves` frame this as a binary — `{nonzero graph-verified rows | written
evidenced source-coverage exclusion}`. Three of the five types fit that binary cleanly. The other
two (EDGE-09, EDGE-11) do not: they are neither graph-populated nor a source-coverage exclusion
(the source artifact is present and fetchable, and the parser/XML-extraction logic is proven
correct against real data) — they are a **confirmed pipeline bug with an identified fix, not yet
applied**. Forcing either into "excluded" would misrepresent a fixable gap as a permanent
structural one; forcing either into "populated" would claim rows that do not exist. Per advisor
guidance during this session's investigation, a third, explicitly-labeled category is used for
these two so the ledger stays honest rather than fitting a false binary:

- **POPULATED** — nonzero graph-verified edges, named parity check present in
  `POPULATED_RELATIONSHIP_TYPES`.
- **EXCLUDED** — written, evidenced source-coverage exclusion (the source data does not exist,
  cannot be obtained, or the platform's ingestion endpoint structurally cannot surface it).
- **ROOT-CAUSED / FIX DEFERRED** — the zero state is fully explained by a confirmed code-level
  gap with an identified fix location; the fix is not applied in this phase because doing so
  requires a scoped decision (fetch-volume/cost tradeoff) and/or live re-fetch + re-derive +
  sync + graph-count work that is out of this phase's inline scope. This is still a **documented**
  disposition, satisfying Success Criterion 6 — it is not an undocumented zero state.

## Ledger

| Type | Relationship | Disposition | Evidence | Disposition doc |
|------|--------------|-------------|----------|------------------|
| **EDGE-05** | `IS_ENTITY_OF` (adviser→company) | **EXCLUDED** — source-coverage exclusion scoped to the current tracking-list universe | Live SQL: `mdm_adviser JOIN mdm_company ON mdm_company.cik = mdm_adviser.cik WHERE mdm_adviser.cik IS NOT NULL` → 0 of 1 adviser. Row-level confirmed (the one adviser's CIK 105958 matches no company). Re-check required if the adviser universe grows. | `06-06-EDGE05-EDGE06-DISPOSITION.md` |
| **EDGE-06** | `IS_PERSON_OF` (adviser→person) | **EXCLUDED** — source-coverage exclusion scoped to the current tracking-list universe | Live SQL: `mdm_adviser JOIN mdm_person ON mdm_person.owner_cik = mdm_adviser.cik WHERE ... linked_company_entity_id IS NULL` → 0 of 1 adviser, 45 persons. Row-level confirmed. Re-check required if the adviser universe grows. | `06-06-EDGE05-EDGE06-DISPOSITION.md` |
| **EDGE-09** | `EMPLOYED_BY` (person→company) | **ROOT-CAUSED / FIX DEFERRED** | Parser (`parse_proxy_fundamentals`) confirmed correct against actual bronze-captured content (5 rows, real Apple DEF 14A). `sec_executive_record`/`sec_earnings_release` are 0 rows platform-wide (266,634 8-K + 52,200 DEF14A-family filings). Live Step Functions + CloudWatch evidence: `Stage1BPerFiling` runs without error and silently skips 100% of candidate filings (1822/1822) because `sec_filing_attachment` has zero rows for them. Root cause: `_is_configured_parser_form` (`warehouse_orchestrator.py:1859-1861`) gates the bulk artifact-fetch pipeline to `OWNERSHIP_FORMS`/`ADV_FORMS` only — 8-K/DEF14A/DEFA14A/PRE14A are never selected for attachment fetch. Fix identified (widen the gate) but not applied — would multiply bulk SEC fetch volume by the size of these form populations (~266k + ~52k filings), a capacity/cost decision out of inline scope. | `06-04-EDGE09-EDGE11-DISPOSITION.md` (2026-07-13 update) |
| **EDGE-10** | `AUDITED_BY` (company→audit_firm) | **EXCLUDED** — source-coverage exclusion (structural SEC API limitation) | Live SEC EDGAR evidence across 3 unrelated large-cap filers (Apple, Microsoft, NVIDIA) plus a clean control fact (`dei:EntityRegistrantName`): the `companyfacts` aggregate API structurally never surfaces `ix:nonNumeric`-tagged DEI facts (`AuditorFirmId`/`AuditorName`/`AuditorLocation`), for any company. `_derive_audited_by` confirmed correct as-is; the gap is entirely upstream (endpoint selection, not a bug). Resolving this would require a new per-filing inline-XBRL ingestion path — an architectural change, out of this milestone. | `06-05-EDGE10-DISPOSITION.md` |
| **EDGE-11** | `INSTITUTIONAL_HOLDS` (adviser→security) | **ROOT-CAUSED / FIX DEFERRED** | Same root cause as EDGE-09: `_is_configured_parser_form` never selects 13F-HR for the bulk artifact-fetch pipeline (0 of 48,877 `13F-HR` filings platform-wide have any `sec_filing_attachment` row). A separate, real bronze-fetch fast-path bug was also found and fixed (`bronze_filing_artifacts.py`'s `_MULTI_ATTACHMENT_FORMS` gate, committed + unit-tested) — but that fix is downstream of the gate above and is only reachable via `targeted_resync`'s single-accession path, never via a standard bulk `load_history`/`bootstrap-batch` run. Both the fast-path fix and the upstream gate widening are required to reach "populated"; only the fast-path fix is applied. | `06-04-EDGE09-EDGE11-DISPOSITION.md` (original + 2026-07-13 update) |

## Success Criterion 6 assertion

**No type in this ledger exits in an undocumented zero state.** Every one of EDGE-05, EDGE-06,
EDGE-09, EDGE-10, EDGE-11 has exactly one disposition above, each backed by live evidence (SQL
queries against dev MDM Postgres, live SEC EDGAR API calls, or live Step Functions execution
history + CloudWatch logs) and a cross-referenced disposition document. Two exclusions (EDGE-05,
EDGE-06) are explicitly scoped to the current small adviser universe and carry a re-check
trigger. One exclusion (EDGE-10) is a structural, not re-fetchable, upstream API limitation. Two
(EDGE-09, EDGE-11) share one root cause and one identified-but-deferred fix — not a permanent
exclusion, but a documented, evidenced gap with a concrete next step, not silence.

## POPULATED_RELATIONSHIP_TYPES status

`POPULATED_RELATIONSHIP_TYPES` (`edgar_warehouse/mdm/snowflake_graph.py:39`) is **unchanged**
this phase: `("COMPANY_HOLDS", "HOLDS", "ISSUED_BY", "IS_INSIDER")`. None of this phase's 5
investigated types reached graph-verified-populated status (2 excluded on data grounds, 1
excluded on a structural API grounds, 2 root-caused with a deferred fix) — per D-05's sequencing
guard, a type must not be added before its own `mdm sync-graph` has produced rows. Adding any of
the 5 now would false-fail `verify-graph`'s named parity check for a type this environment has
never actually populated. `tests/mdm/test_cli_snowflake_graph.py` (18 tests) re-verified passing
with the tuple unchanged.

## Concrete next steps (deferred, not attempted this phase)

1. **EDGE-09/EDGE-11 shared fix**: widen `_is_configured_parser_form`
   (`warehouse_orchestrator.py:1859-1861`) to include 8-K, DEF 14A/DEFA14A/PRE 14A, and 13F-HR —
   a scoped decision given the resulting fetch-volume increase (~266k 8-K + ~52k proxy + ~49k
   13F-HR filings), then: deploy → `--force` re-fetch of already-captured filings for these forms
   → re-derive (`EMPLOYED_BY`, `INSTITUTIONAL_HOLDS`) → `mdm sync-graph` → graph-count
   verification → add both to `POPULATED_RELATIONSHIP_TYPES`.
2. **EDGE-05/EDGE-06 re-check trigger**: re-run the D-04 SQL zero-overlap check if the adviser
   universe grows beyond its current 1 entity (e.g. new ADV electronic filings, a broader
   tracking-list expansion).
3. **EDGE-10**: would require a new per-filing inline-XBRL ingestion path (parsing each 10-K's
   own cover-page facts) — a new architectural surface, not scoped to this milestone.
