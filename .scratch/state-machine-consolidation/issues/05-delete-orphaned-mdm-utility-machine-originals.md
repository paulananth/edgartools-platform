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

**Status:** resolved (2026-08-20)

- [x] Confirm zero running executions across all 7 orphaned machines
      (`mdm-run`, `mdm-backfill-relationships`, `mdm-sync-graph`,
      `mdm-verify-graph`, `mdm-counts`, `mdm-migrate`,
      `mdm-check-connectivity`) before touching anything
- [x] Capture a fresh rollback snapshot of each (mirroring tickets 03/04's
      pattern — `.scratch/state-machine-consolidation/rollback-snapshots/`),
      even though 2026-08-10 snapshots already exist, since these machines'
      *frozen* definitions haven't changed since then (the risk is
      invocation, not drift-since-snapshot) — a fresh snapshot with today's
      date documents the exact state at deletion time
- [x] Confirm nothing in the live repo (scripts, docs, runbooks, this
      CLAUDE.md file) still references any of the 7 by name as if they were
      current/authoritative — grep and fix any found, separately from the
      AWS-side deletion
- [x] Explicit `delete-state-machine` for all 7, live in prod
- [x] Update state-machine-consolidation's map.md: close the "orphaned but
      harmless" characterization in ticket 02's own entry (it's now proven
      wrong) and add this ticket's resolution to Decisions-so-far
- [x] Cross-reference from CLAUDE.md's "MDM Postgres migration-011 schema
      drift" section (the incident this gap caused) so a future reader
      following that section's own citations lands on the corrected
      understanding

## Answer

**Pre-deletion checks:** `list-executions --status-filter RUNNING` returned
`[]` for all 7 machines. Fresh rollback snapshots captured via
`describe-state-machine` for each, dated `20260820`, alongside the existing
`pre-ticket02-deploy-*-20260810.json` snapshots (not overwritten — both
generations kept, since the 2026-08-10 ones capture the state right after
consolidation and the 2026-08-20 ones capture the state right before
deletion; identical content expected between them since nothing updated
these machines in between, which is exactly the bug this ticket exists to
close).

**Repo reference check:** grepped the full repo (`.py`/`.sh`/`.md`) for all
7 names. Every hit was in `CLAUDE.md`, wayfinder maps/tickets, or
`docs/release-readiness/`'s historical write-ups — narrative documentation
of past events, not executable code or anything treating the names as
still-current. One item examined closely:
`.scratch/release-readiness/issues/94-sync-graph-silent-default-limit.md`
(status: open) describes a real, still-unfixed bug in `mdm sync-graph`'s
`limit_per_type` wiring, discovered via the orphaned standalone
`edgartools-prod-mdm-sync-graph` machine. The bug lives in shared
command-expression generation code (`write_mdm_utility_definition`'s
`mdm_sync_graph` branching explicitly "copied verbatim from
`write_mdm_workflow_definition`'s own branching" per that function's own
comment) — so it's very likely also present in `mdm-utility`'s consolidated
`mdm_sync_graph` mode, not eliminated by deleting the orphaned original.
Ticket 94 remains open and unaffected by this deletion; not investigated
further here (out of this ticket's scope), but flagged so whoever picks up
94 next knows the orphaned machine referenced in its discovery notes no
longer exists — reproduce against `mdm-utility`'s `{"mode": "mdm_sync_graph",
...}` instead.

**Deletion:** `aws stepfunctions delete-state-machine` issued for all 7
(`edgartools-prod-mdm-run`, `-backfill-relationships`, `-sync-graph`,
`-verify-graph`, `-counts`, `-migrate`, `-check-connectivity`). Step
Functions deletion is async (`DELETING` → gone); confirmed all 7 fully
removed from `list-state-machines` shortly after. Confirmed live and
untouched: `edgartools-prod-mdm-utility` (the consolidated replacement),
`edgartools-prod-mdm-gold`, `edgartools-prod-mdm-seed-universe` (deliberately
kept per ticket 04), `edgartools-prod-ownership-mdm-gold`,
`edgartools-prod-silver-mdm-gold`, and the unrelated
`canary-mdm-sync-graph-large-t25`.

**Documentation:** `map.md`'s ticket 02 entry and CLAUDE.md's migration-011
section were already corrected in the prior commit (`25ddd5a2`) that opened
this ticket, retracting "orphaned but harmless" and cross-referencing this
ticket. This resolution closes the loop those corrections pointed at.
