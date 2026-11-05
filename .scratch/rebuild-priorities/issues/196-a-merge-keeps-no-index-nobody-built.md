# 196: A merge keeps no index that nobody built

Priority: 196. Map: [Rebuild priorities](../map.md). Opened 2026-11-05 07:19 ET (operator, 2026-11-05: "why the heck you need a
19000 key join this is freeking over engineered fix the dam root casue").

Type: task. Status: in progress. Blocked by: none. Follows ticket 194 (the merge is 58% of a bundle).

## Question

Why does a merge batch take 30 s, and what is the smallest change that removes the cause?

## Found

- The lookup table holds 6.2 million entries for 331,000 records. 17.8 of every 19 entries per record, and 1.2 of 1.55 GB of
  bodies, belong to two search indexes (name search and the detail lookup).
- Both indexes are derived from the masters and already have an owner rebuild. But an index counted as built at generation 0,
  so a store loaded from empty kept both inside every batch, and search refuses to answer unless they are current anyway.
- The batch probes about 19,000 entries in a table larger than the database's memory; the same join took 24.6 s cold and
  1.6 s warm.

## Checklist

- [x] Root cause named with a measurement (2026-11-05 06:58 ET; ticket 194).
- [x] A merge writes no entries for an index with no coverage row, at any generation (`master_index.state`): the new batches wrote 11.6k lookup entries instead of 19k+ with no search entries (checked on the store, 2026-11-05 07:12 ET).
- [x] Test: a save on a store nobody built leaves search refusing, one rebuild makes it answer, and the next save keeps it; it failed before the change (`DID NOT RAISE`) and passes after (`test_normal_master_search[unbuilt-*]`, 2026-11-05 07:19 ET).
- [x] The existing search and detail scenarios build the index first (`rebuild(owner)`): 5 of 5 detail and 11 of 12 search cases pass locally; the twelfth lost its throwaway MySQL container (infrastructure, passes alone).
- [ ] Time a batch on a lookup table without the search entries (table compacted): result in the next line.
- [ ] Rebuild both indexes once after a full load and time that pass.
- [x] Learning → skill: `mdm-engineering` "A merge keeps an index only after the owner has built it".
