"""The fold-sightings-into-periods family folds pasted sightings into periods."""
import json
import os
import subprocess
import sys
from pathlib import Path

from edgar_warehouse.rules.try_page import press

D1, D2, D3, D4 = (f"2024-0{month}-15T00:00:00+00:00" for month in (1, 3, 6, 9))


def seen(on, held=True, basis="observed", n=1, title=None):
    return {"on": on, "held": held, "basis": basis, "title": title,
            "assertion_id": f"a{n}", "subject": f"filing-{n}"}


def _try(*sightings, expected=None):
    return press("Try", "link_periods", rule=json.dumps({"sightings": list(sightings)}), inputs={},
                 expected=expected)


def _period(start, end=None, end_basis=None, last=None, start_basis="observed", titles=()):
    return {"valid_from": start, "valid_from_basis": start_basis, "valid_to": end,
            "valid_to_basis": end_basis, "last_observed": last, "titles": list(titles)}


def test_a_dated_sighting_becomes_the_period_the_relationship_held():
    tried = _try(seen(D1), expected={"periods": [_period(D1, last=D1)], "contradictions": []})
    assert tried["passed"] is True
    assert tried["actual"]["periods"] == [_period(D1, last=D1)]


def test_a_missing_later_file_does_not_invent_an_end():
    for sightings in ([seen(D1)], [seen(D1), seen(D3, n=2)]):
        (period,) = _try(*sightings)["actual"]["periods"]
        assert period["valid_to"] is None and period["valid_to_basis"] is None
    assert _try(seen(D1), seen(D3, n=2))["actual"]["periods"][0]["last_observed"] == D3


def test_a_later_filing_that_drops_the_capacity_is_what_ends_the_period():
    periods = _try(seen(D1), seen(D2, held=False, n=2), seen(D4, n=3))["actual"]["periods"]
    assert periods == [_period(D1, D2, "observed", D1), _period(D4, last=D4)]


def test_sightings_fold_by_event_date_not_by_the_order_pasted():
    forward = _try(seen(D1), seen(D2, held=False, n=2), seen(D4, n=3))
    backward = _try(seen(D4, n=3), seen(D2, held=False, n=2), seen(D1))
    assert forward["actual"] == backward["actual"]


def test_a_sighting_after_a_stated_end_goes_to_a_steward_and_does_not_reopen():
    actual = _try(seen(D1), seen(D2, held=False, basis="stated", n=2), seen(D3, n=3))["actual"]
    assert actual["periods"] == [_period(D1, D2, "stated", D1)]
    assert actual["contradictions"] == [
        {"stated_end": D2, "on": D3, "assertion_id": "a3", "subject": "filing-3"}]


def test_the_title_is_a_dated_detail_of_the_period():
    (period,) = _try(seen(D1, title="Example Director"), seen(D2, title="Example Director", n=2),
                     seen(D3, title="Example Chair", n=3))["actual"]["periods"]
    assert period["titles"] == [{"title": "Example Director", "on": D1},
                                {"title": "Example Chair", "on": D3}]


def test_a_bad_paste_is_a_refusal_not_a_traceback():
    unreadable_time = {**seen(D1), "on": "2024-01-15"}
    no_identity = {key: value for key, value in seen(D1).items() if key != "assertion_id"}
    for rule in [
        json.dumps({"sightings": [{**seen(D1), "held": 1}]}),
        "not json",
        "[1]",
        json.dumps({}),
        json.dumps({"sightings": "none"}),
        json.dumps({"sightings": [1]}),
        json.dumps({"sightings": [{**seen(D1), "basis": "guessed"}]}),
        json.dumps({"sightings": [{**seen(D1), "held": "yes"}]}),
        json.dumps({"sightings": [unreadable_time]}),
        json.dumps({"sightings": [no_identity]}),
    ]:
        refused = press("Try", "link_periods", rule=rule, inputs={})
        assert list(refused) == ["refused"] and refused["refused"], rule


def test_no_other_family_is_imported():
    code = ("import sys, edgar_warehouse.rules.bench_families.link_periods;"
            "print('edgar_warehouse.rules.bench_families.link_masters' in sys.modules)")
    root = str(Path(__file__).resolve().parents[2])
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([root, os.environ.get("PYTHONPATH", "")])}
    shown = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
    assert shown.stdout.strip() == "False"
