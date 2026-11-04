"""The words ticket 178 changed, for tests that compare with answers recorded before it.

A historic digest or retired-mapper outcome was made when the Name Count was called the
census; the test puts the old words back before it hashes, so the recorded answer still
stands and nothing is re-baselined for a rename.
"""
RENAMED_BY_TICKET_178 = {
    "name_count": "name_census", "sec-company-landing-v8": "sec-company-landing-v7",
    "sec-company-landing-v9": "sec-company-landing-v7",  # ticket 01's version, put back to the one recorded
    **{f"name_count_{part}": f"census_{part}" for part in (
        "field", "entries_field", "holder_keys_field", "holder_count_field", "identifier_count_field",
        "other_holders_field")}}


def old_words(value):
    """`value` with every key and text equal to a renamed word put back."""
    if isinstance(value, dict):
        return {old_words(k): old_words(v) for k, v in value.items()}
    if isinstance(value, list):
        return [old_words(v) for v in value]
    return RENAMED_BY_TICKET_178.get(value, value) if isinstance(value, str) else value


# Ticket 01 (operator, 2026-11-04: exact name only): the SEC company and GLEIF level 1 contracts gained a
# `name_id` cross-reference, and so a new version. A test that compares with a digest recorded before it
# puts the old version back and takes the cross-reference away.
VERSIONS_BEFORE_NAME_ID = {"sec-company-landing-v9": "sec-company-landing-v8", "gleif-native-record-v2": "gleif-native-record-v1"}


def before_name_id(contract: dict) -> dict:
    """`contract` as it was before the `name_id` cross-reference."""
    adapter = dict(contract["adapter"])
    for part in ("cross_references", "cross_reference_formats"):
        kept = {k: v for k, v in (adapter.get(part) or {}).items() if k != "name_id"}
        if kept:
            adapter[part] = kept
        else:
            adapter.pop(part, None)
    adapter["version"] = VERSIONS_BEFORE_NAME_ID.get(adapter.get("version"), adapter.get("version"))
    return {**contract, "adapter": adapter}


def without_name_id(record: dict) -> dict:
    """A record as it was written before the `name_id` cross-reference (ticket 01)."""
    body = dict(record)
    references = {k: v for k, v in (body.get("cross_references") or {}).items() if k != "name_id"}
    if references:
        body["cross_references"] = references
    else:
        body.pop("cross_references", None)
    provenance = body.get("provenance") or {}
    if provenance.get("adapter_version") == "gleif-native-record-v2":
        body["provenance"] = {**provenance, "adapter_version": "gleif-native-record-v1"}
    return body
