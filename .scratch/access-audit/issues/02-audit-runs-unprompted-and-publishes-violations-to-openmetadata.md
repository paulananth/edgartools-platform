# The access audit runs with no setup and publishes each finding to OpenMetadata as a violation

Status: open
Type: task

Operator, 2026-11-22: "do not add additional requirements for running audit, it must be exposed to openmetadata as violation no word is needed to run audit".

Found while closing ticket 14 of the hosted-mirroring map: `access_audit.py` ran only the workstation platform, because the Snowflake adapter's
`configured(env)` needs `AUDIT_SNOWFLAKE_CONNECTION` to be exported, and the script needs `edgar_warehouse` installed. The Snowflake policy
control (POL) was therefore never read.

## Checklist

- [ ] Failing test first: an audit run with an empty environment still reads Snowflake through the auditor connection (`edgartools-audit`) and reports POL as pass or fail, never "not configured"
- [ ] The audit runs with no exported variable and no `uv sync`: the auditor connection is the default, and every read stays read-only (the audit still refuses an administrator identity)
- [ ] Each failed or not-tested control is published to OpenMetadata as a violation (control id, platform, severity, the fix), with no operator words needed to run or publish
- [ ] The publication follows the OpenMetadata skill's existing exposure path; no second catalog client
- [ ] Standards, Spec and GoF review of the diff
- [ ] Re-run the audit on `snowflake`: POL passes (closes the open line of hosted-mirroring ticket 14)
- [ ] Learning → skill: name the access-audit skill line this ticket changed, or "none"
