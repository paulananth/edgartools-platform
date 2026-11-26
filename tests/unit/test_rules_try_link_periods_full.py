"""The fold-sightings short words become the complete sightings the fold reads."""
import json
import shutil

from edgar_warehouse.mdm.relationships import fold_sightings
from edgar_warehouse.rules.bench_families import link_periods_full
from edgar_warehouse.rules.try_page import FAMILY_DIR, families, load_full

D1, D2, D3 = "2024-01-15T00:00:00+00:00", "2024-03-15T00:00:00+00:00", "2024-06-15T00:00:00+00:00"


def short(n, on, held=True, how="observed", **more):
    return {"seen on": on, "still held": held, "how known": how, "filing id": f"a{n}",
            "filing": f"filing-{n}", **more}


def full(n, on, held=True, basis="observed", **more):
    return {"on": on, "held": held, "basis": basis, "assertion_id": f"a{n}",
            "subject": f"filing-{n}", **more}


def explain(*sightings):
    return link_periods_full.explain(json.dumps({"sightings": list(sightings)}))


def test_the_shown_sighting_is_the_invented_sighting_and_folds_to_its_period():
    shown = explain(short(1, D1, title=None))
    assert shown["document"] == {"sightings": [{**full(1, D1), "title": None}]}
    assert shown["lines"] == [
        {"word": "seen on", "stored": "on"}, {"word": "still held", "stored": "held"},
        {"word": "how known", "stored": "basis"}, {"word": "filing id", "stored": "assertion_id"},
        {"word": "filing", "stored": "subject"}]
    periods, contradictions = fold_sightings(shown["document"]["sightings"])
    assert periods == [{"valid_from": D1, "valid_from_basis": "observed", "valid_to": None,
                        "valid_to_basis": None, "last_observed": D1, "titles": []}]
    assert contradictions == []


def test_no_end_is_invented_from_a_missing_later_file():
    for sightings in ([short(1, D1)], [short(1, D1), short(2, D3)]):
        shown = explain(*sightings)
        (period,), _ = fold_sightings(shown["document"]["sightings"])
        assert period["valid_to"] is None and period["valid_to_basis"] is None


def test_an_end_comes_from_a_sighting_that_drops_the_capacity():
    shown = explain(short(1, D1), short(2, D2, held=False))
    (period,), _ = fold_sightings(shown["document"]["sightings"])
    assert (period["valid_to"], period["valid_to_basis"]) == (D2, "observed")


def test_a_title_keeps_its_name_and_a_word_is_listed_once():
    shown = explain(short(1, D1, title="Example Director"), short(2, D2, title="Example Director"))
    assert shown["document"]["sightings"][0]["title"] == "Example Director"
    assert [line["word"] for line in shown["lines"]].count("seen on") == 1


def test_a_bare_stored_key_is_refused_with_the_word_to_type_and_the_words_accepted():
    for stored, typed in [("on", "seen on"), ("held", "still held"), ("basis", "how known"),
                          ("assertion_id", "filing id"), ("subject", "filing")]:
        sighting = {key: value for key, value in short(1, D1).items() if key != typed}
        sighting[stored] = "x"
        refused = explain(sighting)
        assert list(refused) == ["refused"]
        assert f"'{stored}' is a stored key. Type '{typed}' instead." in refused["refused"]
        assert "Words this file accepts:" in refused["refused"] and "last seen" in refused["refused"]


def test_an_end_cannot_be_typed_into_a_sighting():
    for key in ("ends", "valid_to", "end known by", "valid_to_basis"):
        refused = explain({**short(1, D1), key: D2})
        assert list(refused) == ["refused"]
        assert "An end is not typed" in refused["refused"] and "drops the capacity" in refused["refused"]


def test_a_period_word_is_not_a_sighting_word():
    for key in ("starts", "last seen", "valid_from", "last_observed"):
        refused = explain({**short(1, D1), key: D1})
        assert list(refused) == ["refused"] and "describes a period" in refused["refused"]


def test_a_sighting_missing_a_word_or_with_an_unknown_word_is_refused():
    missing = explain({key: value for key, value in short(1, D1).items() if key != "filing id"})
    assert "'filing id'" in missing["refused"] and list(missing) == ["refused"]
    unknown = explain({**short(1, D1), "no such word": 1})
    assert list(unknown) == ["refused"] and "'no such word' is not a word" in unknown["refused"]


def test_the_full_sightings_are_ones_the_fold_accepts():
    for rule in ["not json", "[1]", json.dumps({}), json.dumps({"sightings": [1]}),
                 json.dumps({"sightings": [short(1, D1, how="guessed")]}),
                 json.dumps({"sightings": [short(1, D1, held="yes")]}),
                 json.dumps({"sightings": [short(1, "2024-01-15")]})]:
        refused = link_periods_full.explain(rule)
        assert list(refused) == ["refused"] and refused["refused"], rule


def test_the_page_ignores_the_short_words_until_the_run_file_exists(tmp_path):
    shutil.copy(FAMILY_DIR / "link_periods_full.py", tmp_path)
    assert families(tmp_path) == []
    assert load_full("link_periods", tmp_path) is None
    (tmp_path / "link_periods.py").write_text("title = 'Example'\ninputs = []\n")
    assert families(tmp_path) == ["link_periods"]
    assert load_full("link_periods", tmp_path).words[0] == {"word": "seen on", "stored": "on"}
