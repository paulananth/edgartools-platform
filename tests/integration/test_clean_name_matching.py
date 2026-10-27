"""Identifier-contract fixture used by the configured-route integration tests."""
from tests.mdm.test_clean_activation import CIK_CONTRACT

GLEIF = "fixture.secondary"
LEI_CONTRACT = {
    **CIK_CONTRACT,
    "authority": "GLEIF",
    "sources": [GLEIF],
    "normalizer": "normalize_identifier@lei-v1",
}
