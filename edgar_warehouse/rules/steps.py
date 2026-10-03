"""The custom steps a rules file may name: the last resort (ticket 08).

A step is a lookup or transformation the configuration cannot state. It is a
plain function of one value, registered here under its name and version, and
listed in its source's Mapping Document. The engine refuses a contract that
names a step missing from this table when the contract loads.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

Value = str | int | float | None

def epoch_microseconds(value: Value) -> int:
    """An explicit timezone-bearing ISO timestamp, as exact integer microseconds.

    No floating point rounding, source-specific imports or external lookups.
    Empty, numeric and timezone-free inputs are refused rather than guessed.
    """
    if not isinstance(value, str) or not value:
        raise ValueError("epoch_microseconds needs a timezone-bearing timestamp string")
    at = datetime.fromisoformat(value)
    if at.tzinfo is None:
        raise ValueError("epoch_microseconds needs an explicit timezone")
    delta = at.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


STEPS: dict[str, Callable[[Value], Value]] = {"epoch_microseconds@1": epoch_microseconds}
