# AWS running-resource check

Type: task
Status: resolved

## Request

Operator: "add this to skill", following a live AWS running-resource inventory.
Document the repeatable read-only check and distinguish running work from idle
resources that can incur charges.

## Parts

- [x] Add a linked operations recipe covering account, regions, compute, jobs, schedules and retained resources; verified by documentation review (2026-11-27 20:28 ET).
- [x] Verify commands against live AWS inventory, including RDS clusters and event buses; Standards, Spec and GoF review found no issues (inherited Codex reviewers; Haiku unavailable in this runtime) (2026-11-27 20:28 ET).
- [x] Published draft PR #2225: https://github.com/paulananth/edgartools-platform/pull/2225; current-head CI gates ready status and merge (2026-11-27 20:28 ET).
- [x] Learning → skill: aws-snowflake-operations/RUNNING.md records the running-resource procedure and its reporting limits; verified by review (2026-11-27 20:28 ET).
