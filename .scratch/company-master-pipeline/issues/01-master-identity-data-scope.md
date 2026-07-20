# 01 — Master identity data scope

Type: grilling
Status: resolved

## Question

Exactly which SEC data source(s) constitute "master identity" for this
pipeline? Candidates already captured elsewhere in the platform today:

- `company_tickers.json` / `company_tickers_exchange.json` — global reference
  files, already captured by `_sync_reference_data` (ticker/CIK/exchange
  mapping only).
- Per-CIK `submissions.json` — already captured by every `bootstrap-batch`
  run (`_capture_submissions_main`); carries entity name, SIC code, entity
  type, former names, addresses.

Does "master identity" mean reusing these two existing captures as-is (just
under this pipeline's own orchestration/sequencing), or does it need
additional fields/sources not currently captured anywhere?

## Blocked by

None — can start immediately.

## Answer

Reuse both existing captures as-is, nothing new to build: global
`company_tickers.json`/`company_tickers_exchange.json` reference data (ticker/
CIK/exchange mapping, via `_sync_reference_data`) plus per-CIK
`submissions.json` (entity name, SIC code, entity type, former names,
addresses, via `_capture_submissions_main`). This pipeline's job is
orchestration/sequencing of already-captured data, not new SEC ingestion.
