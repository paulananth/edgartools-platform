"""Bounded native GLEIF archives. Parsing grants no identity/binding authority."""

from __future__ import annotations

import copy
from datetime import UTC, datetime

from edgar_warehouse.rules import files as rules_files

from .adapters import (
    UnsupportedRecord,
    category_kind,
    format_value,
    normalize,
    value,
)
from .evidence import deferred_record, instant
from .store import Conflict, canonical

VERSION = "gleif-native-record-v1"
FORMATS = {
    "level1": ("LEI_3.1", "records"),
    "relationships": ("RR_2.1", "relations"),
    "reporting_exceptions": ("REPEX_2.1", "exceptions"),
}
# REPEX 2.1 retains the deprecated values for historical source compatibility.
# See GLEIF's Reporting Exceptions 2.1 ExceptionReasonEnum.
EXCEPTION_REASONS = {
    "NO_LEI",
    "NATURAL_PERSONS",
    "NON_CONSOLIDATING",
    "NO_KNOWN_PERSON",
    "NON_PUBLIC",
    "BINDING_LEGAL_COMMITMENTS",
    "LEGAL_OBSTACLES",
    "DISCLOSURE_DETRIMENTAL",
    "DETRIMENT_NOT_EXCLUDED",
    "CONSENT_NOT_OBTAINED",
}


def validate_metadata(member: str, metadata: dict) -> None:
    if not isinstance(metadata, dict):
        raise Conflict("Invalid GLEIF member metadata")
    if member not in FORMATS or metadata.get("cdf_version") != FORMATS[member][0]:
        raise Conflict("Unsupported GLEIF CDF version/member")
    if metadata.get("format") not in {"json.zip", "xml.zip"}:
        raise Conflict("Unsupported GLEIF archive format")
    count = metadata.get("record_count")
    if type(count) is not int or not 0 <= count <= 10_000_000:
        raise Conflict("Invalid GLEIF record count")
    try:
        date = instant(metadata["content_date"])
        mode = metadata["file_content"]
        if mode == "GLEIF_FULL_PUBLISHED" and metadata.get("delta_start") is None:
            return
        if mode == "GLEIF_DELTA_PUBLISHED" and instant(metadata["delta_start"]) < date:
            return
    except (KeyError, ValueError, TypeError) as exc:
        raise Conflict("Invalid GLEIF source time") from exc
    raise Conflict("Unsupported GLEIF publication mode or predecessor time")


def release_sequence(value: str) -> int:
    delta = instant(value) - datetime(1970, 1, 1, tzinfo=UTC)
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def validate_release(manifest: dict, native: dict) -> None:
    """Release metadata comes from the captured adapter manifest, never filenames."""
    if native.get("version") != VERSION or set(native.get("record_sources", {})) != set(
        FORMATS
    ):
        raise Conflict("Unsupported native GLEIF dataset contract")
    codes = list(native["record_sources"].values())
    if any(not isinstance(c, str) or not c for c in codes) or len(set(codes)) != len(
        codes
    ):
        raise Conflict("Native record sources must be distinct dataset codes")
    if manifest.get("publication_family") != "golden_copy":
        raise Conflict("Native GLEIF Golden Copy cannot consume a mapping family")
    if {m["member"] for m in manifest["members"]} != set(FORMATS):
        raise Conflict("Golden Copy requires L1, RR and REPEX together")
    try:
        release = instant(manifest["publication_time"])
        if release_sequence(manifest["publication_time"]) != manifest["sequence"]:
            raise Conflict("Native release sequence disagrees with publisher time")
        for member in manifest["members"]:
            meta = member["native"]
            validate_metadata(member["member"], meta)
            if instant(meta["content_date"]) > release:
                raise Conflict("Native content date exceeds release time")
            expected = (
                "GLEIF_FULL_PUBLISHED"
                if manifest["mode"] == "full"
                else "GLEIF_DELTA_PUBLISHED"
            )
            if meta["file_content"] != expected:
                raise Conflict("Native member coverage disagrees with release")
        scope = native["company_leis"]
        if not isinstance(scope, list) or not scope or len(set(scope)) != len(scope):
            raise Conflict("Native Company scope must be explicit and unique")
        for lei in scope:
            format_value(lei, "lei")
    except (KeyError, ValueError, TypeError) as exc:
        raise Conflict("Invalid native release metadata or Company scope") from exc


def dataset_contract(member: str, *, level1_source: str | None = None) -> dict:
    """Governance input, not registration or activation. Field ranks live in policy.

    Each member's mapping is data in `rules/sources/gleif/source.yaml` (rules
    skill ticket 01). A relationship points at the Level 1 source the file
    names, at both ends; `level1_source` replaces it for a caller that
    registers Level 1 under another code.
    """
    for entry in rules_files.source("gleif")["mdm"].values():
        contract = entry["contract"]
        if contract["adapter"]["native_member"] == member:
            if level1_source is not None:
                contract = copy.deepcopy(contract)
                for relationship in contract["adapter"].get("relationships", []):
                    relationship["target_source"] = level1_source
                    if relationship.get("source_key"):  # a link starts at Level 1 too
                        relationship["source_source"] = level1_source
            return contract
    raise ValueError("Unknown native GLEIF member")


def _refuse_deletion(row: dict) -> None:
    """GLEIF flags a deletion in delta files only; in a full file the field is
    present and empty on 4% of reporting exceptions (ticket 18). A flag with a
    value on one of our Companies' records is never read as a live record; it
    blocks until someone decides. Checked after scope, so a delta's deletions
    of every other LEI stay out of scope and never block."""
    extension = row.get("Extension")
    flag = extension.get("gleif:Deletion") if isinstance(extension, dict) else extension
    if flag is not None:
        raise UnsupportedRecord("gleif_deletion_flag")


