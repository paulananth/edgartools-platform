# 05 — Delete the 7 orphaned original MDM Utility Machine state machines

Type: task

**What to build:** Not a build — cleanup. Ticket 02 flagged, but never
ticketed, that collapsing 7 individual MDM CLI-wrapper state machines
(`mdm-run`, `mdm-backfill-relationships`, `mdm-sync-graph`,
`mdm-verify-graph`, `mdm-counts`, `mdm-migrate`, `mdm-check-connectivity`)
into one consolidated `edgartools-prod-mdm-utility` machine (`{"mode":
"..."}`) on 2026-08-10 left the 7 originals `ACTIVE` in AWS, calling them
"orphaned but harmless." **That call was wrong — proven live, 2026-08-20.**

**What actually happened:** a real prod incident (documented in CLAUDE.md's
"MDM Postgres migration-011 schema drift" section) was marked "resolved
2026-08-19" on the strength of two verification steps: running
`edgartools-prod-mdm-migrate` (reported SUCCEEDED) and re-verifying with
`edgartools-prod-mdm-run --limit 25` (reported no errors). **Both of those
were the orphaned originals, not `mdm-utility`** — both still reference a
task-def revision (`edgartools-prod-mdm-{small,medium}:149`) from an image
pushed 2026-08-09, over a week stale by the time they were invoked. That
stale image's code predates the `source_content_hash` migration entirely:

- `mdm-migrate`'s "SUCCEEDED" was a **false positive** — its stale image's
  migration set doesn't include migration 011 at all, so there was nothing
  to fail on; the real Postgres schema was never touched.
- `mdm-run`'s "no errors" was a **false negative** — its stale image's ORM
  model doesn't declare `source_content_hash` yet, so it never queried for
  the missing column in the first place. Not evidence the fix worked; only
  evidence the check never actually tested the fix.

Re-run against the real, current `edgartools-prod-mdm-utility` machine
(`{"mode": "mdm_migrate"}`, then a scoped verify via `{"mode": "mdm_run"}`-
equivalent on the current `edgartools-prod-mdm-medium:178` task def)
confirmed the migration genuinely had never been applied to the live
database until this second, correct attempt — the prior "resolved" claim
was itself never actually verified.

**This is a general hazard, not a one-off:** any of the 7 orphaned
originals can be invoked (by an operator, an agent, muscle memory, or a
stale runbook/doc referencing the old name) and will silently run whatever
code was live on 2026-08-10, giving misleadingly clean-looking
success/failure signals that say nothing about current prod behavior. The
longer they're left `ACTIVE`, the further their frozen task-def revisions
drift from reality, and the more convincing a false result becomes.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] Confirm zero running executions across all 7 orphaned machines
      (`mdm-run`, `mdm-backfill-relationships`, `mdm-sync-graph`,
      `mdm-verify-graph`, `mdm-counts`, `mdm-migrate`,
      `mdm-check-connectivity`) before touching anything
- [ ] Capture a fresh rollback snapshot of each (mirroring tickets 03/04's
      pattern — `.scratch/state-machine-consolidation/rollback-snapshots/`),
      even though 2026-08-10 snapshots already exist, since these machines'
      *frozen* definitions haven't changed since then (the risk is
      invocation, not drift-since-snapshot) — a fresh snapshot with today's
      date documents the exact state at deletion time
- [ ] Confirm nothing in the live repo (scripts, docs, runbooks, this
      CLAUDE.md file) still references any of the 7 by name as if they were
      current/authoritative — grep and fix any found, separately from the
      AWS-side deletion
- [ ] Explicit `delete-state-machine` for all 7, live in prod
- [ ] Update state-machine-consolidation's map.md: close the "orphaned but
      harmless" characterization in ticket 02's own entry (it's now proven
      wrong) and add this ticket's resolution to Decisions-so-far
- [ ] Cross-reference from CLAUDE.md's "MDM Postgres migration-011 schema
      drift" section (the incident this gap caused) so a future reader
      following that section's own citations lands on the corrected
      understanding

## Answer

<!-- filled in on resolution -->
