# Lineage

The service canvas is not a target's lineage. A target's graph is the
governance picture below. Publish native edges for that picture. Keep the
mapping document in the rules repository.


## Three layers

The shipped lineage page has three layers. A target's picture is not one of
them, and none of them replaces the others. Read the layer you were asked
about. Do not answer a service question with a table edge, or a product
question with a pipeline task.

1. Service. One pipeline service per source or standalone pipeline, plus the
   database service. Steps are not services. Bookkeeping is not a service.
   A blank service canvas does not mean the other layers are empty.
2. Domain. The subject of a trusted output. A processing store, a pipeline,
   a feed, and a control are not domains. An output with no declared subject
   is absent from this layer.
3. Data product. Only a package the configuration names, with its purpose and
   its assets. A feed, a pipeline, a journal, a document table, and a subject
   with no package are not products. A prepared dataset that fills a package
   is an input of that product, not a lineage node and not a new product.

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
- Name Matching is the only material derived control. It is built from SEC filer
  names and the verified GLEIF Golden Copy, digest-checked against the capture
  receipts, and it feeds mastering. Show both sources into that control.
- The eight Bookkeeping steps stay one node: main, keys, catalog, name matching,
  combine, records, merge, processed. They are tasks, not graph nodes.
- Company master and the Change Journal are the trusted outputs.
- The capture target and the merge-batch target stay off this graph.
- On the three layers: the service layer is that source's pipeline service
  and the database service; the domain layer is the subject of the master;
  the data product layer is the legal-entity package. Name Matching, the ticker
  reference, and the journal are not that product.
- No live catalog objects were changed by the prototype. Publication follows
  this picture; do not invent a pipeline to draw the steps.
