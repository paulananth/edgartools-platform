Type: grilling
Status: open
Blocked by: 01
Labels: `wayfinder:grilling`

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
