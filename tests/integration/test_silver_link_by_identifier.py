"""Real PG16: a silver row finds its master by an identifier the master holds.

Operator, 2026-11-17, "Link by identifier (Recommended)": a registration or prospectus row states
the ticker its shares list under; its Security link fills only when exactly one Security holds
that ticker, so a reused ticker, or one no Security holds yet, leaves the link empty.
Invented values only.
"""

from __future__ import annotations

from edgar_warehouse.silver_writer.writer import MdmIds
from tests.integration.test_form4_security_ticker import ONE, OPENFIGI, THREE, TWO, openfigi, policy_body
from tests.integration.test_openfigi_security import bound
from tests.support import masters

BY_TICKER = {"columns": ["ticker"], "kind": "security", "identifier": "ticker", "to_part": "listed",
             "source_key": "ticker", "mdm_id_column": "listed_security_mdm_id"}


def test_a_ticker_one_security_holds_finds_it_and_a_reused_or_unheld_ticker_finds_none(database):
    masters.seed(database.application, [openfigi(ONE, "EXA"), openfigi(TWO, "EXB"), openfigi(THREE, "EXB")],
                 policy_body())
    found = MdmIds(database.application)(BY_TICKER, {"EXA", "EXB", "EXC"})
    assert found == {"EXA": bound(database, OPENFIGI, ONE)}


def test_a_ticker_held_by_another_kind_finds_no_security(database):
    masters.seed(database.application, [openfigi(ONE, "EXA")], policy_body())
    assert MdmIds(database.application)({**BY_TICKER, "kind": "company"}, {"EXA"}) == {}
