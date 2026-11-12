"""A run holds its source's frozen rules: the name and the digest of the body. A run with a feed
also holds that feed's declared configuration."""
import pytest

from edgar_warehouse.bookkeeping.clean.engine import _authority
from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.rules import frozen
from edgar_warehouse.rules.acquisition_authority import registration_authority

FEED = {"family": "fixture", "datasets": ["fixture.v1"], "scope": ["fixture"],
        "capabilities": {"capture": "provider.capture", "fetch": "http.conditional"},
        "completeness": {"format": "json", "required": [], "allow_empty": True, "max_bytes": 1024},
        "required_producers": ["capture"], "url_prefixes": ["https://fixture.invalid/"]}
CONTRACT = {"family": "fixture", "adapter": {"kind": "company"}}


def export(**changes):
    body = {"source": "fixture", "acquisition": {"version": 1, "feeds": {"fixture": FEED}},
            "dataset_contracts": {"fixture.v1": {"contract": CONTRACT}}, **changes}
    return frozen.of("source", "fixture", {k: v for k, v in body.items() if v is not None})


def test_a_run_over_captured_data_holds_the_name_and_digest():
    assert _authority(export(), {"source": "fixture"}) == {
        "name": "fixture", "version": export()["version"], "digest": export()["digest"]}


def test_a_run_with_a_feed_holds_that_feeds_configuration():
    assert _authority(export(), {"source": "fixture", "feed": "fixture"})["configuration"] == FEED
    with pytest.raises(Blocked, match="absent from the source's acquisition section"):
        _authority(export(), {"source": "fixture", "feed": "other"})


def test_rules_whose_digest_is_not_their_bodys_are_refused():
    with pytest.raises(Blocked, match="frozen rules"):
        _authority({**export(), "digest": "0" * 64}, {"source": "fixture"})


def test_a_dataset_registers_under_its_sources_frozen_rules():
    assert registration_authority(export(), "fixture.v1", CONTRACT)["rules"]["name"] == "fixture"


def test_a_source_with_no_feed_of_its_own_registers_its_datasets():
    bare = export(acquisition=None, bronze={"family": "fixture"})
    assert registration_authority(bare, "fixture.v1", CONTRACT)["source_family"] == "fixture"


def test_a_source_whose_feeds_miss_a_dataset_is_refused():
    with pytest.raises(Blocked, match="exactly one feed"):
        registration_authority(export(), "other.v1", CONTRACT)


def test_a_source_with_no_feed_names_the_family_it_reads():
    bare = export(acquisition=None, bronze={"family": "other"})
    with pytest.raises(Blocked, match="names the family its source reads"):
        registration_authority(bare, "fixture.v1", CONTRACT)
