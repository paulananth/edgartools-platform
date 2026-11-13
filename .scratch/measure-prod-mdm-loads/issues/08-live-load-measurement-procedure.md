# What exactly is the measured-load procedure, run by run?

Type: task
Status: resolved
Blocked by: 01, 07

## Question

The plan's measurement procedure is specified only in outline. This ticket settles the mechanics
that a runner must follow, so two runs of it produce comparable numbers.

Decide and record, for one approved target:

1. The exact command, with every flag spelled out: source, target, capture folder, capture run ID,
   stores folder, `--workers 1 --bundles 1 --minutes 120`, the declared `--fact name=value` and
   `--file name=path` inputs, `--plan` first and the same command without `--plan` after approval.
2. Where the per-target private log is written, its mode, and the rule that it is never printed to
   the chat.
3. How the invocation is bracketed: ET timestamps before and after, `time -p`, and the two derived
   figures — `active_command_seconds` as the sum of `time`'s `real` across invocations, and
   `target_wall_seconds` as final verified completion minus the first invocation start, including
   pauses and resumes.
4. The exact `profile_load.py steps` invocation per bundle run ID, and how its event intervals map
   onto the report's step-interval fields, including the `mdm.prepare` + `mastering.merge` sum that
   becomes `mdm_write_step_seconds`.
5. What to do when `load` reports `selected = 0`: no run, no timing, and the historical evidence
   carried forward instead.
6. The order of targets, and how the three declared link targets (`gleif/subfund-pairs`,
   `iapd.adv/custodians`, `sec.ownership/security_symbols`) are sequenced against their consumers.

This ticket may be AFK where the mechanics follow from the repository's existing commands and
skills, and HITL only where a choice remains. Record the resolved procedure in the ticket, and
append a one-line gist to the map's Decisions so far.

## Answer

Decided 2026-11-13. Because the live-load path is closed
([07](07-live-load-authorization-path.md)), this procedure is **specified but not executed**, and
the retrospective report uses the retained-evidence branch below instead.

### A. The command, when the gates clear

```
edgar-warehouse load \
  --source <source> --target <target> \
  --capture <capture-folder> \
  --capture-run <id> \
  --stores "$HOME/.local/share/edgartools/hosted-prod" \
  --workers 1 --bundles 1 --minutes 120 \
  --fact name=value --file name=path ...
```

- `--fact` and `--file` values come from the active target's Rules and the retained manifest, via
  `scripts/run_inputs.py <source>`. **Never invented.**
- The same command runs twice: once with `--plan` (which must list the documents and bundles it
  would process, the open runs it would finish or leave, and any blocker), then without `--plan`
  after the approval. The plan is not readiness evidence.
- Never `--force`, `--all`, or `mdm clear-source`. No provider request.

### B. The private log

- Path: `~/.local/share/edgartools/load-logs/measure-prod-<source>-<target>/<run-label>.log`, the
  report directory mode `0700`, each file mode `0600`.
- The log holds the command line, stdout and stderr. **It is never printed to the chat.** Only
  counts, run ids, statuses and durations are reported.

### C. Bracketing and the two durations

Each invocation is bracketed:

```
start_et=$(TZ=America/New_York date -Iseconds)
{ time -p edgar-warehouse load ... ; } 2> >(tee -a "$log" >&2)
end_et=$(TZ=America/New_York date -Iseconds)
```

- **`active_command_seconds`** — the sum of `time`'s `real` across every invocation of the target.
- **`target_wall_seconds`** — final verified completion time minus the **first** invocation start,
  including pauses and resumes between invocations.
- The target wall time includes all of the target's declared steps and is **never** the sum of step
  intervals.

### D. Step intervals

Per bundle run id, with an explicit `--run`:

```
uv run --no-sync --extra mdm python skills/data-operations/scripts/profile_load.py steps --run <run-id>
```

- One interval per exact Bookkeeping step name and run id. These are **event intervals**, not SQL
  CPU time.
- `mdm_write_step_seconds` = the `mdm.prepare` intervals + the `mastering.merge` intervals.
- Every other step interval is kept under its own operation name.
- A step name in the report carries the rules version that produced it. The retained runs were
  frozen under `rules-2026-11-11.go-live-hosted-2` and `rules-2026-11-10.go-live-8`, and the current
  Rules reshaped the extract passes on 2026-11-12 — so a step the current Rules declare but the
  retained runs did not run is reported as **not evidenced**, never as completed.

### E. `selected = 0`

No run is submitted, no timing is invented. The row records `selected: 0` and the already-processed
count, and the historical evidence carries forward.

### F. Order

One target at a time, in `rules/source-sequence.yaml` order, then the three link targets ahead of
their consumers:

1. `gleif/subfund-pairs` → before `sec.nport.security`
2. `iapd.adv/custodians` → before `iapd.adv/mastering`
3. `sec.ownership/security_symbols` → after OpenFIGI security data is present

Before any dispatch expected to exceed ten minutes, the estimate is reported. While a run is
active, `profile_load.py progress` is used and checked every 30 minutes.

### G. The branch this measurement actually takes

With the gates closed, the report is built from retained evidence:

| Field | Source |
|---|---|
| run state, units, verified, pending, created, completed | `measure-prod-runs-verified.json` |
| considered / selected / already / bundles / run ids / log name | `measure-prod-load-summaries.json` (32 invocations) |
| step intervals | `measure-prod-step-intervals.json` (1,442 intervals) |
| per-contract outcomes | `measure-prod-source-outcomes.json` (11 contracts) |
| initialization | the retained Snowflake query-history export |
| target wall time, active command time | **unavailable** — no invocation boundary and no `time -p` output survives |
