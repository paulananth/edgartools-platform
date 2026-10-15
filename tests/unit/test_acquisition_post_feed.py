"""Ticket 92: what a POST feed may declare, checked when the Rules load (no request)."""
import pytest

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.rules.acquisition_authority import acquisition


def feed(**changes):
    value = {"family": "mapping", "datasets": [], "scope": ["batch"], "required_producers": ["mapping"],
             "url_prefixes": ["https://provider.example/v3/"],
             "capabilities": {"capture": "provider.capture", "fetch": "https.post"},
             "completeness": {"format": "json_array", "required": [], "allow_empty": False, "max_bytes": 1024},
             "secret_header": {"name": "X-Provider-Key", "environment": "PROVIDER_API_KEY"}}
    value.update(changes)
    return {"acquisition": {"version": 1, "feeds": {"mapping": value}}}


def test_a_post_feed_with_one_key_header_and_an_array_answer_loads():
    assert acquisition(feed())["mapping"]["capabilities"]["fetch"] == "https.post"


@pytest.mark.parametrize("change", [
    {"secret_header": {"name": "User-Agent", "environment": "PROVIDER_API_KEY"}},   # our own header
    {"secret_header": {"name": "content-type", "environment": "PROVIDER_API_KEY"}},
    {"secret_header": {"name": "X Key", "environment": "PROVIDER_API_KEY"}},
    {"secret_header": {"name": "X-Key", "environment": "lower_case"}},
    {"secret_header": {"name": "X-Key"}},
    {"capabilities": {"capture": "provider.capture", "fetch": "http.conditional"}},  # a key on a GET feed
    {"completeness": {"format": "json_array", "required": ["x"], "allow_empty": False, "max_bytes": 1024}},
])
def test_a_post_feed_is_refused_when_it_could_misuse_a_key_or_an_array(change):
    with pytest.raises(Blocked):
        acquisition(feed(**change))


def test_an_array_answer_is_for_a_post_feed_only():
    body = feed(capabilities={"capture": "provider.capture", "fetch": "http.conditional"})
    del body["acquisition"]["feeds"]["mapping"]["secret_header"]
    with pytest.raises(Blocked):
        acquisition(body)
