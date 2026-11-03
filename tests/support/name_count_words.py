"""The words ticket 178 changed, for tests that compare with answers recorded before it.

A historic digest or retired-mapper outcome was made when the Name Count was called the
census; the test puts the old words back before it hashes, so the recorded answer still
stands and nothing is re-baselined for a rename.
"""
RENAMED_BY_TICKET_178 = {
    "name_count": "name_census", "sec-company-landing-v8": "sec-company-landing-v7",
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
