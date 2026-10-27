"""The FIGI a 13F filer states, read only from a row with no put or call
(ticket 138; operator, 2026-10-27: "On, set aside put/call"): an option row
names its underlying's FIGI. The real chain on invented holdings: the source
extract, the reduction, the combine, mdm.prepare and the Dataset Contract.
Invented values only."""

from __future__ import annotations

from tests.integration.test_security_share_class import thirteenf_records

# Invented CUSIPs, check digits valid; invented FIGIs.
PLAIN, OPTION, MIXED, WORDED = "ZZ0000013", "ZZ0000021", "ZZ0000039", "ZZ0000047"


def row(cusip: str, figi: str, put_call: str | None = None) -> str:
    option = "" if put_call is None else f"<putCall>{put_call}</putCall>"
    return (f"<infoTable><nameOfIssuer>EXAMPLE CORP</nameOfIssuer><titleOfClass>COM</titleOfClass>"
            f"<cusip>{cusip}</cusip><figi>{figi}</figi><value>1</value>{option}</infoTable>")


def test_a_figi_filed_only_on_put_or_call_rows_is_not_read(tmp_path):
    rows = "".join([
        row(PLAIN, "BBGZ0000PL11"),
        row(OPTION, "BBGZ0000OP11", "Put"), row(OPTION, "BBGZ0000OP22", "CALL"),
        # The lexically first FIGI is on the call row; the plain row's is kept.
        row(MIXED, "BBGZ0000MX11", "Call"), row(MIXED, "BBGZ0000MX22"),
        # A putCall the filer wrote as "None" is no option.
        row(WORDED, "BBGZ0000WD11", "None")])
    records = thirteenf_records(tmp_path, rows)
    assert {r["provenance"]["record_key"]: r.get("cross_references", {}) for r in records} == {
        PLAIN: {"figi": "BBGZ0000PL11"}, OPTION: {}, MIXED: {"figi": "BBGZ0000MX22"},
        WORDED: {"figi": "BBGZ0000WD11"}}
    # The CUSIP filed only on option rows is still a Security record, as today.
    assert {r["provenance"]["record_key"]: r["identifiers"] for r in records}[OPTION] == {"cusip": OPTION}
