# Define the BatchSilver Contention-Safe Publication Boundary

Type: grilling
Status: open
Blocked by: 03

## Question

Which publication architecture must ensure that MaxConcurrency=4 BatchSilver tasks never perform an unguarded last-writer-wins upload to the same monolith or shard object—distinct immutable batch outputs with deterministic consolidation, shard-level serialization, or conditional versioned rehydrate-and-merge—and what compatibility and recovery contract must downstream full-dataset readers observe?
