"""A source's frozen rules for MDM registration tests: one invented feed and one Dataset Contract."""

from __future__ import annotations

from edgar_warehouse.control_contract import digest
from edgar_warehouse.mdm.store import register_dataset as register_from_rules


def authority(code: str, body: dict, version: str) -> dict:
    name = "fixture-registration"
    feed = {
        "family": body["family"],
        "datasets": [code],
        "scope": ["fixture"],
        "capabilities": {"capture": "provider.capture", "fetch": "http.conditional"},
        "completeness": {"format": "json", "required": [], "allow_empty": True, "max_bytes": 1024},
        "required_producers": ["fixture"],
        "url_prefixes": ["https://fixture.invalid/"],
    }
    document = {
        "source": name,
        "acquisition": {"version": 1, "feeds": {"fixture": feed}},
        "dataset_contracts": {code: {"contract": body}},
    }
    return {"kind": "source", "name": name, "version": version, "digest": digest(document), "body": document}


def register_dataset(conn, code: str, registry_version: str, body: dict) -> None:
    return register_from_rules(conn, code, body, rules_authority=authority(code, body, registry_version))
