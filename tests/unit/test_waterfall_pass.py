"""The waterfall pass: SEC filers read from the stored company records, GLEIF entities from the whole
publication, paired one to one pass by pass. The pairs replace the answer a separate file put on each
SEC record (ticket 202, step A). Invented names only."""
from collections import Counter

import pytest

from edgar_warehouse.mdm import cascade, waterfall
from edgar_warehouse.mdm.store import Conflict

ADDRESS = {"street": "1 Example Way", "city": "Exampleton", "postcode": "12345", "country": "US"}
PASSES = [{"pass": "name and street", "compare": ["street", "city", "postcode"], "rule_id": "r1"},
          {"pass": "name only", "compare": None, "rule_id": "r2"}]


def sec_record(cik, name, address=ADDRESS):
    return cascade.record(cik, {"name": name, "state_of_incorporation": "DE"},
                          {"address": address, "business_country": "US"}, None, {"cik": cik})


def entity(lei, *names, address=ADDRESS, eligible=True):
    keys = frozenset(cascade.legal_form_key(n) for n in names)
    return cascade.Entity(lei, keys, cascade.place(address), "US-DE", eligible, "2026-01-01",
                          legal=cascade.legal_form_key(names[0]))


def test_filers_come_from_the_stored_company_records():
    [filer] = waterfall.filers_from_records([sec_record("0000000001", "Alpha Widgets Inc")])

    assert filer.cik == "0000000001"
    assert filer.key == cascade.sec_legal_form_key("Alpha Widgets Inc")
    assert filer.place.key == ("1 Example Way", "12345", "US")


def test_a_name_held_by_one_filer_and_one_entity_binds_in_the_first_pass_that_agrees():
    filers = waterfall.filers_from_records([sec_record("0000000001", "Alpha Widgets Inc")])

    pairs = waterfall.assignments(filers, [entity("LEI-A", "Alpha Widgets Inc")], PASSES, gleif_addresses=Counter(),
                                  over_shared=10)

    assert pairs["0000000001"]["lei"] == "LEI-A" and pairs["0000000001"]["pass"] == "name and street"


def test_a_name_two_filers_share_binds_neither():
    filers = waterfall.filers_from_records([sec_record("0000000001", "Alpha Widgets Inc"),
                                            sec_record("0000000002", "Alpha Widgets Inc")])

    pairs = waterfall.assignments(filers, [entity("LEI-A", "Alpha Widgets Inc")], PASSES, gleif_addresses=Counter(),
                                  over_shared=10)

    assert pairs == {}


def test_the_gleif_address_counts_join_the_filers_when_an_address_is_over_shared():
    # An address more than `over_shared` entities use is compared by its country only, so the street pass
    # no longer tells two places apart: the shared GLEIF count is part of the answer.
    other = {**ADDRESS, "street": "9 Elsewhere Road"}
    filers = waterfall.filers_from_records([sec_record("0000000001", "Alpha Widgets Inc", other)])
    gleif = Counter({("1 Example Way", "12345", "US"): 50})

    pairs = waterfall.assignments(filers, [entity("LEI-A", "Alpha Widgets Inc")], PASSES, gleif_addresses=gleif,
                                  over_shared=3)

    assert pairs["0000000001"]["pass"] == "name only"


def test_the_pass_pairs_each_filer_with_its_entity_and_a_shared_name_binds_neither_filer():
    filers = waterfall.filers_from_records([
        sec_record("0000000001", "Alpha Widgets Inc"),
        sec_record("0000000002", "Beta Gadgets Inc", {**ADDRESS, "street": "2 Other Street"}),
        sec_record("0000000003", "Gamma Tools Inc"),
        sec_record("0000000004", "Gamma Tools Inc")])
    entities = [entity("LEI-A", "Alpha Widgets Inc"), entity("LEI-B", "Beta Gadgets Inc"),
                entity("LEI-G", "Gamma Tools Inc")]
    gleif = Counter({("1 Example Way", "12345", "US"): 4})

    new = waterfall.assignments(filers, entities, PASSES, gleif_addresses=gleif, over_shared=10)

    assert {cik: pair["lei"] for cik, pair in new.items()} == {"0000000001": "LEI-A", "0000000002": "LEI-B"}


class FakeStore:
    def __init__(self, rows):
        self.rows_given, self.asked = rows, []

    def rows(self, sql, values=()):
        self.asked.append((sql, list(values)))
        return self.rows_given


def test_the_stored_company_records_become_filers_whether_the_body_is_text_or_already_parsed():
    import json
    store = FakeStore([(json.dumps(sec_record("0000000001", "Alpha Widgets Inc")),),
                       (sec_record("0000000002", "Beta Gadgets Inc"),)])

    filers = waterfall.stored_filers(store, "sec.company.v1")

    assert [f.cik for f in filers] == ["0000000001", "0000000002"]
    assert store.asked == [("select body from mastering_record where source_code=%s", ["sec.company.v1"])]


