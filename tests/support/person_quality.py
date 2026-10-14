"""Person's quality before rebuild ticket 10, for tests that pin record ids
taken earlier: a record names its quality version, so v2 moves every id."""

V1 = "sec-person-quality-v1"
V2 = "sec-person-quality-v2"
TICKET_10_CHECK = "legal_name_has_letter"


def before_ticket_10(contract: dict) -> dict:
    """The Person contract with quality v1: v2 less its one new check."""
    quality = contract["quality"]
    assert quality["version"] == V2, quality["version"]
    return {**contract, "quality": {**quality, "version": V1,
                                    "checks": [c for c in quality["checks"] if c["id"] != TICKET_10_CHECK]}}
