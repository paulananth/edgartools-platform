"""Securities mastering: one Security per 13F CUSIP."""

from edgar_warehouse.mdm.clean.securities import publish


def test_one_security_per_cusip_with_a_normalized_title():
    published = publish(
        [
            {"cusip": "02079K305", "title": "CAP STK CL A", "issuer_name": "ALPHABET INC"},
            {"cusip": "02079K305", "title": "COM", "issuer_name": "GOOGLE INC"},
            {"cusip": "02079K305", "title": "CL A", "issuer_name": "Alphabet Inc"},
            {"cusip": "02079K107", "title": "CAP STK CL C", "issuer_name": "ALPHABET INC"},
            {"cusip": "02079K907", "title": "OPTIONS", "issuer_name": "ALPHABET INC"},
            {"cusip": "000000000", "title": "COM", "issuer_name": "SOME CO"},
        ]
    )

    by_cusip = {security["cusip"]: security for security in published["securities"]}
    assert set(by_cusip) == {"02079K305", "02079K107", "02079K907", "000000000"}
    assert by_cusip["02079K305"]["title"] == "Class A"
    assert by_cusip["02079K107"]["title"] == "Class C"
    assert by_cusip["02079K907"]["title"] == "Option"
    assert by_cusip["000000000"]["title"] is None
    assert published["holdings"] == [
        {"cusip": "02079K305", "filed_title": "CAP STK CL A", "filed_issuer_name": "ALPHABET INC"},
        {"cusip": "02079K305", "filed_title": "COM", "filed_issuer_name": "GOOGLE INC"},
        {"cusip": "02079K305", "filed_title": "CL A", "filed_issuer_name": "Alphabet Inc"},
        {"cusip": "02079K107", "filed_title": "CAP STK CL C", "filed_issuer_name": "ALPHABET INC"},
        {"cusip": "02079K907", "filed_title": "OPTIONS", "filed_issuer_name": "ALPHABET INC"},
        {"cusip": "000000000", "filed_title": "COM", "filed_issuer_name": "SOME CO"},
    ]
    assert "companies" not in published
