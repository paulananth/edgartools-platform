# Readback and reconciliation traps

Part of the `openmetadata` skill: [SKILL.md](SKILL.md) says when to read this.

## Readback and reconciliation traps

- Read column annotations with **both `fields=columns,tags`**. In 2.0.2, asking
  only for tags can return columns with empty tags despite stored annotations.
  Check domain/product fields separately in the same request when needed.
- Request `fields=tasks` when checking pipeline tasks and downstream dependencies.
- Native lineage edge `lineageDetails.pipeline` references the pipeline;
  `columnsLineage` names fully qualified upstream/downstream columns and the
  transformation. A registered pipeline with tasks alone does not supply that
  edge association. No transformation SQL is invented for a non-SQL process.
- **Checking lineage is a read.** Verify an edge with
  `GET /api/v1/lineage/...`, never with the `PUT` that writes it.
  `PUT /api/v1/lineage/domain/name/{domain}/table/name/{table}` replaces the
  edge's description with whatever body it carries, so a probe that PUTs `{}`
  blanks the description of every edge it touches. A later
  `rules catalog publish` restores those descriptions from the plan; verify
  each affected edge's `lineageDetails.description` matches the plan
  afterwards.
- Descriptions may have one transport layer of HTML entity escaping. Normalize
  Markdown fields once for comparison; keep identity, rule parameters and hashes
  exact. A genuine semantic difference must still fail.
- Bot PUT may retain curated descriptions. Compare the result, and patch only
  explicitly configuration-owned fields using JSON Patch when authorized.
  Check identity before and after; preserve other owners' labels and wording.
- List all pages and constrain ownership by exact service membership or an
  explicit ownership receipt. Domains, glossaries, terms and quality resources
  are global and are not assumed removed when a service is reset.
- **A list endpoint omits the relationships it does not name.** A table in the
  `/tables` list carries no `domains`, no `tags` and no `certification`; a
  glossary term in the `/glossaryTerms` list carries no relations; a data
  product in the `/dataProducts` list carries no `assets` and no `inputPorts`.
  An absent field in a list response is not proof the link is absent. Read each
  relation from its own endpoint or with its own `fields=` parameter, and read
  a data product's assets from `GET /api/v1/dataProducts/{id}/assets` and its
  input ports from `GET /api/v1/dataProducts/{id}/inputPorts` (the
  `/name/{fqn}/inputPorts` form answers the same rows).
- **A glossary term's relations live in `relatedTerms`.** Read them with
  `GET /api/v1/glossaryTerms/{id}?fields=relatedTerms`, by the term's id. The
  name form does not resolve for a term whose name contains a space. The
  server materializes each planned relation in both directions, so a planned
  set of N edges reads back as 2N; compare against the planned set plus its
  reverse.
- **A lineage edge's description lives in `lineageDetails.description`.** The
  edge's top-level `description` is empty on 2.0.7, so a readback that reads
  the top level reports every edge as undescribed. Compare
  `lineageDetails.description`.
- **A lineage graph's `nodes` may omit the entity you queried.** Reading one
  table's lineage returns the other endpoints of its edges; the subject table
  is often absent from `nodes`. Resolve both ends of an edge through a global
  id-to-FQN map built from the `/tables` and `/pipelines` lists rather than
  from that response's `nodes` alone.
- **The server quotes a FQN whose name contains a dot.** `silver."iapd.adv"`
  and `silver.iapd.adv` are the same schema under two spellings. Compare on
  the unquoted dotted path, or quote the way the publisher's `fqn` helper does,
  or a set comparison reports every such object as both missing and extra.
- **A data product's assets can exceed the plan.** The server rolls a
  planned asset's child tables into the product's asset list, so the live count
  is larger than the planned count. Require every planned asset to be present
  and account for each extra as a child of a planned asset; the product is
  correct when nothing is unexplained.

- A renamed source leaves its old tables behind. Such a table still holds its
  test cases, so `DELETE /tables/{id}?hardDelete=true` answers 400 "table is not
  empty"; the publisher deletes with `recursive=true` (a
  source ID rename). A publish that names a
  renamed source creates its new pipelines, schema, tables and test cases and
  removes the old ones in the same run; do not delete them by hand.
