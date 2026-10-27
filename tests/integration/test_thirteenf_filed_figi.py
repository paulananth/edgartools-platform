"""The FIGI a 13F filer states, read only from a row with no put or call
(ticket 138; operator, 2026-10-27: "On, set aside put/call"): an option row
names its underlying's FIGI. The real chain on invented holdings: the source
extract, the reduction, the combine, mdm.prepare and the Dataset Contract.
Invented values only."""

from __future__ import annotations

from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, register_policy
from edgar_warehouse.rules import files
from tests.integration import test_nport_link_start as nport
from tests.integration import test_openfigi_security as openfigi
from tests.integration.test_security_share_class import THIRTEENF, thirteenf_records
from tests.support.rules_authority import register_dataset

# Invented CUSIPs, check digits valid; invented FIGIs.
PLAIN, OPTION, MIXED, WORDED = "ZZ0000906", "ZZ0000914", "ZZ0000922", "ZZ0000930"


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


def test_a_cusip_filed_only_on_option_rows_creates_its_own_security(database, tmp_path):
    """Its put and call rows name another Security's FIGI, which it never reaches."""
    held = openfigi.figis(openfigi.EQUITY)[0]
    thirteenf = thirteenf_records(tmp_path / "13f", row(OPTION, held, "Call") + row(PLAIN, held))
    answers, _ = openfigi.prepared_records(tmp_path / "openfigi", ("cusip",))
    with database.admin.begin() as conn:
        for name, code in ((THIRTEENF, openfigi.THIRTEENF), ("openfigi", openfigi.CODE)):
            register_dataset(conn, code, database.registry, files.mdm_contract(name, code))
        policy = register_policy(conn, openfigi.policy_body())
    stage = MergeStage(Store(database.application))
    nport.apply(stage, policy, "openfigi", answers, 1)
    nport.apply(stage, policy, "13f", thirteenf, 2)
    equity = openfigi.bound(database, openfigi.CODE, openfigi.EQUITY)
    assert openfigi.bound(database, openfigi.THIRTEENF, PLAIN) == equity
    own = openfigi.bound(database, openfigi.THIRTEENF, OPTION)
    assert own != equity and openfigi.securities(database)[own]["identifiers"] == {"cusip": [OPTION]}
