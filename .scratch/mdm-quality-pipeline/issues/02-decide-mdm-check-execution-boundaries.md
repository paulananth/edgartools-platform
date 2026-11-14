Type: grilling
Status: resolved
Blocked by: 01
Labels: `wayfinder:grilling`

## Checklist

- [x] Trace the current record-check path and available bounded/resumable execution scopes. 2026-11-13 20:42 ET
- [x] Record the approved execution boundary for current and any future check grains. 2026-11-13 20:42 ET
- [x] Add the linked decision summary to the map. 2026-11-13 20:42 ET
- [x] Validate the ticket and map update with `git diff --check` and the overlap guard. 2026-11-13 20:42 ET
- [x] Learning → skill: none; no reusable skill gap was identified. 2026-11-13 20:42 ET

# Decide MDM Check Execution Boundaries

## Question

Where should each approved MDM check execute so its result covers the intended
records without changing merge behavior or missing duplicates across batches?

Use the inventory from [Decide the MDM Quality Inventory and Scope](01-decide-mdm-quality-inventory-and-scope.md).
Keep current per-record evaluation in `mastering.merge` explicit. Decide the
generic boundary for any delivery-wide, publication-wide, or master-state
check, including how checks see all rows in their declared scope while the
pipeline remains bounded and resumable. The design must not add
Company-, Person-, or Security-specific branches to the shared evaluator.

## Answer

Approved by the operator on 2026-11-13:

- Keep the current source-record checks in `mastering.merge` normalization,
  before each eligible record is merged.
- Run any approved delivery-wide or publication-wide check in one generic
  pre-merge evaluation over the complete prepared publication manifest, not
  independently per merge batch. The prepared publication identity and its
  pinned input define the default scope. Cross-source or cross-publication
  scopes must be named explicitly by the check contract.
- Include every mapped record in that declared publication population,
  including records set aside by per-record checks. A check may exclude a
  subset only when its own contract explicitly limits applicability.
- Keep the evaluation bounded and resumable: stream the scope, persist
  deterministic intermediate results with per-unit checkpoints, and do not
  begin merge writes until the full-scope evaluation completes.
- Run any approved persisted-master-state check after all relevant merge
  batches commit. Read the full population declared by the check, read-only,
  on a consistent snapshot. Use changed-master-only scope only when the check
  contract explicitly defines that narrower population.
- Keep scope evaluation generic across entity kinds. MDM executes checks;
  Bookkeeping retains their evidence; OpenMetadata is the sole user-facing
  place to discover and view every check and result.

No delivery-wide, publication-wide, or persisted-master-state check is in the
approved inventory today. These boundaries specify how a future evidence-backed
check would execute; they do not activate or create checks. Failure behavior
without an explicit contract action stays unresolved per the inventory
decision.
