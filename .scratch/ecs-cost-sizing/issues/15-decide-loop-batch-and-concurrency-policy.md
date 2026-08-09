# Decide the Loop, Batch, and Concurrency Policy

Type: grilling
Status: open
Blocked by: 07, 12, 13

## Question

For each loop class, what batch or window size, records-per-item range,
`MaxConcurrency`, retry budget, timeout, failure tolerance, and backpressure
rule best balances throughput, correctness, quotas, memory pressure, and cost?

Decide explicit policies for CIK batches/windows, filing/accession work,
relationship types, generation partitions, graph sync, and verification. Use
observed records per item and per execution rather than a universal batch size.
Preserve sequential execution where canonical publication, DuckDB writers,
Snowflake Postgres contention, SEC rate limits, or graph consistency require
it; otherwise prioritize reducing the end-to-end critical path through measured
parallelism, batching, and quota headroom. Prefer the fastest correct complete
configuration on the accepted cost frontier, not the lowest-cost configuration
in isolation.
