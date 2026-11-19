# The shared load-errors.log is rotated

Status: open
Type: task
Owner: Claude

Operator, 2026-11-18: "fix load-errors.log is never rotated, research based on Datadog or other log aggregation best practices".
This is the open part of ticket 01 ("`load-errors.log` is never rotated and mixes runs").

## Findings

- Every `load` process appends a block (`$ <command>` then its error text) to one file in the stores folder
  (`edgar_warehouse/rules/driving.py`, two copies of the same open-append-write), across every lane and every run. It has
  no size or age bound; the hosted load's file was 737 KB after one run.
- The scheduler reads it by byte offset (`errors_since`): a file replaced or shortened during an attempt returns nothing,
  so a step's errors would be lost without a word.

## What the practice says

- Datadog's [log file control with logrotate](https://datadoghq.com/blog/log-file-control-with-logrotate): rotate by size
  (`maxsize`) and age, keep a count (`rotate N`), `compress` rotated files with `delaycompress` so the newest rotated file
  stays readable, prefer `create` (rename, then a new file) to `copytruncate`, which can lose the lines written between the
  copy and the truncate.
- [Fluent Bit](https://github.com/fluent/fluent-bit/issues/375) and [Vector](https://github.com/timberio/vector-test-harness/blob/master/cases/file_rotate_truncate_correctness)
  report data loss and duplicates from copy-truncate rotation: rename-based rotation is the safe form for a file other
  processes still write.
- The [twelve-factor logs rule](https://www.12factor.net/logs): the app does not manage its logfiles; the environment routes
  the stream. Here the file is the operator's private error store (it can hold addresses, so it is never shipped), so the
  platform keeps it small itself rather than leaving it to an agent.
- The [Python logging cookbook](https://pypi.org/project/concurrent-log-handler/0.9.18/) (via ConcurrentRotatingFileHandler's
  notes): `RotatingFileHandler` is not safe across processes; a lock is needed, or one writer. Many `load` processes write
  here, so rotation takes a lock.

## Parts

- [x] Consult the GoF reviewer: "leave it" for lack of a growth figure; not taken, since the operator asked for it and an unbounded shared file is the defect. Taken: one module with one `write` function, not a class; the reader compares the file's identity (inode), not its size, so a rotated file that grew past the old offset is not misread. Not a risk: a writer holding a file open across two whole rotations (20 MiB of other writes between its open and its one append) 2026-11-18 22:05 ET
- [x] Failing tests first: `tests/unit/test_error_log.py` (7 tests; the module did not exist, so each failed on import): a write that would pass the limit renames the file; the second rotation gzips `.1` into `.2.gz` and the count is kept; rotated files past the age are removed; four processes writing across many rotations lose no block; a step finds its errors whether or not the file rotated during its attempt 2026-11-18 22:04 ET
- [x] Build `edgar_warehouse/rules/error_log.py` (rename-based rotation under a lock file, 10 MiB, five kept, 30 days; `.1` plain, older gzip); the two writers in `driving.py` call it; the scheduler reads by `position` and `since`, which follow one rotation; `tests/unit/test_load_chain.py` updated for the position; 158 loader, driving and lint tests pass 2026-11-18 22:04 ET
- [x] Runbooks (init, daily run) and the data-operations skill name `load-errors.log.1` and the gzipped files 2026-11-18 22:04 ET
- [ ] Known: a step whose attempt spans two rotations (20 MiB of errors in one attempt) gets only the current file's errors; the earlier part is in the gzipped files
- [ ] Known and left: the file still mixes runs; each block names its command and `--source`/`--target`, not the run label
- [x] Learning → skill: data-operations names where the rotated errors are 2026-11-18 22:04 ET
