"""Pure control-envelope primitives shared without importing a runtime owner."""

from __future__ import annotations

import json


class Blocked(ValueError):
    """Execution cannot safely reconstruct or verify its frozen scope."""


def canonical(value) -> str:
    import edgar_control
    encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    try:
        return edgar_control.canonicalize(encoded)
    except UnicodeEncodeError:
        # Opaque processing metadata may contain lone surrogates until unused
        # columns are dropped. Preserve Python code points for native equality;
        # durable UTF-8 hashes and publication retain their existing refusal.
        return edgar_control.canonicalize_opaque(value)


def digest(value) -> str:
    import edgar_control
    return edgar_control.digest_json(json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False))


def reference(value: dict) -> dict:
    import edgar_control
    try:
        edgar_control.check_reference(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except ValueError as error:
        raise Blocked(str(error)) from None
    return value
