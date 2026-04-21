"""Shared command execution wrapper."""

from __future__ import annotations

import json
from typing import Any

from edgar_warehouse.application.context_builder import build_warehouse_context
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.application import runtime_legacy


def execute_standard_command(command_name: str, args: Any) -> int:
    arguments = runtime_legacy._namespace_to_payload(args)
    runtime_mode = "infrastructure_validation"
    try:
        context = build_warehouse_context(command_name)
        runtime_mode = context.runtime_mode
        payload = runtime_legacy._execute_warehouse(context=context, command_name=command_name, arguments=arguments)
    except WarehouseRuntimeError as exc:
        print(json.dumps(runtime_legacy._error_payload(command_name, arguments, str(exc), runtime_mode=runtime_mode), indent=2, sort_keys=True))
        return 2

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0
