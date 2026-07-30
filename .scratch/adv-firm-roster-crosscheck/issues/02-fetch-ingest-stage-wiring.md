# 02 — Fetch + ingest + Stage wiring for Firm Roster

**What to build:** A Firm Roster fetch entry point (either a `fetch-adv-bulk` sibling
command, or an added mode on the same command, reusing its pure decision functions —
`periods_to_fetch`, `select_downloadable`, etc. — for the Firm Roster's own monthly
cadence) that downloads the CSV zip, computes its SHA-256, stages it to S3 per ADR 0002's
bronze-persist-on-fetch convention (same family as the already-bronze-persisted IAPD Form
ADV Part 1 public bulk), and writes a manifest entry with a new `kind: "iapd_firm_roster"`.

Add a new `elif kind == "iapd_firm_roster":` branch to `ingest-relationship-sources`'s
existing `kind`-dispatch block in `warehouse_orchestrator.py` (which already branches on
`"iapd_adv_bulk"` and `"sec_subsidiary_exhibit"`), calling ticket 01's parser's ingest
function. No new CLI surface for consumption — this reuses the existing generic
manifest-consuming command.

Wire the Firm Roster fetch into the same `AdvBulkFetch` Stage the sibling
[ADV fetch pipeline wiring spec](../../adv-fetch-pipeline-wiring/spec.md) already added to
`load_history` and `daily_incremental` (now shipped — see that spec's tickets 01/02). The
Firm Roster fetch runs alongside the existing `advFilingData` fetch in that same Stage, on
the same daily cadence — no separate Step Functions schedule. It shares the Stage's
existing lenient `Catch` (falls through to `MdmRun` on failure): a Firm Roster fetch/parse
failure must never affect MDM entity resolution, graph sync, or the existing
`advFilingData` ingestion path, since this cross-check is purely additive.

**Blocked by:** Ticket 01 (Firm Roster parser + silver table) — the ingest dispatch branch
needs the parser's ingest function to call.

**Status:** ready-for-agent

- [ ] Fetch decision logic (Firm Roster's own `periods_to_fetch`/`select_downloadable`
      equivalents, and its manifest `kind` value) is tested at the same seam
      `tests/application/test_adv_bulk_fetch.py` already uses for `advFilingData` — pure
      functions, fake `fetch_metadata`/`fetch_archive`/`upload` callables, no real network
      or S3 calls.
- [ ] `ingest-relationship-sources`'s `kind`-dispatch test coverage is extended with an
      `"iapd_firm_roster"` case, asserting the new parser is invoked and its row counts are
      reflected in `rows_written`.
- [ ] The generated `load_history` and `daily_incremental` Step Functions JSON show the
      Firm Roster fetch running inside the existing `AdvBulkFetch` Stage (structural test
      additions in `tests/architecture/test_load_history_state_machine.py` and
      `test_daily_incremental_state_machine.py`, following those files' existing
      conventions), with the same lenient `Catch`-to-`MdmRun` behavior as the rest of the
      Stage.
- [ ] All pre-existing tests in the touched files still pass.
