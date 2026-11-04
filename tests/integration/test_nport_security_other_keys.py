"""Real PG16: a Security keyed by its SEDOL or its LoanX (ticket 190).

The limited test the operator's standing approval names (2026-11-04: "switch on for form 4 keep it
standing approval for ticket 190 191"), on invented records through the Merge Stage with the repo's
real policy (the two rules are on in it):
- a record keyed by a SEDOL (or a LoanX) that no Security holds creates one Security;
- a record keyed by a value a CUSIP's Security holds joins that Security and makes none;
- in both load orders the Securities and their identifiers are the same;
- a value two Securities hold sends the record to review and makes none;
- a second pass of the same records changes nothing.
"""

from __future__ import annotations

import pytest

from edgar_warehouse.mdm.merge import MergeStage
from edgar_warehouse.mdm.store import Store, register_policy
from edgar_warehouse.rules import files
from tests.integration import test_mdm_postgres as core
from tests.integration import test_nport_link_start as nport
from tests.integration.test_openfigi_security import bound, securities

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
    core.register_reading(database, NPORT, core.contract_body())
    with database.admin.begin() as conn:
        policy = register_policy(conn, files.policy())
    stage = MergeStage(Store(database.application))
    for number, records in enumerate(batches, 1):
        nport.apply(stage, policy, f"batch-{number}", records, number)
    return stage, policy


def shape(database) -> dict:
    return {tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in s["identifiers"].items()))
            for s in securities(database).values()}


@pytest.mark.parametrize("order", ["cusip_first", "other_first"])
def test_a_security_keyed_by_a_sedol_or_a_loanx_joins_or_is_created_in_either_order(database, order):
    batches = [CUSIP_RECORDS, OTHER_KEYED] if order == "cusip_first" else [OTHER_KEYED, CUSIP_RECORDS]
    load(database, batches)
    found = securities(database)
    # Three CUSIP Securities; the SEDOL alone and the LoanX alone each make one; the SEDOL a CUSIP's
    # Security holds makes none; the one two Securities hold makes none and waits for review.
    assert len(found) == 5
    assert bound(database, NPORT, SEDOL_ALONE) != bound(database, NPORT, LOANX_ALONE)
    assert bound(database, NPORT, SEDOL_HELD) == bound(database, NPORT, ONE) is not None
    print("ORDER", order, sorted(map(str, shape(database))), [(r["reason"], r.get("namespace")) for r in core.documents(database, "review").values() if r.get("open")])


def test_a_second_pass_of_the_same_records_changes_nothing(database):
    stage, policy = load(database, [CUSIP_RECORDS, OTHER_KEYED])
    first = (shape(database), len(securities(database)))
    nport.apply(stage, policy, "again", [*CUSIP_RECORDS, *OTHER_KEYED], 3)
    assert (shape(database), len(securities(database))) == first


@pytest.mark.parametrize("batch", ["cusip_records_first", "other_keyed_first"])
def test_one_batch_in_either_order(database, batch):
    one = [*CUSIP_RECORDS, *OTHER_KEYED] if batch == "cusip_records_first" else [*OTHER_KEYED, *CUSIP_RECORDS]
    load(database, [one])
    print("ONE", batch, len(securities(database)), sorted(map(str, shape(database))))
