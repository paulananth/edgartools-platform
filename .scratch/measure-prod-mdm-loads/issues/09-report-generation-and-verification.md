# How is the private measurement report produced and verified?

Type: task
Status: open
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
