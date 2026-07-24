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
- Existing contract:
  [`docs/release-readiness/adviser-fund-source-contract.md`](../../docs/release-readiness/adviser-fund-source-contract.md),
  approved via `.scratch/release-readiness/issues/13-define-adviser-fund-source-contract.md`
  (resolved) and implemented per
  `.scratch/release-readiness/issues/21-implement-authoritative-form-adv-private-fund-ingestion.md`
  (marked resolved, commits `ddc24d3`/`846d648`/`4f4e1a9`). **Ticket 01
  found the contract and parser were never actually broken** — last
  session's "zero rows" finding came from staging the wrong SEC product
  (the sec.gov Firm Roster CSV) instead of the correct one
  (`adviserinfo.sec.gov`'s monthly `advFilingData` relational feed, which
  the parser's existing regexes match exactly). This map still owns Ticket
  21 (explicit user decision, 2026-07-24), but the reconciliation is now
  much lighter: confirm the operational fetch target, not rewrite the
  parser. See ticket 01's Answer/research file for full detail.
- Every session should default to `/grilling` + `/domain-modeling` for
  design decisions; use `/research` (background subagent) for fact-finding
  that needs primary-source SEC/IAPD documentation, not code already in
  this repo.
- **Corrected by ticket 01 (2026-07-24):** the authoritative per-fund source
  (`advFilingData`) is a **monthly delta of filing activity**, not a
  full-universe snapshot — verified by row count (June 2026: 2,938 firm
  rows vs. ~17,073 registered firms total, ~17% coverage). This is actually
  closer in shape to 13F/proxy's windowed relationship types than
  originally assumed — it needs a rolling multi-month union (deduped by
  CRD/FilingID, latest per firm), not a single current-snapshot fetch. The
  separate Firm Roster CSV (`sec.gov`) *is* a true full-universe
  point-in-time snapshot, but only carries aggregate private-fund counts,
  not per-fund identity. Ticket 03's Q1/Q2 answers need to be revisited
  under this corrected model.
- **Hard requirement, restated explicitly by the user (2026-07-24): ADV data
  must reach the Neo4j/Snowflake graph, end to end — not stop at silver.**
  This binds every ticket's resolution, especially ticket 02: if bulk data
  truly only supports firm-level aggregate private-fund counts (no PFID),
  that may force `MANAGES_FUND` itself to degrade or drop — but it must
  **not** become a reason to drop Adviser/Fund entity resolution or graph
  sync altogether. At minimum, resolved Adviser and Fund entities (from
  whatever the Firm Roster format actually supports) must resolve into MDM
  and sync to the hosted graph; `MANAGES_FUND` edge fidelity is the part
  that's genuinely at risk pending ticket 01/02, not the graph destination
  itself. Ticket 04's manual validation is the checkpoint that proves this
  actually happened (real nodes/edges, not the placeholder 112/1 counts).

## Decisions so far

- [01 — Confirm Scope of IAPD Bulk Format Change](issues/01-confirm-scope-of-iapd-format-change.md)
  — the old relational per-fund format was never discontinued; it moved to
  `adviserinfo.sec.gov`'s monthly `advFilingData` feed. `adv_bulk_ingest.py`'s
  existing parser already matches this feed's real files — last session's
  "zero rows" blocker was caused by fetching the wrong SEC product, not a
  format change the parser needs rewriting for. New finding: the feed is a
  monthly filing-activity delta (~17% of firms/month), not a full snapshot,
  so full coverage needs a rolling multi-month window.
- [03 — ADV Time-Scope and Cadence Semantics](issues/03-adv-time-scope-and-cadence-semantics.md)
  — `load_history` fetches a rolling ~13-month window of monthly deltas
  only (no 2000-2024 historical backfill, mirroring the 13F/proxy
  narrow-to-current-state precedent); `daily_incremental` runs daily gated
  by a local `dataset_period`-already-ingested check (unchanged by the
  delta-vs-snapshot correction); each `dataset_period` is fully immutable
  once ingested; ERA and RIA get identical handling.

## Not yet specified

- Longer-term: whether ADV data should ever get its own Stage-0-style phase
  woven into `load_history`/`daily_incremental` the way Company Identity did
  (company-master-pipeline tickets 05/06), or stays a separate
  `ingest-relationship-sources` invocation alongside them — ticket 06
  resolves the immediate wiring shape; whether it later gets promoted to a
  first-class phase is out of view until that ships and is observed running.

## Out of scope

(none yet)