- A glossary term has no status in its create body (`CreateGlossaryTerm`, 2.0.2).
  A put, a relation write and a tag on an asset all leave it `Approved`, and a
  patch of one term resets its related terms. With `--draft-terms` the publisher
  patches `/entityStatus` to `Draft` as its last write, reads each status back and
  patches again until none is left. Without it, a publish leaves the server's status.
- The server's `GlossaryTermApprovalWorkflow` approves any created or updated
  term that has no reviewer, a few seconds after the write. It keeps terms
  `Approved` whatever `--draft-terms` does. To see Draft on a server, suspend it:
  `PUT /api/v1/governance/workflowDefinitions/name/GlossaryTermApprovalWorkflow/suspend`
  (undo with `/resume`). Check `suspended` is true before a publish.
- What the catalog holds for quality and mapping: a quality case sits on the table
  it checks (source datasets and silver tables from their quality rules; a master
  kind table from its identifier limits: one case per `claim.forward` and
  `claim.reverse` of each identifier in `merge/kinds/<kind>.yaml`, none where the
  limit is null). The complete per-source `MAPPING.xlsx` remains the
  integration specification in the rules repository. The operator deferred
  publishing the document itself as a Pipeline custom property ("defer document but publish lineage"). OpenMetadata 2.0.7 stores
  `entity_extension.extension` in `VARCHAR(512)`, below the raw text length
  of every source workbook. Do not embed or truncate the workbook, alter the
  schema, or create a link property without a new operator request.
  Publish native lineage only. Each source target keeps one Pipeline for its
  tasks and run status; it carries no lineage edge. Each step a steward can see
  fail (capture, combine, prepare, merge, land, derive, and the step that reads
  a pinned run file) is its own Pipeline named `<target>:<step>` in the same
  PipelineService, and carries the lineage. A step has inbound edges from the
  feeds, reference files and run file it reads, edges to the next step, and
  outbound edges to what it writes: the prepared dataset, mastered tables,
  Silver tables, and the Change Journal after the last step when the target
  records processed files. A run file's own edges come from the feeds its
  contract requires. A feed no step reads, a plumbing step, and a Bookkeeping
  task are not on the graph. The service layer shows pipeline services beside
  the database service and is not the picture; the Domain and Data Product
  layers are separate views. Rule-derived table and column edges describe
  supported transformations. `rules catalog publish` reconciles these edges in
  both directions; `rules catalog check` reads them through
  `GET /api/v1/lineage/pipeline/name/<URL-encoded-FQN>?upstreamDepth=1&downstreamDepth=1`
  and checks table edges separately. New source pipelines are discovered from
  YAML; no source-specific code is needed.
  Silver-only `MAPPING.xlsx` files have empty `Fields` sheets. Their Silver
  specs have descriptive `source` text, not complete field-path maps; do not
  invent column lineage from it. A code list edge maps its `code` to each
  column that holds those codes. A captured file feed's edge to its dataset
  stays table-to-table: a file has no columns.
  Standalone `pipeline.yaml` files create Pipeline entities but no service
  lineage edges in the current model.
  A page with an empty Quality tab is a table with no configured check.

- A profile has one native place, the table profile. `PUT /api/v1/tables/{id}/tableProfile`
  takes `{"tableProfile": {"timestamp": <ms>, "rowCount": n, "columnCount": n}}`; read it with
  `GET /api/v1/tables/{fqn}/tableProfile/latest` (the `profile` field); remove one with
  `DELETE /api/v1/tables/{fqn}/table/{timestamp}/profile`. The publisher writes it for every
  silver table of a source that has a `profile.yaml`: the profile date is the timestamp, and
  the counts are the part's rows and the silver table's columns, counts only. The source
  schema and each kind table say which profile feeds them, or "Not profiled yet". `catalog check`
  reads the latest profile back and reports "profile changed, publish again" for a table whose
  profile differs. Try the API on a throwaway table, never on a catalog table: a test value
  written to a real table must then be deleted by its timestamp.
