# Reading the catalog and each load

Start with the question you need answered. Keep technical detail behind the
relevant asset or run reference.

| Question | Read |
|---|---|
| What is this data about? | Domain and glossary definition. |
| Where is it and what does a row mean? | Table description, columns and processing layer. A catalog entry can describe a logical asset; verify the physical store separately. |
| Where did it come from? | Asset lineage and the pipeline's ordered tasks. |
| Can I use this package? | Product purpose, assets, input ports and actual quality results. |
| Did this load finish? | Its Bookkeeping run, verified receipts and destination checks. |

A layer, certification, approved term or green catalog publish does not prove
a load completed. Publication confirms metadata only within the reported
readback scope. A quality definition explains a check; a quality result records
an actual execution. Read the publisher's declared scope before treating the
whole catalog as confirmed.

## One summary for each load

Show one summary per Bookkeeping run. Keep repeated attempts under that run;
keep a distinct rerun separate. Link it to the source, target and catalog
pipeline through their configured identities.

| Show | Evidence |
|---|---|
| Source, target and run reference | Frozen Bookkeeping run and configuration. |
| State and last observed time | Run state plus the time the observer read it; display times in ET. A stale observation stays visibly stale. |
| Current steps and progress | Work-item counts by step and state. Label these as work units, not rows or bytes. Parallel steps may be active together. |
| Inputs and outputs | Frozen inputs, worker receipts and destination verification. Show expected and verified counts with their units. |
| Quality outcome | Executed checks and their results. Missing results mean unknown. |
| Retry or failure | Attempt counts, concise error, affected step and a private diagnostic reference. |
| Completion and next action | Final run checks, destination evidence and pending Journal deliveries; name the remaining action when incomplete. |

Use the runner's state without inventing a percent complete or ETA. Zero units,
an expired lease, an old heartbeat or a missing result each needs its own cause;
none alone proves success or failure. A worker finishing is insufficient when
verification or delivery remains pending. Counts and sanitized causes belong in
the summary; records, credentials and raw logs stay private.

If Bookkeeping cannot be reached, show “observation unavailable” and the last
observation time. Preserve the last known run state and mark it stale. An
observer connection failure does not establish that the load itself failed.

## What is available today

Bookkeeping provides the authoritative run view:

```bash
edgar-warehouse bookkeeping runs --limit 20
edgar-warehouse bookkeeping status <run-id> --limit 100
edgar-warehouse bookkeeping checks <run-id>
edgar-warehouse bookkeeping leases <run-id> --limit 100
```

Use its private runtime environment. A status response's `items` list is bounded;
its aggregate `counts` describe all selected units. Use `--step <step>` to inspect
one step. Receipts and destination checks establish output counts; work-item
counts alone do not.

OpenMetadata currently holds configured pipeline/task metadata and lineage.
Its pipeline status API can accept externally reported execution status, but
the platform has no installed Bookkeeping-to-OpenMetadata reporter. Therefore
per-load progress in OpenMetadata is **not connected**. A catalog pipeline's
presence or status badge cannot establish coverage of every load.

Before claiming that connection works, verify one real run end to end: its run
identity, steps, retry/failure, final output checks and observation time must
match Bookkeeping. Then account for every load in the reviewed source/time
window, including failed and unfinished loads. Missing, duplicate or stale run
reports must remain visible. Do not synthesize status records to demonstrate
observability. Implementation needs a separately scoped integration; changing
catalog descriptions cannot supply live run evidence.

For worker execution and recovery, follow the [Bookkeeping skill](../../bookkeeping/SKILL.md).
For source load operation, follow [data operations](../../data-operations/SKILL.md).
