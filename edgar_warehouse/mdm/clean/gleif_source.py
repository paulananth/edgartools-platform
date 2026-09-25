"""Bounded native GLEIF archives. Parsing grants no identity/binding authority."""

from __future__ import annotations

import hashlib
import tempfile
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from typing import IO, BinaryIO

import ijson
from lxml import etree

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
XML = {
    "level1": ("leidata", "LEIData", "LEIHeader", "LEIRecords", "LEIRecord"),
    "relationships": (
        "rr",
        "RelationshipData",
        "Header",
        "RelationshipRecords",
        "RelationshipRecord",
    ),
    "reporting_exceptions": (
        "repex",
        "ReportingExceptionData",
        "Header",
        "ReportingExceptions",
        "Exception",
    ),
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


class _BoundedReader:
    def __init__(self, stream: IO[bytes], maximum: int, record_limit: int):
        self.stream, self.maximum, self.record_limit = stream, maximum, record_limit
        self.total = self.since_record = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise Conflict("Unbounded native source read")
        raw = self.stream.read(min(size, 65536))
        self.total += len(raw)
        self.since_record += len(raw)
        if self.total > self.maximum or self.since_record > self.record_limit + 65536:
            raise Conflict("GLEIF expanded file or record exceeds bound")
        return raw


def _json_records(stream: _BoundedReader, wrapper: str):
    events = iter(ijson.basic_parse(stream, use_float=True))

    def expect(event, value=None):
        if next(events) != (event, value):
            raise Conflict("Unexpected GLEIF JSON structure")

    def value(first, depth=0):
        if depth > 64:
            raise Conflict("GLEIF nesting exceeds bound")
        event, item = first
        if event == "start_map":
            result = {}
            while (entry := next(events))[0] != "end_map":
                if entry[0] != "map_key" or entry[1] in result:
                    raise Conflict("Duplicate or invalid GLEIF JSON key")
                result[entry[1]] = value(next(events), depth + 1)
            return result
        if event == "start_array":
            items = []
            while (entry := next(events))[0] != "end_array":
                items.append(value(entry, depth + 1))
            return items
        if event not in {"string", "number", "boolean", "null"}:
            raise Conflict("Invalid GLEIF JSON value")
        return item

    expect("start_map")
    expect("map_key", wrapper)
    expect("start_array")
    while (entry := next(events))[0] != "end_array":
        if entry[0] != "start_map":
            raise Conflict("Native GLEIF record must be an object")
        record = value(entry)
        stream.since_record = 0
        yield record
    expect("end_map")
    if next(events, None) is not None:
        raise Conflict("Trailing GLEIF JSON data")


def _xml_value(node, namespace):
    result = {"@" + key: val for key, val in node.attrib.items()}
    for child in node:
        if not isinstance(child.tag, str):
            raise Conflict("GLEIF XML entities are unsupported")
        key = child.tag.removeprefix("{" + namespace + "}")
        value = _xml_value(child, namespace)
        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]
            result[key].append(value)
        else:
            result[key] = value
    if node.text and node.text.strip():
        result["$"] = node.text.strip()
    return result


def _xml_records(stream, member, metadata):
    namespace, root_name, header_name, container, record_name = XML[member]
    namespace = f"http://www.gleif.org/data/schema/{namespace}/2016"
    tags = [
        f"{{{namespace}}}{n}" for n in (root_name, header_name, container, record_name)
    ]
    parser = etree.XMLPullParser(
        events=("start", "end"),
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        huge_tree=False,
        remove_comments=True,
    )
    root = None
    header_seen = container_seen = False
    while raw := stream.read(65536):
        parser.feed(raw)
        for event, node in parser.read_events():
            if root is None:
                root = node
                if node.tag != tags[0] or node.getroottree().docinfo.doctype:
                    raise Conflict("Invalid GLEIF XML root/namespace or DTD")
            if event == "start" and node.getparent() is root:
                if node.tag == tags[1]:
                    if header_seen or container_seen:
                        raise Conflict("Duplicate/misplaced GLEIF XML header")
                elif node.tag == tags[2]:
                    if not header_seen or container_seen:
                        raise Conflict("Invalid GLEIF XML record container")
                    container_seen = True
                else:
                    raise Conflict("Unexpected GLEIF XML top-level element")
            if event != "end":
                continue
            if node.tag == tags[1] and node.getparent() is root:
                header = _xml_value(node, namespace)
                expected = {
                    "ContentDate": metadata["content_date"],
                    "FileContent": metadata["file_content"],
                    "RecordCount": str(metadata["record_count"]),
                    "DeltaStart": metadata.get("delta_start"),
                }
                for key, wanted in expected.items():
                    if not isinstance(header.get(key, {}), dict):
                        raise Conflict("Duplicate GLEIF XML header field")
                    actual = header.get(key, {}).get("$")
                    if key in {"ContentDate", "DeltaStart"} and actual and wanted:
                        actual, wanted = instant(actual), instant(wanted)
                    if actual != wanted:
                        raise Conflict(
                            "GLEIF XML header disagrees with pinned metadata"
                        )
                header_seen = True
                node.clear()
                stream.since_record = 0
            elif node.getparent() is not None and node.getparent().tag == tags[2]:
                if node.tag != tags[3]:
                    raise Conflict("Unexpected GLEIF XML record")
                value = _xml_value(node, namespace)
                # Native JSON RR uses one additional wrapper; normalize both.
                yield (
                    {"RelationshipRecord": value}
                    if member == "relationships"
                    else value
                )
                stream.since_record = 0
                node.clear()
                while node.getprevious() is not None:
                    del node.getparent()[0]
    parser.close()
    if not header_seen or not container_seen:
        raise Conflict("Incomplete GLEIF XML header/container")


