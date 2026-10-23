# Publish governed owner installation learning

Type: task
Status: resolved
Assignee: Codex

## Parts

- [x] Review the storage ticket's normal caller and independent installation evidence — PostgreSQL/MySQL five-wheel proofs pass, 2026-10-23 15:20 ET.
- [x] Document the normal owner installation boundary, exact configuration numbers, pending recovery and inherited grants in mdm-engineering — skill and storage reference updated, 2026-10-23 15:20 ET.
- [x] Validate source neutrality and registered commands — 79 genericity/skill-command tests pass; the local storage-reference link and its heading resolve, 2026-10-23 15:20 ET.
- [x] Publish a separate PR with the implementation prerequisite — PR #1153 names #1152 as its merge prerequisite, 2026-10-23 15:30 ET.
- [x] Verify CI on the guidance revision and retain final landing-head checks and named merge approval as separate PR gates — all nine checks pass at 51582ecd, 2026-10-23 15:30 ET.
- [x] Learning → skill: mdm-engineering, Governed owner installation; exact-number, recovery and grant qualification guidance updated and 79 checks pass, 2026-10-23 15:20 ET.

## Scope

Documentation only. This guidance depends on governed-storage engine PR #1152;
merge it after that prerequisite. Normal MySQL mastering, SQL Server normal
installation, PostgreSQL routine retirement and source activation stay open.

## Review

### Standards

Separate fresh branch and worktree. Provider/source/entity-neutral instructions;
counts and invented fixtures only. No credentials or deployment changes.

### Spec

Explains the qualified normal-owner workflow and its remaining merge boundary.
Recovery requires restoration for a missing installed object. Exact-number
readback and inherited column grants are qualification requirements.

### GoF

Documentation-only guidance for the existing adapter seam. No new abstraction
or duplicated merge algorithm; no design-pattern refactor warranted.

## Answer

The normal-owner installation boundary and its exact-value, grant and recovery
requirements now live in mdm-engineering and its storage reference. All 79
local checks and all nine CI checks pass on the published guidance revision.
Merge after implementation #1152 and named operator approval. This
checklist-only closeout also needs green final-head checks, whose live status
is held in the PR rather than another recursive CI-status commit.
