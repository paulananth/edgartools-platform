# 02 — Non-streaming read_bytes/write_bytes buffering as the shared root cause

Type: research
Status: resolved
Blocked by: none
Blocks: none directly, but reframes the destination (see map's widened scope
and ticket 04/05)

## Question

`seed-universe`'s OOM was fixed same-day via a `wh_large_arn` memory bump
(PR #391), matching the same fix already applied to `Stage0CompanyIdentity`,
`ComputeWindows`, and `gold-refresh` earlier in this go-live. Is there a
single mechanism shared across all four commands that explains why they all
hit the same failure class, independent of what each command does with the
canonical database once opened?

## Answer

Yes. `_hydrate_silver_database_from_storage`
(`edgar_warehouse/application/warehouse_orchestrator.py:938-969`) is called
unconditionally by every command that isn't lease-only (PR #390) or
shard-aware (`bootstrap-batch` only). Its download step is fully
non-streaming:

```python
payload = read_bytes(remote_path)   # object_storage.py:449-458 --
                                     # fs.open(remote_path, "rb").read() reads
                                     # the ENTIRE S3 object into one Python
                                     # bytes value before returning
local_path.write_bytes(payload)     # then writes that whole in-memory buffer
                                     # to local disk
```

`read_bytes()` (`edgar_warehouse/infrastructure/object_storage.py:449-458`)
has no chunking, no `fs.get()`-style streaming copy, no bounded read loop --
`handle.read()` with no size argument returns the whole object as one
Python `bytes`. For a 1,517MB+ canonical `silver.duckdb` (2026-08-08 size,
still growing), this means every hydrate-consuming command pays a peak
Python-process memory cost of roughly the full object size for this step
alone, **before** DuckDB opens anything or any command-specific logic runs.
This is independent of whether the command is read-only (`seed-universe`'s
`get_active_ciks`-shaped reads), write-heavy (13F holdings ingestion), or
does almost nothing with the data (`Stage0CompanyIdentity`'s identity
checks) -- the hydrate step's cost is the same for all of them because it
happens before any of that.

**Asymmetry with the write/publish side:** `_publish_silver_database_if_remote`
(`warehouse_orchestrator.py:972-1048`) already has a "skip-if-unchanged"
optimization (release-readiness ticket 79) -- a local-only fingerprint
comparison that skips the entire download/merge/upload/promote cycle when
nothing changed. No equivalent exists on the **read/hydrate** side: the
full-object buffer-then-write always happens, even for a command that turns
out to make zero writes.

**Conclusion:** the `wh_large_arn` bumps applied to all four commands so far
(Stage0CompanyIdentity, ComputeWindows, gold-refresh, seed-universe) have
been raising the memory ceiling to tolerate this O(2x file size) buffering
pattern, not fixing it. As canonical `silver.duckdb` keeps growing past
1,517MB, the same class of failure will recur at the new ceiling too, for
any command that still goes through this path -- including commands not yet
hit (nothing about the pattern is `seed-universe`-specific). A streaming
download (chunked read + write, or `fsspec`'s `fs.get(remote, local)`,
neither of which requires ever holding the full object in one Python value)
would cut this step's peak memory to a small constant, independent of
canonical's size, for every affected command -- not just `seed-universe`.

This does not eliminate the need for a full local copy on disk (DuckDB
still opens the whole local file for any command that isn't shard-aware or
lease-only), and it does not by itself address the write/publish side's
symmetric full-object buffering in `write_bytes`'s remote branch
(`object_storage.py:430-441`, `fs.open(destination, "wb").write(payload)`,
and the earlier checksum-then-atomic-put path at `object_storage.py:284-296`
which computes `hashlib.sha256(payload)` over the whole in-memory payload).
Those are real, related, but distinct design surfaces -- see ticket 04.
