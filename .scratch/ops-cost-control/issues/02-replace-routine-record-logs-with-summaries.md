# Replace Routine Per-Record Logs with Bounded Summaries

Type: task
Status: resolved
Blocked by: 01

## Question

How should the measured routine per-record log contributors be replaced with
bounded stage, batch, or disposition summaries while retaining actionable
failure identity and enough structured context for the seven-day Operational
Forensics Window?

Implement only evidence-ranked contributors. Preserve error and retry evidence,
run/image identity, aggregate counts, durations, skipped/failed dispositions,
and bounded samples where needed. Add regression tests for event cardinality
and required forensic fields.

## Answer

Implemented 2026-08-11, scoped to [Attribute Production Log Volume by Event
Family](01-attribute-production-log-volume.md)'s finding 1 only (the diagnostic
full-payload dump) — not finding 2 (per-record SEC-call/fetch events). Rationale
for the split below.

**What was implemented — finding 1 (61.9M bytes, 71% of records; zero
information loss):**

`_command_result_for_log()` (new, `warehouse_orchestrator.py`, next to
`_emit_pipeline_event`) bounds a command result's `raw_writes` field to
`COMMAND_RESULT_RAW_WRITES_LOG_SAMPLE = 5` entries before printing, adding
`raw_writes_total_count`/`raw_writes_sample_size` when truncated; every other
field in the payload (`run_id`, `command`, `status`, `bronze_object_count`,
`silver_table_counts`, `gold_row_counts`, `snowflake_export_row_counts`, etc.)
is untouched — `raw_writes` is the only field whose size scales with documents
processed. `_print_command_result()` wraps the print call. Both near-duplicate
call sites now go through it: `run_command` (`warehouse_orchestrator.py:265`,
same file) and `execute_standard_command`
(`application/workflows/command_runner.py:39`, calls
`warehouse_orchestrator._print_command_result`) — a plain function extraction
fixing both at once, not a GoF pattern (this is a two-line duplication, not a
pattern-shaped problem — `/gof-refactor-reviewer`'s Rule 0 applies directly:
"extraction problem... say so, don't apply a pattern").

**Confirmed zero information loss before implementing, not assumed:** traced
`raw_writes` end to end. `_execute_warehouse_bronze_capture` passes the exact
same list to `db.complete_pipeline_run(..., raw_writes=raw_writes, ...)`
(`warehouse_orchestrator.py:678,745`), which persists it verbatim into
`pipeline_run.raw_writes_json` (`silver_store.py:3207-3226`) — durably written
into the silver database before it publishes to S3, on both the success and
exception paths. Each entry's underlying document is separately durable as its
own bronze S3 object (`_read_bronze_if_cached`/`_read_bronze_by_checkpoint`,
`warehouse_orchestrator.py:5417-5466`, `layer: "bronze_raw"`). So the full
per-document stdout dump duplicated data captured twice over already — this is
exactly the "Daily-Artifact Run Manifest / Outcome Ledger" duplication ticket
01 flagged, confirmed at the source-line level, not by assumption. Kept a
bounded 5-entry sample (rather than dropping the field) so a human skimming
CloudWatch still sees representative document shape without paying for
thousands of them.

**Deliberately NOT touched — finding 2 (sec_pull_started/completed,
artifact_content_fetch_started/completed, sec_call_started/completed,
~100M bytes):** traced these to `bronze_filing_artifacts.py:253,277,585,606`,
`infrastructure/edgartools_sec_gateway.py:127,150,156,184,209`, and
`infrastructure/sec_client.py:75,86` — all inside the low-level SEC HTTP
client/gateway, emitted per network call/attempt. Unlike finding 1, these are
**not** duplicated elsewhere: they're the only per-call record of retry
attempts, timing, and rate-limit behavior, and this repo has already leaned on
this exact instrumentation to root-cause a real production incident (see
CLAUDE.md's "Artifact-throttle 5-whys" — the per-accession
`sec_pull_completed`/`network_fetches` distinction traces straight back to
these events). Collapsing them into a bounded summary is a genuine, currently
undecided design question — the map's own "Not yet specified" section still
asks "whether their summaries should be per stage, batch, accession
disposition, or bounded time window," and the map's Notes caution "do not
force a pattern merely to aggregate logs." Implementing that now, inside a
task ticket, would be deciding an unresolved design question by fiat rather
than by grilling it — left as a fog item for a future grilling ticket if the
seven-day retention fix (ticket 03) plus finding-1's removal don't already
bring volume into an acceptable range on their own.

**Tests:** `tests/unit/test_command_result_log_summary.py` (new, 8 tests) —
cardinality bound (large list truncated to the sample size, small/at-limit
lists pass through unchanged and un-copied), no mutation of the caller's
original payload, all required forensic fields (`run_id`, `command`, `status`,
`message`, `bronze_object_count`, `silver_table_counts`, `gold_row_counts`,
`snowflake_export_row_counts`) survive bounding verbatim, and two
integration-style tests (`capsys`) proving both `run_command` and
`execute_standard_command` actually print the bounded form end to end. Full
repo suite green: 1986 passed, 4 skipped.

Not yet committed/deployed as of this entry — code change and tests are on
disk only.
