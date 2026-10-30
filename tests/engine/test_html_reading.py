"""An HTML page read through the configured engine (ticket 149), from inside a
capture snapshot as `provider.capture` keeps it: a ZIP of `metadata.json` and
`payload`. The page is flat: `title`, each `block` of text, and
each table `row` as one record (`@table`, `@row`, its cells `c1`, `c2`...). Every name and number here is invented.
"""
import io
import zipfile

import pytest

from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected

PAGE = (b"<html><head><title>Invented Co. registration</title><script>var x = '<p>no</p>';</script></head>"
        b"<body><div><p><b>Invented Co.</b></p><p>1,000,000 Shares of Common&nbsp;Stock"
        b"<p>Price range $10.00 to $12.00 per share</div>"
        b"<table><tr><th>Title of class</th><th>Proposed maximum offering price</th></tr>"
        b"<tr><td>Common stock</td><td>$ 12,000,000</td></tr></table></body></html>")


def snapshot(page: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("metadata.json", b'{"invented": true}')
        archive.writestr("payload", page)
    return out.getvalue()


def contract(**read):
    return {"read": {"format": "html", "container": "zip", "member": "payload", **read, "tables": {
        "page": {"each": ".", "columns": {"title": {"text": {"path": "title.$"}}}},
        "blocks": {"each": "block", "columns": {"text": {"text": {"path": "$"}}}},
        "rows": {"each": "row", "columns": {"table": {"text": {"path": "@table"}}, "row": {"text": {"path": "@row"}},
                                            "c1": {"text": {"path": "c1.$"}}, "c2": {"text": {"path": "c2.$"}}}}}}}


def test_a_page_in_a_capture_snapshot_reads_as_blocks_and_table_cells():
    tables = SourceEngine(contract()).read(snapshot(PAGE)).tables
    assert tables["page"] == [{"title": "Invented Co. registration"}]
    assert tables["blocks"] == [{"text": "Invented Co."}, {"text": "1,000,000 Shares of Common Stock"},
                                {"text": "Price range $10.00 to $12.00 per share"}]
    assert tables["rows"] == [
        {"table": "1", "row": "1", "c1": "Title of class", "c2": "Proposed maximum offering price"},
        {"table": "1", "row": "2", "c1": "Common stock", "c2": "$ 12,000,000"}]


def test_windows_1252_is_read_when_declared_and_refused_when_not():
    page = b"<p>Caf\xe9 \x93quoted\x94</p>"
    tables = SourceEngine(contract(encoding=["utf-8", "windows-1252"])).read(snapshot(page)).tables
    assert tables["blocks"] == [{"text": "Café “quoted”"}]
    with pytest.raises(SourceRejected) as refused:
        SourceEngine(contract()).read(snapshot(page))
    assert refused.value.code == "encoding"


def test_more_blocks_and_rows_than_declared_refuse():
    with pytest.raises(SourceRejected) as refused:
        SourceEngine(contract(limits={"max_bytes": 1048576, "max_records": 3})).read(snapshot(PAGE))
    assert refused.value.code == "limit_exceeded"
