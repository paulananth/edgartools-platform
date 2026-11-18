# Bound the memory of silver.land: its keys go to disk, not a set

Status: open
Type: task

Operator, 2026-11-18: "make this load memory efficient: the N-PORT silver worker holds 1.2 GB ... streaming it in bounded
pieces would be the real fix". Opened from `.scratch/worker-memory/issues/01-lower-worker-memory.md`.

## Finding

`silver_land.execute` and `check` kept `seen`, a set holding a tuple of key strings for every row of the whole input, to
build a receipt (rows, distinct keys, a digest of the sorted keys) and then to ask silver whether it holds each key; the
receipt sorted a second copy. It grows with the input and nothing bounded it. The rows themselves are already bounded: they
arrive in pieces and land in deliveries of up to 10,000.

## Parts

- [x] `KeySet` holds at most a limit of keys in memory, writes each full buffer as a sorted run in a temporary folder and
  reads them back merged in key order; the receipt's digest is byte for byte the one the sorted set gave, so stored
  receipts still verify (2026-11-18 09:06 ET; `tests/unit/test_silver_keyset.py`, 4 tests, each failing first: the module did not exist;
  digest equal to `sha256(json.dumps(sorted(keys)))`; spill files removed; memory never past the limit)
- [x] The missing-keys check reads the keys in order and asks silver for 500 first-key values at a time (`missing`), where it
  held every key (2026-11-18 09:06 ET; `test_missing_asks_silver_a_group_of_first_key_values_at_a_time_and_counts_what_it_lacks`)
- [x] Measured on 3 million invented keys of the shape of a holding's key (accession and holding id): the set peaked at 612 MB,
  the key set at 43 to 46 MB, with the same digest; the time was 17.5 s for the set and 17.7 to 26.9 s for the key set over
  three runs (2026-11-18 09:14 ET; `scripts/dev/bench_silver_keys.py set 3000000` and `... keyset 3000000`)
- [x] Spec review: a merge never opens more runs than its fan-in (64), merging down in passes (`test_a_merge_never_opens_more_runs_than_its_fan_in_however_many_were_spilled`: about 300 runs at a fan-in of 4 opened them all, so a unit near the 100 million row cap would have hit the open-file limit); a missing-keys question also ends at 50,000 keys, so a first column with few distinct values cannot bring every key back (`test_missing_also_bounds_a_group_by_its_keys_so_few_first_values_cannot_bring_every_key_back_into_memory`: `missing` had no key limit) (2026-11-18 09:14 ET)
- [ ] The real effect on the N-PORT silver worker, measured after the hosted load ends (`footprint -p` on the step against its
  1.2 GB): the checkout the load runs from cannot change under it
- [ ] The rest of that worker's memory, if any: the pieces of the reading and the quality reports are bounded by design
  (pieces of 8 MiB, deliveries of 10,000 rows); measure before claiming more
- [x] Learning → skill: mdm-engineering, "A worker's memory is its imports plus its data" names the rule: a worker holds a
  bounded piece, and what must span the whole input goes to disk in sorted runs (2026-11-18 09:06 ET)

## Processing identity

`silver_land.py` is a pinned runtime file of the silver.land worker, so a store that holds silver data read through it
reads its documents again at the next load after this merges. It merges after the hosted fresh load ends.
