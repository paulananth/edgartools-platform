# Publish each audit finding to OpenMetadata, run Postgres without uv sync, import the policy reader

Status: open
Type: task

Operator, 2026-11-22: "do not add additional requirements for running audit, it must be exposed to openmetadata as violation no word is needed to run audit". Parts moved from ticket 02.

## Checklist

- [ ] Each failed or not-tested control is published to OpenMetadata as a violation (control id, platform, severity, the fix), with no operator words needed to run or publish
- [ ] The publication follows the OpenMetadata skill's existing exposure path; no second catalog client
- [ ] The audit runs with no `uv sync`: the postgres adapter imports `edgar_warehouse` lazily
- [ ] Import the policy reader procedure and its grant into the access Terraform state
- [ ] Learning → skill: name the skill line this ticket changed, or "none"
