"""Real PG16: a filed CUSIP and ISIN on two Securities bind by the CUSIP (ticket 138 part A2b).

The operator, 2026-10-25: "bind by CUSIP if matches if not then try isin"; "cusip is a
seperate than isin it can never be merges". An N-PORT holding filing a CUSIP one Security
holds and an ISIN another holds binds to the CUSIP's; the ISIN stays the other's: it is
withheld from the bound Security's identifiers and from every holder lookup, so a later
holding filing only that ISIN finds its own Security. Invented values only.
"""

from __future__ import annotations

from edgar_warehouse.mdm.clean.record_reads import for_connection
from edgar_warehouse.mdm.clean import binding
from edgar_warehouse.mdm.clean.evidence import decision
from tests.integration import test_clean_mdm_postgres as core
from tests.integration import test_nport_link_start as nport
from tests.integration import test_openfigi_security as figi

NPORT = figi.NPORT_ISIN  # sec.nport.security.v2, the N-PORT Security contract
CUSIP, ISIN = figi.EQUITY, figi.ISIN


def holding(key, revision=1, **identifiers):
    return core.source(key=key, source_code=NPORT, kind="security", revision=revision,
                       fields={"name_of_issuer": "EXAMPLE CORP"}, identifiers=identifiers)


def reviews(database):
    return [v for v in core.documents(database, "review").values() if v.get("open")]


def test_a_filed_cusip_and_isin_on_two_securities_bind_by_the_cusip(database):
    stage, policy = figi.load(database, [("nport-1", [holding("by-cusip", cusip=CUSIP), holding("by-isin", isin=ISIN)])])
    by_cusip, by_isin = figi.bound(database, NPORT, "by-cusip"), figi.bound(database, NPORT, "by-isin")
    assert None not in (by_cusip, by_isin) and by_cusip != by_isin
    both = holding("both", cusip=CUSIP, isin=ISIN)
    nport.apply(stage, policy, "nport-2", [both], 2)
    assert figi.bound(database, NPORT, "both") == by_cusip and not reviews(database)
    securities = figi.securities(database)
    # The ISIN stays the other Security's: never on two.
    assert securities[by_cusip]["identifiers"] == {"cusip": [CUSIP]}
    assert securities[by_isin]["identifiers"] == {"isin": [ISIN]}
    # A holding filing only the ISIN finds its own Security, not an ambiguous pair.
    nport.apply(stage, policy, "nport-3", [holding("isin-later", isin=ISIN)], 3)
    assert figi.bound(database, NPORT, "isin-later") == by_isin and not reviews(database)
    # The same holding again gives its Security nothing it withheld.
    nport.apply(stage, policy, "nport-4", [holding("both", revision=2, cusip=CUSIP, isin=ISIN)], 4)
    assert figi.securities(database)[by_cusip]["identifiers"] == {"cusip": [CUSIP]} and not reviews(database)
    assert len(figi.securities(database)) == 2

    # A steward revokes that bind and binds it again, withholding nothing: the ISIN
    # is then that Security's too, so the next holding filing only it is ambiguous.
    from edgar_warehouse.mdm.clean.record_reads import for_connection
    with database.application.connect() as conn:
        (bind,) = [d for d in for_connection(conn).related_decisions({both["subject"]})
                   if d["operation"] == "bind" and d["subject"] == both["subject"]]
    assert bind["withheld"] == [{"namespace": "isin", "raw": ISIN}]
    later = "2026-10-17T00:00:00+00:00"  # after the rule's bind
    revoke = decision("revoke", actor="steward", reason="fixture", at="2026-10-16T12:00:00Z",
                      target=bind["decision_id"], subject=both["subject"], entity_id=by_cusip)
    rebind = decision("bind", actor="steward", reason="fixture", at="2026-10-16T12:00:01Z",
                      subject=both["subject"], entity_id=by_cusip, evidence=[both["assertion_id"]])
    stage.apply(batch_id="steward", run_id=str(core.uuid4()), policy_digest=policy, consumer="check",
                expected_checkpoint=4, checkpoint=5, as_of=later, decisions=[revoke, rebind])
    assert figi.securities(database)[by_cusip]["identifiers"] == {"cusip": [CUSIP], "isin": [ISIN]}
    stage.apply(batch_id="nport-6", run_id=str(core.uuid4()), policy_digest=policy, consumer="check",
                expected_checkpoint=5, checkpoint=6, as_of=later, assertions=[holding("isin-after", isin=ISIN)])
    assert figi.bound(database, NPORT, "isin-after") is None
    assert "ambiguous_identifier" in [r["reason"] for r in reviews(database)]


def test_a_bind_withholding_a_value_no_other_security_holds_is_stale(database):
    """Re-checked under the lock: a value is withheld only while another Security holds
    it; if that Security lost it since the proposal, the proposal is assessed again."""
    stage, policy = figi.load(database, [("nport-1", [holding("by-cusip", cusip=CUSIP), holding("by-isin", isin=ISIN)])])
    both = holding("both", cusip=CUSIP, isin=ISIN)
    proposed = stage.propose(policy_digest=policy, assertions=[both], decisions=[], identities=[],
                             as_of="2026-10-16T00:00:00+00:00")
    body = figi.policy_body()
    with database.application.connect() as conn:
        assert not binding.proposal_is_stale(for_connection(conn), body, proposed)
        (bind,) = proposed["decisions"]
        bind["withheld"] = [{"namespace": "isin", "raw": "ZZ0000000024"}]  # no Security holds it
        assert binding.proposal_is_stale(for_connection(conn), body, proposed)
