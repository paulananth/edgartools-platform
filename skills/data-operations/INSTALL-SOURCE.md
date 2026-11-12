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
   not install, approve or start a run. Detail is in
   `docs/specs/source-sequencing.md` in the repository.
2. **Install that source only.** Save its document into the Rules database.
   `rules load` saves every file under a root; do not use it for one source. A new store taking every
   source (a go-live) needs nothing but git: `rules load --root rules --version <name>` saves each document
   and approves it from `rules/approvals.yaml` with no test run, then `rules activate` each one (merge
   policy first, then the pipeline, then the sources).
   ```bash
   edgar-warehouse rules save --source <name> --version <v> rules/sources/<name>/source.yaml
   ```
   Check it offline first with `edgar-warehouse rules check --source <name>`.
   Then record that version's proof before any approval: carry the last
   proof forward when [mdm-engineering](../mdm-engineering/SKILL.md#choose-the-cheapest-proof)'s
   "Choose the cheapest proof" allows it, and run no new test. Otherwise data-onboarding's **test** step runs and records one (`rules
   test --version`). A test that stops is not a proof and is not recorded.
3. **Enable it.** Follow [APPROVE](../data-onboarding/APPROVE.md). Source `governance.env` beside
   `worker.env`: activation registers the version in MDM and stops with "MDM activation requires an
   explicit destination connection" without it. Activate
   the merge policy this source depends on first, then this source:
   ```bash
   edgar-warehouse rules activate --source <name> --version <v>
   edgar-warehouse rules status --source <name>
   ```
   Enabled means `rules status` shows that version `active`. There is no
   separate enable command.
   **A source that masters nothing needs no proof and no approval** (operator: "There is nothing to prove in silver it is just one to one no
   mastering"): one with no Dataset Contract, no `mdm` target and no acquisition
   maps its files one to one into silver. Check it (`rules check`), save it, and
   `rules activate` it from draft; `rules test` refuses such a source anyway.
   Its silver tables must be registered first (`infra/scripts/deploy-silver-local.sh
   <name>`), and a load stops before it starts if an env file has no silver login.
4. **Load it.** One command, for any source and target, over files already
   captured. See **Load a capture** below.

A test of this path, and how to clear that test, is
[Test and clear a source run](RUNBOOK.md#test-and-clear-a-source-run).
