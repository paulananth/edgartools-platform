# Managed mirroring guidance and approved resize

Status: claimed
Type: task

## Parts

- [x] Read installed mirror instructions and verify unsupported burstable family; live Snowflake inspection, 2026-11-14 22:10 ET.
- [x] Submit the operator-approved Standard resize; ALTER accepted, 2026-11-14 22:10 ET.
- [ ] Verify READY on the approved family; an accepted request alone is insufficient.
- [x] Update the data-platform skill with generic routing, readiness and separate approval gates; focused guide and reusable SQL template, 2026-11-14 22:10 ET.
- [x] Verify documentation with 110 genericity/path checks and 4 architecture checks; Standards/Spec/GoF reviews completed and literal-input guidance corrected, 2026-11-14 22:10 ET.
- [x] Publish the skill and operational record in draft PR #1794; unfinished resize verification and mirror pre-flight remain explicit, 2026-11-14 22:11 ET.
- [x] Learning → skill: data-platform/HOSTED-MIRRORING.md records hosted mirroring readiness and resize-versus-create approval boundaries, 2026-11-14 22:10 ET.

## Scope

The operator approved the proposed resize with failover when ready. Mirror
creation remains unapproved and source relation/type pre-flight remains
incomplete. No consumer grants are requested. Credentials and source values
are excluded from this public record.

## Follow-up

A local monitor checks the approved resize every 30 minutes, exits on verified
READY/approved family, query failure or a 90-minute deadline, and writes a
private local status record. Final mirror pre-flight remains blocked until
the supported family is verified and source database access is available.
Keep this PR draft until resize verification and the final head checks pass.
