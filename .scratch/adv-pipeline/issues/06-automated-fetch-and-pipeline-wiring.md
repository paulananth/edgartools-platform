# 06 — Automated Fetch and Pipeline Wiring Shape

Type: grilling
Status: open
Blocked by: 02, 03, 04
Blocks: none

## Question

With the parser/private-fund strategy (ticket 02), cadence semantics
(ticket 03), and a manually-validated pipeline (ticket 04) all settled,
decide the concrete shape of automated ingestion:

1. What component scrapes the IAPD bulk-data listing page for the current
   month's (non-predictable) filenames, downloads, SHA-256s, and stages to
   S3 — a new `edgar-warehouse` CLI subcommand (mirroring the
   `ingest-relationship-sources --kind iapd_adv_bulk` manifest-based
   pattern), or something else?
2. How does it plug into `load_history` — a new Stage, or a step within an
   existing stage? (Company Identity's precedent in
   `.scratch/company-master-pipeline/issues/05-bulk-mode-state-machine-shape.md`
   wove itself in as a strict Stage 0 before Branch A; decide whether ADV
   should mirror that shape or stay a standalone invocation per this map's
   "Not yet specified" note on first-class-phase promotion.)
3. How does it plug into `daily_incremental` given ticket 03's monthly
   cadence answer — same state machine, gated by a cheap
   already-ingested-this-month check so it no-ops on every day that isn't a
   new snapshot month?
4. What CLI flags/state-machine inputs thread the `dataset_period`
   idempotency key through, mirroring how `artifact_policy` was threaded
   through `load_history`'s SM input for the artifact-throttle fix?

## Answer

(pending)
