# ADV Pipeline

## Destination

A decided, buildable plan for the full Form ADV data pipeline: reconcile the
existing adviser-fund source contract with the real current SEC/IAPD bulk
format (confirmed changed as of 2026-07-24 — see Notes), decide the
private-fund-detail strategy, and specify automated fetch wired into
`load_history` (baseline) and `daily_incremental` (ongoing refresh), all the
way through silver → MDM entity resolution → derived relationships →
Neo4j/Snowflake graph. Hands off to `/to-spec` + `/to-tickets` +
`/implement` once the map is clear — this map decides, it does not build
(with the narrow exception of the manual end-to-end validation task, which
is execution needed to unblock a later decision, not the destination itself).

## Notes

- Domain: edgartools-platform, AWS-first SEC EDGAR data platform. Consult
  root `CONTEXT.md` for canonical vocabulary; flag conflicts via
  `/domain-modeling` rather than silently overriding.
- **This is the "own future map" that `company-master-pipeline`'s map
  explicitly deferred** ("ADV pipeline shape (own future map)" in its Not
  yet specified section) — that map's Company Identity Pipeline work is a
  separate, already-decided effort and is not touched here.
- Standing preference: reuse existing capabilities before building new
  ones. Confirmed already working (validated live against Ticket 20's graph
  work, 2026-07-23/24): `mdm run --entity-type adviser --entity-type fund`,
  `mdm derive-relationships`, `mdm sync-graph`, `mdm verify-graph`,
  `mdm graph-activate`, and `ingest-relationship-sources --kind
  iapd_adv_bulk` (needs a source manifest with `storage_path` + `sha256`,
  already implemented). The only genuinely missing/broken pieces are: (1)
  the parser's assumed archive format, (2) automated fetch, (3) pipeline
  wiring.
- Primary context artifact for this whole map:
  [`docs/release-readiness/adv-bulk-ingest-format-change-2026-07-24.md`](../../docs/release-readiness/adv-bulk-ingest-format-change-2026-07-24.md)
  — documents the live-format discovery and a candidate ordered next-steps
  list this map formalizes into tickets.
- Existing (now-questionable) contract:
  [`docs/release-readiness/adviser-fund-source-contract.md`](../../docs/release-readiness/adviser-fund-source-contract.md),
  approved via `.scratch/release-readiness/issues/13-define-adviser-fund-source-contract.md`
  (resolved) and implemented per
  `.scratch/release-readiness/issues/21-implement-authoritative-form-adv-private-fund-ingestion.md`
  (marked resolved, commits `ddc24d3`/`846d648`/`4f4e1a9`) — but that
  implementation's `_rows()` filename regexes in
  [`edgar_warehouse/application/adv_bulk_ingest.py`](../../edgar_warehouse/application/adv_bulk_ingest.py)
  target the old relational archive shape (`IA_ADV_Base`,
  `Schedule_D_7B1/7B2`, `ADV_Filing_Types`) and matched **zero rows** when
  tested against the live July 2026 SEC bulk archive
  (`IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_<id>.CSV`, a single flat file with
  aggregate-only private-fund counts). This map owns re-deciding Ticket 21,
  not release-readiness's map (explicit user decision, 2026-07-24).
- Every session should default to `/grilling` + `/domain-modeling` for
  design decisions; use `/research` (background subagent) for fact-finding
  that needs primary-source SEC/IAPD documentation, not code already in
  this repo.
- IAPD bulk data is a full point-in-time **roster snapshot** (current firms
  + their current filing state), not a historical time-windowed feed like
  13F/proxy — there is no "N years of ADV data" to fetch the way there is
  for filing-based relationship types. The original "run ADV for 1 year"
  framing does not map onto how the source actually works; ticket 03
  resolves what cadence/scope concept replaces it.

## Decisions so far

(none yet)

## Not yet specified

- Whether `MANAGES_FUND`'s graph contract (PFID-keyed, no name-only
  identity, per `adviser-fund-source-contract.md`) needs to change shape if
  bulk data truly only offers firm-level aggregate counts — depends on
  ticket 01's research answer and ticket 02's strategy decision; too coarse
  to ticket until those land.
- Longer-term: whether ADV data should ever get its own Stage-0-style phase
  woven into `load_history`/`daily_incremental` the way Company Identity did
  (company-master-pipeline tickets 05/06), or stays a separate
  `ingest-relationship-sources` invocation alongside them — ticket 06
  resolves the immediate wiring shape; whether it later gets promoted to a
  first-class phase is out of view until that ships and is observed running.

## Out of scope

(none yet)
