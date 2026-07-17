"""Dual-mode capture contract (ADR 0002 + Ticket 20 coexistence).

normal
  Silver is the runtime system of engagement. Bronze for edgartools-sourced SEC
  objects is written only when an operator explicitly requests persist.

strict_release
  Always persist immutable evidence artifacts required for relationship bulk-load
  and release GO (Ticket 20). Does not relax silver SoE skips for re-runs; it
  requires evidence bytes to exist when candidates are loaded.

Non-edgartools sources (IAPD ADV bulk, PCAOB bulk, operator FOIA drops, etc.)
always require an immutable archive under both modes.
"""

from __future__ import annotations

import os
from typing import Final

CAPTURE_MODE_NORMAL: Final = "normal"
CAPTURE_MODE_STRICT_RELEASE: Final = "strict_release"
CAPTURE_MODES: Final = frozenset({CAPTURE_MODE_NORMAL, CAPTURE_MODE_STRICT_RELEASE})

# Env vars (operator-facing contract for tickets 03–07)
ENV_CAPTURE_MODE = "WAREHOUSE_CAPTURE_MODE"
ENV_PERSIST_BRONZE = "WAREHOUSE_PERSIST_BRONZE"
ENV_RELEASE_MODE = "WAREHOUSE_RELEASE_MODE"  # legacy alias → strict_release when truthy


def resolve_capture_mode(
    *,
    explicit: str | None = None,
    environ: dict[str, str] | None = None,
) -> str:
    """Return normal or strict_release.

    Precedence: explicit argument → WAREHOUSE_CAPTURE_MODE → WAREHOUSE_RELEASE_MODE
    truthy → normal.
    """
    env = environ if environ is not None else os.environ
    if explicit is not None:
        mode = explicit.strip().lower()
    else:
        raw = (env.get(ENV_CAPTURE_MODE) or "").strip().lower()
        if raw:
            mode = raw
        elif _env_truthy(env.get(ENV_RELEASE_MODE)):
            mode = CAPTURE_MODE_STRICT_RELEASE
        else:
            mode = CAPTURE_MODE_NORMAL
    if mode not in CAPTURE_MODES:
        raise ValueError(
            f"invalid capture mode {mode!r}; expected one of {sorted(CAPTURE_MODES)}"
        )
    return mode


def should_persist_bronze(
    *,
    capture_mode: str | None = None,
    explicit_persist: bool | None = None,
    source_is_edgartools: bool = True,
    environ: dict[str, str] | None = None,
) -> bool:
    """Whether raw payloads must be written to bronze for this capture.

    - Non-edgartools sources: always True
    - strict_release: always True
    - normal: True only if explicit_persist or WAREHOUSE_PERSIST_BRONZE is truthy
    """
    env = environ if environ is not None else os.environ
    if not source_is_edgartools:
        return True
    mode = capture_mode if capture_mode is not None else resolve_capture_mode(environ=env)
    if mode == CAPTURE_MODE_STRICT_RELEASE:
        return True
    if explicit_persist is True:
        return True
    if explicit_persist is False:
        return False
    return _env_truthy(env.get(ENV_PERSIST_BRONZE))


def non_edgartools_source_requires_bronze() -> bool:
    """Contract constant: non-library sources always archive immutably."""
    return True


def _env_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}
