"""Faults must invalidate full-archive qualification, including native decoder faults."""
import hashlib
import zipfile

import pytest

from edgar_warehouse.bookkeeping.clean.config import Blocked
from edgar_warehouse.rules.source_engine import SourceRejected
from scripts.qualification import qualify_json_archive_parity as parity


def archive(tmp_path, body=b'{"records":[{"a":1,"b":2},{"v":-0.0}]}'):
    path = tmp_path / 'capture.zip'
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as zipped:
        zipped.writestr('capture.json', body)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_full_archive_proof_has_pinned_count_and_canonical_source_hash(tmp_path):
    path, digest = archive(tmp_path)
    report = parity.qualify(path, digest, 'records', 2)
    expected = b'{"a":1,"b":2}\n{"v":-0.0}\n'
    assert report['receipt']['record_count'] == report['expected_records'] == 2
    assert report['canonical_source_hash'] == hashlib.sha256(expected).hexdigest()
    assert report['typed_order_differences'] == 0


def test_publisher_count_mismatch_cannot_produce_report(tmp_path):
    path, digest = archive(tmp_path)
    with pytest.raises(ValueError, match='Pinned publication count'):
        parity.qualify(path, digest, 'records', 3)


def test_changed_authenticated_archive_refuses(tmp_path):
    path, digest = archive(tmp_path)
    with pytest.raises(Blocked, match='hash mismatch'):
        parity.qualify(path, '0' * 64, 'records')


def test_corrupted_zip_member_refuses_even_with_matching_archive_hash(tmp_path):
    path, _ = archive(tmp_path)
    data = path.read_bytes().replace(b'"a":1', b'"a":9', 1)
    path.write_bytes(data)
    with pytest.raises(SourceRejected, match='CRC'):
        parity.qualify(path, hashlib.sha256(data).hexdigest(), 'records')


@pytest.mark.parametrize('fault', ['type', 'key_order', 'float_sign'])
def test_native_decoder_fault_is_detected_independently(tmp_path, monkeypatch, fault):
    path, digest = archive(tmp_path)
    actual = parity.stream_json_array
    def corrupted(stream, *, on_record, **kwargs):
        def consume(row, index):
            if fault == 'type' and 'a' in row: row['a'] = True
            elif fault == 'key_order' and 'a' in row: row = dict(reversed(list(row.items())))
            elif fault == 'float_sign' and 'v' in row: row['v'] = 0.0
            on_record(row, index)
        return actual(stream, on_record=consume, **kwargs)
    monkeypatch.setattr(parity, 'stream_json_array', corrupted)
    with pytest.raises(SourceRejected, match='Typed/key-order difference'):
        parity.qualify(path, digest, 'records')


def test_independent_additional_null_record_is_not_confused_with_eof(tmp_path, monkeypatch):
    path, digest = archive(tmp_path)
    actual = parity.ijson.items
    def extra_null(*args, **kwargs):
        yield from actual(*args, **kwargs)
        yield None
    monkeypatch.setattr(parity.ijson, 'items', extra_null)
    with pytest.raises(ValueError, match='additional records'):
        parity.qualify(path, digest, 'records')


@pytest.mark.parametrize('member', ['level1', 'relationships', 'reporting-exceptions'])
def test_full_xml_parity_uses_publisher_header_and_independent_decoder(tmp_path, member):
    from scripts.qualification import qualify_xml_archive_parity as xml
    from tests.engine.test_gleif_reading_contracts import configured, archive as xml_archive
    path = tmp_path / 'capture.xml.zip'
    path.write_bytes(xml_archive(configured(member, 'xml'), member, 'xml'))
    kind, cdf = {'level1':('lei2','LEI_3.1'), 'relationships':('rr','RR_2.1'),
                 'reporting-exceptions':('repex','REPEX_2.1')}[member]
    metadata = {'data':{'publish_date':'2026-09-11 16:00:00', 'full_file':{'xml':{
        'type':kind, 'format':'xml', 'delta_type':'GoldenCopy', 'cdf_version':cdf,
        'record_count':3, 'size':path.stat().st_size}}}}
    result = xml.qualify(path, hashlib.sha256(path.read_bytes()).hexdigest(), member, metadata,
                         content_date='2026-09-11T16:00:00+00:00')
    assert result['receipt']['record_count'] == 3
    assert result['typed_value_differences'] == 0
    metadata['data']['full_file']['xml']['record_count'] = 2
    with pytest.raises(SourceRejected, match='record count'):
        xml.qualify(path, hashlib.sha256(path.read_bytes()).hexdigest(), member, metadata,
                    content_date='2026-09-11T16:00:00+00:00')


def test_implementation_change_during_json_scan_refuses_report(tmp_path, monkeypatch):
    path, digest = archive(tmp_path)
    observations = iter([[{'sha256':'before'}], [{'sha256':'after'}]])
    monkeypatch.setattr(parity, 'implementation_evidence', lambda: next(observations))
    with pytest.raises(ValueError, match='implementation changed'):
        parity.qualify(path, digest, 'records')


@pytest.mark.parametrize('member', ['level1', 'relationships', 'reporting-exceptions'])
def test_xml_content_date_is_independent_of_api_publication_slot(tmp_path, member):
    from scripts.qualification import qualify_xml_archive_parity as xml
    from tests.engine.test_gleif_reading_contracts import configured, archive as xml_archive
    path = tmp_path / 'different-content-time.zip'
    path.write_bytes(xml_archive(configured(member, 'xml'), member, 'xml',
        header_changes={'ContentDate':'2026-09-11T16:07:44Z'}))
    kind, cdf = {'level1':('lei2','LEI_3.1'), 'relationships':('rr','RR_2.1'),
                 'reporting-exceptions':('repex','REPEX_2.1')}[member]
    metadata = {'data':{'publish_date':'2026-09-11 16:00:00', 'full_file':{'xml':{
        'type':kind, 'format':'xml', 'delta_type':'GoldenCopy', 'cdf_version':cdf,
        'record_count':3, 'size':path.stat().st_size}}}}
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = xml.qualify(path, digest, member, metadata, content_date='2026-09-11T16:07:44+00:00')
    assert result['content_date'] == '2026-09-11T16:07:44+00:00'
    assert result['publish_date'] == '2026-09-11 16:00:00'
    with pytest.raises(SourceRejected, match='content date'):
        xml.qualify(path, digest, member, metadata, content_date='2026-09-11T16:00:00+00:00')


def test_qualification_evidence_hashes_actual_native_extension():
    from edgar_warehouse.rules import source_engine
    evidence = {item["path"]: item["sha256"] for item in parity.implementation_evidence()}
    for path in source_engine.runtime_files():
        assert evidence[str(path.resolve())] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert any(path.endswith((".so", ".pyd", ".dylib")) for path in evidence)
