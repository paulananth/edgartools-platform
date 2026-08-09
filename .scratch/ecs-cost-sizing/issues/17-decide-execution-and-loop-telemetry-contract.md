# Decide the Execution and Loop Telemetry Contract

Type: grilling
Status: open
Blocked by: 10, 12, 13

## Question

What durable metrics and identifiers must every workflow, stage, and loop emit
so value, throughput, cost, and regressions can be compared without manual log
reconstruction?

Decide a minimal contract covering execution and release identity, workflow
and stage name, task definition and image digest, loop item type and count,
selected/attempted/committed/exported/skipped/rejected/retried/deduplicated
records, duration, peak CPU/memory, outcome, output manifest, and cost
attribution keys. Choose the durable source for each field and define how a
missing counter fails the optimization gate rather than being interpreted as
zero.
