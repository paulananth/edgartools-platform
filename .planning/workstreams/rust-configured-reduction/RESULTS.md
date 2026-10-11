# Configured Rust reduction: local implementation evidence

Baseline: `45525cd8bc1df550bfba10022bd5eead1f41359d`; dedicated branch
`codex/rust-configured-reduction`. Scope is the `reduce` branch of the existing
`source.combine` worker. Materialized combination/joins and MDM merge remain
unchanged. Claude's live Company/control and profiling paths were inspected
and the overlap guard passed before edits and before commit.

## Behavior and verification

- Rust owns generic group accumulation, exact-text keys, distinct membership,
  last occurrence, full-set exclusions, lexical samples and final ordering.
- Python validates the existing outer contract, authenticates and exhausts every
  input (including unselected rows/readings), enforces aggregate input/output
  budgets, encodes/writes results and independently verifies them.
- Native state budgets preserve compact UTF-8 canonical payload accounting.
  Conversion batches contain at most 1,024 selected rows; the GIL is released
  for native accumulation. Failed state cannot finalize or accept more rows.
- Native binary and facade now participate in the worker execution digest.
  Existing frozen runs must resume with their pinned runtime; this change
  does not replace those run identities or activate a rules version.
- `uv run --no-sync pytest tests/engine/test_native_reduction.py
  tests/engine/test_source_reduction.py tests/engine/test_source_combine.py
  tests/engine/test_source_nested_combine.py tests/engine/test_source_engine.py
  tests/engine/test_source_input_pins.py -q`: **120 passed**.
- Full `cargo test --locked --manifest-path crates/source-contract/Cargo.toml`
  suite passed. After adding native unit coverage, `cargo test --locked
  --manifest-path crates/source-contract/Cargo.toml --lib reduction::tests`
  passed all **3 reduction unit tests**.
- Existing worker tests prove repeat execution/verification, receipt identity,
  bounds, last/null semantics and refusal to publish after late corruption.
  New seeded tests compare exact native output with an independent expected
  table calculation, including Unicode/control text and cross-source exclusion.
- Platform skill command/link checks and `git diff --check` pass.

## Offline worker benchmark

Five equivalent trials per implementation/workload/concurrency. Each timed run
performs worker execute **and** independent verify: authenticated local reads,
native conversion, encoding, writes and read-back. Baseline Python is loaded
from the pinned original worker using git only in the experiment; production
code has no Python fallback. Every output receipt hash matches exactly.

The initial smaller trials overlapped test/build activity. They were repeated
with those tasks stopped; the table uses the repeat for 20,000 rows and the
initial run for 100,000 rows. Raw trials and RSS are in
[benchmark.json](benchmark.json) and [benchmark-repeat-small.json](benchmark-repeat-small.json).
The deterministic generator and comparison are in [benchmark.py](benchmark.py).
Each worker reads two tables of the listed size and computes three groups.
Concurrent worker counts mean independent invocations in Python threads.

| Rows per table | Workers | Python median (s) | Rust median (s) | Speedup | Peak RSS change |
|---|---|---|---|---|---|
| 20,000 | 1 | 1.116 | 0.352 | 3.17x | +25.0% |
| 20,000 | 2 | 2.441 | 0.697 | 3.50x | +24.7% |
| 20,000 | 4 | 5.883 | 1.517 | 3.88x | +33.4% |
| 100,000 | 1 | 6.739 | 1.738 | 3.88x | +22.5% |
| 100,000 | 2 | 13.040 | 3.012 | 4.33x | +10.3% |
| 100,000 | 4 | 28.791 | 6.080 | 4.74x | +21.1% |

RSS is fresh-process high-water memory; it includes imports and decoding.
Native copying/container allocations increase measured RSS on these fixtures.
The canonical state/key/member bounds remain enforced but are not an RSS cap.
The adoption tradeoff is explicit: faster generic execution with higher memory
on these bounded synthetic workloads. No production workload or whole-pipeline
performance qualification is claimed.

Native binary SHA256: `3be1d73984d9504a3014935e8191e415e5844c9f5f613e29cdace47612990770`.
Current source.combine execution digest: `3b76e542598f31a051e566ade1c056a121e44bc7fa0c2ef344cfe5b4015f8496`.

## Scope limits and next work

No AWS operations, deployment, operator activation or database migrations were
performed. No claim of new PostgreSQL concurrency qualification is made; the
transaction/lease paths are unchanged. Source-specific corpus and installed
end-to-end pipeline qualification remain necessary before operational rollout.
Configured merge kernels and materialized combination/joins are later slices
with their own ownership checks and semantic/recovery gates.
