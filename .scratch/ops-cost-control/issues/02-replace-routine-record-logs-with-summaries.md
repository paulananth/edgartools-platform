# Replace Routine Per-Record Logs with Bounded Summaries

Type: task
Status: open
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
