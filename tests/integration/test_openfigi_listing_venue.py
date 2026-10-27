"""A listing's venue: the MIC RDM's iso-10383-mic pairs with its OpenFIGI exchange
code (ticket 138, the Listing). Runs OpenFIGI's source extract over the invented
answers of test_openfigi_security."""

import json
from pathlib import Path

from edgar_warehouse.rules import files
from tests.integration.test_openfigi_security import EQUITY, prepared_records


def test_a_listing_venue_is_the_mic_its_exchange_code_pairs_with(tmp_path):
    """A listing's MIC is the one RDM's iso-10383-mic pairs with its exchange code
    (ticket 138, the Listing); a composite's code pairs with none."""
    records, _ = prepared_records(tmp_path, ("cusip",))
    (equity,) = (r for r in records if r["provenance"]["record_key"] == EQUITY)
    found = {row["key"]: row.get("mic") for row in equity["details"]["listings"]}
    assert found == {"BBGZ0000VS14": None, "BBGZ0000VN15": "XNYS", "BBGZ0000GR13": None, "BBGZ0000GY18": "XETR"}


def test_the_mic_table_in_the_reading_is_the_published_code_set():
    """The reading embeds RDM's iso-10383-mic version 1 crosswalk, each OpenFIGI exchange code to its MIC."""
    published = Path(files.ROOT / "reference" / "published" / "iso-10383-mic" / "1" / "canonical.jsonl")
    pairs = {walk[2]: row["code"] for row in map(json.loads, published.read_text().splitlines())
             for walk in row["crosswalk"] if walk[0] == "openfigi-exchange-codes"}
    embedded = files.source("openfigi")["read"]["references"]["mic"]
    assert {code: row["mic"] for code, row in embedded.items()} == pairs and len(pairs) == 246
