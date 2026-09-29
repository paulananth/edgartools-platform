"""Validated command registrations; legacy acquisition commands are retired."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

ExecuteCommand = Callable[[Any], int]
ResolveCommandScope = Callable[..., dict[str, Any]]
PlanCommandWrites = Callable[..., dict[str, str]]


@dataclass(frozen=True)
class AcquisitionCommandRegistration:
    name: str
    execute: ExecuteCommand
    resolve_scope: ResolveCommandScope
    planned_writes: PlanCommandWrites

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("name must not be empty")
        for behavior_name in ("execute", "resolve_scope", "planned_writes"):
            if not callable(getattr(self, behavior_name)):
                raise TypeError(f"{behavior_name} must be callable")


def build_acquisition_command_registry(
    registrations: Iterable[AcquisitionCommandRegistration],
) -> dict[str, AcquisitionCommandRegistration]:
    registry: dict[str, AcquisitionCommandRegistration] = {}
    for registration in registrations:
        if registration.name in registry:
            raise ValueError(f"Duplicate acquisition command registration: {registration.name}")
        registry[registration.name] = registration
    return registry


_ACQUISITION_COMMAND_REGISTRATIONS = build_acquisition_command_registry(())


def acquisition_command_registration(command_name: str) -> AcquisitionCommandRegistration | None:
    return _ACQUISITION_COMMAND_REGISTRATIONS.get(command_name)


def registered_acquisition_handlers() -> dict[str, ExecuteCommand]:
    return {
        command_name: registration.execute
        for command_name, registration in _ACQUISITION_COMMAND_REGISTRATIONS.items()
    }
