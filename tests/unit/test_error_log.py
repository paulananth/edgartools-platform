"""The shared load-errors.log is rotated by size, by renaming, under a lock, and keeps a bounded number of files."""

from __future__ import annotations

import gzip
import multiprocessing
import os
import time

from edgar_warehouse.rules import error_log


def block(number: int, size: int = 100) -> str:
    return f"$ run --source s --target t\nerror {number} " + "x" * size + "\n"


def test_a_write_appends_and_makes_a_private_file(tmp_path):
    log = tmp_path / "load-errors.log"
    error_log.write(log, block(1))
    error_log.write(log, block(2))
    assert log.read_text() == block(1) + block(2)
    assert oct(log.stat().st_mode & 0o777) == "0o600"
    assert error_log.rotated(log) == []


def test_a_write_that_would_pass_the_limit_renames_the_file_and_starts_a_new_one(tmp_path):
    log = tmp_path / "load-errors.log"
    error_log.write(log, block(1, 300), limit=400)
    error_log.write(log, block(2), limit=400)
    assert (tmp_path / "load-errors.log.1").read_text() == block(1, 300)  # the newest rotated file stays readable
    assert log.read_text() == block(2)


def test_the_second_rotation_compresses_the_older_file_and_the_count_is_kept(tmp_path):
    log = tmp_path / "load-errors.log"
    for number in range(1, 9):
        error_log.write(log, block(number, 300), limit=400, keep=3)
    names = sorted(p.name for p in tmp_path.iterdir() if p.name != "load-errors.log.lock")
    assert names == ["load-errors.log", "load-errors.log.1", "load-errors.log.2.gz", "load-errors.log.3.gz"]
    assert gzip.decompress((tmp_path / "load-errors.log.2.gz").read_bytes()).decode() == block(6, 300)
    assert (tmp_path / "load-errors.log.1").read_text() == block(7, 300)
    assert log.read_text() == block(8, 300)


def test_rotated_files_past_the_age_are_removed(tmp_path):
    log = tmp_path / "load-errors.log"
    error_log.write(log, block(1, 300), limit=400)
    error_log.write(log, block(2, 300), limit=400)
    error_log.write(log, block(3, 300), limit=400)  # now .1 and .2.gz exist
    old = time.time() - 40 * 86400
    os.utime(tmp_path / "load-errors.log.2.gz", (old, old))
    error_log.write(log, block(4, 300), limit=400, max_age_days=30)
    assert not (tmp_path / "load-errors.log.3.gz").exists()  # the old .2.gz shifted to .3.gz and was removed for its age
    assert [p.name for p in error_log.rotated(log)] == ["load-errors.log.1", "load-errors.log.2.gz"]


def _writer(path, start, count):
    for number in range(start, start + count):
        error_log.write(path, block(number, 200), limit=3000, keep=50)


def test_writers_in_several_processes_lose_no_block_across_rotations(tmp_path):
    log = tmp_path / "load-errors.log"
    processes = [multiprocessing.Process(target=_writer, args=(log, start * 1000, 40)) for start in range(4)]
    for p in processes:
        p.start()
    for p in processes:
        p.join(60)
        assert p.exitcode == 0
    text = ""
    for part in reversed(error_log.rotated(log)):
        text += (gzip.decompress(part.read_bytes()).decode() if part.suffix == ".gz" else part.read_text())
    text += log.read_text()
    found = sorted(int(line.split()[1]) for line in text.splitlines() if line.startswith("error "))
    assert found == sorted(start * 1000 + i for start in range(4) for i in range(40))


def test_a_step_finds_its_errors_whether_or_not_the_file_rotated_during_its_attempt(tmp_path):
    log = tmp_path / "load-errors.log"
    error_log.write(log, block(1, 300), limit=1000)
    start = error_log.position(log)  # the attempt starts here
    error_log.write(log, block(2, 300), limit=1000)  # still under the limit: appended
    assert error_log.since(log, start) == block(2, 300)
    error_log.write(log, block(3, 300), limit=1000)  # past the limit: blocks 1 and 2 move to .1, block 3 starts a file
    assert (tmp_path / "load-errors.log.1").read_text() == block(1, 300) + block(2, 300)
    assert error_log.since(log, start) == block(2, 300) + block(3, 300)
    assert error_log.since(log, error_log.position(log)) == ""


def test_a_missing_file_has_no_errors_and_a_position_of_nothing(tmp_path):
    log = tmp_path / "load-errors.log"
    assert error_log.since(log, error_log.position(log)) == ""
    error_log.write(log, block(1))
    assert error_log.since(log, error_log.position(tmp_path / "absent.log")) == block(1)
