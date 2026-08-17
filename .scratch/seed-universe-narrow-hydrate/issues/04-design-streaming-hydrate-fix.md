# 04 — Design the streaming download fix for _hydrate_silver_database_from_storage

Type: grilling
Status: resolved
Blocked by: 02, 03 (both resolved)
Blocks: none

## Question

Design the streaming download fix for `_hydrate_silver_database_from_storage`'s
non-streaming `read_bytes()`/`write_bytes()` buffering (ticket 02's finding).
Decide scope (which of the three full-buffer points found in the
read/merge/publish cycle get fixed now vs. deferred) and mechanism.

## Answer

Investigation found `StorageLocation.upload_file()`
(`edgar_warehouse/infrastructure/object_storage.py:151-167`) already
implements the exact streaming pattern needed, just in the opposite
direction: "Stream a local file to storage without loading it fully into
memory," via `shutil.copyfileobj(src, dst, length=chunk_size)` through an
`fs.open(destination, "wb")` handle. There is no symmetric `download_file()`
for S3-to-local.

Tracing the full read/merge/publish cycle surfaced three distinct full-buffer
points, not one:

1. `_hydrate_silver_database_from_storage` (`warehouse_orchestrator.py:948`)
   -- the one every observed OOM (Stage0CompanyIdentity, ComputeWindows,
   gold-refresh, seed-universe) actually failed in.
2. `_publish_silver_database_if_remote`'s merge step
   (`warehouse_orchestrator.py:1042`) -- re-downloads canonical a second time
   via `read_bytes()` to build the merge baseline.
3. Same function, `merged_local.read_bytes()`
   (`warehouse_orchestrator.py:1046`) -- buffers the merged output for its
   MD5 checksum and staged upload.

`_hydrate_shard_for_window` (`warehouse_orchestrator.py:1142-1184`, the
`bootstrap-batch` shard path) has the identical bug pattern at smaller
scale.

User decisions (all three recommended answers accepted):

- **Scope**: fix only point #1 (the proven failure point) and
  `_hydrate_shard_for_window`'s identical pattern, in this pass. Points #2
  and #3 are real but unobserved as a live problem -- filed as a follow-up
  rather than bundled in, to keep this fix scoped and low-risk.
- **Mechanism**: add `StorageLocation.download_file(relative_path,
  local_path, chunk_size=8*1024*1024)`, mirroring `upload_file`'s existing
  signature and streaming implementation exactly (reversed direction).
  `_hydrate_silver_database_from_storage` and `_hydrate_shard_for_window`
  both switch from `read_bytes()` + `Path.write_bytes()` to this method;
  `size_bytes` for their pipeline events comes from `local_path.stat().st_size`
  instead of `len(payload)`.
- **Fingerprinting**: `compute_silver_fingerprint(local_path)` needs no
  change -- it already operates on the on-disk file after hydration
  completes, not on the in-memory payload.

Implemented directly following this ticket's resolution:

- `StorageLocation.download_file()` added (`object_storage.py:170-190`),
  mirroring `upload_file`'s exact streaming pattern in reverse
  (`fs.open(source, "rb")` -> local file handle via
  `shutil.copyfileobj(..., length=chunk_size)`).
- `_hydrate_silver_database_from_storage` and `_hydrate_shard_for_window`
  (`warehouse_orchestrator.py`) both switched from `read_bytes()` +
  `Path.write_bytes()` to `context.storage_root.download_file(...)`;
  `size_bytes` for their pipeline events now comes from
  `local_path.stat().st_size`.
- New test file `tests/unit/test_object_storage_download_file.py` (4 tests)
  locks in the streaming behavior directly -- a recording fake read handle
  asserts every `read()` call during a remote download is bounded by
  `chunk_size`, never an unbounded whole-object read (the exact bug this
  fix removes).
- Updated 3 existing tests that mocked the module-level `read_bytes()`
  function to instead mock the new `download_file()` method:
  `test_sharding.py::test_hydrate_downloads_only_overlapping_shard`,
  `test_sharding.py::test_bootstrap_chunk_uses_shard_aware_hydrate`,
  `test_skip_noop_silver_publish.py`'s `_hydrate()` helper (used by all 4
  tests in that file). Verified these were genuinely testing the changed
  code path (not testing `_publish_silver_database_if_remote`'s separate,
  deliberately-unchanged `read_bytes()` calls at
  `warehouse_orchestrator.py:1042/1046` -- those two tests'
  `read_bytes` mocks in `test_skip_noop_silver_publish.py` lines 121/219
  are correctly left untouched).
- Full suite green: 1138 passed, 4 skipped, 35 subtests passed, 0 failures
  (`tests/unit` + `tests/architecture`).

Not yet done: commit, PR, deploy to prod -- pending explicit authorization.