def inspect_archive(
    stream: BinaryIO,
    *,
    member: str,
    metadata: dict,
    expected_sha256: str,
    on_record: Callable[[dict, int], None] | None = None,
    max_compressed: int = 1024**3,
    max_expanded: int = 16 * 1024**3,
    max_record: int = 1024**2,
) -> dict:
    """Verify through EOF. Callbacks may prepare evidence, never commit it.

    JSON metadata must come from the verified publication manifest. It is not
    inferred from the ZIP filename. A private compressed snapshot prevents a
    changed file between hashing and parsing from authenticating different bytes.
    """
    validate_metadata(member, metadata)
    sha, size, count = hashlib.sha256(), 0, 0
    content = hashlib.sha256()
    with tempfile.TemporaryFile() as snapshot:
        while raw := stream.read(1024**2):
            size += len(raw)
            if size > max_compressed:
                raise Conflict("GLEIF compressed size exceeds bound")
            snapshot.write(raw)
            sha.update(raw)
        if sha.hexdigest() != expected_sha256:
            raise Conflict("GLEIF archive hash mismatch")
        snapshot.seek(0)
        try:
            with zipfile.ZipFile(snapshot) as archive:
                files = archive.infolist()
                if len(files) != 1 or files[0].is_dir() or files[0].flag_bits & 1:
                    raise Conflict("GLEIF requires one unencrypted ZIP member")
                if files[0].file_size > max_expanded:
                    raise Conflict("GLEIF expanded size exceeds bound")
                with archive.open(files[0]) as source:
                    bounded = _BoundedReader(source, max_expanded, max_record)
                    records = (
                        _json_records(bounded, FORMATS[member][1])
                        if metadata["format"] == "json.zip"
                        else _xml_records(bounded, member, metadata)
                    )
                    for row in records:
                        encoded = canonical(row).encode()
                        if len(encoded) > max_record:
                            raise Conflict("GLEIF record exceeds bound")
                        content.update(encoded + b"\n")
                        if count >= metadata["record_count"]:
                            raise Conflict("GLEIF record count mismatch")
                        if on_record:
                            on_record(row, count)
                        count += 1
                    if (
                        count != metadata["record_count"]
                        or bounded.total != files[0].file_size
                    ):
                        raise Conflict("GLEIF record count or expanded length mismatch")
        except (
            zipfile.BadZipFile,
            ijson.JSONError,
            etree.XMLSyntaxError,
            StopIteration,
            ValueError,
        ) as exc:
            raise Conflict(f"Invalid GLEIF archive: {exc}") from exc
    return {
        "adapter_version": VERSION,
        "raw_evidence_hash": sha.hexdigest(),
        "canonical_source_hash": content.hexdigest(),
        "record_count": count,
        # All native record content remains domain evidence, including fields
        # with no approved master projection. The tagged interpretation retains
        # those facts without hashing ZIP paths, timestamps or compression.
        "domain_content_hash": hashlib.sha256(
            f"{VERSION}\n{member}\n{content.hexdigest()}".encode()
        ).hexdigest(),
        "compressed_bytes": size,
        "expanded_bytes": bounded.total,
    }


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


