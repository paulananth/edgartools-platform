# Should parts of Clean MDM be rewritten in Rust?

2026-10-10, branch `claude/company-source-retirement`. Short answer: **no new Rust now.** The heaviest step already runs in Rust. Today's failure is a limit on how many bytes a proposal may hold, and the language it is written in does not affect that. The remaining costs come from doing the same work twice and re-reading shared inputs, and changing those does not need a new language.

## What was measured today

- **Synthetic GLEIF reading.** 20,000 records through the real worker path, both execute and verify, using `gleif_reading` from `tests/mdm/test_clean_company_source.py:170`.
  - Total: 18.8 s, or 0.94 ms per record. Production: 3,393 s for 3,428,477 records, or 0.99 ms per record (TICKET.md:66). The two rates are nearly the same, so the synthetic run is representative.
  - cProfile shows 14.6 s spent inside the native call `source_contract.Engine.scan_json_array`, which is 77% of the time. The Python callbacks (`source_stream.project` and `source_engine.receive`) take about 2.6 s (14%). Building the contract takes about 0.3 s.
- **Name Frequency tests** (`tests/mdm/test_clean_name_frequency.py`, 10 passed, 18.1 s under the profiler).
  - Loading the rules files took 10.95 s. Most of that is PyYAML's `compose` through `files._rules_node` (`edgar_warehouse/rules/files.py:102-108`). It runs 169 times.
  - Building the engine in Rust took 2.0 s over 58 builds.
  - The 548 KB contract `rules/sources/gleif/census-complete-stream.yaml` costs 162 ms to parse and 124 ms to build into an engine. `census-main.yaml` costs 19.5 ms and 4.6 ms.
