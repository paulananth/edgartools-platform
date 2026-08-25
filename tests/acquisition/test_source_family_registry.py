from __future__ import annotations

from unittest.mock import patch

import pytest

from edgar_warehouse.acquisition.source_family_registry import (
    CompanyFactsPolicy,
    FilingArtifactPolicy,
    ReferenceCatalogPolicy,
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


def test_company_facts_policy_fetches_via_edgartools_sec_gateway() -> None:
    """Ticket 22: companyfacts JSON is a catalog/facts object class, same
    gateway boundary as submissions -- see this module's own docstring.
    """

    policy = CompanyFactsPolicy(identity="EdgarTools Platform test@example.com")

    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_sec_catalog_bytes",
        return_value=b'{"cik": 320193, "facts": {}}',
    ) as mocked:
        payload = policy.fetch("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json")

    mocked.assert_called_once_with(
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        "EdgarTools Platform test@example.com",
    )
    assert payload == b'{"cik": 320193, "facts": {}}'


def test_company_facts_policy_completeness_allows_an_empty_facts_section() -> None:
    """Advisor trap: a real CIK can have zero XBRL facts -- completeness is
    "well-formed JSON object", not "non-empty facts section".
    """

    policy = CompanyFactsPolicy(identity="EdgarTools Platform test@example.com")

    assert policy.is_complete(b'{"cik": 320193, "facts": {}}') is True
    assert policy.is_complete(b"") is False
    assert policy.is_complete(b"not json") is False
    assert policy.is_complete(b"[1, 2, 3]") is False  # valid JSON, not an object


def test_company_facts_policy_rejects_an_unknown_completeness_policy() -> None:
    policy = CompanyFactsPolicy(
        identity="EdgarTools Platform test@example.com",
        completeness_policy="some_future_policy",
    )

    with pytest.raises(UnsupportedCompletenessPolicy):
        policy.is_complete(b'{"cik": 320193}')


def test_reference_catalog_policy_fetches_via_edgartools_sec_gateway() -> None:
    """Ticket 23: ticker catalogs are a catalog/facts object class, same
    gateway boundary as submissions/company_facts -- see this module's own
    docstring.
    """

    policy = ReferenceCatalogPolicy(identity="EdgarTools Platform test@example.com")

    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_sec_catalog_bytes",
        return_value=b'{"fields": ["cik", "name", "ticker", "exchange"], "data": []}',
    ) as mocked:
        payload = policy.fetch("https://www.sec.gov/files/company_tickers_exchange.json")

    mocked.assert_called_once_with(
        "https://www.sec.gov/files/company_tickers_exchange.json",
        "EdgarTools Platform test@example.com",
    )
    assert payload == b'{"fields": ["cik", "name", "ticker", "exchange"], "data": []}'


def test_reference_catalog_policy_completeness_accepts_both_sec_ticker_shapes() -> None:
    policy = ReferenceCatalogPolicy(identity="EdgarTools Platform test@example.com")

    # company_tickers_exchange.json shape.
    assert policy.is_complete(b'{"fields": ["cik", "ticker"], "data": [[320193, "AAPL"]]}') is True
    # company_tickers.json shape (numbered-dict of entries).
    assert policy.is_complete(b'{"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple"}}') is True


def test_reference_catalog_policy_completeness_allows_a_valid_empty_catalog() -> None:
    """Bullet 2: a valid zero-member catalog must complete without fabricated
    rows -- both SEC shapes have a legitimate empty form.
    """

    policy = ReferenceCatalogPolicy(identity="EdgarTools Platform test@example.com")

    assert policy.is_complete(b'{"fields": ["cik", "ticker"], "data": []}') is True
    assert policy.is_complete(b"{}") is True


def test_reference_catalog_policy_completeness_rejects_malformed_or_unrecognized_shapes() -> None:
    """Advisor trap ``_parse_company_ticker_rows`` doesn't guard against on its
    own: a payload that decodes to well-formed JSON but matches neither SEC
    ticker-catalog shape would otherwise silently parse to zero rows,
    indistinguishable from a genuine empty catalog -- completeness must catch
    this before it ever reaches the parser.
    """

    policy = ReferenceCatalogPolicy(identity="EdgarTools Platform test@example.com")

    assert policy.is_complete(b"") is False
    assert policy.is_complete(b"not json") is False
    assert policy.is_complete(b"[1, 2, 3]") is False  # valid JSON, not an object
    assert policy.is_complete(b'{"unexpected": "shape"}') is False
    assert policy.is_complete(b'{"0": {"missing_cik_str": true}}') is False


def test_reference_catalog_policy_rejects_an_unknown_completeness_policy() -> None:
    policy = ReferenceCatalogPolicy(
        identity="EdgarTools Platform test@example.com",
        completeness_policy="some_future_policy",
    )

    with pytest.raises(UnsupportedCompletenessPolicy):
        policy.is_complete(b'{"fields": [], "data": []}')
