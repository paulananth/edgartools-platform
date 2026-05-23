"""ShardManifest parsing and CIK-band resolution utilities.

All functions in this module are pure and have no external dependencies beyond
the stdlib ``json`` module and ``WarehouseRuntimeError``.

Shard manifest JSON schema::

    {
        "shard_count": 4,
        "schema_version": "1",
        "created_at": "2026-05-21T00:00:00Z",
        "bands": [
            {"shard_index": 0, "cik_min": 0,       "cik_max": 1053917},
            {"shard_index": 1, "cik_min": 1053918,  "cik_max": 1523562},
            {"shard_index": 2, "cik_min": 1523563,  "cik_max": 1819990},
            {"shard_index": 3, "cik_min": 1819991,  "cik_max": 9999999}
        ],
        "checksums": {"0": "<sha256>", ...}
    }

Band boundaries are inclusive on both ends.  Adjacent bands must not overlap:
``band[n].cik_max + 1 == band[n+1].cik_min``.  A given CIK therefore falls in
exactly one band, and ``band_for_cik`` returns that band's ``shard_index``.
"""

from __future__ import annotations

import json

from edgar_warehouse.application.errors import WarehouseRuntimeError

_REQUIRED_KEYS = ("shard_count", "bands", "checksums")


def load_manifest(manifest_bytes: bytes) -> dict:
    """Parse and validate a shard-manifest.json payload.

    Parameters
    ----------
    manifest_bytes:
        Raw bytes read from S3 (or another byte source).

    Returns
    -------
    dict
        The parsed manifest dictionary.

    Raises
    ------
    WarehouseRuntimeError
        If the bytes are not valid JSON or the top-level required keys are
        missing (``shard_count``, ``bands``, ``checksums``).
    """
    try:
        data = json.loads(manifest_bytes)
    except (json.JSONDecodeError, ValueError) as exc:
        raise WarehouseRuntimeError(f"shard manifest is not valid JSON: {exc}") from exc

    missing = [k for k in _REQUIRED_KEYS if k not in data]
    if missing:
        raise WarehouseRuntimeError(
            f"shard manifest is missing required keys: {missing}"
        )

    return data


def shards_for_window(manifest: dict, cik_min: int, cik_max: int) -> list[int]:
    """Return all shard indices whose CIK bands overlap ``[cik_min, cik_max]``.

    The overlap test is the standard interval overlap condition::

        band.cik_max >= cik_min  AND  band.cik_min <= cik_max

    Parameters
    ----------
    manifest:
        A parsed shard manifest dictionary (as returned by :func:`load_manifest`).
    cik_min:
        The lower bound CIK value (inclusive).  Must be a non-negative integer.
    cik_max:
        The upper bound CIK value (inclusive).  Must be >= ``cik_min``.

    Returns
    -------
    list[int]
        Shard indices in ascending order whose bands intersect the given window.
        Returns an empty list if no bands overlap.

    Raises
    ------
    WarehouseRuntimeError
        If ``cik_min`` is not a non-negative integer or ``cik_max < cik_min``.

    Notes
    -----
    The ``--cik-offset`` CLI argument is a **positional index** into the sorted
    MDM CIK list, NOT a CIK value.  Callers must resolve positional offsets to
    actual CIK values *before* calling this function.
    """
    if not isinstance(cik_min, int) or cik_min < 0:
        raise WarehouseRuntimeError(
            f"cik_min must be a non-negative integer, got: {cik_min!r}"
        )
    if not isinstance(cik_max, int) or cik_max < cik_min:
        raise WarehouseRuntimeError(
            f"cik_max must be an integer >= cik_min ({cik_min}), got: {cik_max!r}"
        )

    result: list[int] = []
    for band in manifest["bands"]:
        if band["cik_max"] >= cik_min and band["cik_min"] <= cik_max:
            result.append(band["shard_index"])

    result.sort()
    return result


def band_for_cik(manifest: dict, cik: int) -> int:
    """Return the shard index of the unique band containing ``cik``.

    Band boundaries are inclusive.  If two bands share a boundary value the
    lower-index band wins (per D-01: ``band.cik_max`` belongs to the band that
    declares it; the next band starts at ``cik_max + 1``).

    Parameters
    ----------
    manifest:
        A parsed shard manifest dictionary.
    cik:
        The CIK value to look up.

    Returns
    -------
    int
        The ``shard_index`` of the band that contains ``cik``.

    Raises
    ------
    WarehouseRuntimeError
        If no band covers the given CIK (e.g. ``cik`` exceeds all band
        boundaries).
    """
    if not isinstance(cik, int) or cik < 0:
        raise WarehouseRuntimeError(
            f"cik must be a non-negative integer, got: {cik!r}"
        )

    for band in manifest["bands"]:
        if band["cik_min"] <= cik <= band["cik_max"]:
            return band["shard_index"]

    raise WarehouseRuntimeError(
        f"CIK {cik} is not covered by any band in the shard manifest"
    )
