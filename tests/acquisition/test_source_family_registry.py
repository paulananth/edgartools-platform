from __future__ import annotations

from unittest.mock import patch

from edgar_warehouse.acquisition.source_family_registry import FilingArtifactPolicy


def test_filing_artifact_policy_fetches_via_byte_preserving_filing_content_gateway() -> None:
    policy = FilingArtifactPolicy(identity="EdgarTools Platform test@example.com")

    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_filing_content_bytes",
        return_value=b"raw filing bytes",
    ) as mocked:
        payload = policy.fetch("https://www.sec.gov/Archives/example.xml")

    mocked.assert_called_once_with(
        "https://www.sec.gov/Archives/example.xml",
        "EdgarTools Platform test@example.com",
    )
    assert payload == b"raw filing bytes"


def test_filing_artifact_policy_completeness_requires_non_empty_payload() -> None:
    policy = FilingArtifactPolicy(identity="EdgarTools Platform test@example.com")

    assert policy.is_complete(b"some bytes") is True
    assert policy.is_complete(b"") is False
