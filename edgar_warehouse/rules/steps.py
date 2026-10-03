"""The custom steps a rules file may name: the last resort (ticket 08).

A step is a lookup or transformation the configuration cannot state. It is a
plain function of one value, registered here under its name and version, and
listed in its source's Mapping Document. The engine refuses a contract that
names a step missing from this table when the contract loads.
"""

from __future__ import annotations

from collections.abc import Callable

Value = str | int | float | None

STEPS: dict[str, Callable[[Value], Value]] = {}
