# Qualify Snowflake Postgres and rehearse cutover

Type: task
Status: open
Owner: Codex
Blocked by: 06

## Work

Use same migrations on an isolated target after local acceptance. Pin approved inputs; rehearse catch-up, consumer reconciliation and rollback. Set live target and retention details before activation; retain legacy MDM.

## Evidence

On 2026-09-19 the user selected local PostgreSQL for continued qualification
and 30 days of legacy retention after cutover. Snowflake qualification is
deferred. The user asked for an explanation of pinned inputs; the inherited
three-company local landing bundle is being inspected as a candidate.
Source/consumer integration gates must finish before any consumer cutover.
