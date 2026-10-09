# Offline whole-source Name Frequency qualification

These scripts qualify the configured projection against retained independent
functions. They are test tooling; they do not introduce a production loader,
activate a caller, install databases or make source-provider requests.

## Inputs and order

Run from the repository root with the project's Python 3.12 environment and
its freshly built `source-contract` extension (`uv sync --extra engine`).
The scripts use the existing local captures below and write evidence under
`/private/tmp/codex-census-eof-proof`; preserve that directory during a scan.

1. `build_frequency_rules.py --check` checks both generated Rules byte for
   byte without writing. Omit `--check` only when intentionally regenerating
   Rules for review, before starting qualification.
2. `publication_population.py` reads the pinned publisher metadata and the
   separate publication authority binding already recorded in this repository.
3. `sec_source_population.py` exhausts the 69 landed SEC captures in the
   existing `~/.local/share/edgartools/clean-mdm/proving/cm27` fixture. It executes
   and verifies Source Extracts before deriving wanted keys. Company and former
   name bytes must match historical Name Frequency pins; address and manifest
   bytes receive authenticated immutable receipts for this qualification.
   **Historical address pins are not claimed:** the older Name Frequency
   document did not contain them.
4. `whole_source_frequency.py` uses the exact pinned GLEIF JSON archive named
   by `.planning/workstreams/company-census-evidence/gleif-runtime/level1-json-runtime-parity.json`.
   It validates the archive hash, publisher count, original expanded bytes,
   every projected row, global address occurrence counts, scoped last-occurrence
   state, complete Name Frequency entries and all seven cascade passes. It also
   compares entries to the previous complete pinned Name Frequency output.

Use `uv run python crates/source-contract/tests/qualification/<script>.py`.
For measured samples, set `CENSUS_BOUNDED=1` on the SEC script and
`CENSUS_LIMIT=1000` on the full comparison script. A bounded result explicitly
reports `original_source_eof: false`. Complete upstream proofs must exist before
running the combined comparison. Announce the measured full-scan estimate.

## Evidence and limits

The full comparison pins its executed script, native extension, Python runtime
files, upstream proofs and Rules before and after traversal. Do not modify those
files while it runs. The raw oracle table exists only in memory inside this test;
it is never published or persisted as a Source Extract. Original provider EOF
is required; neither a repackaged prefix nor the bounded sample qualifies.

The output contains the complete Name Frequency receipt and global-address
frequency digest, plus counts, timing, policy, runtime pins and explicit flags.
`global-address-frequency.jsonl` is created exclusively: an existing file must
not be overwritten. Preserve a completed evidence directory and choose a fresh
output location in the script before an intentional repeat.

This interpreter comparison does **not** prove full `source.read` worker
execute/replay at archive scale or installed empty PostgreSQL16 population.
Those gates, active caller replacement, old-parser deletion and deployment
remain open. The publication metadata's authenticated count does not replace
archive attestation or the separately pinned publication authority binding.
