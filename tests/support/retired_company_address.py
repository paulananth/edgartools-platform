"""Historical address oracle for qualification only; never shipped in a wheel.

Frozen from company_source at a2a26a45. Active preparation uses configured reading.
The pinned SEC-to-ISO reference is shared governance data, not a loader.
"""
from edgar_warehouse.mdm.clean.names import edgar_jurisdiction


def business_address(row: dict) -> dict:
    """One landed business address as the Company record carries it."""
    place = edgar_jurisdiction(row["state_or_country"] or row.get("country_code"))
    return {
        "street": row["street1"] or None,
        "street2": row["street2"] or None,
        "city": row["city"] or None,
        # A region only for a state or province: SEC writes a foreign country
        # in the same field ("P7", the Netherlands), which is the country
        # (ticket 18).
        "region": (row["state_or_country"] or None) if place and "-" in place else None,
        "postal_code": row["zip_code"] or None,
        "country": place.split("-")[0] if place else None,
    }

