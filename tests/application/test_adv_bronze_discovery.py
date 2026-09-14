"""silver-merge-engine-migration Ticket 07: ADV bronze discovery takes explicit
artifacts only. The registry path (sec_company_filing plus attachments and raw
objects read from the local store) was deleted: that store is never hydrated,
so it always found nothing.
"""

from __future__ import annotations

from edgar_warehouse.application.adv_bronze_discovery import (
    AdvBronzeArtifactCandidate,
    discover_adv_bronze_artifacts,
    read_adv_bronze_artifacts,
)


def test_explicit_artifacts_accept_adv_and_report_non_adv():
    result = discover_adv_bronze_artifacts(
        [
            {
                "accession_number": "0001111111-24-000030",
                "cik": "999001",
                "form": "adv/a",
                "storage_path": "s3://bucket/explicit-adv.xml",
            },
            {
                "accession_number": "0001111111-24-000031",
                "form": "4",
                "storage_path": "s3://bucket/form4.xml",
            },
        ]
    )

    assert result.candidates == (
        AdvBronzeArtifactCandidate(
            accession_number="0001111111-24-000030",
            cik=999001,
            form="ADV/A",
            storage_path="s3://bucket/explicit-adv.xml",
        ),
    )
    assert [(issue.accession_number, issue.reason) for issue in result.issues] == [
        ("0001111111-24-000031", "non_adv_form")
    ]


def test_explicit_artifacts_without_accession_or_storage_path_are_issues():
    result = discover_adv_bronze_artifacts(
        [
            {"form": "ADV", "storage_path": "s3://bucket/no-accession.xml"},
            {"accession_number": "0001111111-24-000032", "form": "ADV", "storage_path": "  "},
        ]
    )

    assert result.candidates == ()
    assert [(issue.accession_number, issue.reason) for issue in result.issues] == [
        (None, "missing_accession_number"),
        ("0001111111-24-000032", "empty_storage_path"),
    ]


def test_accession_list_filters_named_artifacts():
    result = discover_adv_bronze_artifacts(
        [
            {"accession_number": "0001111111-24-000033", "form": "ADV", "storage_path": "s3://bucket/a.xml"},
            {"accession_number": "0001111111-24-000034", "form": "ADV", "storage_path": "s3://bucket/b.xml"},
        ],
        accession_list=["0001111111-24-000034"],
    )

    assert [candidate.accession_number for candidate in result.candidates] == ["0001111111-24-000034"]
    assert result.issues == ()


def test_read_adv_bronze_artifacts_uses_injected_reader_and_continues_on_unreadable():
    candidates = (
        AdvBronzeArtifactCandidate(
            accession_number="0001111111-24-000040",
            cik=1,
            form="ADV",
            storage_path="s3://bucket/readable.xml",
        ),
        AdvBronzeArtifactCandidate(
            accession_number="0001111111-24-000041",
            cik=1,
            form="ADV",
            storage_path="s3://bucket/unreadable.xml",
        ),
    )
    calls: list[str] = []

    def read_bytes_fn(storage_path: str) -> bytes:
        calls.append(storage_path)
        if storage_path.endswith("unreadable.xml"):
            raise OSError("permission denied")
        return b"<adv/>"

    result = read_adv_bronze_artifacts(candidates, read_bytes_fn=read_bytes_fn)

    assert calls == ["s3://bucket/readable.xml", "s3://bucket/unreadable.xml"]
    assert len(result.payloads) == 1
    assert result.payloads[0].candidate.accession_number == "0001111111-24-000040"
    assert result.payloads[0].payload == b"<adv/>"
    assert len(result.issues) == 1
    assert result.issues[0].reason == "unreadable_storage_path"
    assert result.issues[0].accession_number == "0001111111-24-000041"
    assert result.issues[0].storage_path == "s3://bucket/unreadable.xml"
