"""The shared load error log: appended by every load process, rotated by size, read by byte position.

Many processes append blocks to one private file, so rotation follows the practice for a file other processes still
write (logrotate's `create` mode, Datadog's log-file guidance): the file is renamed, never copied and truncated (a
copy-truncate loses the lines written between the copy and the truncate), and a new file starts at once. The newest
rotated file stays plain (`.1`, logrotate's `delaycompress`) so it is readable without decompressing; older ones are
gzipped (`.2.gz`, `.3.gz`, ...). A count and an age bound what is kept. One lock file serialises rotation, because
nothing in the standard library makes rotation safe across processes.

A writer that opened the file just before a rename finishes its block in `.1`; no block is split or lost, since each
block is one append.
"""
from __future__ import annotations

import fcntl
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


def _rotate(path: Path, added: int, limit: int, keep: int, max_age_days: float) -> None:
    lock = os.open(path.with_name(path.name + ".lock"), os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
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
        cutoff = time.time() - max_age_days * 86400
        for part in rotated(path):
            if part.stat().st_mtime < cutoff:
                part.unlink(missing_ok=True)
        for number in range(keep + 1, keep + 50):  # files left by a larger count
            _name(path, number).unlink(missing_ok=True)
    finally:
        os.close(lock)  # closing the descriptor releases the lock


def position(path: Path) -> tuple[int, int]:
    """Where the file stands now: its identity and its size, for `since`. A missing file is (0, 0)."""
    try:
        found = Path(path).stat()
    except FileNotFoundError:
        return (0, 0)
    return (found.st_ino, found.st_size)


def since(path: Path, start: tuple[int, int]) -> str:
    """What was written after `start` (a `position`), across one rotation: the end of the file it was taken on (now
    `.1`) and the file now current. After more than one rotation the earlier part is in the gzipped files and only the
    current file is returned."""
    path = Path(path)
    inode, offset = start
    try:
        current = path.stat()
    except FileNotFoundError:
        return ""
    if current.st_ino == inode:
        return _read(path, offset)
    newest = _name(path, 1)
    head = _read(newest, offset) if newest.exists() and newest.stat().st_ino == inode else ""
    return head + _read(path, 0)


def _read(path: Path, offset: int) -> str:
    with path.open("rb") as handle:
        handle.seek(offset)
        return handle.read().decode(errors="replace")
