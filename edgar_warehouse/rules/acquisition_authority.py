"""Frozen Rules acquisition authority; no provider-specific configuration code."""

from __future__ import annotations

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
        ]["fetch"] not in {"http.conditional", "sec.conditional"}:
            raise Blocked("Unsupported acquisition capability")
        completeness = value["completeness"]
        if (
            not isinstance(completeness, dict)
            or set(completeness) != {"format", "required", "allow_empty", "max_bytes"}
            or completeness["format"]
            not in {"json", "xml", "zip", "text", "ticker_catalog"}
            or not isinstance(completeness["required"], list)
            or any(not isinstance(k, str) or not k for k in completeness["required"])
            or type(completeness["allow_empty"]) is not bool
            or type(completeness["max_bytes"]) is not int
            or not 1 <= completeness["max_bytes"] <= 1024**3
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


def frozen_authority(export: dict, feed: str, *, artifacts=None) -> dict:
    if (
        export.get("kind") != "source"
        or export.get("status") not in {"active", "proven"}
        or export["body"].get("source") != export.get("name")
        or digest(export["body"]) != export.get("digest")
    ):
        raise Blocked("A frozen proven Rules source envelope is required")
    proof, approval = export.get("proof") or {}, export.get("approval") or {}
    if not proof_holds(export):
        raise Blocked("Acquisition requires verified Rules proof")
    validation_proof(export["body"], proof, artifacts=artifacts)
    if (
        approval.get("digest") != export["digest"]
        or not approval.get("by")
        or not approval.get("at")
    ):
        raise Blocked("Acquisition requires approval of the exact Rules version")
    feeds = acquisition(export["body"])
    if feed not in feeds:
        raise Blocked("Feed is absent from frozen acquisition authority")
    return {
        "name": export["name"],
        "version": export["version"],
        "digest": export["digest"],
        "feed": feed,
        "configuration": feeds[feed],
        "proof": proof,
        "approval": approval,
    }


def registration_authority(export: dict, code: str, contract: dict) -> dict:
    feeds = acquisition(export["body"])
    declared = [
        (feed, value) for feed, value in feeds.items() if code in value["datasets"]
    ]
    if len(declared) != 1 or declared[0][1]["family"] != contract["family"]:
        raise Blocked("Dataset requires exactly one approved feed with matching family")
    frozen = frozen_authority(export, declared[0][0])
    if export["body"].get("mdm", {}).get(code, {}).get("contract") != contract:
        raise Blocked(
            "Dataset contract differs from the frozen approved Rules document"
        )
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


def proof_holds(export: dict) -> bool:
    """A version's test evidence stands: its proof passed, or the operator
    overruled a failing one when approving this exact version."""
    proof, approval = export.get("proof") or {}, export.get("approval") or {}
    if proof.get("digest") != export.get("digest"):
        return False
    return proof.get("passed") is True or (
        proof.get("passed") is False and approval.get("digest") == export.get("digest") and bool(approval.get("overrule")))


def validation_proof(body: dict, proof: dict, *, artifacts=None) -> None:
    feeds = acquisition(body)
    verified = proof.get("acquisition")
    if not isinstance(verified, dict) or set(verified) != set(feeds):
        raise Blocked("Rules proof must qualify every declared acquisition feed")
    for feed, value in verified.items():
        if not isinstance(value, dict) or set(value) != {
            "manifest",
            "counts",
            "checks",
        }:
            raise Blocked("Feed proof requires baseline manifest, counts and checks")
        reference(value["manifest"])
        if artifacts is not None:
            artifacts.verified(value["manifest"], max_bytes=32 * 1024**2)
        if (
            not isinstance(value["counts"], dict)
            or set(value["counts"]) != set(feeds[feed]["required_producers"])
            or any(
                not isinstance(count, dict)
                or set(count) != {"expected", "verified"}
                or type(count["expected"]) is not int
                or count["expected"] < 0
                or type(count["verified"]) is not int
                or count["verified"] != count["expected"]
                for count in value["counts"].values()
            )
            or not isinstance(value["checks"], dict)
            or not value["checks"]
            or any(v is not True for v in value["checks"].values())
        ):
            raise Blocked(
                "Acquisition proof requires complete producer counts and verified checks"
            )
