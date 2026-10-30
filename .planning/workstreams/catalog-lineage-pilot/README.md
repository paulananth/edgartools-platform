# Review one pipeline before extending catalog lineage

This is a bounded prototype, not a new runtime publisher. All names and field
definitions in example.json are invented. The configuration drives both native
API metadata and the review page; the code has no entity/provider rename list.
It does not execute the example operations, load source records or call providers.

Use these plain descriptions in the overview:

- Bookkeeping records successful artifact processing so work can resume from
  the last successful point.
- Change Journal decides whether an artifact needs processing, avoiding
  unnecessary repeat work. This removes the waste of overprocessing.

From the repository root:

```bash
uv run --no-project .planning/workstreams/catalog-lineage-pilot/pilot.py \
  --config .planning/workstreams/catalog-lineage-pilot/example.json --publish
uv run --no-project .planning/workstreams/catalog-lineage-pilot/render.py
lavish-axi .lavish/lineage-pilot.html
```

The explicit publish option writes metadata only to an isolated review namespace
and refuses existing objects without its ownership marker. It uses the existing
private catalog worker file outside Git. It has no reset or deletion operation.
The example remains available for operator review; cleanup follows that review.

## Evidence

Actual native API test: 3 datasets, 2 stages, 2 field lineage links and 1 pipeline.
Every edge references the native pipeline. Exact field mappings, transformations,
stage dependencies and the descriptive control interactions were read back.
A deliberately incorrect expected transformation failed verification. Repeating
publication retained the pipeline ID/version. See receipt.json for counts only.
Three invalid configurations (unknown input field, invalid dependency and unknown
control stage) were rejected in an additional local check. The page's initial
collapsed state, detail panels and unique diagram identifiers were checked by an
HTML parser. No browser or computer-use tool was used to inspect the page.

## Deliberate limits

- Native field lineage and associated pipeline are verified; separate native UI
  control lanes are not implemented. Control interactions are stored in the
  pipeline description and drawn separately in the review preview.
- Platform-wide navigation and cross-pipeline shared-node reuse are not qualified
  by a single example. The review page explicitly identifies that limit.
- The invented operations are labels, not runnable workers. Their flow does not
  assert that any production pipeline executes those operations.
- No operational records, failure/retry diagnostics, quality execution results or
  publication enforcement were added. Those belong to data-operations.
- Operator review is pending. No production rollout follows automatically.

## Standards

Own fresh branch/worktree; API-only; no source values or credentials in artifacts.
Production catalog code and other runtimes' files remain untouched. The scope
guard protects the example services, while unexpected identities fail closed.

## Spec

The overview starts collapsed. Expanding the pipeline shows data movement and
separate control interactions; expanding a stage shows field mappings and
quality rules. One invented example is held for review before further rollout.

## GoF

The existing projection/API boundary is adequate. A configuration-driven
prototype needs plain functions, not a new object hierarchy. No refactor of the
production publisher is justified by this pilot alone.
