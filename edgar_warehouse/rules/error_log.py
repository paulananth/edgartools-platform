"""The shared load error log: appended by every load process, rotated by size, read by byte position.

Many processes append blocks to one private file, so rotation follows the practice for a file other processes still
write (logrotate's `create` mode, Datadog's log-file guidance): the file is renamed, never copied and truncated (a
copy-truncate loses the lines written between the copy and the truncate), and a new file starts at once. The newest
rotated file stays plain (`.1`, logrotate's `delaycompress`) so it is readable without decompressing; older ones are
gzipped (`.2.gz`, `.3.gz`, ...). A count and an age bound what is kept. One lock file serialises rotation, because
nothing in the standard library makes rotation safe across processes.

A writer that opened the file just before a rename finishes its block in `.1`; each block is one append, so blocks of
different processes do not interleave.

A reader keeps a position (the rotation count and the size) taken before its work. The count, kept in `<name>.gen`
and raised under the lock at each rotation, says how many times the file was rotated since, so a freed file identity
that the system reuses cannot be mistaken for the old file.
"""
from __future__ import annotations

import gzip
import os
import shutil
import time
from pathlib import Path

LIMIT = 10 * 1024 * 1024  # a file this size is rotated before the next block would pass it
KEEP = 5  # rotated files kept: `.1` plain, `.2.gz` to `.<KEEP>.gz`
MAX_AGE_DAYS = 30  # a rotated file last written longer ago than this is removed


def _name(path: Path, number: int) -> Path:
    return path.with_name(f"{path.name}.{number}" + ("" if number == 1 else ".gz"))


def _generation(path: Path) -> int:
    try:
        return int(path.with_name(path.name + ".gen").read_text() or 0)
    except (FileNotFoundError, ValueError):
        return 0


def rotated(path: Path) -> list[Path]:
    """The rotated files that exist, newest first (`.1`, `.2.gz`, ...)."""
    path = Path(path)
    return [part for part in (_name(path, number) for number in range(1, 100)) if part.exists()]


def write(path: Path, text: str, *, limit: int = LIMIT, keep: int = KEEP, max_age_days: float = MAX_AGE_DAYS) -> None:
    """Append one block, rotating first when it would take the file past `limit`."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode()
    if _full(path, len(data), limit):
        _rotate(path, len(data), limit, keep, max_age_days)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        view = memoryview(data)
        while view:  # one append for the block, so another process's block never lands inside it
            view = view[os.write(fd, view):]
    finally:
        os.close(fd)


def _full(path: Path, added: int, limit: int) -> bool:
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return False
    return size > 0 and size + added > limit


def _hold(fd: int) -> None:
    """Wait for the rotation lock: `flock` on Linux and macOS, `msvcrt.locking` on Windows (which retries for ten seconds)."""
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX)


def _rotate(path: Path, added: int, limit: int, keep: int, max_age_days: float) -> None:
    lock = os.open(path.with_name(path.name + ".lock"), os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        _hold(lock)
        if not _full(path, added, limit):  # another process rotated while this one waited
            return
        for number in range(keep, 1, -1):
            source, target = _name(path, number - 1), _name(path, number)
            target.unlink(missing_ok=True)
            if not source.exists():
                continue
            if number == 2:  # `.1` is plain; it is gzipped as it ages into `.2.gz`
                stamp = source.stat().st_mtime
                with source.open("rb") as plain, gzip.open(target, "wb") as packed:
                    shutil.copyfileobj(plain, packed)
                os.utime(target, (stamp, stamp))
                source.unlink()
            else:
                source.rename(target)
        os.replace(path, _name(path, 1))
        counter = path.with_name(path.name + ".gen")
        scratch = counter.with_name(counter.name + ".new")
        scratch.write_text(str(_generation(path) + 1))
        os.replace(scratch, counter)  # a reader sees the old count or the new one, never half of it
        cutoff = time.time() - max_age_days * 86400
        for part in rotated(path):
            if part.stat().st_mtime < cutoff:
                part.unlink(missing_ok=True)
        for number in range(keep + 1, keep + 50):  # files left by a larger count
            _name(path, number).unlink(missing_ok=True)
    finally:
        os.close(lock)  # closing the descriptor releases the lock


def position(path: Path) -> tuple[int, int]:
    """Where the file stands now: its rotation count and its size, for `since`. The file is made empty if it is not
    there, so a rotation after this point is seen as one."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.close(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600))
    while True:  # a rotation between the two reads of the count would pair the new file's size with the old count
        before = _generation(path)
        size = path.stat().st_size
        if _generation(path) == before:
            return (before, size)


def since(path: Path, start: tuple[int, int]) -> str:
    """What was written after `start` (a `position`): from the offset in the file now current, or, after one rotation,
    from the offset in `.1` (the file that was current) and then the whole current file. After more than one rotation
    the earlier part is in the gzipped files and only the current file is returned."""
    path = Path(path)
    generation, offset = start
    if not path.exists():
        return ""
    rotations = _generation(path) - generation
    if rotations <= 0:
        return _read(path, offset)
    newest = _name(path, 1)
    head = _read(newest, offset) if rotations == 1 and newest.exists() else ""
    return head + _read(path, 0)


def _read(path: Path, offset: int) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(offset)
            return handle.read().decode(errors="replace")
    except FileNotFoundError:  # rotated between the check and the open
        return ""
