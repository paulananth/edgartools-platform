"""All member templates: explicit scope, source ordinals and XML metadata."""
import io
import json
import zipfile
from xml.etree import ElementTree as ET

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceRejected
from edgar_warehouse.workers import source_read
from tests.engine.test_source_stream_worker import task

LEI_A = "5493001KJTIIGC8Y1R12"
LEI_B = "5493001Z012YSB2A0K51"
DATE = "2026-09-11T16:00:00+00:00"
DELTA = "2026-09-10T16:00:00+00:00"
MEMBERS = ["level1", "relationships", "reporting-exceptions"]


def configured(member, format, *, delta=False):
    rules = files.load(files.ROOT / "sources" / "gleif" / f"{member}-{format}.yaml")
    rules["read"]["references"]["approved_scope"] = {LEI_A: {"selected": True}, LEI_B: {"selected": True}}
    if format == "xml":
        refs = rules["read"]["stream"]["header_read"]["references"]
        refs["content_dates"] = {DATE: {"valid": True}}
        refs["record_counts"] = {"3": {"valid": True}}
        refs["file_content"] = {"GLEIF_DELTA_PUBLISHED" if delta else "GLEIF_FULL_PUBLISHED":
                                {"valid": True, "requires_delta": delta}}
        refs["delta_starts"] = {DELTA: {"valid": True}} if delta else {}
    return rules


def records(member):
    if member == "relationships":
        return [{"RelationshipRecord": {"Relationship": {"StartNode": {"NodeID": {"$": a}},
                    "EndNode": {"NodeID": {"$": b}}}}} for a, b in [(LEI_A, "outside"), (LEI_A, LEI_B), ("outside", LEI_B)]]
    return [{"LEI": {"$": lei}, "Evidence": {"$": "keep"}} for lei in ["outside", LEI_A, "outside"]]


def archive(rules, member, format, *, delta=False, header_changes=None):
    rows = records(member)
    spec = rules["read"]["stream"]
    if format == "json":
        wrapper = {"level1": "records", "relationships": "relations", "reporting-exceptions": "exceptions"}[member]
        body = json.dumps({wrapper: rows}).encode()
    else:
        envelope = spec["xml"]
        namespace = envelope["namespace"]
        def element(parent, name): return ET.SubElement(parent, f"{{{namespace}}}{name}")
        root = ET.Element(f"{{{namespace}}}{envelope['root']}")
        header = element(root, envelope["header"])
        metadata = {"ContentDate": DATE, "FileContent": "GLEIF_DELTA_PUBLISHED" if delta else "GLEIF_FULL_PUBLISHED",
                    "RecordCount": "3", "DeltaStart": DELTA if delta else None}
        metadata.update(header_changes or {})
        for name, value in metadata.items():
            if value is not None: element(header, name).text = value
        container = element(root, envelope["container"])
        def fields(parent, row):
            for key, value in row.items():
                if key == "$": parent.text = value
                else: fields(element(parent, key), value)
        for row in rows:
            fields(element(container, envelope["record"]), row["RelationshipRecord"] if member == "relationships" else row)
        body = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr("captured." + format, body)
    return output.getvalue()


def bound_task(tmp_path, store, body, rules, count=3):
    envelope = task(tmp_path, store, [body], rules)
    manifest = store.json(envelope["input"])
    ref = manifest["artifacts"][0]
    context = store.put(tmp_path.as_uri(), {"version": 1, "input": ref, "values": {"publication_count": count}})
    envelope["input"] = store.put(tmp_path.as_uri(), {**manifest, "version": 2, "artifacts": [{"input": ref, "context": context}]})
    return envelope


@pytest.mark.parametrize("member", MEMBERS)
@pytest.mark.parametrize("format", ["json", "xml"])
def test_all_members_preserve_selected_raw_record_and_original_source_position(tmp_path, member, format):
    store, rules = Artifacts(), configured(member, format)
    envelope = bound_task(tmp_path, store, archive(rules, member, format), rules)
    receipt = source_read.execute(envelope, store)
    assert source_read.execute(envelope, store) == receipt
    artifact = store.json(receipt)["artifacts"][0]
    assert artifact["record_count"] == 3
    table = member.replace("-", "_")
    rows = [row for part in artifact["partitions"] for row in store.json(part["receipt"])["tables"][table]]
    assert rows == [{"record": records(member)[1], "source_index": 2}]
    assert source_read.verify({**envelope, "candidate": receipt}, store) == ({"source.output": True}, [])


@pytest.mark.parametrize("member", MEMBERS)
def test_xml_delta_header_matches_pinned_predecessor(tmp_path, member):
    store, rules = Artifacts(), configured(member, "xml", delta=True)
    envelope = bound_task(tmp_path, store, archive(rules, member, "xml", delta=True), rules)
    assert store.json(source_read.execute(envelope, store))["artifacts"][0]["record_count"] == 3


@pytest.mark.parametrize("member", MEMBERS)
@pytest.mark.parametrize("predecessor", [None, "2026-09-10T15:59:00Z"])
def test_xml_delta_requires_the_pinned_predecessor_time(tmp_path, member, predecessor):
    store, rules = Artifacts(), configured(member, "xml", delta=True)
    envelope = bound_task(tmp_path, store, archive(rules, member, "xml", delta=True,
        header_changes={"DeltaStart": predecessor}), rules)
    with pytest.raises(SourceRejected): source_read.execute(envelope, store)
    assert not (tmp_path / "reading.json.parts").exists()


def test_xml_content_timestamp_compares_instants_not_lexical_spelling(tmp_path):
    store, rules = Artifacts(), configured("level1", "xml")
    envelope = bound_task(tmp_path, store, archive(rules, "level1", "xml",
        header_changes={"ContentDate": "2026-09-11T18:00:00.000+02:00"}), rules)
    assert store.json(source_read.execute(envelope, store))["artifacts"][0]["record_count"] == 3


@pytest.mark.parametrize("member", MEMBERS)
@pytest.mark.parametrize("changes", [{"ContentDate": "2026-09-11T16:01:00Z"}, {"RecordCount": "2"},
    {"FileContent": "GLEIF_DELTA_PUBLISHED"}, {"DeltaStart": DELTA}])
def test_xml_metadata_disagreement_refuses_before_publication(tmp_path, member, changes):
    store, rules = Artifacts(), configured(member, "xml")
    envelope = bound_task(tmp_path, store, archive(rules, member, "xml", header_changes=changes), rules)
    with pytest.raises(SourceRejected): source_read.execute(envelope, store)
    assert not (tmp_path / "reading.json.parts").exists()


@pytest.mark.parametrize("member", MEMBERS)
def test_xml_template_empty_metadata_references_refuse(tmp_path, member):
    store, rules = Artifacts(), configured(member, "xml")
    rules["read"]["stream"]["header_read"]["references"]["content_dates"] = {}
    envelope = bound_task(tmp_path, store, archive(rules, member, "xml"), rules)
    with pytest.raises(SourceRejected): source_read.execute(envelope, store)
    assert not (tmp_path / "reading.json.parts").exists()
