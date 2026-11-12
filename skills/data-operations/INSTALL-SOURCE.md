# Install and enable one source

Part of the `data-operations` skill: [SKILL.md](SKILL.md) says when to read this.

## Install and enable one source

Use this when the task is to load and master one Rules source before the next.
The order and the run target come from `rules/source-sequence.yaml`. `after`
is preferred order only. `requires` is a real input dependency. One invocation
submits one source.

1. **Check the wiring.** Select that source alone:
   ```bash
   edgar-warehouse rules sequence check --source <name>
   ```
   Exit 0 and status `configured` means its `target` is a declared Bookkeeping
   target whose steps have workers. Exit 3 with `source_target_not_configured`
   means stop only when that source's `source.yaml` declares no Bookkeeping
   target. The inventory holds one `target`. A source that declares several,
   and whose sequence comment names them in order, is wired: run those
   targets in that order; `rules/source-sequence.yaml` gives the order of
   sources, and a domain skill gives a domain's. Do not add a second inventory
   field, and do not submit another source in its place. A successful check does
   not start a run. Detail is in
   `docs/specs/source-sequencing.md` in the repository.
2. **Check it.** `edgar-warehouse rules check --source <name>`. The files under `rules/` are the rules: nothing
   is saved, approved or activated first.
3. **Register it** (the load does this itself; run it alone only to see the result):
   ```bash
   edgar-warehouse rules register --source <name>
   ```
   It registers the merge rules and the source's Dataset Contracts in MDM with the store owner's connection
   (`MDM_REGISTRATION_DATABASE_URL`, [Connection URLs and environment](../data-platform/SKILL.md#connection-urls-and-environment)).
   A source that lands silver needs its silver tables registered first (`infra/scripts/deploy-silver-local.sh
   <name>`), and a load stops before it starts if an env file has no silver login.
4. **Load it.** One command, for any source and target, over files already
   captured. See **Load a capture** below.

A test of this path, and how to clear that test, is
[Test and clear a source run](RUNBOOK.md#test-and-clear-a-source-run).
