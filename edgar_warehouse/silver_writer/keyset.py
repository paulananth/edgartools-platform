"""The distinct keys of what silver.land landed, held on disk in sorted runs, never all in memory.

A receipt names the rows landed, their distinct keys and a digest of those keys; the check then asks silver whether it
holds each key. A set of every key grows with the input, so a worker that holds one grows with the largest load. A KeySet
holds at most `limit` keys in memory, writes each full buffer as a sorted run in a temporary folder, and reads them back
merged in key order, so the digest is the one `sha256(json.dumps(sorted(keys)))` gave and every stored receipt still
verifies."""

from __future__ import annotations

import hashlib
import heapq
import json
import shutil
import tempfile
from collections.abc import Callable, Iterable, Iterator
from typing import Self
from pathlib import Path


class KeySet:
    def __init__(self, limit: int = 100_000, fan_in: int = 64):
        self._limit = limit
        self._fan_in = fan_in
        self._buffer: set[tuple[str, ...]] = set()
        self._folder = Path(tempfile.mkdtemp(prefix="silver-keys-"))
        self._runs: list[Path] = []
        self._serial = 0

    def _new_run(self) -> Path:
        self._serial += 1
        return self._folder / f"run-{self._serial:06d}"

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        shutil.rmtree(self._folder, ignore_errors=True)

    def add(self, keys: Iterable[tuple[str, ...]]) -> None:
        for key in keys:
            self._buffer.add(key)
            if len(self._buffer) >= self._limit:
                self._spill()

    def _spill(self) -> None:
        path = self._new_run()
        with path.open("w") as out:
            for key in sorted(self._buffer):
                out.write(json.dumps(list(key)) + "\n")
        self._runs.append(path)
        self._buffer = set()

    @staticmethod
    def _read(path: Path) -> Iterator[tuple[str, ...]]:
        with path.open() as source:
            for line in source:
                yield tuple(json.loads(line))

    def _merge_down(self) -> None:
        """Merge the runs `fan_in` at a time into longer ones until no more than `fan_in` remain, so a read never holds
        more files open than that however large the input (the open-file limit of the machine is not the input's)."""
        while len(self._runs) > self._fan_in:
            merged = []
            for start in range(0, len(self._runs), self._fan_in):
                group = self._runs[start:start + self._fan_in]
                path = self._new_run()
                last = None
                with path.open("w") as out:
                    for key in heapq.merge(*(self._read(run) for run in group)):
                        if key != last:
                            out.write(json.dumps(list(key)) + "\n")
                            last = key
                for run in group:
                    run.unlink()
                merged.append(path)
            self._runs = merged

    def sorted(self) -> Iterator[tuple[str, ...]]:
        """Every distinct key, once, in key order."""
        self._merge_down()
        last = None
        for key in heapq.merge(*(self._read(run) for run in self._runs), sorted(self._buffer)):
            if key != last:
                yield key
                last = key

    def summary(self) -> tuple[int, str]:
        """The distinct keys and the sha256 of their sorted JSON, in one pass."""
        digest, count = hashlib.sha256(b"["), 0
        for key in self.sorted():
            digest.update((b"," if count else b"") + json.dumps(list(key), separators=(",", ":")).encode())
            count += 1
        digest.update(b"]")
        return count, digest.hexdigest()


def missing(keys: Iterator[tuple[str, ...]], fetch: Callable[[list[str]], set[tuple[str, ...]]], group: int = 500,
            limit: int = 50_000) -> int:
    """How many of the keys (in key order) silver lacks, asking it for up to `group` first-key values at a time: only the
    rows of those values (a filer, an accession), so another unit's rows cannot hide a missing one. A question also
    ends once it holds `limit` keys, so a table whose first column has few distinct values cannot bring every key back
    into memory; one first-key value with more keys than that is still asked as a whole."""
    lacking, wanted, firsts = 0, [], []

    def flush() -> None:
        nonlocal lacking, wanted, firsts
        if firsts:
            lacking += len(set(wanted) - fetch(firsts))
        wanted, firsts = [], []

    for key in keys:
        if not firsts or firsts[-1] != key[0]:
            if len(firsts) == group or len(wanted) >= limit:
                flush()
            firsts.append(key[0])
        wanted.append(key)
    flush()
    return lacking
