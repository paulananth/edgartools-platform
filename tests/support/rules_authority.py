"""Isolated approved Rules source fixture for Clean MDM registration tests.

The production registrar still validates the complete frozen source envelope.
These tests synthesize that envelope because their subject is the MDM reading,
not the Rules approval workflow (covered by the integration acceptance suite).
"""

from __future__ import annotations

from edgar_warehouse.bookkeeping.clean.config import digest
from edgar_warehouse.mdm.clean.store import register_dataset as register_from_rules


def authority(code: str, body: dict, version: str) -> dict:
    name = "fixture-registration"
    feed = {
        "family": body["family"],
        "datasets": [code],
        "scope": ["fixture"],
        "capabilities": {"capture": "provider.capture", "fetch": "http.conditional"},
        "completeness": {
            "format": "json",
            "required": [],
            "allow_empty": True,
            "max_bytes": 1024,
        },
        "required_producers": ["fixture"],
        "url_prefixes": ["https://fixture.invalid/"],
    }
    document = {
        "source": name,
        "acquisition": {"version": 1, "feeds": {"fixture": feed}},
        "mdm": {code: {"contract": body}},
    }
    content_hash = digest(document)
    proof = {
        "passed": True,
        "digest": content_hash,
        "acquisition": {
            "fixture": {
                "manifest": {"uri": "file:///fixture/manifest.json", "sha256": "0" * 64},
                "counts": {"fixture": {"expected": 0, "verified": 0}},
                "checks": {"fixture": True},
            }
        },
    }
    return {
        "kind": "source",
        "name": name,
        "version": version,
        "digest": content_hash,
        "body": document,
        "status": "active",
        "proof": proof,
        "approval": {"digest": content_hash, "by": "offline-test", "at": "2026-01-01T00:00:00Z"},
    }


def register_dataset(conn, code: str, registry_version: str, body: dict) -> None:
    return register_from_rules(
        conn,
        code,
        body,
        rules_authority=authority(code, body, registry_version),
    )
