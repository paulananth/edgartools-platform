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

**Status:** ready-for-agent

## Question

Is the standalone `seed_universe` workflow (`workflow_profile()`'s
`seed_universe → medium`) genuinely safe on medium (4096MB), or does it
carry the same OOM risk `load_history`'s `SeedUniverse` state was bumped to
large to fix on 2026-08-09 — and should `command_task_profile()`'s
`seed-universe` entry be `large` instead of `medium`?

- [ ] Determine whether the standalone workflow's typical/max universe size
      at seed time differs meaningfully from load_history's (if the
      standalone workflow only ever runs against a much smaller universe,
      medium may genuinely be safe there even though load_history needed
      large)
- [ ] Either bump `command_task_profile()`'s `seed-universe` entry to
      `large` (if the risk is real and the two call sites should converge),
      or record why medium is safe for the standalone workflow specifically
      (if it's a genuine, deliberate, tested difference, not unverified
      luck)
- [ ] Once decided, `command_task_profile()`'s single entry is updated to
      match — this ticket exists specifically because a command can't have
      two different "true" profiles once ticket 04 retires the redundant
      mechanisms

## Answer

<!-- filled in on resolution -->