def gleif_tables(*legal_names, address=ADDRESS, copies=1):
    """The whole-publication reading's tables for invented entities (one legal name each)."""
    rows = []
    for number, name in enumerate(legal_names):
        key = cascade.legal_form_key(name)
        rows.append({"key": key, "lei": f"LEI-{number}", "updated": "2026-01-01", "source_index": number,
                     "cascade": {"legal": key, "lei": f"LEI-{number}", "place": address, "jurisdiction": "US-DE",
                                 "eligible": True, "last_update": "2026-01-01"}})
    return {"a_legal": rows, "b_other": [], "c_transliterated": [],
            "d_addresses": [{"street": address["street"], "postcode": address["postcode"],
                             "country": address["country"]}] * copies}


def test_folding_keeps_the_entities_that_hold_a_wanted_name_and_counts_every_address():
    wanted = {cascade.legal_form_key("Alpha Widgets Inc")}
    counts = Counter()

    legal, other, entities = waterfall.fold_reading(
        [gleif_tables("Alpha Widgets Inc", "Unrelated Holdings Inc", copies=2)], cascade_wanted=wanted,
        address_counts=counts)

    assert [e.lei for e in entities] == ["LEI-0"]  # the entity that holds no wanted name is not a candidate
    assert legal == {cascade.legal_form_key("Alpha Widgets Inc"): {"LEI-0": "2026-01-01"},
                     cascade.legal_form_key("Unrelated Holdings Inc"): {"LEI-1": "2026-01-01"}}
    assert counts == Counter({("1 Example Way", "12345", "US"): 2})


def test_the_pass_over_a_publication_pairs_the_stored_filers_with_its_entities():
    filers = waterfall.filers_from_records([sec_record("0000000001", "Alpha Widgets Inc"),
                                            sec_record("0000000002", "Beta Gadgets Inc")])

    pairs = waterfall.over_publication(filers, [gleif_tables("Alpha Widgets Inc", "Beta Gadgets Inc")], PASSES,
                                       over_shared=10)

    assert {cik: pair["lei"] for cik, pair in pairs.items()} == {"0000000001": "LEI-0", "0000000002": "LEI-1"}


class FakeOpened:
    """Stands for `source_readings.OpenedExtract`: one archive, a `wanted` lookup and the tables of one chunk."""

    def __init__(self, tables, wanted, records=1, contract=None):
        self.contract, self.artifacts = contract, [{"record_count": records, "input": {"sha256": "a" * 64}}]
        self._tables, self._wanted = tables, wanted

    def lookup_sets(self, _):
        return {"wanted": self._wanted}

    def chunks(self):
        yield 0, 0, {"tables": self._tables}, 0


METADATA = {"file_content": "GLEIF_FULL_PUBLISHED", "record_count": 1, "content_date": "2026-01-01"}


def serve(monkeypatch, wanted, records=1):
    from edgar_warehouse.rules import files as rules_files
    tables = gleif_tables("Alpha Widgets Inc")
    monkeypatch.setattr(waterfall.source_readings, "OpenedExtract",
                        lambda *a, **k: FakeOpened(tables, wanted, records, rules_files.load(waterfall.GLEIF_READING)))
    monkeypatch.setattr(waterfall, "validate_metadata", lambda kind, metadata: None)


def test_pairs_reads_the_publication_for_the_names_of_the_stored_filers(monkeypatch):
    filers = waterfall.filers_from_records([sec_record("0000000001", "Alpha Widgets Inc")])
    serve(monkeypatch, waterfall.wanted_names(filers))

    publication, found = waterfall.pairs(filers, {}, None, METADATA, PASSES, over_shared=10)

    assert publication["record_count"] == 1 and publication["archive_sha256"] == "a" * 64
    assert {cik: pair["lei"] for cik, pair in found.items()} == {"0000000001": "LEI-0"}


def test_a_reading_that_projected_other_names_is_refused(monkeypatch):
    filers = waterfall.filers_from_records([sec_record("0000000001", "Alpha Widgets Inc")])
    serve(monkeypatch, {"someone else"})

    with pytest.raises(Conflict, match="other names"):
        waterfall.pairs(filers, {}, None, METADATA, PASSES, over_shared=10)


def test_a_delta_publication_is_refused(monkeypatch):
    filers = waterfall.filers_from_records([sec_record("0000000001", "Alpha Widgets Inc")])
    serve(monkeypatch, waterfall.wanted_names(filers))

    with pytest.raises(Conflict, match="never a delta"):
        waterfall.pairs(filers, {}, None, {**METADATA, "file_content": "GLEIF_DELTA"}, PASSES, over_shared=10)
