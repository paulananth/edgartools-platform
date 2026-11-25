# 01: A load is named after what it loads, never after a file; the load board has three colours

Status: resolved
Type: task
Blocked by: none

Operator, 2026-11-25 (recorded 2026-11-25 07:27 ET): "1) we cannot have date in the load name -03, -06, 2025q4 ... decouple filename from load 2) on grafana when not running color is gray, running and completed green, failed red ask question if needed". Asked what colour a stalled or locked step takes: "Both red".

## Checklist

- [x] GoF consult (agent `reviewer`, Haiku): no pattern; one function giving one view a delivery. It named four readers a step of several deliveries would break; each is changed: readiness, the step listing, the bundle progress, the minutes bound (2026-11-25 07:27 ET)
- [x] A step loads every delivery of its source's `inputs.yaml`, in that file's order, or the one kind it names with `input:`; 47 steps become 30, none named after a date (`test_no_step_or_input_of_the_load_jobs_names_a_date`) (2026-11-25 07:27 ET)
- [x] Nothing loads again because of it: the 47 capture runs are the same before and after (compared; `capture_name` in the inputs file holds what a delivery is called in its run; `test_the_capture_runs_stay_as_the_store_was_loaded`). Adding a file renames no earlier run (2026-11-25 07:27 ET)
- [x] A step's deliveries run in one log and stop at the first that does not finish; an attempt after it finds the loaded ones done; a forced load gives each its own revision; a step with one `revision` and several deliveries is refused (2026-11-25 07:27 ET)
- [x] The load board: grey not running, green running or done, red failed, stalled or locked; codes unchanged, so history keeps its meaning (2026-11-25 07:27 ET)
- [x] Tests: 285 passed in load jobs, monitoring, pipeline, readiness and the skill checks (2026-11-25 07:27 ET)
- [x] Learning → skill: data-operations SKILL.md, "Where retained files are"; load-monitoring SKILL.md, "The design" (2026-11-25 07:27 ET)

Form ADV's custodians now load March before June (they ran June first); the links are built once after the load, so the order decides no link. The catalog's status of a step stays its last run's.
