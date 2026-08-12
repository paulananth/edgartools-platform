# Measure Every Loop and Record Funnel

Type: research
Status: claimed
Blocked by: 01

## Question

For every Step Functions Map/Distributed Map and every material internal CLI
loop, what is the loop item, item source, batch or window size, item count per
execution, records selected and attempted per item, records committed and
exported, idempotent skips, rejects, retries, duplicates, duration, peak
CPU/memory, and effective concurrency?

Cover at least CIK batches, CIK windows, filing/accession loops, relationship
types, generation partitions, graph-sync batches, and MDM limits. Reconcile
Step Functions history, Map Run metrics, ECS task metrics, logs, S3 manifests,
run summaries, and durable outcome ledgers. Explicitly distinguish a loop item
from the number of records produced by that item so `records per loop` cannot
be mistaken for `Map item count`.
