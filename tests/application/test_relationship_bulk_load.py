from __future__ import annotations





def _filing(accession: str, form: str, *, cik: int = 1, items: str | None = None,
            filing_date: str = "2024-05-01", report_date: str | None = None) -> dict:
    return {
        "accession_number": accession,
        "cik": cik,
        "form": form,
        "items": items,
        "filing_date": filing_date,
        "report_date": report_date,
    }


def test_insider_inventory_dedupes_and_excludes_corporates() -> None:
    """Ticket 21 slice 1: one observation per (owner, issuer) across filings,
    flags OR-merged, corporate owners excluded, nameless+cikless rows dropped."""
    from edgar_warehouse.application.relationship_bulk_load import insider_inventory

    class FakeSilver:
        def fetch(self, sql, params=None):
            assert "sec_ownership_reporting_owner" in sql
            assert params == [88000]
            return [
                {"owner_cik": 1111, "owner_name": "Jane Doe", "issuer_cik": 88000,
                 "is_director": 1, "is_officer": 0, "is_ten_percent_owner": 0},
                # same person+issuer from a later filing, officer flag now set
                {"owner_cik": 1111, "owner_name": "Jane Doe", "issuer_cik": 88000,
                 "is_director": 0, "is_officer": 1, "is_ten_percent_owner": 0},
                # corporate reporting owner — excluded
                {"owner_cik": 500, "owner_name": "Fund LP", "issuer_cik": 88000,
                 "is_director": 0, "is_officer": 0, "is_ten_percent_owner": 1},
                # name-only identity (no owner_cik)
                {"owner_cik": None, "owner_name": "Bob Roe", "issuer_cik": 88000,
                 "is_director": 0, "is_officer": 1, "is_ten_percent_owner": 0},
                # no identity at all — dropped
                {"owner_cik": None, "owner_name": " ", "issuer_cik": 88000,
                 "is_director": 1, "is_officer": 0, "is_ten_percent_owner": 0},
            ]

    inventory = insider_inventory(FakeSilver(), [88000], exclude_owner_ciks=[500])
    assert len(inventory) == 2
    jane = next(o for o in inventory if o.owner_cik == 1111)
    assert jane.is_director and jane.is_officer and not jane.is_ten_percent_owner
    bob = next(o for o in inventory if o.owner_cik is None)
    assert bob.owner_name == "Bob Roe"


def test_partition_insider_coverage_fail_closed_partition() -> None:
    """Ticket 21 slice 2: identified requires person AND issuer AND an
    IS_INSIDER version; each failure mode lands in unresolved with a reason."""
    from edgar_warehouse.application.relationship_bulk_load import (
        InsiderObservation, partition_insider_coverage,
    )

    inv = [
        InsiderObservation(1111, "Jane Doe", 88000, True, True, False),
        InsiderObservation(2222, "No Person", 88000, True, False, False),
        InsiderObservation(3333, "No Issuer", 77000, True, False, False),
        InsiderObservation(4444, "No Version", 88000, False, True, False),
    ]
    result = partition_insider_coverage(
        inv,
        resolve_person=lambda cik, name: None if cik == 2222 else f"p{cik}",
        resolve_issuer=lambda cik: None if cik == 77000 else f"c{cik}",
        has_insider_version=lambda p, c: p != "p4444",
    )
    assert result["insider_total"] == 4
    assert result["insider_identified"] == 1
    assert result["insider_unresolved"] == 3
    reasons = {r["owner_cik"]: r["reason"] for r in result["unresolved"]}
    assert reasons == {2222: "unresolved_person", 3333: "unresolved_issuer",
                       4444: "missing_is_insider_version"}


