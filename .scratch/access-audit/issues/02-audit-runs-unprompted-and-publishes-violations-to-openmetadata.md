# The access audit runs with no setup and publishes each finding to OpenMetadata as a violation

Status: claimed
Type: task

Operator, 2026-11-22: "do not add additional requirements for running audit, it must be exposed to openmetadata as violation no word is needed to run audit".

Found while closing ticket 14 of the hosted-mirroring map: `access_audit.py` ran only the workstation platform, because the Snowflake adapter's
`configured(env)` needs `AUDIT_SNOWFLAKE_CONNECTION` to be exported, and the script needs `edgar_warehouse` installed. The Snowflake policy
control (POL) was therefore never read.

## Checklist

- [x] Failing test first (failed: `configured({})` was False; passes now, 55 unit tests green) 2026-11-22 12:22 ET: an audit run with an empty environment still reads Snowflake through the auditor connection (`edgartools-audit`) and reports POL as pass or fail, never "not configured"
- [x] Snowflake runs with no exported variable (live run read 12 controls as the auditor) 2026-11-22 12:22 ET; ~~no `uv sync`~~ still open: the postgres adapter imports `edgar_warehouse`: the auditor connection is the default, and every read stays read-only (the audit still refuses an administrator identity)
- [ ] Each failed or not-tested control is published to OpenMetadata as a violation (control id, platform, severity, the fix), with no operator words needed to run or publish
- [ ] The publication follows the OpenMetadata skill's existing exposure path; no second catalog client
- [ ] Standards, Spec and GoF review of the diff
- [ ] Re-run the audit on `snowflake`: POL passes (closes the open line of hosted-mirroring ticket 14)
- [ ] Learning → skill: name the access-audit skill line this ticket changed, or "none"
- [ ] Finding: POL is NOT_TESTED because the auditor holds no privilege on the two policies (DESCRIBE fails with "must have at least one privilege granted on POLICY"; SHOW lists none). The only policy privilege that allows it (APPLY) also lets the role attach policies, which breaks read-only: decide the read path (ACCOUNT_USAGE views lack the values) before granting
- [x] Decision (operator, 2026-11-22: "use the procedure skill and make it vendor audit so that we can add other data platforms"): read policy values through an administrator-owned read-only reader with one vendor-neutral JSON shape; Snowflake's is a procedure in Terraform (`terraform validate` passes, 56 unit tests green); not applied yet 2026-11-22 12:29 ET
- [ ] Apply the procedure and its grant (access-admin identity or a bootstrap), then re-run POL