def dataset_contract(member: str, *, level1_source: str = "gleif.level1.v1") -> dict:
    """Governance input, not registration or activation. Field ranks live in policy."""
    mapping: dict = {
        "version": VERSION,
        "native_member": member,
        "retain_deferred": True,
        "source_record_provenance": True,
        "field_shape": "nullable_text",
        "fields": {},
        "provenance": {"native_record": "_native"},
    }
    if member == "level1":
        mapping.update(
            kind_field="Entity.EntityCategory.$",
            kind_values={"GENERAL": "company"},
            # What a record in each other GLEIF category probably is, so the
            # Stage can sort it; none of these creates an identity. A sole
            # proprietor is left unnamed: it is not settled as Person.
            probable_kind_values={
                "FUND": "fund_structure",
                "BRANCH": "branch",
                "RESIDENT_GOVERNMENT_ENTITY": "government",
                "INTERNATIONAL_ORGANIZATION": "international_organization",
            },
            record_key=["LEI.$"],
            record_key_format="lei",
            identifiers={"lei": "LEI.$"},
            identifier_formats={"lei": "lei"},
        )
        mapping["fields"] = {
            # `name` is shared with SEC, SEC first where both supply it.
            # `jurisdiction` is GLEIF's alone; SEC gives state of incorporation
            # as its own field (operator, 2026-09-24).
            "name": "Entity.LegalName.$",
            "address": {
                "components": {
                    "street": "Entity.LegalAddress.FirstAddressLine.$",
                    "city": "Entity.LegalAddress.City.$",
                    "region": "Entity.LegalAddress.Region.$",
                    "postcode": "Entity.LegalAddress.PostalCode.$",
                    "country": "Entity.LegalAddress.Country.$",
                }
            },
            "jurisdiction": "Entity.LegalJurisdiction.$",
            "gleif_legal_form": "Entity.LegalForm.EntityLegalFormCode.$",
            "gleif_entity_status": "Entity.EntityStatus.$",
            "gleif_registration_status": "Registration.RegistrationStatus.$",
            "gleif_initial_registration": "Registration.InitialRegistrationDate.$",
            "gleif_last_update": "Registration.LastUpdateDate.$",
            "gleif_next_renewal": "Registration.NextRenewalDate.$",
            "gleif_managing_lou": "Registration.ManagingLOU.$",
            "gleif_validation_source": "Registration.ValidationSources.$",
            "gleif_registration_authority": "Entity.RegistrationAuthority.RegistrationAuthorityID.$",
            "gleif_registration_authority_entity_id": "Entity.RegistrationAuthority.RegistrationAuthorityEntityID.$",
            "gleif_entity_creation_date": "Entity.EntityCreationDate.$",
        }
        # What the SEC-to-GLEIF matching rules compare; not Company fields
        # (ticket 08). The headquarters address, never a registered agent's.
        mapping["matching"] = {
            "headquarters_postal_code": "Entity.HeadquartersAddress.PostalCode.$",
            "headquarters_country": "Entity.HeadquartersAddress.Country.$",
        }
    elif member == "relationships":
        mapping.update(
            kind="company",
            record_key=["start", "end", "relationship_type"],
            relationships=[
                {
                    "type_field": "relationship_type",
                    "type_values": {
                        "IS_DIRECTLY_CONSOLIDATED_BY": "IS_DIRECTLY_CONSOLIDATED_BY",
                        "IS_ULTIMATELY_CONSOLIDATED_BY": "IS_ULTIMATELY_CONSOLIDATED_BY",
                    },
                    "target_key": ["end"],
                    "target_source": level1_source,
                    "valid_from": "valid_from",
                    "valid_to": "valid_to",
                    "scope": "GLEIF accounting consolidation",
                    "properties": {
                        "source_relationship_status": "status",
                        "source_registration_status": "registration_status",
                    },
                }
            ],
        )
    elif member == "reporting_exceptions":
        mapping.update(kind="company", record_key=["LEI.$", "ExceptionCategory.$"])
    else:
        raise ValueError("Unknown native GLEIF member")
    return {
        "provider": "GLEIF",
        "nonblocking_deferred_reasons": [
            "outside_approved_company_scope",
            "unsupported_identity_kind",
            "reported_parent_exception",
        ],
        "family": "gleif",
        "schema_version": VERSION,
        "publication_families": ["golden_copy"],
        "record_key": "native LEI or composite source key",
        "publication_key": "verified GLEIF release",
        "effective_time": "LastUpdateDate or unknown",
        "semantics": "patch; absence never retires an identity",
        "adapter": mapping,
    }


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
