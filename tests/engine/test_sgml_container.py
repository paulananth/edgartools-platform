"""An SGML submission file read through the configured engine (profiling ticket 07).

`container: sgml` hands `format: xml` the one document whose text holds
`<XML>`; a context field may name an SGML header line and is filled from it,
never by the caller. Every name and number here is invented.
"""
import pytest

from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected

CONTRACT = {"read": {
    "format": "xml", "container": "sgml", "root": "sampleDocument",
    "context": {"accession": {"type": "text", "sgml_header": "ACCESSION NUMBER"}},
    "tables": {"filing": {"each": ".", "columns": {
        "accession": {"context": {"name": "accession"}}, "code": {"text": {"path": "item.code.$"}}}}}}}


def submission(*documents: bytes, header: bytes = b"ACCESSION NUMBER:\t0000000000-26-000001\n") -> bytes:
    return (b"<SEC-DOCUMENT>x.txt : 20260102\n<SEC-HEADER>x.hdr.sgml : 20260102\n" + header
            + b"</SEC-HEADER>\n" + b"".join(documents) + b"</SEC-DOCUMENT>\n")


def document(name: bytes, text: bytes) -> bytes:
    return b"<DOCUMENT>\n<TYPE>4\n<FILENAME>" + name + b"\n<TEXT>\n" + text + b"\n</TEXT>\n</DOCUMENT>\n"


XML = b"<XML>\n<?xml version=\"1.0\"?>\n<sampleDocument><item><code>P</code></item></sampleDocument>\n</XML>"


def test_the_xml_document_is_read_with_its_header_accession():
    engine = SourceEngine(CONTRACT)
    engine.validate_context({})  # the caller supplies nothing the header fills
    tables = engine.read(submission(document(b"a.xml", XML), document(b"ex.txt", b"TEXT"))).tables
    assert tables == {"filing": [{"accession": "0000000000-26-000001", "code": "P"}]}


@pytest.mark.parametrize("file, code", [
    (submission(document(b"ex.txt", b"TEXT")), "sgml_documents"),
    (submission(document(b"a.xml", XML), document(b"b.xml", XML)), "sgml_documents"),
    (submission(document(b"a.xml", XML), header=b"CONFORMED SUBMISSION TYPE:\t4\n"), "sgml_header"),
])
def test_a_file_the_container_cannot_settle_is_refused(file, code):
    with pytest.raises(SourceRejected) as refused:
        SourceEngine(CONTRACT).read(file)
    assert refused.value.code == code


def test_the_caller_cannot_supply_a_header_field():
    with pytest.raises(SourceRejected) as refused:
        SourceEngine(CONTRACT).read(submission(document(b"a.xml", XML)), context={"accession": "x"})
    assert refused.value.code == "invalid_context"
