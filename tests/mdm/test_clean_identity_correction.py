"""Correcting a wrong link: revoking a bind in the journal (ticket 13)."""

from __future__ import annotations

import pytest

from edgar_warehouse.mdm.clean.evidence import decision
from edgar_warehouse.mdm.clean.identity import replay
from edgar_warehouse.mdm.clean.store import Conflict

AS_OF = "2026-09-30T00:00:00+00:00"
SEC, GLEIF = "sec.submissions.company.v1:0000824142", "gleif.level1.v1:549300ZHF0E5VM7PUD37"
AAON, OTHER = "00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"
IDENTITIES = [{"entity_id": e, "kind": "company", "published_at": "2026-01-01T00:00:00+00:00"}
              for e in (AAON, OTHER)]


def bind(subject, entity, at="2026-02-01T00:00:00+00:00", **rule):
    return decision("bind", actor="rule:sec-gleif-name-postal@2026-09-25.2", reason="name_match", at=at,
                    subject=subject, entity_id=entity, evidence=["a1"], **rule)


def revoke(target, at="2026-03-01T00:00:00+00:00", **changes):
    body = {"subject": target["subject"], "entity_id": target["entity_id"], **changes}
    return decision("revoke", actor="operator", reason="rule sec-gleif-name-postal@2026-09-25.2 corrected",
                    at=at, target=target["decision_id"], **body)


def test_a_revoked_bind_leaves_its_record_unbound():
    wrong = bind(GLEIF, AAON)
    state = replay(IDENTITIES, [bind(SEC, AAON), wrong, revoke(wrong)], AS_OF)
    assert state.bindings == {SEC: AAON}


def test_after_a_revocation_the_record_may_bind_to_another_company():
    wrong = bind(GLEIF, AAON)
    later = bind(GLEIF, OTHER, at="2026-04-01T00:00:00+00:00")
    state = replay(IDENTITIES, [wrong, revoke(wrong), later], AS_OF)
    assert state.bindings == {GLEIF: OTHER}


def test_a_new_bind_before_its_revocation_is_still_a_move():
    wrong = bind(GLEIF, AAON)
    early = bind(GLEIF, OTHER, at="2026-02-15T00:00:00+00:00")
    with pytest.raises(Conflict, match="correction"):
        replay(IDENTITIES, [wrong, early, revoke(wrong)], AS_OF)


def test_a_revocation_must_name_the_bind_it_revokes():
    wrong = bind(GLEIF, AAON)
    with pytest.raises(Conflict, match="names the bind"):
        replay(IDENTITIES, [wrong, revoke(wrong, entity_id=OTHER)], AS_OF)


def test_a_revocation_before_its_bind_is_refused():
    wrong = bind(GLEIF, AAON)
    with pytest.raises(Conflict, match="earlier decision"):
        replay(IDENTITIES, [wrong, revoke(wrong, at="2026-01-15T00:00:00+00:00")], AS_OF)


def test_a_revocation_is_never_revoked_a_new_bind_restores_a_link():
    wrong = bind(GLEIF, AAON)
    undo = revoke(wrong)
    restore = decision("revoke", actor="operator", reason="the link was right", at="2026-04-01T00:00:00+00:00",
                       target=undo["decision_id"])
    with pytest.raises(Conflict, match="Invalid reversal/revocation target"):
        replay(IDENTITIES, [wrong, undo, restore], AS_OF)


def test_a_bind_is_revoked_once_only():
    wrong = bind(GLEIF, AAON)
    again = revoke(wrong, at="2026-05-01T00:00:00+00:00")
    with pytest.raises(Conflict, match="already revoked"):
        replay(IDENTITIES, [wrong, revoke(wrong), again], AS_OF)


def quarantine(target, at="2026-03-15T00:00:00+00:00"):
    return decision("quarantine", actor="operator", reason="no rule can decide this link", at=at,
                    subject=target["subject"], entity_id=target["entity_id"], evidence=["a1"])


def test_a_quarantined_record_is_unbound_and_its_company_named():
    wrong = bind(GLEIF, AAON)
    state = replay(IDENTITIES, [bind(SEC, AAON), wrong, revoke(wrong), quarantine(wrong)], AS_OF)
    assert state.bindings == {SEC: AAON}
    assert state.quarantined == {GLEIF: AAON}


def test_a_record_still_bound_cannot_be_quarantined():
    wrong = bind(GLEIF, AAON)
    with pytest.raises(Conflict, match="Revoke the record's bind"):
        replay(IDENTITIES, [wrong, quarantine(wrong)], AS_OF)
    # Nor while bound, though the revocation comes later.
    with pytest.raises(Conflict, match="Revoke the record's bind"):
        replay(IDENTITIES, [wrong, quarantine(wrong, at="2026-02-15T00:00:00+00:00"), revoke(wrong)], AS_OF)


def test_a_quarantined_record_never_binds_until_lifted():
    wrong = bind(GLEIF, AAON)
    held = quarantine(wrong)
    during = bind(GLEIF, OTHER, at="2026-04-01T00:00:00+00:00")
    with pytest.raises(Conflict, match="left out of matching"):
        replay(IDENTITIES, [wrong, revoke(wrong), held, during], AS_OF)
    lift = decision("revoke", actor="operator", reason="rule corrected", at="2026-05-01T00:00:00+00:00",
                    target=held["decision_id"], subject=GLEIF)
    after = bind(GLEIF, OTHER, at="2026-06-01T00:00:00+00:00")
    state = replay(IDENTITIES, [wrong, revoke(wrong), held, lift, after], AS_OF)
    assert state.quarantined == {} and state.bindings == {GLEIF: OTHER}
