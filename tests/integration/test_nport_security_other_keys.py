"""Real PG16: a Security keyed by its SEDOL or its LoanX (ticket 190).

The limited test the operator's standing approval names (2026-11-04: "switch on for form 4 keep it
standing approval for ticket 190 191"), on invented records through the Merge Stage with the repo's
real policy (the two rules are on in it):
- a record keyed by a SEDOL (or a LoanX) that no Security holds creates one Security;
- a record keyed by a value a CUSIP's Security holds joins that Security and makes none, when it
  is published in a batch after the CUSIP's (records of one batch never match each other);
- a value two Securities hold sends the record to review and makes none;
- a second pass of the same records changes nothing.
"""

from __future__ import annotations

from tests.integration import test_mdm_postgres as core
from tests.integration.test_openfigi_security import bound, securities
from tests.support import masters

NPORT = "sec.nport.security.v2"
ONE, TWO, THREE = "ZZ0000013", "ZZ0000021", "ZZ0000039"  # invented CUSIPs, check digits valid
SEDOL_HELD, SEDOL_ALONE, SEDOL_SHARED = "C000008", "D000007", "B000009"  # invented, check digits valid
LOANX_ALONE = "LX000002"


def record(key: str, **identifiers) -> dict:
    """The record's key class is a matching field, as record.yaml writes it."""
    key_class = "cusip" if "cusip" in identifiers else next(iter(identifiers))
    return core.source(key=key, source_code=NPORT, kind="security", fields={"name_of_issuer": "Example Corp."},
                       identifiers=identifiers, provenance={"matching": {"key_class": key_class}})


CUSIP_RECORDS = [record(ONE, cusip=ONE, sedol=[SEDOL_HELD]), record(TWO, cusip=TWO, sedol=[SEDOL_SHARED]),
                 record(THREE, cusip=THREE, sedol=[SEDOL_SHARED])]
OTHER_KEYED = [record(SEDOL_HELD, sedol=SEDOL_HELD), record(SEDOL_ALONE, sedol=SEDOL_ALONE),
               record(LOANX_ALONE, loanx=LOANX_ALONE), record(SEDOL_SHARED, sedol=SEDOL_SHARED)]


def load(database, batches):
    for records in batches:
        masters.seed(database.application, records)


def shape(database) -> dict:
    return {tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in s["identifiers"].items()))
            for s in securities(database).values()}


def test_the_keyed_records_of_a_second_batch_join_the_security_holding_their_value_or_create_one(database):
    load(database, [CUSIP_RECORDS, OTHER_KEYED])
    found = securities(database)
    # Three CUSIP Securities; the SEDOL alone and the LoanX alone each make one; the SEDOL a CUSIP's
    # Security holds makes none; the one two Securities hold makes none and waits for review.
    assert len(found) == 5
    assert bound(database, NPORT, SEDOL_ALONE) != bound(database, NPORT, LOANX_ALONE)
    assert bound(database, NPORT, SEDOL_HELD) == bound(database, NPORT, ONE) is not None
    assert bound(database, NPORT, SEDOL_SHARED) is None
    assert "ambiguous_identifier" in masters.reviews(database.application)


def test_in_one_batch_a_keyed_record_makes_its_own_security_which_is_why_there_is_a_second_batch(database):
    load(database, [[*CUSIP_RECORDS, *OTHER_KEYED]])
    assert len(securities(database)) == 7  # records of one batch never match each other


def test_a_second_pass_of_the_same_records_changes_nothing(database):
    load(database, [CUSIP_RECORDS, OTHER_KEYED])
    first = (shape(database), len(securities(database)))
    masters.seed(database.application, [*CUSIP_RECORDS, *OTHER_KEYED])
    assert (shape(database), len(securities(database))) == first


FIGI_HELD, FIGI_UNHELD = "BBGZ0000VS14", "BBGZ0000VS23"  # invented, check digits valid (ticket 139)


def test_a_figi_only_holding_finds_the_security_holding_its_figi_and_makes_nothing(database):
    """Ticket 139: find only. OpenFIGI's Security holds the FIGI; N-PORT's record binds to it; an unheld FIGI waits."""
    openfigi = core.source(key=ONE, source_code="openfigi.security.v3", kind="security", fields={"name_of_issuer": "Example Corp."},
                           identifiers={"cusip": ONE, "figi": [FIGI_HELD]})
    keyed = [core.source(key=f, source_code=NPORT, kind="security", fields={}, cross_references={"figi": f},
                         provenance={"matching": {"key_class": "figi"}}) for f in (FIGI_HELD, FIGI_UNHELD)]
    load(database, [[openfigi], keyed])
    found = securities(database)
    assert len(found) == 1  # nothing was created
    assert bound(database, NPORT, FIGI_HELD) == bound(database, "openfigi.security.v3", ONE) is not None
    assert bound(database, NPORT, FIGI_UNHELD) is None  # waits: no Security holds it
    assert found[bound(database, NPORT, FIGI_HELD)]["identifiers"]["figi"] == [FIGI_HELD]  # never given to it by N-PORT
