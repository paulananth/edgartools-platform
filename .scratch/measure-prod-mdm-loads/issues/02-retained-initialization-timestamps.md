# Which initialization timestamps are actually retained?

Type: research
Status: resolved
Blocked by:

## Question

The measurement report has an `initialization` section: instance request start, `READY` time,
per-store migration durations, and an end-to-end-from-init interval. Which of those timestamps
exist in retained evidence, and which must be reported as `unavailable`?

Search the private `~/.local/share/edgartools/load-logs/` directory, the private
`~/.local/share/edgartools/hosted-prod/` metadata (names, timestamps and event kinds only — never
the raw body of `create-instance.json`), and the repository's checked-in operational records, for:

1. The Snowflake operation-log record of the `CREATE POSTGRES INSTANCE` request — its start time.
2. The recorded `READY` observation time for `EDGARTOOLS_PROD_MDM`.
3. MDM migration command events (`mdm_command_started` / `mdm_command_completed`, carrying
   `duration_ms` and UTC `emitted_at`) for MDM, Bookkeeping, Silver and Change Journal.
4. Any earlier evidence that could substitute for an exact init start, and why it does or does not
   qualify (a file modification time does not).

Report each as found-or-not-found with the exact evidence path, the event kind and the timestamp in
UTC and in ET. Distinguish what the plan's `initialization_ready_at_et` field can hold from what
needs a separate `unavailable_reason`. Write the findings to
`.scratch/measure-prod-mdm-loads/evidence/02-retained-initialization-timestamps.md`. No credentials,
DSNs or host values.

## Answer

Evidence: [02-retained-initialization-timestamps.md](../evidence/02-retained-initialization-timestamps.md)
(branch `codex/wayfinder-measure-prod-loads-20261113`, commit `7758ed5b`).

- **Instance request start and end: found exactly.** `CREATE POSTGRES INSTANCE` ran
  2026-11-10 21:31:51.570 → 21:32:06.340 ET (SUCCESS), from the retained Snowflake query-history
  export `measure-prod-readonly-20261112T180117Z/query-history-postgres.json`. The instance's own
  `created_on` is 2026-11-10 21:32:04.947 ET.
- **Exact READY transition: not found.** The earliest provable observation of `READY` is the
  2026-11-12 11:53:53 ET `SHOW POSTGRES INSTANCES`; no `DESCRIBE` result body was retained.
  `ready_transition_at_et` stays `null`; an observation field may carry 2026-11-12 11:53:53 ET
  labelled as an observation.
- **Per-store migration durations: not found.** No migration ran through Snowflake SQL, no
  migration event was retained, and no migration may be re-run to manufacture timings.
- **Only `build-lookups` command events exist** (5 events in 3 logs) — not initialization.
- **Consequence:** `end_to_end_from_init_seconds` stays `null`; the report keeps the verified
  baseline interval as its elapsed measure.
