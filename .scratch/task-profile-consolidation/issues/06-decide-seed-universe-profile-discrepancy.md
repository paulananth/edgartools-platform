# 06 — Decide whether the standalone `seed-universe` workflow needs the same large-profile fix load_history's own SeedUniverse got

Type: grilling

**What to build:** Not a build — a decision. The `seed-universe` CLI
command currently runs on two different task profiles depending on which
state machine invokes it, and nobody has decided whether that's safe:

- The standalone `seed_universe` Step Function resolves it via
  `workflow_profile()` → **medium** (4096MB) — this is what
  `command_task_profile()`'s `seed-universe` entry also encodes (ticket 01).
- `load_history`'s own `SeedUniverse` state (inside
  `write_load_history_definition`) was bumped to **large** (8192MB) on
  2026-08-09, after a live exit-137 OOM: `seed-universe`'s `run_command()`
  dispatch unconditionally hydrates the full canonical silver.duckdb
  (1.5GB+ and growing) before its own `db.get_active_ciks()`/tracking-status
  logic runs — see the comment above `write_load_history_definition`'s
  `seed = ecs_state(wh_large_arn, ...)` call.

Both invocations run the identical `edgar-warehouse seed-universe` command
with the identical dispatch code path. The OOM's root cause (unconditional
full silver.duckdb hydration before any filtering) has no obvious reason to
differ between the two call sites — the standalone workflow may simply not
have been exercised at large enough universe size yet to have hit it, not
because it's structurally safe on medium.

**Discovered while:** implementing task-profile-consolidation ticket 03
(2026-08-19), correcting a separate, unrelated stale-value bug in
`command_task_profile()`'s `bootstrap-next` entry. Re-deriving
`write_load_history_definition`'s real wiring surfaced this second,
genuine (not stale-comment) discrepancy as a side effect — not
independently investigated further, since neither ticket 02 nor 03 touches
`SeedUniverse` or the standalone `seed_universe` workflow.

**Blocked by:** None — can start immediately

**Status:** resolved (2026-08-20)

## Question

Is the standalone `seed_universe` workflow (`workflow_profile()`'s
`seed_universe → medium`) genuinely safe on medium (4096MB), or does it
carry the same OOM risk `load_history`'s `SeedUniverse` state was bumped to
large to fix on 2026-08-09 — and should `command_task_profile()`'s
`seed-universe` entry be `large` instead of `medium`?

- [x] Determine whether the standalone workflow's typical/max universe size
      at seed time differs meaningfully from load_history's (if the
      standalone workflow only ever runs against a much smaller universe,
      medium may genuinely be safe there even though load_history needed
      large)
- [x] Either bump `command_task_profile()`'s `seed-universe` entry to
      `large` (if the risk is real and the two call sites should converge),
      or record why medium is safe for the standalone workflow specifically
      (if it's a genuine, deliberate, tested difference, not unverified
      luck)
- [x] Once decided, `command_task_profile()`'s single entry is updated to
      match — this ticket exists specifically because a command can't have
      two different "true" profiles once ticket 04 retires the redundant
      mechanisms

## Answer

**This ticket's own premise had gone stale by the time it was worked.** It
was written 2026-08-19 assuming `seed-universe`'s OOM risk was still live
and unaddressed. Investigating for this resolution surfaced that a separate
wayfinder effort, `seed-universe-narrow-hydrate`
(`.scratch/seed-universe-narrow-hydrate/map.md`), had already shipped the
actual root-cause fix in the interim — not found or cross-referenced when
ticket 06 was originally opened, since neither effort links to the other.

**Root cause fixed and confirmed live:** the 2026-08-09 OOM's actual
mechanism — `seed-universe`'s dispatch unconditionally buffering the entire
canonical `silver.duckdb` into memory during hydration, before any
per-command filtering logic runs — is fixed by two changes, both verified
(via `git merge-base --is-ancestor`) to be ancestors of the currently
deployed prod image (`85ab9e65a599`):

- **Streaming hydrate** (PR #392, commit `d95e2bbc`) — replaced
  `_hydrate_silver_database_from_storage`'s non-streaming full-buffer
  `read_bytes()`/`write_bytes()` download with a chunked stream
  (`StorageLocation.download_file()`), so hydrate's peak memory is O(chunk
  size), not O(canonical file size). This is the exact mechanism the
  original 2026-08-09 OOM hit.
- **MDM as novelty-detection source of record** (PR #394, commit
  `7868ee77`) — `seed-universe`'s "is this CIK already tracked" filter moved
  from a silver read (`db.get_active_ciks()`) to
  `_get_mdm_tracked_ciks("active")`, an indexed Postgres query against MDM
  that touches silver/duckdb not at all.

Both fixes apply to the `seed-universe` command's dispatch code uniformly —
there is no code path by which the standalone workflow and load_history's
`SeedUniverse` state could still differ in hydrate-time memory behavior.
The asymmetry that originally motivated bumping load_history's copy to
`large` (an unpatched, real OOM mechanism only observed at load_history's
scale) is gone at its root, not because the standalone workflow happens to
run smaller universes.

**A separate, unpatched risk was found and weighed, not the one this ticket
was originally about:** the merge/publish step
(`_publish_silver_database_if_remote`) still buffers canonical in full,
twice, in an unpatched, non-streaming way — explicitly deferred in the
narrow-hydrate map's own ticket 04 as "real but unobserved as a live
problem," not proven safe. Checked live (2026-08-20): canonical
`silver.duckdb` is currently **1.5 GiB**
(`s3://edgartools-prod-warehouse-690839588395/warehouse/silver/sec/silver.duckdb`),
so this step's peak is roughly ~3GB — comfortably inside medium's 4096MB
envelope today, with real but shrinking headroom as canonical grows
(documented elsewhere as actively growing). This risk is identical for
*both* call sites (same shared merge/publish code path), so it doesn't
create or resolve the asymmetry this ticket was scoped to decide — it's
orthogonal.

**Decision (user, presented with the above via /grilling):** keep
`command_task_profile()`'s `seed-universe` entry at `medium`. Root-cause fix
is live and verified; today's canonical size clears the one remaining
unpatched risk with real headroom; converging the two call sites *downward*
(cheaper) is preferred over converging upward, with the explicit
understanding this should be revisited if canonical growth erodes that
headroom.

**Built:** updated `command_task_profile()`'s inline comment
(`infra/scripts/deploy-aws-application.sh`) to record this decision and its
evidence in place of the old "KNOWN, DELIBERATELY UNRESOLVED DISCREPANCY"
language. No functional/value change — the entry was already `medium`,
matching the standalone workflow's pre-existing live behavior; this ticket
converts an unverified assumption into a verified, evidence-backed decision.

**Follow-on, out of this ticket's scope, opened separately per user
direction:** ticket 07 (`.scratch/task-profile-consolidation/issues/
07-decide-whether-to-revert-load-historys-seeduniverse-off-large.md`) — the
`seed-universe-narrow-hydrate` map's own stated destination included
"deciding whether `seed-universe` can move back to a smaller profile once
both fixes are in place" for load_history's own `SeedUniverse` state
specifically, but that map closed its frontier without ever making that
call. Not decided here — ticket 06's own acceptance criteria scope only
`command_task_profile()`'s single entry, which already matched the
standalone workflow and needed no code change to converge; load_history's
own hardcoded `wh_large_arn` reference is untouched.
