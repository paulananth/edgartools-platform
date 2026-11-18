"""The distinct keys of what silver.land landed, held on disk in sorted runs, never all in memory.

A receipt names the rows landed, their distinct keys and a digest of those keys; the check then asks silver whether it
holds each key. A set of every key grows with the input, so a quarter of N-PORT holdings made a 1.2 GB worker. A KeySet
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
    def __init__(self, limit: int = 100_000):
        self._limit = limit
        self._buffer: set[tuple[str, ...]] = set()
        self._folder = Path(tempfile.mkdtemp(prefix="silver-keys-"))
        self._runs: list[Path] = []

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
        path = self._folder / f"run-{len(self._runs):06d}"
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

    def sorted(self) -> Iterator[tuple[str, ...]]:
        """Every distinct key, once, in key order."""
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

    def distinct(self) -> int:
        return self.summary()[0]

    def digest(self) -> str:
        return self.summary()[1]


def missing(keys: Iterator[tuple[str, ...]], fetch: Callable[[list[str]], set[tuple[str, ...]]], group: int = 500) -> int:
    """How many of the keys (in key order) silver lacks, asking it for `group` first-key values at a time: only the rows
    of those values (a filer, an accession), so another unit's rows cannot hide a missing one, and never more of them
    in memory than one group holds."""
    lacking, wanted, firsts = 0, [], []

    def flush() -> None:
        nonlocal lacking, wanted, firsts
        if firsts:
            lacking += len(set(wanted) - fetch(firsts))
        wanted, firsts = [], []

    for key in keys:
        if not firsts or firsts[-1] != key[0]:
            if len(firsts) == group:
                flush()
            firsts.append(key[0])
        wanted.append(key)
    flush()
    return lacking