- **Combine costs** (synthetic microbenchmark, run in this repo's environment):
  - A 2.5 MB, 10,500-row catalog reading takes 39 ms to parse and hash.
  - Each `canonical()` row check over all its rows takes 44 ms.
  - A 2 MB census takes 78 ms to parse and hash.
- **Two profiles left out.** I also profiled `tests/engine/test_company_preparation_cutover.py` (17 of 18 failed) and `test_prepared_bundle_is_bounded_pinned_and_idempotent` (failed). They fail on this branch, so their numbers measure error paths, and I do not use them.
- **The installed wheel.** It was built from the `edgartools-platform-claude-gleif` worktree (`source_contract-0.1.0.dist-info/direct_url.json`, 3.9 MB `.so`). That fits a release build, because maturin's PEP 517 backend builds in release mode by default (https://www.maturin.rs/distribution.html: "all builds are in release mode"). Production images run `maturin build --release` (`Dockerfile.mdm-deps:14`, `Dockerfile.warehouse-deps:14`).

## (a) Where the costs are

| Cost | Evidence | What kind of cost |
|---|---|---|
| GLEIF and other streamed reads | 77% of the time inside `scan_json_array` (above) | **Already Rust.** The time is spent inside the Rust engine itself. |
| Verifying a reading recomputes it | `source_read.verify` re-runs `_output`/`source_stream.output` (`edgar_warehouse/workers/source_read.py:287-299`). GLEIF: 3,393 s to execute, 4,706 s to verify (TICKET.md:66). | Deliberate double work |
| The same for prepare and combine | `mdm_prepare.verify` rebuilds `_documents` (`edgar_warehouse/workers/mdm_prepare.py:189-198`). Company preparation verifies every combine (`edgar_warehouse/mdm/clean/company_prepare.py:105-106, 153`). | Deliberate double work |
| Shared inputs re-read for every 1–2 Company unit | Each combine unit takes the whole catalog reading and the census reading (`company_prepare.py:140-150`). `source_combine._rows` recomputes `canonical(expected)` for every row (`edgar_warehouse/workers/source_combine.py:126-131`). Re-reading the census for every Company was 71% of the old 1.93 s per Company (TICKET.md:317). | Python CPU, but the root cause is reading the whole input each time |
| Loading rules and contracts | Pure-Python YAML validation of every node (`files.py:102-108`). Each `source.read` loads its contract again (`source_read.py:41`). | Python CPU, a fixed cost per unit |
| mdm.merge | The assessment runs the whole `write_batch` and rolls it back (`mdm.preview_batch`, `001_mdm.sql:870-883`, called at `merge.py:780`). `apply_assessment` then runs `_execute` again (`merge.py:344-349`). The 5.2 min for 6,726 records has not been split into its parts. | Postgres work and round trips to it; Postgres is Snowflake-hosted (CLAUDE.md) |

Hashing (sha256) is small in every profile, for example 0.04 s over 368 calls.

## (b) Candidates for Rust

- **source.read engine.** Already Rust (`crates/source-contract`, PyO3 0.25 abi3; `Cargo.toml`, `src/python.rs:139-216`).
  - The remaining lever is profiling the existing engine. About 0.36 ms per record of native time is slow for Rust, and the contract is interpreted for every record.
  - A second, smaller lever is the per-record Python callback. Each record makes a `Python::with_gil` call (`python.rs:165`), and `project` re-encodes every row only to measure its size (`source_stream.py:158`). Moving the `project` sizing into Rust could save about 14% of the read.
  - **Gain: up to about 15% from the callback work. A Rust profiling pass might find more, but that is unmeasured.**
- **source.combine (Python).** Rust would shave the constant factor, but each unit would still re-read the whole catalog. Narrowing the catalog to the chunk's CIKs and hoisting `canonical(expected)` out of the row loop fixes the root cause in Python.
  - **Gain from Rust: small once the inputs are narrowed.**
- **mdm.prepare.** Mostly JSON-lines encoding and file writes (`mdm_prepare.py:90-112`). **Gain: not material.**
- **mdm.merge matching, binding and proposal assembly.** These are bound by Postgres: snapshots, `preview_batch`, closure loads (`merge.py:504-530, 715-781`). A Rust client cannot speed up SQL that runs on the server or the network round trips to it.
  - **Gain: not material.**
- **Verification.** The doubling comes from a design choice (an independent recompute), not from the language. Rust would speed both halves equally, so verification would still cost as much as execution.

## (c) Does the language affect the proposal-size failure? No.

`mdm.record_match_proposal` refuses a body over 16,777,216 bytes or more than 1,000 decisions (`001_mdm.sql:893-899`). That limit is the project's own, not Postgres's. Here is what makes the body big:

1. **Assertions are stored twice.** The body holds `command`, which is the caller's whole command including its assertions (`merge.py:291-302`). It also holds `effects`, which is `request = {**command, ...}` (`merge.py:757-758`) copied in full (`merge.py:809-812`). Measured on SEC: 2.75 MB in each copy.
2. **`before` and `projections`.** The current entity bodies (`merge.py:806-808`) and every projection (`merge.py:766-768`) go into `effects`.
3. **Batches are cut by count, not by bytes.** `BATCH = 1000` (`mdm_prepare.py:45`) and `LIMIT = 1000` (`edgar_warehouse/workers/mdm_merge.py:32`). `RECORD_BYTES` bounds the records file but not the proposal, so a GLEIF batch only fails when it reaches merge.

**Why `effects` must be whole today.** `write_batch` compares the request with `b->'effects'` by jsonb equality (`001_mdm.sql:547`). `apply_assessment` re-runs from `body["command"]` (`merge.py:349`), so `command` must also stay whole.

**The real fixes:**

- **Byte-bounded batches in `mdm.prepare`.** Close a batch at a budget of about 6 MB of records, chosen because the records appear about 2.5 times in the body.
  - This alone fixes GLEIF, with no schema change.
- **Stop storing the assertions twice.** Store `effects` without `assertions`, and in `write_batch` compare `r->'assertions'` with `b->'command'->'assertions'`.
  - This needs a new migration and must be tested against a populated table (CLAUDE.md).
  - It also needs a check that the two lists are equal; `assess` sorts the command's assertions (`merge.py:293-300`).
  - Saves about 27%. On its own that brings GLEIF to about 14.3 MB, which is too thin a margin. This is extrapolated from SEC; I did not break down the GLEIF body.
- **Keep evidence by reference.** Keep `effects` as a sha256 digest only.
  - The digest must be computed in SQL from the jsonb value. jsonb does not keep key order or whitespace (https://www.postgresql.org/docs/16/datatype-json.html), so a Python `canonical()` hash would not match.
  - Provenance (about 1.4 MB per copy) could name the bronze receipt instead of repeating it in the body.
- **Raise 16 MB.** This is possible, but it goes against the bounded-assessment design, so it is the operator's choice and not recommended.

## (d) Recommendation, in order

1. Close `mdm.prepare` batches by bytes, at about 6 MB per batch. This unblocks the GLEIF proof without touching Postgres.
2. Add a migration so `effects` no longer stores the assertions a second time. Test it on a populated store.
3. Make Company preparation narrow: give each chunk the catalog rows it needs (as is already done for the census), and hoist `canonical(expected)`. Both are Python changes.
4. Cache the contracts that are loaded and built, per process and keyed by their sha256. That removes the fixed per-unit YAML and engine-build cost.
5. Only if GLEIF reading time still matters: profile `scan_json_array` natively and move the `project` sizing into Rust. Do this inside the existing crate. Do not rewrite MDM in Rust.
6. Leave the execute-then-verify recompute as it is. It is the integrity guarantee. To cut its cost, run verifiers in parallel, not in a different language.

Note: `.scratch/l4-batch-size/test_batch_size.py` was already modified before this research began, and it was not touched.
