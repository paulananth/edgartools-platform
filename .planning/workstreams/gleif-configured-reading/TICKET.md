# Configured GLEIF reading and complete parser retirement

Continue the original self-sustaining skills / Rules creator / parsing / MDM / custom-mode goal. Local qualification only. Branch `codex/gleif-configured-reading-20261005` follows ready PR #830; no merge or source activation is authorized here.

- [x] Verify complete cached Level 1 JSON parity against the independent historical reader, including typed values, key order, canonical digest, metadata count, archive bytes, expanded bytes, CRC and EOF — 2026-10-06 06:12 ET, full-level1-json-parity.json records 3,428,477 exact comparisons, zero differences, 13,252,301,819 expanded bytes, 5,618.33s (93.6 minutes). Configured projection, XML and mastering remain separate unfinished gates.
- [ ] Project framed JSON records inside the native engine using the existing configured table interpreter; measure against the current Python materialization/serialization path on captured records.
- [ ] Add configured GLEIF member contracts, approved scope and source metadata evidence; qualify installed private publication and refusal/recovery.
- [ ] Implement and qualify generic XML record framing, namespace/header/metadata assertions and all three GLEIF members.
- [ ] Replace active GLEIF runtime consumers and remove the old reader/dependency after complete source proof.
- [ ] Replace remaining Company landing/preparation/provenance/census/cascade routes with configured reading and mastering.
- [ ] Prove installed empty-store 6,414 Company / 3,052 CIK+LEI population, unchanged replay and recovery.
- [ ] Reconcile Claude/Codex completion trackers against live merged code and verification; delete remaining retired parser code and tests.
- [ ] Independent review, affected tests, restricted PostgreSQL 16 installed qualification and full CI; create reviewable PRs.

GoF/history review: `source_stream.py` currently converts each native record into Python, serializes it again and calls the ordinary engine. The stable engine's table interpreter should remain one function; native framing can call it on an existing typed tree. No source-specific strategy classes or loader callbacks are needed. Preserve measured numeric and object-order semantics before adopting the faster boundary.

Full JSON comparison runs as process handle 98749 using `/private/tmp/codex-full-gleif-parity.py`; results will be written only after complete EOF. Metadata declares 3,428,477 Level 1 records. Two independent authenticated compressed snapshots avoid macOS shared file offsets; expanded content remains streamed. Do not restart solely because an observation expires.

PR #830 is merged as bc146cd4 and #831 is merged as d4f7fe36. Rebase this active branch onto current main while preserving its native-projection work. Both isolated review agents are unavailable due to their usage limit; complete a focused manual review before reporting independent review coverage.
