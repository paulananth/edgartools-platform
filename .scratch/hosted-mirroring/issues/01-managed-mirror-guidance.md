# Managed mirroring guidance and approved resize

Status: claimed
Type: task

## Parts

- [x] Read installed mirror instructions and verify unsupported burstable family; live Snowflake inspection, 2026-11-14 22:10 ET.
- [x] Submit the operator-approved Standard resize; ALTER accepted, 2026-11-14 22:10 ET.
- [x] Verify READY on the approved family; bounded monitor confirmed STANDARD_M, PostgreSQL 16 and 50 GB, 2026-11-15 06:57 ET.
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
Resize verification completed. Mirror creation remains unapproved; this PR
updates guidance and helper placement only.

## Final-output scope ruling

The operator chose repository configuration as exposure authority, projected
to OpenMetadata, with the same final master and silver table scope for managed
mirroring and AutoOntology. The operator requested skills updates and directed
that reusable scripts live outside infra.

- [x] Document one final-table contract derived from requirements/mappings, with human review before exposure approval and gates for both consumers; skill review, 2026-11-15 06:57 ET.
- [x] Relocate reusable catalog helpers and resize template to their owning skills; callers and explicit configuration updated, 2026-11-15 06:57 ET.
- [x] Verify moved-helper tests, CLI entrypoints, 113 genericity/path checks and isolated bundle portability; Standards/Spec/GoF reviews passed, 2026-11-15 06:57 ET.
- [ ] Publish the revised PR and verify final-head CI.
- [x] Learning → skill: data-profiling owns mapping/requirement evidence and human review; FINAL-TABLES.md owns common consumer scope; data-platform owns portable helper placement, 2026-11-15 06:57 ET.

Exact table-selection configuration, eligibility-tag projection and runtime
enforcement remain implementation gaps; no live tags, consumer inventories,
reader grants or mirrors are changed by this skills update.

## CI failure and fix

The original Engine job failed test_doctor_passes_from_the_installed_bundle
and test_doctor_names_a_command_no_skill_may_write: HOSTED-MIRRORING.md linked
out of the shipped skill tree into infra. An isolated skill-tree reproduction
with the old guide failed on that exact unresolved link. Moving the SQL helper
inside the owning skill fixes the packaging boundary;
test_skill_commands_and_links_resolve_without_checkout passes on the revised
tree. No doctor assertion or packaging guard was relaxed. Final CI remains
required on the revised PR head.

## Integrated human review ruling

The operator confirmed that data-profiling supplies evidence and data-modeling
defines final outputs and per-output current/history scope from requirements
and mappings. The exact proposed table list is included in the existing
requirements-and-mapping approval, with no separate tagging approval round.
The profiling/modeling skills and modeling requirements now state that boundary.
Final Standards and Spec reviews found no conflicting approval rule.

## Tag-controlled consumer skills

- [x] Update hosted mirroring, OpenMetadata and AutoOntology guidance to resolve approved exposure tags into exact physical table lists; missing/pending/stale assignments deny selection and never fall back to schemas, 2026-11-15 07:06 ET.
- [x] Update the installed snowflake-postgres mirror sub-skill with the same optional tag-controlled workflow and validate its frontmatter, 2026-11-15 07:06 ET.
- [x] Keep reusable helpers with owning skills and preserve unrelated checkout WIP; no new infrastructure helper or live operation, 2026-11-15 07:06 ET.
- [x] Verify 113 genericity/path checks, isolated bundle portability, diff formatting and Standards/Spec/GoF review, 2026-11-15 07:06 ET.
- [ ] Publish the tag-controlled skill update and verify final-head CI.
- [x] Learning → skill: exact tag selection, independently verified OpenMetadata projection and explicit reconciliation for removed tags, 2026-11-15 07:06 ET.

The installed mirror skill is a local installation update; the supplied archive
is unchanged. Tag assignment, selector implementation and live publication
remain outside this skills-only task.

## Skill length CI repair

- [x] Reproduce test_every_skill_file_is_short_enough_to_read_whole: the OpenMetadata main skill had 529 lines and failed the unchanged 500-line bound, 2026-11-15 07:17 ET.
- [x] Move the exposure-tag procedure into the owning skills references/EXPOSURE-TAGS.md and link it from the main skill; preserve the full procedure, 2026-11-15 07:17 ET.
- [x] Verify the exact failing test, all six skill-policy checks, isolated bundle portability and 114 guide/genericity checks; main skill is 499 lines, 2026-11-15 07:17 ET.
- [ ] Publish repair and verify CI on its head before readiness/merge.
- [x] Learning → skill: branch-specific OpenMetadata exposure procedure uses progressive disclosure inside the owning skill; helpers remain with their skill, 2026-11-15 07:17 ET.
