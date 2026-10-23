"""The Company's fields before rebuild ticket 129, fixes 2 and 3, for tests that
pin answers taken earlier: GLEIF's record-keeping dates and the SIC code's label
left the Company (operator, 2026-10-22), so every projection and record id moved."""

import copy

FIELDS_BACK = {
    "sec.submissions.company.v1": ("sic", {"sic_description": {"value": {
        "path": "sic_description", "path_mode": "literal", "type": "text", "null_if_blank": True}}}),
    "gleif.level1.v1": ("gleif_initial_registration", {name: {"value": {
        "path": f"Registration.{path}.$", "null_if_blank": True, "type": "text", "path_mode": "literal"}}
        for name, path in (("gleif_last_update", "LastUpdateDate"), ("gleif_next_renewal", "NextRenewalDate"))}),
}


def reading_before_ticket_129(reading: dict, code: str) -> dict:
    """A source extract with the ticket 129 fields put back, each where it stood."""
    after, back = FIELDS_BACK[code]
    reading = copy.deepcopy(reading)
    holder = reading["read"]["tables"]["mapped"]["columns"]["fields"]["object"]
    assert not set(back) & set(holder["fields"]), code
    fields = {}
    for name, body in holder["fields"].items():
        fields[name] = body
        if name == after:
            fields.update(back)
    holder["fields"] = fields
    if "input_fields" in reading:
        reading["input_fields"] = sorted([*reading["input_fields"], *back])
    return reading


def before_ticket_129(contract: dict, code: str) -> dict:
    """The contract with its ticket 129 fields put back."""
    adapter = {**contract["adapter"], "reading": reading_before_ticket_129(contract["adapter"]["reading"], code)}
    return {**contract, "adapter": adapter}
