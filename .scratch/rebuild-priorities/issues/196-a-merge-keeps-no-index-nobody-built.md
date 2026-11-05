# 196: A merge keeps no index that nobody built (and the merge is still slow)

Priority: 196. Map: [Rebuild priorities](../map.md). Opened 2026-11-05 07:19 ET (operator, 2026-11-05: "why the heck you need a
19000 key join this is freeking over engineered fix the dam root casue").

Type: task. Status: in progress (the search entries are removed; the merge is still slow). Blocked by: none. Follows ticket 194 (the merge is 58% of a bundle).

## Question

Why does a merge batch take 30 s or more, and what is the smallest change that removes the cause?

## Found

- The lookup table holds 6.2 million entries for 331,000 records. 17.8 of every 19 entries per record, and 1.2 of 1.55 GB of
  bodies, belong to two search indexes (name search and the detail lookup).
- Both indexes are derived from the masters and already have an owner rebuild. But an index counted as built at generation 0,
  so a store loaded from empty kept both inside every batch, and search refuses to answer unless they are current anyway.
- The batch probed about 19,000 entries in a table larger than the database's memory; the same join took 24.6 s cold and
  1.6 s warm. After removing the search entries and compacting the table to fit in memory, a batch was still about 60 s.

## Checklist

- [x] First theory measured: random probes of a table larger than memory (24.6 s cold, 1.6 s warm for 19,000 keys; 2026-11-05 06:58 ET). It did not hold: the compacted table gave no speed-up (below).
- [x] A merge writes no entries for an index with no coverage row, at any generation (`master_index.state`): the new batches wrote 11.6k lookup entries instead of 19k+ with no search entries (checked on the store, 2026-11-05 07:12 ET).
- [x] Test: a save on a store nobody built leaves search refusing, one rebuild makes it answer, and the next save keeps it; it failed before the change (`DID NOT RAISE`) and passes after (`test_normal_master_search[unbuilt-*]`, 2026-11-05 07:19 ET).
- [x] The existing search and detail scenarios build the index first (`rebuild(owner)`): 5 of 5 detail and 11 of 12 search cases pass locally; the twelfth lost its throwaway MySQL container (infrastructure, passes alone).
- [x] Time a batch on a lookup table without the search entries (table compacted to 1.6 GB, index 0.4 GB): **no faster**, 2 batches in 121 s (about 60 s each), 22,000 lookup entries written (2026-11-05 07:24 ET). So the search entries and the table size were not the main cost. Postgres runs the call on one CPU core; the statements `auto_explain` logged inside the function add up to about 15 s a call.
- [x] Where one batch's 60 s goes (the profile tool's `sample` view over 60 s, 2026-11-05 07:30 ET): `mdm_store_apply` 27 s (45%), preparation reads 9 s (15%), and the other 24 s the database is idle while Python prepares (40%).
- [x] The preparation, profiled with `cProfile` on a preview of one batch (nothing written): 18.6 s, of which 13.3 s is 61 database statements. 10.8 s is `related_decisions` / `retained_groups` in 3 calls and 9.9 s of it is `correction.quarantined`: for each of about 1,000 records it loads every related decision body (about 3 per record) only to find a quarantine decision, which is rare, and it does so 3 times a batch.
- [ ] Decide the preparation fix. (a) Read each record's related decisions once per batch, not three times (about 7 s of 60). (b) Keep a lookup of quarantine decisions per record, so the check reads nothing when there are none (about 10 s of 60; the engine that writes the lookups is Rust, and a store needs a rebuild of it). 
- [ ] The apply call (27 s, 45%): `auto_explain` shows no statement over 3 s; it is 14 statements that each decode and hash the batch's 11,000 entries. A temporary table of the decoded entries made once would make each statement an indexed read. Changes a frozen storage protocol; operator's decision.
- [ ] Rebuild both indexes once after a full load and time that pass.
- [x] Learning → skill: `mdm-engineering` "A merge keeps an index only after the owner has built it".
