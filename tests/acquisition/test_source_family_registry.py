from __future__ import annotations

from unittest.mock import patch

import pytest

from edgar_warehouse.acquisition.source_family_registry import (
    FilingArtifactPolicy,
    SubmissionsPolicy,
    UnsupportedCompletenessPolicy,
)


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


def test_filing_artifact_policy_rejects_an_unknown_completeness_policy() -> None:
    """Ticket 32 bullet 1: completeness_policy is a real dispatch key, not
    inert metadata -- an unimplemented value must fail closed at fetch time.
    """

    policy = FilingArtifactPolicy(
        identity="EdgarTools Platform test@example.com",
        completeness_policy="some_future_policy",
    )

    with pytest.raises(UnsupportedCompletenessPolicy):
        policy.is_complete(b"some bytes")


def test_submissions_policy_fetches_via_edgartools_sec_gateway() -> None:
    """Ticket 21: submissions.json is a catalog object class, not a filing
    document/attachment -- it must go through edgartools_sec_gateway.
    download_bytes, never filing_content_gateway (reserved for filing
    document/attachment bytes; see this module's own docstring).
    """

    policy = SubmissionsPolicy(identity="EdgarTools Platform test@example.com")

    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_sec_catalog_bytes",
        return_value=b'{"cik": "0000320193"}',
    ) as mocked:
        payload = policy.fetch("https://data.sec.gov/submissions/CIK0000320193.json")

    mocked.assert_called_once_with(
        "https://data.sec.gov/submissions/CIK0000320193.json",
        "EdgarTools Platform test@example.com",
    )
    assert payload == b'{"cik": "0000320193"}'


def test_submissions_policy_completeness_requires_valid_json_object() -> None:
    policy = SubmissionsPolicy(identity="EdgarTools Platform test@example.com")

    assert policy.is_complete(b'{"cik": "0000320193"}') is True
    assert policy.is_complete(b"") is False
    assert policy.is_complete(b"not json") is False
    assert policy.is_complete(b"[1, 2, 3]") is False  # valid JSON, not an object


def test_submissions_policy_rejects_an_unknown_completeness_policy() -> None:
    policy = SubmissionsPolicy(
        identity="EdgarTools Platform test@example.com",
        completeness_policy="some_future_policy",
    )

    with pytest.raises(UnsupportedCompletenessPolicy):
        policy.is_complete(b'{"cik": "0000320193"}')
