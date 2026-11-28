# The mirror is refreshed when a load ends

Status: resolved
Type: task
Owner: claude (operator, 2026-11-27: "make the mirror run now is it possible if so add it to skill to trigger it once the load complete")

`aws-20261127` ended at 18:57:35 ET, and Gold's link tests could not read it: the finish wrote `master_binding` (4,460,191 rows
in PostgreSQL) and `relationship` (416,877) between 18:52 and 18:57 ET, five minutes after the mirror's last apply
(`LIST_MIRRORS`: `LAST_APPLY_TIME` 15:47:04, Snowflake's session time), and its refresh interval is 60 minutes. At 19:29 ET the
mirror held 0 rows of either.

## 5 whys

1. Gold's 25 link tests failed after a load that succeeded.
2. The mirror held none of the finish's rows.
3. The mirror applies changes only at its 60-minute refresh interval, and the finish ended just after an apply.
4. Nothing asked the mirror to apply once the load ended: both launchers stopped at the execution's result.
5. `REFRESH_MIRROR` ("apply pending changes to a mirror immediately and clear `last_apply_time`", Snowflake's mirror procedures
   reference) was not among the mirror commands, so no step could call it.

## Checklist

- [x] Live: `REFRESH_MIRROR('edgartools_mirror')` as the mirror operator at 19:32:37 ET returned "Refresh dispatched via EXECUTE TASK"; `LAST_APPLY_TIME` moved from 15:47:04 to 16:32:43 (Snowflake's session time, six seconds later), and the mirror's `master_binding` held 4,460,191 rows at 19:33 ET, equal to PostgreSQL (2026-11-27 19:42 ET)
- [x] Live, with nothing pending (19:35 ET): the refresh clears `LAST_APPLY_TIME` and no apply sets it, so `mirror_refresh.py --minutes 5` ended with exit 1 and says so; the load is done either way (2026-11-27 19:42 ET)
- [x] `mirror_refresh.py`: REFRESH_MIRROR on the recorded mirror, then waits until its last apply time is set again and moved (`test_the_refresh_returns_the_new_apply_time_once_the_recorded_mirror_has_applied`, `test_a_refresh_not_applied_within_its_minutes_returns_nothing_and_stops_listing`, `test_a_refused_statement_ends_the_refresh_with_its_error_number_and_no_login`; each fails today with `FileNotFoundError`, the module absent); `mirror_sql.py refresh` writes the call (`test_refresh_applies_the_recorded_mirrors_pending_changes_now` failed today with `SystemExit: 2`, argparse's "invalid choice: 'refresh'"); mirror tests 26 passed (2026-11-27 19:42 ET)
- [x] Both launchers, `aws-load.sh` and `load.sh`, run it after a load that succeeds, never after `--plan`; a refresh that fails leaves the load done. The two-line tail run under `set -euo pipefail` with a stand-in `uv` exiting 0 and 1, `plan` false and true: exit 0 every time, the refresh called only when `plan` is false (2026-11-27 19:42 ET)
- [x] Skills: HOSTED-MIRRORING (after a load the mirror is refreshed, never waited for; the `mirror: applied at` line is when Gold reads the load), HOSTED-LOADS (both launchers refresh; a fresh worktree syncs `--extra mirror`), initialize runbook step 8c (`dbt test` after that line) (read in the diff) (2026-11-27 19:42 ET)
- [x] `/code-review` (risky-reviewer: Standards, Spec, GoF). Fixed: `load.sh` did not refresh (one shared `mirror_refresh.py` for both launchers); the skill left a manual row-count check (the script waits for the apply); the launcher's claim had only `bash -n` (the stand-in run above); the quoted failure was the wrong exception; GoF: the lifecycle actions were listed twice and an unhandled action fell through to `create` (one `LIFECYCLE` tuple, `create` refused unless named). Noted: a fresh worktree without the `mirror` extra makes the refresh fail softly (HOSTED-LOADS' sync line now names it) (2026-11-27 19:42 ET)
- [x] Learning → skill: data-platform HOSTED-MIRRORING, "After a load the mirror is refreshed, never waited for" (2026-11-27 19:42 ET)
