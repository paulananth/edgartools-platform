# Lineage

The service canvas is not a target's lineage. A target's graph is the
governance picture below. Publish native edges for that picture. Keep the
mapping document in the rules repository.

## What the graph shows

Each inbound edge ties to an actual source the target reads:

- a captured feed, or
- a named reference file the target reads and that is not one of its feeds.

A dataset the same target prepares is an intermediate. Leave it off the graph
unless that dataset is itself a configured output.

A pinned run file that a step reads is a material control. Draw it once. Its
inbounds are the actual sources that build it, including another source when
the control's contract names that source. Do not add a node for each captured
step. Add a captured intermediate only when it is material: a steward needs it
to trust the output, and it is not already covered by the control or the source.

Bookkeeping steps stay tasks on the one pipeline. Do not add a pipeline, a
task node, or a captured-file node to force a step onto the canvas. Do not
add a Bookkeeping pipeline.

Trusted outputs are the configured mastered or prepared tables. Add the change
journal when the target records processed files. Sibling targets stay on their
own pipelines; do not draw them here.

## How to check

Read the target pipeline graph, not the service canvas alone. The connected
nodes are the sources, the material control, and the trusted outputs. The
pipeline's tasks are the Bookkeeping steps, and those names are not separate
nodes.

When the operator asks to see the shipped UI, open that target's lineage tab
with Playwright. Confirm the same nodes and the absence of immaterial captured
steps. A passing API write is not that confirmation.

## Examples

SEC Company mastering, approved 2026-11-08:

- SEC submissions and the ticker reference are direct inputs.
- Name Count is the only material derived control. It is built from SEC filer
  names and the verified GLEIF Golden Copy, digest-checked against the capture
  receipts, and it feeds mastering. Show both sources into that control.
- The eight Bookkeeping steps stay one node: main, keys, catalog, name count,
  combine, records, merge, processed. They are tasks, not graph nodes.
- Company master and the Change Journal are the trusted outputs.
- The capture target and the merge-batch target stay off this graph.
- No live catalog objects were changed by the prototype. Publication follows
  this picture; do not invent a pipeline to draw the steps.
