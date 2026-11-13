# How is the private measurement report produced and verified?

Type: task
Status: resolved
Blocked by: 05, 06, 08

## Question

The measurement ends in one private report. This ticket settles how it is produced, where it lives,
and how it is checked — before anyone reads it as a result.

Decide and record:

1. The report directory under `~/.local/share/edgartools/load-logs/` — its name, its mode `0700`,
   and the modes `0600` on each file inside it.
2. The report's files: the Markdown report, the structured JSON, the source snapshot it was built
   from, and the validation result. The Markdown never carries a credential, DSN, host value,
   source row value or record identifier.
3. The reconciliation checks the validation step performs and must pass:
   - every configured source/target name from the inventory appears exactly once;
   - every completed run has expected units equal to verified units and zero pending deliveries;
   - every load summary satisfies `considered = selected + already_processed`;
   - every bundle run ID is present in its target's row;
   - `end_to_end_from_init_seconds` exists only when both init endpoints exist;
   - every entity row lists its active contributing source contracts and its link status;
   - `unique_master_count` is `unavailable` wherever no approved record-reader count exists;
   - no `active_command_seconds` or `target_wall_seconds` is presented where its timestamps are
     missing.
4. The redaction pass: how a scan confirms no forbidden value is present, without printing any
   value in the process.
5. The retention rule: what is kept, for how long, and where — and that the raw Snowflake outputs
   stay private beside the report rather than being copied into it.

Record the resolved procedure in the ticket, and append a one-line gist to the map's Decisions so
far.

## Answer

Decided 2026-11-13. The procedure is specified; the report itself is produced by the handoff
session ([10](10-measurement-handoff.md)), not by this map.

### A. Where it lives

```
~/.local/share/edgartools/load-logs/measure-prod-<YYYYMMDD-HHMMSS-ET>/
```

- directory mode `0700`; every file inside mode `0600`.

### B. What is in it

| File | What it is |
|---|---|
| `report.md` | the human artifact |
| `report.json` | the structured report — the Markdown is a rendering of it, never a separate claim |
| `metadata.json` | target, code ref, rules versions, gates, baseline, evidence file list with sha256 |
| `validation.json` | the reconciliation checks below and their outcome |
| `evidence/` | copies of the retained exports the report was built from, each with its sha256 |

The Markdown never carries a credential, DSN, host value, source row value or record identifier.
The raw Snowflake outputs stay private **beside** the report and are never copied into it.

### C. The validation checks

The validation step must pass, and its failures name the row at fault:

1. Every configured source/target name from the inventory appears exactly once — 13 sources, 17
   measured names (19 configured, minus the two capture targets).
2. Every run counted as verified has `state == complete`, `verified == units` and `pending == 0`.
3. Every load summary reconciles `considered = selected + already_processed` — 32 invocations.
4. Every bundle run id appears in its target's row.
5. `end_to_end_from_init_seconds` exists only when both initialization endpoints exist — it is
   absent, because the READY transition is unavailable.
6. Every entity row lists its gating contributing contracts and its link status, and states the
   explained count as unchecked.
7. `unique_master_count` is `unavailable` wherever no approved record-reader count exists — which
   is everywhere.
8. No `active_command_seconds` or `target_wall_seconds` is presented where its timestamps are
   missing.
9. Every step interval carries the rules version that produced it, and a step the current Rules
   declare but the retained runs did not run is marked not evidenced.
10. Every timestamp is ET with the correct offset across the November DST boundary.

### D. The redaction pass

A scan over every output file checks that no value from the credential-bearing sources appears:
the private `*.env` files' values, the `create-instance.json` body, the Snowflake host, and any
`postgresql://` or `snowflake://` URI. The scan **reports a count of matches, never the matched
value**. A non-zero count fails the report.

### E. Retention

The report directory and its evidence copies are kept as long as the retained load logs are — they
sit in the same private tree under `~/.local/share/edgartools/load-logs/`, mode `0700`. The raw
Snowflake outputs remain private beside the report; they are evidence, not report content.
