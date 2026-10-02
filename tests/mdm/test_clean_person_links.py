"""The Person link engine (mastering to-do 14; `docs/specs/person/consumer.md`,
"Relationships" and "Temporal behavior").

A Forms 3/4/5 filing states, per reporting owner, the capacities the owner
holds at the issuer on the filing's event date. Each filing is its own record
(ticket 02, D3) and adds a dated sighting to the link keyed by Person, Company
and capacity. The sightings fold into dated periods:
- the first sighting opens a period with an observed start;
- a later filing from the same issuer that drops the capacity ends it
  (observed end); a later sighting opens a new period;
- silence never ends it;
- a sighting after a stated end does not reopen it: a steward decides.
"""

from __future__ import annotations

from types import SimpleNamespace

from edgar_warehouse.mdm.clean.relationships import fold_sightings, project
from edgar_warehouse.mdm.clean.store import digest

D1, D2, D3, D4 = (f"2024-0{m}-15T00:00:00+00:00" for m in (1, 3, 6, 9))


def seen(on, held=True, basis="observed", title=None, n=1):
    return {"on": on, "held": held, "basis": basis, "title": title,
            "assertion_id": f"a{n}", "subject": f"filing-{n}"}


def test_the_first_sighting_opens_a_period_with_an_observed_start():
    periods, contradictions = fold_sightings([seen(D1), seen(D2, n=2)])
    assert periods == [{"valid_from": D1, "valid_from_basis": "observed", "valid_to": None,
                        "valid_to_basis": None, "last_observed": D2, "titles": []}]
    assert contradictions == []


def test_a_filing_that_drops_the_capacity_ends_the_period_and_a_later_one_reopens_it():
    periods, _ = fold_sightings([seen(D1), seen(D2, held=False, n=2), seen(D4, n=3)])
    assert [(p["valid_from"], p["valid_to"], p["valid_to_basis"]) for p in periods] == [
        (D1, D2, "observed"), (D4, None, None)]


def test_sightings_fold_by_event_date_not_by_arrival():
    assert fold_sightings([seen(D4, n=3), seen(D2, held=False, n=2), seen(D1)]) == fold_sightings(
        [seen(D1), seen(D2, held=False, n=2), seen(D4, n=3)])


def test_the_title_is_a_dated_detail_of_the_period():
    (period,), _ = fold_sightings([seen(D1, title="President and CEO"),
                                   seen(D2, title="President and CEO", n=2),
                                   seen(D3, title="Chief Executive Officer", n=3)])
    assert period["titles"] == [{"title": "President and CEO", "on": D1},
                                {"title": "Chief Executive Officer", "on": D3}]


def test_a_sighting_after_a_stated_end_goes_to_a_steward_and_does_not_reopen():
    periods, contradictions = fold_sightings(
        [seen(D1), seen(D2, held=False, basis="stated", n=2), seen(D3, n=3)])
    assert [(p["valid_to"], p["valid_to_basis"]) for p in periods] == [(D2, "stated")]
    assert contradictions == [{"stated_end": D2, "on": D3, "assertion_id": "a3",
                               "subject": "filing-3"}]


def test_a_sighting_on_the_day_of_a_stated_end_is_reporting_lag_not_a_contradiction():
    periods, contradictions = fold_sightings(
        [seen(D1), seen(D2, held=False, basis="stated", n=2), seen(D2, n=3)])
    assert [p["valid_to"] for p in periods] == [D2]
    assert contradictions == []


def test_a_stated_start_after_a_stated_end_opens_a_new_period():
    periods, contradictions = fold_sightings(
        [seen(D1), seen(D2, held=False, basis="stated", n=2), seen(D3, basis="stated", n=3)])
    assert [(p["valid_from"], p["valid_from_basis"]) for p in periods] == [
        (D1, "observed"), (D3, "stated")]
    assert contradictions == []


def test_a_drop_with_nothing_open_ends_nothing():
    assert fold_sightings([seen(D1, held=False)]) == ([], [])


# project(): the link through the engine, on synthetic records.

PERSON, ISSUER = "sec/owner/1", "sec/issuer/2"


def engine(*filings):
    state = SimpleNamespace(bindings={PERSON: "p", ISSUER: "c"}, canonical={"p": "p", "c": "c"})
    entities = {"p": {"kind": "person", "status": "accepted", "profiles": []},
                "c": {"kind": "company", "status": "accepted", "profiles": []}}
    claims = {f"filing-{n}": {"assertion_id": f"a{n}", "relationships": [
        {"source_subject": PERSON, "target_subject": ISSUER, **link} for link in links]}
        for n, links in enumerate(filings, 1)}
    return project(claims, state, entities, D4)


