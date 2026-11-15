# Managed mirroring guidance and approved resize

Status: claimed
Type: task

## Parts

- [x] Read installed mirror instructions and verify unsupported burstable family; live Snowflake inspection, 2026-11-14 22:10 ET.
- [x] Submit the operator-approved Standard resize; ALTER accepted, 2026-11-14 22:10 ET.
- [ ] Verify READY on the approved family; an accepted request alone is insufficient.
- [x] Update the data-platform skill with generic routing, readiness and separate approval gates; focused guide and reusable SQL template, 2026-11-14 22:10 ET.
- [x] Verify documentation with 110 genericity/path checks and 4 architecture checks; Standards/Spec/GoF reviews completed and literal-input guidance corrected, 2026-11-14 22:10 ET.
- [ ] Publish the skill and operational record in a PR; keep unfinished operation explicit.
- [x] Learning → skill: data-platform/HOSTED-MIRRORING.md records hosted mirroring readiness and resize-versus-create approval boundaries, 2026-11-14 22:10 ET.

## Scope

The operator approved the proposed resize with failover when ready. Mirror
creation remains unapproved and source relation/type pre-flight remains
incomplete. No consumer grants are requested. Credentials and source values
are excluded from this public record.
