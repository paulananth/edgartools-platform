"""Pure control-envelope primitives shared without importing a runtime owner."""

from __future__ import annotations

import hashlib
import json
import re


class Blocked(ValueError):
    """Execution cannot safely reconstruct or verify its frozen scope."""


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def reference(value: dict) -> dict:
    if (not isinstance(value, dict) or set(value) != {"uri", "sha256"}
            or not isinstance(value["uri"], str) or not value["uri"]
            or not isinstance(value["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])):
        raise Blocked("A reference requires an exact URI and lowercase SHA-256")
    return value