def form4(on, capacity, kind="EMPLOYED_BY", **more):
    return {"type": kind, "capacity": capacity, "on": on, **more}


def test_one_link_per_person_company_and_capacity():
    links, reviews = engine([form4(D1, "director"), form4(D1, "officer", title="CFO"),
                             form4(D1, "ten_percent_owner", kind="CONTROLS")],
                            [form4(D2, "director")])
    assert reviews == []
    assert sorted((e["type"], e["capacity"], len(e["evidence"])) for e in links) == [
        ("CONTROLS", "ten_percent_owner", 1), ("EMPLOYED_BY", "director", 2),
        ("EMPLOYED_BY", "officer", 1)]


def test_a_link_through_the_engine_takes_its_periods_from_its_sightings():
    links, _ = engine([form4(D1, "director")], [form4(D2, "director", held=False)],
                      [form4(D3, "director")])
    (link,) = links
    assert [(p["valid_from"], p["valid_to"], p["last_observed"]) for p in link["periods"]] == [
        (D1, D2, D1), (D3, None, D3)]


def test_a_capacity_the_type_does_not_have_goes_to_review():
    links, reviews = engine([form4(D1, "ten_percent_owner")], [form4(D1, "director", kind="CONTROLS")])
    assert links == []
    assert [r["reason"] for r in reviews] == ["unsupported_capacity", "unsupported_capacity"]


def test_a_contradicted_stated_end_names_the_link_and_both_ends_for_a_steward():
    links, reviews = engine([form4(D1, "officer")],
                            [form4(D2, "officer", held=False, basis="stated")],
                            [form4(D3, "officer")])
    (link,) = links
    assert reviews == [{"reason": "contradicts_stated_end", "relationship_id": link["relationship_id"],
                        "subject": "filing-3", "assertion_id": "a3", "stated_end": D2, "on": D3,
                        "entities": ["c", "p"]}]


def test_insider_of_is_no_longer_a_link_type():
    _, reviews = engine([form4(D1, "director", kind="INSIDER_OF")])
    assert [r["reason"] for r in reviews] == ["unsupported_relationship"]


# Review findings (three-axis review, 2026-10-02).

def test_a_stated_sighting_outranks_an_observed_one_on_the_same_day():
    periods, _ = fold_sightings([seen(D1), seen(D2, held=False, n=2),
                                 seen(D2, basis="stated", n=3)])
    assert [(p["valid_from"], p["valid_to"]) for p in periods] == [(D1, None)]


def test_a_stated_end_after_an_observed_close_replaces_it_and_still_holds():
    periods, contradictions = fold_sightings(
        [seen(D1), seen(D2, held=False, n=2), seen(D3, held=False, basis="stated", n=3),
         seen(D4, n=4)])
    assert [(p["valid_to"], p["valid_to_basis"]) for p in periods] == [(D3, "stated")]
    assert [c["on"] for c in contradictions] == [D4]


def test_held_and_dropped_on_one_day_is_no_period():
    assert fold_sightings([seen(D1), seen(D1, held=False, n=2)]) == ([], [])


def test_a_link_without_a_capacity_keeps_the_id_it_had():
    state = SimpleNamespace(bindings={"a": "x", "b": "y"}, canonical={"x": "x", "y": "y"})
    entities = {e: {"kind": "company", "status": "accepted", "profiles": []} for e in ("x", "y")}
    claims = {"a": {"assertion_id": "a1", "relationships": [
        {"type": "IS_DIRECTLY_CONSOLIDATED_BY", "target_subject": "b", "valid_from": D1,
         "scope": "GLEIF accounting consolidation"}]}}
    links, _ = project(claims, state, entities, D4)
    direct = [e for e in links if not e["derived"]]
    assert [e["relationship_id"] for e in direct] == [
        digest(["IS_DIRECTLY_CONSOLIDATED_BY", "x", "y", "GLEIF accounting consolidation"])]
    assert "capacity" not in direct[0]


def test_a_person_link_needs_a_dated_sighting_with_a_known_basis():
    links, reviews = engine([{"type": "EMPLOYED_BY", "capacity": "director", "valid_from": D1}],
                            [form4(D1, "officer", basis="guessed")])
    assert links == []
    assert [r["reason"] for r in reviews] == ["unknown_relationship_start", "unknown_date_basis"]


def test_a_link_contradicted_twice_has_one_review():
    _, reviews = engine([form4(D1, "officer")],
                        [form4(D2, "officer", held=False, basis="stated")],
                        [form4(D3, "officer")], [form4(D4, "officer")])
    assert [(r["reason"], r["on"]) for r in reviews] == [("contradicts_stated_end", D3)]
