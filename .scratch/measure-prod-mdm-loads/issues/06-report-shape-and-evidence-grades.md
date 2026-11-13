# What is the report's shape and how does it grade evidence?

Type: grilling
Status: open
Blocked by: 02, 04

## Question

Resolved so far on this map: the entity-kind model
([05](05-entity-kind-contribution-model.md)), the retained run evidence and its join
([04](04-retained-run-evidence-join.md)), the inventory
([03](03-source-target-inventory-and-dependencies.md)), and the initialization timestamps
([02](02-retained-initialization-timestamps.md)). This ticket settles how those findings are written
down.


The plan fixes the report's sections but not the shape of a row when the evidence is partial. The
report must be readable, must never imply a measurement it cannot support, and must reconcile
`considered = selected + already_processed` while keeping every bundle run ID.

Decide, with the operator:

1. The exact row shape for `target_runs[]` — the full field list from the plan, with each field's
   type and its `unavailable` form. In particular: how `target_wall_seconds`,
   `active_command_seconds` and `mdm_write_step_seconds` each render when the underlying
   timestamps are missing.
2. The evidence grade vocabulary: the small set of labels a row may carry (for example
   `verified`, `historical-only`, `partial`, `blocked`) and precisely what each permits the report
   to assert.
3. How a target that was never loaded in production appears — absent from the timeline, or present
   as `blocked` with a reason. This also decides what an entity kind's status can be when a
   contributing source was never run.
4. How the per-source summary row aggregates a source with more than one target: one spanning
   interval, two intervals, or the earliest start and latest completion.
5. Whether the report should be a single Markdown file plus structured JSON, or JSON only, and
   whether the Markdown is the human artifact or a rendering of the JSON.

Answer with the resolved shape, written so a report writer can fill it mechanically. Record the
answer in this ticket and append a one-line gist to the map's Decisions so far.
