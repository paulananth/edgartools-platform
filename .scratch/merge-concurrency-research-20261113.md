# Parallel merging into golden records: what outside sources say (2026-11-13)

Question: how do match-and-merge systems run many writers at once without two golden records for one thing?
Searched the open web only; no provider access. Claims are as the sources state them.

## Findings

1. **Partition first; make the parts independent.** Parallel matching papers name the partitioning of the input as the
   prerequisite that keeps match tasks independent (Data Partitioning for Parallel Entity Matching, arXiv 1006.5309).
   Ataccama's matching architecture treats a partition as a hard boundary: no rule is evaluated across partitions.
   Oracle's bulk match tool groups records into blocks and gives each server one block at a time.
2. **Connected components are the blocks.** Scalable entity resolution clusters with connected-component labelling on
   the match graph (arXiv 1712.09691), and one ACM paper uses connected components as the blocks themselves
   (Connected Components for Scaling Partial-order Blocking to Billion Entities, 2024). Union-find prunes comparisons.
3. **Concurrent merges of one entity are serialized, not avoided.** Senzing states the rule plainly: many threads may
   run, but the same entity id must not be processed in parallel; completion order cannot be assumed, and each change
   returns the entity ids it affected so downstream work is eventually consistent. Oracle's batch deduplication notes a
   merge scans and updates many tables and advises capping concurrent merge jobs.
4. **Streaming and incremental ER.** New records join or merge existing blocks (Incremental Blocking over Web Streaming
   Data, ACM 2019), so a block's membership changes while workers run: a partition fixed up front can be invalidated.
5. **PostgreSQL advisory locks share the one lock table**, sized by `max_locks_per_transaction` x sessions, so a
   transaction that locks thousands of keys can fail with "out of shared memory". Bound the lock count (hashed slots).

## Not found

No source describes concurrency control for the golden-record write itself (locking, versioning, retry) beyond
"one writer per entity id". Splink and Zingg documentation on concurrent loading was not found.

## What this means for the design

- Blocks are keyed by what can match; here a record's identifier values and name keys are its blocking keys.
- Workers should be given whole connected components, so two concurrent batches share no key. A component grows when a
  later file joins it, and a golden record already stored can join two components: take a lock per golden record, in
  sorted order, for the merge itself (Senzing's "not the same entity id in parallel").
- Bound the lock count with hashed slots.

## Sources

- https://arxiv.org/pdf/1006.5309 (Data Partitioning for Parallel Entity Matching)
- https://arxiv.org/pdf/1712.09691 (Scalable Entity Resolution Using Probabilistic Signatures on Parallel Databases)
- https://dl.acm.org/doi/10.1145/3646553 (Connected Components for Scaling Partial-order Blocking to Billion Entities)
- https://dl.acm.org/doi/pdf/10.1145/3350546.3352542 (Incremental Blocking for Entity Resolution over Web Streaming Data)
- https://docs.ataccama.com/mdm/latest/matching/matching-architecture.html
- https://docs.oracle.com/en/cloud/saas/sales/oacdm/high-volume-batch-deduplication.html
- https://senzing.com/docs/tutorials/advanced_replication/
- https://www.postgresql.org/docs/16/runtime-config-locks.html
