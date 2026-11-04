"""Transport retained records and configured field rules to the common Rust engine."""

from __future__ import annotations

from edgar_warehouse.rules.source_engine import (
    choose_field_values,
    describe_field_rules,
    identify_profile,
    prepare_current_records,
)

from .evidence import PROFILE_KINDS, instant
from .store import Conflict

# Compatibility metadata is data; Rust owns the rule interpretation.
PROFILE_IDENTITY = ("role", "authority", "registration", "jurisdiction", "valid_from")
AUTHORITY_SECTIONS, NON_AUTHORITY_SECTIONS = describe_field_rules()


def profile_key(profile):
    return identify_profile(profile)


def current_claims(
    assertions: list[dict], as_of: str, retired: set[str]
) -> dict[str, dict]:
    """Prepare current records once, independently of the database selected."""
    try:
        return prepare_current_records(assertions, instant(as_of).isoformat(), retired)
    except ValueError as error:
        raise Conflict(str(error)) from None


def select_fields(
    kind: str,
    subjects: list[str],
    claims: dict,
    policy: dict,
    overrides: list[dict],
    *,
    as_of: str,
    policy_digest: str,
    entity_id: str = "",
) -> tuple[dict, list[dict], list[dict]]:
    """Carry inputs to one field/profile calculation used by every database."""
    try:
        return choose_field_values({
            "kind": kind,
            "subjects": subjects,
            "claims": claims,
            "policy": policy,
            "overrides": overrides,
            "as_of": instant(as_of).isoformat(),
            "policy_digest": policy_digest,
            "entity_id": entity_id,
            "profile_kinds": {role: sorted(kinds) for role, kinds in PROFILE_KINDS.items()},
        })
    except ValueError as error:
        raise Conflict(str(error)) from None