def record_evidence(
    row: dict,
    *,
    member: str,
    contract: dict,
    source_code: str,
    eligible_leis: set[str],
    publication: dict,
    ordinal: int,
    mapping_version: int = 1,
) -> tuple[str, dict]:
    """Interpret one authenticated record; leave identity decisions to Merge Stage."""
    if (
        contract["adapter"].get("native_member") != member
        or contract["adapter"]["version"] != VERSION
    ):
        raise Conflict("Unregistered native GLEIF interpretation")
    if contract["adapter"].get("classification"):
        # Every Level 1 record the contract admits is one kind, so the contract
        # states it; a rule would need the pinned policy this path never reads.
        raise Conflict("Native GLEIF records do not support classification rules")
    raw = row
    try:
        if member == "relationships":
            row = row.get("RelationshipRecord", {})
            start = format_value(value(row, "Relationship.StartNode.NodeID.$"), "lei")
            end = format_value(value(row, "Relationship.EndNode.NodeID.$"), "lei")
            if any(
                value(row, f"Relationship.{side}.NodeIDType.$") != "LEI"
                for side in ("StartNode", "EndNode")
            ):
                raise UnsupportedRecord("unsupported_relationship_endpoint")
            if start not in eligible_leis or end not in eligible_leis:
                raise UnsupportedRecord("outside_approved_company_scope")
            _refuse_deletion(row)
            periods = value(row, "Relationship.RelationshipPeriods.RelationshipPeriod")
            periods = periods if isinstance(periods, list) else [periods]
            periods = [
                p
                for p in periods
                if isinstance(p, dict)
                and value(p, "PeriodType.$") == "RELATIONSHIP_PERIOD"
            ]
            if len(periods) != 1:
                raise UnsupportedRecord("ambiguous_relationship_period")
            start_at, end_at = (
                value(periods[0], "StartDate.$"),
                value(periods[0], "EndDate.$"),
            )
            if not start_at or (end_at and instant(start_at) >= instant(end_at)):
                raise UnsupportedRecord("invalid_relationship_interval")
            status = value(row, "Relationship.RelationshipStatus.$")
            if status not in {"ACTIVE", "INACTIVE"} or (
                status == "INACTIVE" and not end_at
            ):
                raise UnsupportedRecord("invalid_relationship_status_interval")
            effective = value(row, "Registration.LastUpdateDate.$")
            row = {
                "start": start,
                "end": end,
                "relationship_type": value(row, "Relationship.RelationshipType.$"),
                "valid_from": instant(start_at).isoformat(),
                "valid_to": instant(end_at).isoformat() if end_at else None,
                "status": status,
                "registration_status": value(row, "Registration.RegistrationStatus.$"),
            }
        else:
            lei = format_value(value(row, "LEI.$"), "lei")
            if lei not in eligible_leis:
                # Scope decides whether it waits, not what it probably is.
                raise UnsupportedRecord(
                    "outside_approved_company_scope",
                    probable_kind=category_kind(row, contract["adapter"])
                    if "kind_field" in contract["adapter"]
                    else None,
                )
            _refuse_deletion(row)
            effective = value(row, "Registration.LastUpdateDate.$")
            if member == "level1":
                category = value(row, "Entity.EntityCategory.$")
                if category not in {
                    "GENERAL",
                    "BRANCH",
                    "FUND",
                    "SOLE_PROPRIETOR",
                    "INTERNATIONAL_ORGANIZATION",
                    # A GLEIF category (6,955 records in the 2026-09-11 Golden
                    # Copy), once missing here, so every government record in
                    # scope was set aside as invalid, and blocking, rather than
                    # as not a Company.
                    "RESIDENT_GOVERNMENT_ENTITY",
                }:
                    raise UnsupportedRecord("invalid_identity_kind")
            if member == "reporting_exceptions":
                if value(row, "ExceptionCategory.$") not in {
                    "DIRECT_ACCOUNTING_CONSOLIDATION_PARENT",
                    "ULTIMATE_ACCOUNTING_CONSOLIDATION_PARENT",
                }:
                    raise UnsupportedRecord("unsupported_exception_category")
                if not row.get("ExceptionReason"):
                    raise UnsupportedRecord("missing_exception_reason")
                reasons = row["ExceptionReason"]
                reasons = reasons if isinstance(reasons, list) else [reasons]
                if any(
                    not isinstance(r, dict)
                    or not isinstance(r.get("$"), str)
                    or r["$"] not in EXCEPTION_REASONS
                    for r in reasons
                ):
                    raise UnsupportedRecord("invalid_exception_reason")
                # An exception is retained source evidence, not a new Company
                # binding or a fabricated parent edge.
                raise UnsupportedRecord("reported_parent_exception")
        result = normalize(
            {**row, "_native": raw},
            source_code=source_code,
            contract=contract,
            publication={**publication, "effective_at": effective},
            mapping_version=mapping_version,
        )
        return "assertion", result
    except (UnsupportedRecord, ValueError, TypeError) as exc:
        return "deferred", deferred_record(
            source_code=source_code,
            publication_key=publication["publication_key"],
            record_locator=f"{publication['artifact_sha256']}:record:{ordinal}",
            schema_version=contract["schema_version"],
            reason=exc.reason
            if isinstance(exc, UnsupportedRecord)
            else "invalid_native_field",
            raw_record=raw,
            provenance={
                "adapter_version": VERSION,
                "artifact_sha256": publication["artifact_sha256"],
            },
            probable_kind=getattr(exc, "probable_kind", None),
        )
