"""The custom steps a rules file may name: the last resort (ticket 08).

A step is a lookup or transformation the configuration cannot state. It is a
plain function of one value, registered here under its name and version, and
listed in its source's Mapping Document. The engine refuses a contract that
names a step missing from this table when the contract loads.
"""

from __future__ import annotations

from collections.abc import Callable

Value = str | int | float | None


def blank_missing_token(value: Value) -> Value:
    """`none` and `nan` are null, matching `parse_thirteenf`'s text blanking."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    return None if text.lower() in {"", "none", "nan"} else text


STEPS: dict[str, Callable[[Value], Value]] = {
    "blank_missing_token@1": blank_missing_token,
}
