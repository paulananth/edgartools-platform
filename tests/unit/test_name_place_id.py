"""The name-and-place id (operator, 2026-11-09: "Name plus place"), on invented names."""

import pytest

from edgar_warehouse.mdm.adapters import FORMATS, UnsupportedRecord

ID = FORMATS["name_place_id@1"]


def test_one_name_in_two_cities_is_two_ids_and_in_one_city_is_one():
    here = {"name": "Example Capital", "city": "Example City", "region": "NY", "country": "United States"}
    assert ID(here) == ID({**here, "name": "EXAMPLE  CAPITAL"})
    assert ID(here) != ID({**here, "city": "Other City"})
    assert ID(here) != ID({**here, "name": "Example Capital Two"})


def test_the_name_id_and_the_name_and_place_id_never_collide():
    assert ID({"name": "Example Capital", "city": "Example City"}) != FORMATS["name_id@1"]("Example Capital Example City")


@pytest.mark.parametrize("item", [{"name": "Example Capital"}, {"city": "Example City"}, {"name": " ,. ", "city": "X"}, "Example Capital"])
def test_a_name_or_a_place_with_no_token_is_refused(item):
    with pytest.raises(UnsupportedRecord):
        ID(item)
