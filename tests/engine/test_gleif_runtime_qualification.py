"""Runtime corpus receipts require independent evidence and authenticated complete input."""
import hashlib
import io
import json
import zipfile

import pytest

from scripts.qualification.qualify_gleif_runtime import qualify


def pinned(path, document):
    path.write_text(json.dumps(document))
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("format_name", ["json", "xml"])
@pytest.mark.parametrize("fault", [None, "canonical", "count", "archive", "evidence"])
def test_complete_runtime_receipt_requires_every_pin(tmp_path, format_name, fault):
    body = (b'{"records":[{}]}' if format_name == "json" else
        b'<LEIData xmlns="http://www.gleif.org/data/schema/leidata/2016"><LEIHeader>'
        b'<ContentDate>2026-09-11T16:00:00Z</ContentDate><FileContent>GLEIF_FULL_PUBLISHED</FileContent>'
        b'<RecordCount>1</RecordCount></LEIHeader><LEIRecords><LEIRecord/></LEIRecords></LEIData>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("capture", body)
    raw = buffer.getvalue()
    capture = tmp_path / "capture.zip"
    capture.write_bytes(raw)
    publication = {"record_count": 1, "size": len(raw), "cdf_version": "LEI_3.1"}
    publisher_path, parity_path = tmp_path / "publisher.json", tmp_path / "parity.json"
    publisher_sha = pinned(publisher_path, {"data": {"type": "lei2",
        "publish_date": "2026-09-11 16:00:00", "full_file": {format_name: publication}}})
    report = {"archive": {"uri": capture.as_uri(), "sha256": hashlib.sha256(raw).hexdigest()},
        "receipt": {"record_count": 1, "expanded_bytes": len(body)}, "publisher": publication,
        "content_date": "2026-09-11T16:00:00+00:00",
        "canonical_source_hash": hashlib.sha256(b'{}\n').hexdigest()}
    if fault == "canonical": report["canonical_source_hash"] = "0" * 64
    if fault == "count": report["receipt"]["record_count"] = 2
    if fault == "archive": report["archive"]["sha256"] = "0" * 64
    parity_sha = pinned(parity_path, report)
    if fault == "evidence": parity_sha = "0" * 64
    arguments = ("level1", format_name, parity_path, parity_sha, publisher_path, publisher_sha)
    if fault:
        with pytest.raises(ValueError):
            qualify(*arguments)
    else:
        receipt = qualify(*arguments)
        assert receipt["callback_count"] == 1
        assert receipt["receipt"]["canonical_source_hash"] == report["canonical_source_hash"]
        assert any(p["path"].endswith((".so", ".pyd", ".dylib"))
                   for p in receipt["runtime_implementation"])
