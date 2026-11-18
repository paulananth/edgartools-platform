# Lower the memory of a load's workers

Status: open
Type: task

Operator, 2026-11-18: "Make worker memory footprint low remove all unnecessary libraries". Measured on the 8 GB Mac
during the hosted fresh load (ticket 238).

## Findings

- A bare interpreter is 16 MB; the modules a load imports took it to 72 MB. pyarrow with numpy under it were three
  quarters of that, imported by every worker though only a Parquet source reads one. Now imported when a Parquet file is
  read: 44 MB (28 MB, 39%, in each of the several processes of each load).
- sqlalchemy (23 MB) and yaml (3 MB) are needed; psycopg2 loads at connect (6 MB). `pytz` was declared and used nowhere.
- The workers' data is larger than their libraries: of four running workers one held 1.2 GB (N-PORT silver), the others 58
  to 228 MB.
- The largest memory user on the Mac was not a worker: OrbStack, the Docker VM of the local test stores, at 4.25 GB of 8.

## Parts

- [x] pyarrow and numpy are imported when a Parquet file is read, and the files a run pins are named without importing
  them (2026-11-18 08:27 ET; `test_a_load_that_reads_no_parquet_file_never_imports_pyarrow_or_numpy` failed first: `True True`;
  `test_the_parquet_files_a_run_pins_are_the_same_without_importing_pyarrow` holds the pinned files equal to what the
  imports name; 67 tests; load path import 72 to 44 MB)
- [x] `pytz` leaves the dependencies: nothing in the repository imports it (2026-11-18 08:27 ET; `uv lock` drops two lines)
- [ ] The N-PORT silver worker holds 1.2 GB: find what it keeps (rows of a whole file) and stream it in bounded pieces
- [ ] OrbStack's memory limit is the operator's to set (the local test stores are shared): lowering its 4.25 GB gives the
  loads room; say what the stores need first
- [ ] `ENGINE` runs each load as `uv run --no-sync edgar-warehouse` (a wrapper process of 8 MB for each load): run the
  installed command directly
- [x] Learning → skill: mdm-engineering, "A worker's memory is its imports plus its data" (2026-11-18 08:27 ET)

## Not changed while the hosted load runs

The running loads execute from another checkout; this change is in its own worktree, since a change to a pinned runtime file
(`source_parquet.py`) changes the processing identity of what the load reads, and a retry mid-load would read it as
changed code. It merges, and the next load picks it up, after the chain ends.
