"""Real PG16: an issuer's filed trading symbol finds its Security (ticket 24).

Operator, 2026-11-04, "Yes, Form 4 route only": `ticker` is an identifier of Security that
OpenFIGI issues; a Form 3, 4 or 5 files the issuer's symbol as a cross-reference, lookup only.
The Merge Stage rule `form4-security-ticker`:
- binds the filing's Security record to the one Security that holds the ticker, and gives that
  Security nothing (the symbol is never its identifier);
- waits when no Security holds the ticker, and creates no Security;
- sends the record to review when several Securities hold the ticker (a reused ticker).
The rule is switched on in a copy of the policy only, the ticker contract given a fixture
verification there. Invented values only.
"""

from __future__ import annotations

from edgar_warehouse.rules import files
from tests.integration import test_mdm_postgres as core
from tests.integration.test_openfigi_security import bound, securities
from tests.mdm import policy_layers
from tests.support import masters

OPENFIGI = "openfigi.security.v3"
FORM4 = "sec.ownership.security.v1"
ONE, TWO, THREE = "ZZ0000013", "ZZ0000021", "ZZ0000039"  # invented CUSIPs, check digits valid


def policy_body() -> dict:
    body = policy_layers.with_rules_on(
        files.policy(), "security", "openfigi-security-cusip", "form4-security-ticker")
    body["kinds"]["security"]["identifiers"]["ticker"]["verification"] = {
        "corpus_sha256": "f" * 64, "approved_by": "fixture", "approved_at": "2026-11-04T00:00:00Z",
        "reason": "fixture verification: shape only, not a measurement"}
    return body


def openfigi(cusip: str, ticker: str) -> dict:
    return core.source(key=cusip, source_code=OPENFIGI, kind="security",
                       fields={"name_of_issuer": "Example Corp."},
                       identifiers={"cusip": cusip, "ticker": ticker})


def form4(symbol: str, title: str = "Class A Common Stock") -> dict:
    return core.source(key=f'["1234567","{symbol}","{title}"]', source_code=FORM4, kind="security",
                       fields={},
                       cross_references={"ticker": symbol})


def load(database, openfigi_records: list[dict], form4_records: list[dict]):
    policy = policy_body()
    masters.seed(database.application, openfigi_records, policy)
    masters.seed(database.application, form4_records, policy)


def test_a_filed_symbol_finds_the_one_security_holding_its_ticker_and_makes_nothing(database):
    load(database, [openfigi(ONE, "EXA"), openfigi(TWO, "EXB")], [form4("EXA")])
    found = securities(database)
    assert len(found) == 2
    key = '["1234567","EXA","Class A Common Stock"]'
    assert bound(database, FORM4, key) == bound(database, OPENFIGI, ONE) is not None
    # The symbol is the filer's copy: the Security keeps its own identifiers.
    assert found[bound(database, FORM4, key)]["identifiers"] == {"cusip": [ONE], "ticker": ["EXA"]}


def test_a_symbol_no_security_holds_waits_and_creates_no_security(database):
    load(database, [openfigi(ONE, "EXA")], [form4("EXZ")])
    assert len(securities(database)) == 1
    assert bound(database, FORM4, '["1234567","EXZ","Class A Common Stock"]') is None


def test_a_reused_ticker_held_by_two_securities_goes_to_review(database):
    load(database, [openfigi(ONE, "EXA"), openfigi(TWO, "EXA")], [form4("EXA")])
    assert len(securities(database)) == 2
    assert bound(database, FORM4, '["1234567","EXA","Class A Common Stock"]') is None
    # The symbol reaches two Securities: it waits for review.
    assert "conflicting_identifiers" in masters.reviews(database.application)

