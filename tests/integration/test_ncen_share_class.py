"""Real PG16: an N-CEN share class finds its Security by class id, then by ticker (ticket 234, part 3).

Operator, 2026-11-14: "Class id, then ticker (Recommended)". The Merge Stage rules on N-CEN's share classes:
- `ncen-class-ticker`: a class whose ticker exactly one Security holds (OpenFIGI's, with a CUSIP) joins it;
- a ticker that several Securities hold sends the class to review;
- `ncen-class-id`: a class no Security holds by ticker creates a Security keyed by its SEC class id, which the
  class's later records join.
Invented values only.
"""

from __future__ import annotations

from edgar_warehouse.rules import files
from tests.integration import test_mdm_postgres as core
from tests.integration.test_openfigi_security import bound, securities
from tests.mdm import policy_layers
from tests.support import masters

OPENFIGI = "openfigi.security.v4"
NCEN = "sec.ncen.class.v1"
ONE, TWO = "ZZ0000013", "ZZ0000021"  # invented CUSIPs, check digits valid
CLASS_A, CLASS_B = "C000000001", "C000000002"


def policy() -> dict:
    return policy_layers.with_rules_on(files.policy(), "security", "openfigi-security-cusip")


def openfigi(cusip: str, ticker: str) -> dict:
    return core.source(key=cusip, source_code=OPENFIGI, kind="security", fields={"name_of_issuer": "Example Fund"},
                       identifiers={"cusip": cusip, "ticker": ticker}, provenance={"matching": {"found": ["listed"]}})


def share_class(class_id: str, ticker: str | None) -> dict:
    return core.source(key=class_id, source_code=NCEN, kind="security", fields={"title_of_class": "Class A"},
                       identifiers={"sec_class_id": class_id},
                       cross_references={"ticker": ticker} if ticker else {})


def load(database, held: list[dict], classes: list[dict]):
    body = policy()
    masters.seed(database.application, held, body)
    masters.seed(database.application, classes, body)


def test_a_class_joins_the_one_security_holding_its_ticker(database):
    load(database, [openfigi(ONE, "EXAAX"), openfigi(TWO, "EXBBX")], [share_class(CLASS_A, "EXAAX")])
    found = securities(database)
    assert len(found) == 2
    assert bound(database, NCEN, CLASS_A) == bound(database, OPENFIGI, ONE) is not None
    assert found[bound(database, NCEN, CLASS_A)]["identifiers"]["sec_class_id"] == [CLASS_A]


def test_a_class_whose_ticker_two_securities_hold_goes_to_review(database):
    load(database, [openfigi(ONE, "EXAAX"), openfigi(TWO, "EXAAX")], [share_class(CLASS_A, "EXAAX")])
    assert len(securities(database)) == 2
    assert bound(database, NCEN, CLASS_A) is None
    assert "conflicting_identifiers" in masters.reviews(database.application)


def test_a_class_no_security_holds_creates_one_by_its_class_id(database):
    load(database, [openfigi(ONE, "EXAAX")], [share_class(CLASS_B, "EXZZX"), share_class(CLASS_A, None)])
    found = securities(database)
    assert len(found) == 3
    created = {bound(database, NCEN, CLASS_B), bound(database, NCEN, CLASS_A)}
    assert None not in created and bound(database, OPENFIGI, ONE) not in created and len(created) == 2
