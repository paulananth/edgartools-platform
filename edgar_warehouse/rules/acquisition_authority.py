"""Frozen Rules acquisition authority; no provider-specific configuration code."""

from __future__ import annotations

import re
from uuid import NAMESPACE_URL, uuid5

from edgar_warehouse.control_contract import Blocked, digest, reference


def acquisition(document: dict) -> dict:
    section = document.get("acquisition")
    if (
        not isinstance(section, dict)
        or set(section) != {"version", "feeds"}
        or type(section["version"]) is not int
        or section["version"] != 1
    ):
        raise Blocked("Acquisition requires version 1 and explicit feeds")
    feeds = section["feeds"]
    if not isinstance(feeds, dict) or not feeds:
        raise Blocked("Acquisition requires declared feed identities")
    for feed, value in feeds.items():
        if (
            not isinstance(feed, str)
            or not feed
            or not isinstance(value, dict)
            or set(value)
            - {
                "family",
                "datasets",
                "scope",
                "capabilities",
                "completeness",
                "page_completeness",
                "required_producers",
                "url_prefixes",
                "authorizations",
                "secret_header",
            }
            or not {
                "family",
                "datasets",
                "scope",
                "capabilities",
                "completeness",
                "required_producers",
                "url_prefixes",
            }
            <= set(value)
        ):
            raise Blocked(
                "Each feed declares family, datasets, scope, capabilities, completeness, producers and URLs"
            )
        for key in ("datasets", "scope", "required_producers", "url_prefixes"):
            if (
                not isinstance(value[key], list)
                or not value[key]
                and key != "datasets"
                or any(not isinstance(v, str) or not v for v in value[key])
                or len(set(value[key])) != len(value[key])
            ):
                raise Blocked(f"Feed {feed} requires explicit distinct {key}")
        if not isinstance(value["family"], str) or not value["family"]:
            raise Blocked("Feed family is required")
        if not isinstance(value["capabilities"], dict) or set(
            value["capabilities"]
        ) != {"capture", "fetch"}:
            raise Blocked("Feed requires capture and fetch capability selections")
        if value["capabilities"]["capture"] != "provider.capture" or value[
            "capabilities"
        ]["fetch"] not in {"http.conditional", "sec.conditional", "https.post"}:
            raise Blocked("Unsupported acquisition capability")
        # A provider that wants a key gets it in one named header, read from a
        # named environment variable at the request (ticket 92); only a POST
        # feed (`https.post`: a frozen JSON body, status 200 only) declares one.
        secret = value.get("secret_header")
        if secret is not None and (
            value["capabilities"]["fetch"] != "https.post"
            or not isinstance(secret, dict)
            or set(secret) != {"name", "environment"}
            or not isinstance(secret["name"], str)
            or not re.fullmatch(r"[A-Za-z0-9-]{1,64}", secret["name"])
            # The capture's own headers are never replaced by a secret.
            or secret["name"].lower() in {"user-agent", "accept", "content-type", "content-length",
                                          "host", "if-none-match", "if-modified-since"}
            or not isinstance(secret["environment"], str)
            or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", secret["environment"])
        ):
            raise Blocked("A secret header is a header name and an environment variable, on a POST feed only")
        completeness = value["completeness"]
        if (
            not isinstance(completeness, dict)
            or set(completeness) != {"format", "required", "allow_empty", "max_bytes"}
            or completeness["format"]
            not in {"json", "json_array", "xml", "zip", "text", "ticker_catalog"}
            or not isinstance(completeness["required"], list)
            or any(not isinstance(k, str) or not k for k in completeness["required"])
            or type(completeness["allow_empty"]) is not bool
            or type(completeness["max_bytes"]) is not int
            or not 1 <= completeness["max_bytes"] <= 1024**3
            or completeness["format"] == "json_array" and (
                completeness["required"] or value["capabilities"]["fetch"] != "https.post")
        ):
            raise Blocked(
                "Feed completeness requires supported format, required members, empty policy and size bound"
            )
        page = value.get("page_completeness")
        if page is not None and (
            not isinstance(page, dict) or set(page) != set(completeness)
            or page["format"] != "json" or not isinstance(page["required"], list)
            or not all(isinstance(k, str) and k for k in page["required"])
            or type(page["allow_empty"]) is not bool
            or type(page["max_bytes"]) is not int or not 1 <= page["max_bytes"] <= 1024**3
        ):
            raise Blocked("Invalid pagination completeness contract")
        if any(not prefix.startswith("https://") for prefix in value["url_prefixes"]):
            raise Blocked("Provider requests require approved HTTPS URL prefixes")
        if not isinstance(value.get("authorizations", []), list):
            raise Blocked(
                "Operator authorizations must be approved exact artifact references"
            )
        for ref in value.get("authorizations", []):
            reference(ref)
    return feeds


def processing_authority(export: dict) -> dict:
    """The frozen rules of a source, as a run holds them: its name and the digest of its body."""
    if (
        export.get("kind") != "source"
        or export["body"].get("source") != export.get("name")
        or digest(export["body"]) != export.get("digest")
    ):
        raise Blocked("A run needs a source's frozen rules: its name and the digest of its body")
    return {"name": export["name"], "version": export["version"], "digest": export["digest"]}


def frozen_authority(export: dict, feed: str) -> dict:
    """Live acquisition of `feed`: the source's frozen rules and the feed's declared configuration."""
    authority = processing_authority(export)
    feeds = acquisition(export["body"])
    if feed not in feeds:
        raise Blocked("Feed is absent from the source's acquisition section")
    return {**authority, "feed": feed, "configuration": feeds[feed]}


def registration_authority(export: dict, code: str, contract: dict) -> dict:
    # A source that declares acquisition names each dataset in one feed of its family.
    # One that declares none (it reads files another source's feed captures) registers
    # its datasets on its pipes alone (operator, 2026-10-19).
    if "acquisition" in export["body"]:
        feeds = acquisition(export["body"])
        declared = [
            (feed, value) for feed, value in feeds.items() if code in value["datasets"]
        ]
        if len(declared) != 1 or declared[0][1]["family"] != contract["family"]:
            raise Blocked("Dataset requires exactly one feed with matching family")
    elif contract["family"] != (export["body"].get("bronze") or {}).get("family"):
        raise Blocked("Dataset of a source with no feed of its own names the family its source reads (bronze.family)")
    frozen = processing_authority(export)
    if export["body"].get("dataset_contracts", {}).get(code, {}).get("contract") != contract:
        raise Blocked("Dataset contract differs from the source's frozen rules")
    version_id = str(
        uuid5(
            NAMESPACE_URL,
            f"rules:{export['name']}:{export['version']}:{export['digest']}",
        )
    )
    return {
        "version_id": version_id,
        "status": "active",
        "source_family": contract["family"],
        "coverage_action": "add",
        "rules": frozen,
    }
