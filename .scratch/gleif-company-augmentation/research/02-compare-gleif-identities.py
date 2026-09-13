#!/usr/bin/env python3
"""Offline, fixed-corpus GLEIF identity comparison for Wayfinder Ticket 02.

The Level 1 Golden Copy member is streamed from its ZIP archive.  Nothing in
this script calls a network service or writes to a production system.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import re
import subprocess
import sys
import time
import unicodedata
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import orjson
from rapidfuzz.fuzz import ratio

ROOT = Path(__file__).resolve().parent
GENERATOR_VERSION = "gleif-company-identity-comparison-v1"
NORMALIZATION_VERSION = "gleif-conservative-name-address-v1"
FUZZY_THRESHOLD = 88.0
US_POSTAL_CODES = frozenset(
    ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC", "AS", "GU", "MP", "PR", "VI"]
)
LEGAL_SUFFIXES = (
    ("L", "L", "C"),
    ("L", "L", "P"),
    ("P", "L", "C"),
    ("N", "A"),
    ("S", "A"),
    ("N", "V"),
    ("INCORPORATED",),
    ("CORPORATION",),
    ("COMPANY",),
    ("LIMITED",),
    ("INC",),
    ("CORP",),
    ("CO",),
    ("LLC",),
    ("LLP",),
    ("LP",),
    ("PLC",),
    ("LTD",),
    ("LC",),
    ("NA",),
    ("NV",),
    ("SA",),
)
GENERIC_SUFFIX_BASES = frozenset({"THE", "COMPANY", "CORPORATION", "HOLDINGS", "GROUP"})
GENERIC_FUZZY_TOKENS = frozenset(
    {
        "BANK",
        "CAPITAL",
        "COMPANY",
        "CORPORATION",
        "FINANCIAL",
        "GROUP",
        "HOLDINGS",
        "INTERNATIONAL",
        "LIMITED",
        "MANAGEMENT",
        "SERVICES",
        "TRUST",
    }
)


@dataclass(frozen=True)
class NameValue:
    raw: str
    source: str
    normalized: str
    suffix_normalized: str


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def write_jsonl(path: Path, rows: Iterable[dict]) -> tuple[int, str]:
    count = 0
    digest = hashlib.sha256()
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            line = canonical_json(row) + "\n"
            handle.write(line)
            digest.update(line.encode())
            count += 1
    return count, digest.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def scalar(value: object) -> str | None:
    if isinstance(value, dict):
        value = value.get("$")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def as_list(value: object) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char)).upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", text)).strip()


def normalize_name(value: object) -> str:
    return normalize_text(value)


def suffix_normalize(value: object) -> str:
    tokens = normalize_name(value).split()
    changed = True
    while tokens and changed:
        changed = False
        for suffix in LEGAL_SUFFIXES:
            if len(tokens) > len(suffix) and tuple(tokens[-len(suffix) :]) == suffix:
                tokens = tokens[: -len(suffix)]
                changed = True
                break
    if len(tokens) > 1 and tokens[0] == "THE":
        tokens = tokens[1:]
    result = " ".join(tokens)
    if len(result) < 3 or result in GENERIC_SUFFIX_BASES:
        return normalize_name(value)
    return result


def meaningful_name_tokens(value: object) -> set[str]:
    # Callers pass an already suffix-normalized value. Re-normalizing every
    # GLEIF name here adds millions of redundant Unicode/regex passes.
    return {
        token
        for token in str(value or "").split()
        if len(token) >= 4 and token not in GENERIC_FUZZY_TOKENS
    }


def normalize_postal(value: object) -> str:
    text = re.sub(r"[^A-Z0-9]", "", normalize_text(value))
    if re.fullmatch(r"\d{5}(?:\d{4})?", text):
        return text[:5]
    return text


def normalize_region(value: object) -> str:
    text = normalize_text(value)
    if text.startswith("US ") and text[-2:] in US_POSTAL_CODES:
        return text[-2:]
    return text


def normalized_street_number(value: object) -> str | None:
    match = re.search(r"\b\d+[A-Z]?\b", normalize_text(value))
    return match.group(0) if match else None


def names_for_cohort(row: dict) -> list[NameValue]:
    raw_names: list[tuple[str, str]] = []
    for source, value in (
        ("mdm_canonical", row.get("canonical_name")),
        ("sec_current", row.get("sec_entity_name")),
    ):
        if value:
            raw_names.append((source, str(value)))
    for former in row.get("former_names") or []:
        if former.get("former_name"):
            raw_names.append(("sec_former", str(former["former_name"])))
    seen: set[tuple[str, str]] = set()
    result = []
    for source, raw in raw_names:
        key = (source, raw)
        if key in seen:
            continue
        seen.add(key)
        result.append(NameValue(raw, source, normalize_name(raw), suffix_normalize(raw)))
    return result


def names_for_gleif(entity: dict) -> list[NameValue]:
    raw_names: list[tuple[str, str]] = []
    legal = scalar(entity.get("LegalName"))
    if legal:
        raw_names.append(("gleif_legal", legal))
    other_container = entity.get("OtherEntityNames") or {}
    for item in as_list(other_container.get("OtherEntityName")):
        if not isinstance(item, dict):
            continue
        raw = scalar(item)
        if raw:
            kind = normalize_text(item.get("@type") or "OTHER")
            raw_names.append((f"gleif_other:{kind}", raw))
    translit_container = entity.get("TransliteratedOtherEntityNames") or {}
    for item in as_list(translit_container.get("TransliteratedOtherEntityName")):
        if not isinstance(item, dict):
            continue
        raw = scalar(item)
        if raw:
            raw_names.append(("gleif_transliterated", raw))
    seen: set[tuple[str, str]] = set()
    result = []
    for source, raw in raw_names:
        key = (source, raw)
        if key in seen:
            continue
        seen.add(key)
        result.append(NameValue(raw, source, normalize_name(raw), suffix_normalize(raw)))
    return result


def extract_address(raw: object, source: str) -> dict | None:
    if not isinstance(raw, dict):
        return None
    lines = [scalar(raw.get("FirstAddressLine"))]
    lines.extend(scalar(item) for item in as_list(raw.get("AdditionalAddressLine")))
    lines = [line for line in lines if line]
    result = {
        "source": source,
        "raw": {
            "lines": lines,
            "city": scalar(raw.get("City")),
            "region": scalar(raw.get("Region")),
            "country": scalar(raw.get("Country")),
            "postal_code": scalar(raw.get("PostalCode")),
        },
    }
    result["normalized"] = {
        "lines": [normalize_text(line) for line in lines],
        "city": normalize_text(result["raw"]["city"]),
        "region": normalize_region(result["raw"]["region"]),
        "country": normalize_text(result["raw"]["country"]),
        "postal_code": normalize_postal(result["raw"]["postal_code"]),
        "street_numbers": sorted(
            {number for line in lines if (number := normalized_street_number(line))}
        ),
    }
    return result


def cohort_addresses(row: dict) -> list[dict]:
    result = []
    for raw in row.get("addresses") or []:
        lines = [raw.get("street1"), raw.get("street2")]
        lines = [str(line) for line in lines if line]
        result.append(
            {
                "source": f"sec_{raw.get('address_type') or 'address'}",
                "raw": {
                    "lines": lines,
                    "city": raw.get("city"),
                    "region": raw.get("state_or_country"),
                    "country": raw.get("country"),
                    "postal_code": raw.get("zip_code"),
                },
                "normalized": {
                    "lines": [normalize_text(line) for line in lines],
                    "city": normalize_text(raw.get("city")),
                    "region": normalize_region(raw.get("state_or_country")),
                    "country": normalize_text(raw.get("country")),
                    "postal_code": normalize_postal(raw.get("zip_code")),
                    "street_numbers": sorted(
                        {number for line in lines if (number := normalized_street_number(line))}
                    ),
                },
            }
        )
    return result


def record_fields(record: dict) -> dict:
    entity = record.get("Entity") or {}
    registration = record.get("Registration") or {}
    authority = entity.get("RegistrationAuthority") or {}
    validation_authority = registration.get("ValidationAuthority") or {}
    addresses = [
        value
        for value in (
            extract_address(entity.get("LegalAddress"), "gleif_legal"),
            extract_address(entity.get("HeadquartersAddress"), "gleif_headquarters"),
        )
        if value
    ]
    return {
        "lei": scalar(record.get("LEI")),
        "names": names_for_gleif(entity),
        "addresses": addresses,
        "jurisdiction_raw": scalar(entity.get("LegalJurisdiction")),
        "jurisdiction_normalized": normalize_region(scalar(entity.get("LegalJurisdiction"))),
        "category": scalar(entity.get("EntityCategory")),
        "entity_status": scalar(entity.get("EntityStatus")),
        "registration_status": scalar(registration.get("RegistrationStatus")),
        "corroboration_level": scalar(registration.get("ValidationSources")),
        "registration_authority_id": scalar(authority.get("RegistrationAuthorityID")),
        "registration_authority_entity_id": scalar(
            authority.get("RegistrationAuthorityEntityID")
        ),
        "validation_authority_id": scalar(validation_authority.get("ValidationAuthorityID")),
        "validation_authority_entity_id": scalar(
            validation_authority.get("ValidationAuthorityEntityID")
        ),
    }


def stream_pretty_printed_records(handle) -> Iterable[dict]:
    """Stream objects from the pinned Golden Copy's top-level records array.

    The official JSON is pretty-printed with each record starting and ending at
    column zero.  Refuse unexpected non-whitespace material between records so
    a changed format fails closed rather than silently producing partial data.
    """

    in_records = False
    record_lines: list[bytes] = []
    for line in handle:
        stripped = line.rstrip(b"\r\n")
        if not in_records:
            if b'"records":[' in stripped:
                in_records = True
            continue
        if not record_lines:
            if stripped == b"{":
                record_lines.append(line)
                continue
            if stripped == b"]}" or not stripped.strip():
                continue
            raise RuntimeError(f"unexpected material between records: {stripped[:120]!r}")
        record_lines.append(line)
        if stripped == b"}]}" :
            # The official Golden Copy closes the final record, records array,
            # and top-level object on one line.
            payload = b"".join(record_lines).rstrip(b"\r\n")[:-2]
            yield orjson.loads(payload)
            record_lines.clear()
            return
        if stripped in {b"}", b"},"}:
            payload = b"".join(record_lines)
            if stripped == b"},":
                payload = payload.rstrip(b"\r\n")[:-1]
            yield orjson.loads(payload)
            record_lines.clear()
    if record_lines:
        raise RuntimeError("truncated Level 1 JSON record at end of ZIP member")
    if not in_records:
        raise RuntimeError("Level 1 JSON did not contain a records array")


def best_name_match(mdm_names: list[NameValue], gleif_names: list[NameValue]) -> dict:
    best: dict | None = None
    order = {"exact": 4, "suffix_exact": 3, "fuzzy": 2, "none": 1}
    for mdm in mdm_names:
        for gleif in gleif_names:
            if mdm.normalized and mdm.normalized == gleif.normalized:
                kind, similarity = "exact", 100.0
            elif mdm.suffix_normalized and mdm.suffix_normalized == gleif.suffix_normalized:
                kind, similarity = "suffix_exact", 100.0
            else:
                kind = "fuzzy"
                similarity = round(ratio(mdm.suffix_normalized, gleif.suffix_normalized), 4)
            former = mdm.source == "sec_former" or "PREVIOUS" in gleif.source
            candidate = {
                "kind": kind,
                "similarity": similarity,
                "uses_former_name": former,
                "mdm": {
                    "source": mdm.source,
                    "raw": mdm.raw,
                    "normalized": mdm.normalized,
                    "suffix_normalized": mdm.suffix_normalized,
                },
                "gleif": {
                    "source": gleif.source,
                    "raw": gleif.raw,
                    "normalized": gleif.normalized,
                    "suffix_normalized": gleif.suffix_normalized,
                },
            }
            key = (order[kind], similarity, not former, mdm.source, gleif.source, mdm.raw, gleif.raw)
            if best is None or key > best["_key"]:
                candidate["_key"] = key
                best = candidate
    if best is None:
        return {"kind": "none", "similarity": 0.0, "uses_former_name": False}
    best.pop("_key")
    return best


def compare_context(row: dict, gleif: dict) -> dict:
    mdm_addresses = cohort_addresses(row)
    gleif_addresses = gleif["addresses"]
    postal_match = any(
        left["normalized"]["postal_code"]
        and left["normalized"]["postal_code"] == right["normalized"]["postal_code"]
        for left in mdm_addresses
        for right in gleif_addresses
    )
    city_match = any(
        left["normalized"]["city"]
        and left["normalized"]["city"] == right["normalized"]["city"]
        for left in mdm_addresses
        for right in gleif_addresses
    )
    region_match = any(
        left["normalized"]["region"]
        and left["normalized"]["region"] == right["normalized"]["region"]
        for left in mdm_addresses
        for right in gleif_addresses
    )
    street_number_match = any(
        set(left["normalized"]["street_numbers"])
        & set(right["normalized"]["street_numbers"])
        for left in mdm_addresses
        for right in gleif_addresses
    )
    sec_jurisdiction = normalize_region(row.get("state_of_incorporation"))
    jurisdiction_comparable = sec_jurisdiction in US_POSTAL_CODES and bool(
        gleif["jurisdiction_normalized"]
    )
    jurisdiction_match = jurisdiction_comparable and gleif["jurisdiction_normalized"] in {
        sec_jurisdiction,
        f"US {sec_jurisdiction}",
    }
    jurisdiction_conflict = (
        jurisdiction_comparable
        and gleif["jurisdiction_normalized"].startswith("US ")
        and not jurisdiction_match
    )
    address_support = postal_match or (city_match and (region_match or street_number_match))
    context_dimensions = int(address_support) + int(jurisdiction_match)
    return {
        "mdm_addresses": mdm_addresses,
        "gleif_addresses": gleif_addresses,
        "postal_match": postal_match,
        "city_match": city_match,
        "region_match": region_match,
        "street_number_match": street_number_match,
        "address_support": address_support,
        "mdm_jurisdiction_raw": row.get("state_of_incorporation"),
        "mdm_jurisdiction_normalized": sec_jurisdiction,
        "gleif_jurisdiction_raw": gleif["jurisdiction_raw"],
        "gleif_jurisdiction_normalized": gleif["jurisdiction_normalized"],
        "jurisdiction_comparable": jurisdiction_comparable,
        "jurisdiction_match": jurisdiction_match,
        "jurisdiction_conflict": jurisdiction_conflict,
        "context_dimensions": context_dimensions,
    }


def classify_evidence(name: dict, context: dict, gleif: dict) -> tuple[str, dict, str]:
    exactish = name["kind"] in {"exact", "suffix_exact"}
    category_conflict = (gleif.get("category") or "GENERAL") not in {"GENERAL", ""}
    components = {
        "name_exact": name["kind"] == "exact",
        "name_suffix_exact": name["kind"] == "suffix_exact",
        "name_fuzzy": name["kind"] == "fuzzy",
        "name_similarity": name["similarity"],
        "uses_former_name": name.get("uses_former_name", False),
        "address_support": context["address_support"],
        "postal_match": context["postal_match"],
        "city_match": context["city_match"],
        "region_match": context["region_match"],
        "street_number_match": context["street_number_match"],
        "jurisdiction_match": context["jurisdiction_match"],
        "jurisdiction_conflict": context["jurisdiction_conflict"],
        "category_conflict": category_conflict,
        "proven_authority_identifier_match": False,
        "authority_identifier_comparison": "not_comparable_no_semantically_proven_shared_identifier",
    }
    score = 0
    score += {"exact": 60, "suffix_exact": 55, "fuzzy": 35}.get(name["kind"], 0)
    if name.get("uses_former_name"):
        score -= 5
    score += 20 if context["postal_match"] else 0
    score += 10 if context["city_match"] else 0
    score += 10 if context["region_match"] else 0
    score += 10 if context["street_number_match"] else 0
    score += 15 if context["jurisdiction_match"] else 0
    score -= 20 if context["jurisdiction_conflict"] else 0
    score -= 25 if category_conflict else 0
    components["aggregate_score"] = score
    if exactish and context["address_support"] and not context["jurisdiction_conflict"] and not category_conflict:
        return "B", components, "strong_multi_attribute_review"
    if (
        (exactish and (context["jurisdiction_match"] or context["city_match"] or context["postal_match"]))
        or (
            name["kind"] == "fuzzy"
            and name["similarity"] >= FUZZY_THRESHOLD
            and context["address_support"]
        )
    ) and not category_conflict:
        return "C", components, "contextual_manual_review"
    if category_conflict:
        return "D", components, "entity_category_conflict"
    if context["jurisdiction_conflict"]:
        return "D", components, "jurisdiction_conflict"
    return "D", components, "name_only_or_insufficient_context"


def indexes(
    cohort: list[dict],
) -> tuple[dict, dict, dict, dict, dict, dict[int, list[NameValue]]]:
    exact: dict[str, set[int]] = collections.defaultdict(set)
    suffix: dict[str, set[int]] = collections.defaultdict(set)
    cities: dict[str, set[int]] = collections.defaultdict(set)
    postals: dict[str, set[int]] = collections.defaultdict(set)
    tokens: dict[str, set[int]] = collections.defaultdict(set)
    names: dict[int, list[NameValue]] = {}
    for row in cohort:
        ordinal = int(row["cohort_ordinal"])
        names[ordinal] = names_for_cohort(row)
        for value in names[ordinal]:
            if value.normalized:
                exact[value.normalized].add(ordinal)
            if value.suffix_normalized:
                suffix[value.suffix_normalized].add(ordinal)
            for token in meaningful_name_tokens(value.suffix_normalized):
                tokens[token].add(ordinal)
        for address in cohort_addresses(row):
            if city := address["normalized"]["city"]:
                cities[city].add(ordinal)
            if postal := address["normalized"]["postal_code"]:
                postals[postal].add(ordinal)
    return exact, suffix, cities, postals, tokens, names


def scan_candidates(
    cohort: list[dict], archive_path: Path, expected_records: int
) -> tuple[list[dict], dict]:
    by_ordinal = {int(row["cohort_ordinal"]): row for row in cohort}
    exact, suffix, cities, postals, tokens, mdm_names = indexes(cohort)
    candidates: list[dict] = []
    records_scanned = 0
    malformed_lei = 0
    started = time.monotonic()
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) != 1:
            raise RuntimeError(f"expected one Level 1 member, found {len(members)}")
        member_name = members[0].filename
    # Decompress in a separate process so DEFLATE and JSON parsing use separate
    # CPU cores. The byte stream is identical to ZipFile.open(); no extraction
    # or intermediate uncompressed file is created.
    process = subprocess.Popen(
        ["unzip", "-p", str(archive_path), member_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdout is None or process.stderr is None:
        raise RuntimeError("failed to open streaming unzip pipes")
    try:
        with process.stdout as handle:
            for record in stream_pretty_printed_records(handle):
                records_scanned += 1
                gleif = record_fields(record)
                lei = gleif["lei"]
                if not lei or not re.fullmatch(r"[A-Z0-9]{20}", lei):
                    malformed_lei += 1
                    continue
                ordinals: set[int] = set()
                exact_ordinals: set[int] = set()
                for name in gleif["names"]:
                    exact_ordinals.update(exact.get(name.normalized, ()))
                    exact_ordinals.update(suffix.get(name.suffix_normalized, ()))
                ordinals.update(exact_ordinals)
                context_ordinals: set[int] = set()
                for address in gleif["addresses"]:
                    if city := address["normalized"]["city"]:
                        context_ordinals.update(cities.get(city, ()))
                    if postal := address["normalized"]["postal_code"]:
                        context_ordinals.update(postals.get(postal, ()))
                token_ordinals: set[int] = set()
                for name in gleif["names"]:
                    for token in meaningful_name_tokens(name.suffix_normalized):
                        token_ordinals.update(tokens.get(token, ()))
                fuzzy_name_matches = {}
                for ordinal in (context_ordinals & token_ordinals) - exact_ordinals:
                    name = best_name_match(mdm_names[ordinal], gleif["names"])
                    if name["kind"] == "fuzzy" and name["similarity"] >= FUZZY_THRESHOLD:
                        ordinals.add(ordinal)
                        fuzzy_name_matches[ordinal] = name
                for ordinal in sorted(ordinals):
                    row = by_ordinal[ordinal]
                    name = fuzzy_name_matches.get(ordinal) or best_name_match(
                        mdm_names[ordinal], gleif["names"]
                    )
                    context = compare_context(row, gleif)
                    tier, components, reason = classify_evidence(name, context, gleif)
                    candidate_id = digest_text(
                        f"{GENERATOR_VERSION}|{row['entity_id']}|{lei}"
                    )
                    candidates.append(
                        {
                            "candidate_id": candidate_id,
                            "comparison_run_id": None,
                            "generator_version": GENERATOR_VERSION,
                            "normalization_version": NORMALIZATION_VERSION,
                            "cohort_ordinal": ordinal,
                            "cohort_stratum": row["cohort_stratum"],
                            "mdm_entity_id": row["entity_id"],
                            "cik": int(row["cik"]),
                            "lei": lei,
                            "candidate_rank": None,
                            "evidence_tier": tier,
                            "generator_reason_code": reason,
                            "name_comparison": name,
                            "context_comparison": context,
                            "score_components": components,
                            "mdm_raw": {
                                "canonical_name": row.get("canonical_name"),
                                "sec_entity_name": row.get("sec_entity_name"),
                                "former_names": row.get("former_names") or [],
                                "state_of_incorporation": row.get("state_of_incorporation"),
                                "addresses": row.get("addresses") or [],
                                "ticker": row.get("ticker"),
                                "sic_code": row.get("sic_code"),
                            },
                            "gleif_raw": {
                                "names": [
                                    {"source": value.source, "raw": value.raw}
                                    for value in gleif["names"]
                                ],
                                "addresses": [address["raw"] | {"source": address["source"]} for address in gleif["addresses"]],
                                "jurisdiction": gleif["jurisdiction_raw"],
                                "category": gleif["category"],
                                "entity_status": gleif["entity_status"],
                                "registration_status": gleif["registration_status"],
                                "corroboration_level": gleif["corroboration_level"],
                                "registration_authority_id": gleif["registration_authority_id"],
                                "registration_authority_entity_id": gleif[
                                    "registration_authority_entity_id"
                                ],
                                "validation_authority_id": gleif["validation_authority_id"],
                                "validation_authority_entity_id": gleif[
                                    "validation_authority_entity_id"
                                ],
                            },
                        }
                    )
                if records_scanned % 250_000 == 0:
                    elapsed = time.monotonic() - started
                    print(
                        f"scanned={records_scanned:,} candidates={len(candidates):,} elapsed={elapsed:.1f}s",
                        file=sys.stderr,
                        flush=True,
                    )
                # The Golden Copy carries footer metadata after the records
                # array. Ticket 01 already verified the archive SHA and CRC;
                # stop at the publication's declared record count so footer
                # objects cannot be mistaken for LEI records.
                if records_scanned == expected_records:
                    break
        stderr = process.stderr.read().decode(errors="replace")
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(
                f"streaming unzip failed with status {return_code}: {stderr[-2000:]}"
            )
    except BaseException:
        process.terminate()
        process.wait()
        raise
    finally:
        process.stderr.close()
    if records_scanned != expected_records:
        raise RuntimeError(
            f"record count mismatch: scanned={records_scanned} expected={expected_records}"
        )
    candidates.sort(
        key=lambda item: (
            item["cohort_ordinal"],
            -item["score_components"]["aggregate_score"],
            item["lei"],
        )
    )
    run_id = digest_text(
        f"{GENERATOR_VERSION}|{sha256(ROOT / '01-company-cohort-1000.jsonl')}|{sha256(archive_path)}"
    )[:32]
    ranks: collections.Counter[int] = collections.Counter()
    for candidate in candidates:
        ordinal = candidate["cohort_ordinal"]
        ranks[ordinal] += 1
        candidate["candidate_rank"] = ranks[ordinal]
        candidate["comparison_run_id"] = run_id
    return candidates, {
        "records_scanned": records_scanned,
        "malformed_lei_records": malformed_lei,
        "candidate_rows": len(candidates),
        "cohort_rows_with_candidates": len(ranks),
        "comparison_run_id": run_id,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> dict | None:
    if total == 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return {"lower": centre - margin, "upper": centre + margin, "method": "wilson_95"}


def finalize(
    cohort: list[dict], candidates: list[dict], decisions_path: Path, output_dir: Path
) -> tuple[list[dict], list[dict], dict]:
    decisions = read_jsonl(decisions_path)
    by_candidate = {row["candidate_id"]: row for row in decisions}
    candidate_ids = {row["candidate_id"] for row in candidates}
    if len(decisions) != len(by_candidate) or set(by_candidate) != candidate_ids:
        missing = sorted(candidate_ids - set(by_candidate))
        extra = sorted(set(by_candidate) - candidate_ids)
        raise RuntimeError(
            f"decision coverage mismatch decisions={len(decisions)} candidates={len(candidates)} "
            f"missing={len(missing)} extra={len(extra)}"
        )
    allowed = {"same_legal_entity", "different_legal_entity", "unresolved"}
    reviewed_candidates = []
    for candidate in candidates:
        decision = by_candidate[candidate["candidate_id"]]
        if decision.get("candidate_disposition") not in allowed:
            raise RuntimeError(f"invalid candidate disposition for {candidate['candidate_id']}")
        reviewed_candidates.append(candidate | {"manual_review": decision})

    grouped: dict[int, list[dict]] = collections.defaultdict(list)
    for candidate in reviewed_candidates:
        grouped[candidate["cohort_ordinal"]].append(candidate)
    dispositions = []
    for row in cohort:
        ordinal = int(row["cohort_ordinal"])
        rows = grouped.get(ordinal, [])
        same = [item for item in rows if item["manual_review"]["candidate_disposition"] == "same_legal_entity"]
        unresolved = [item for item in rows if item["manual_review"]["candidate_disposition"] == "unresolved"]
        if not rows:
            disposition = "no_candidate"
            reason = "no_candidate"
            accepted_lei = None
        elif len(same) == 1 and not unresolved:
            disposition = "accepted_same_legal_entity"
            reason = same[0]["manual_review"]["reason_code"]
            accepted_lei = same[0]["lei"]
        elif not same and not unresolved:
            disposition = "rejected_different"
            reason = "all_candidates_different_legal_entity"
            accepted_lei = None
        else:
            disposition = "unresolved"
            reason = "ambiguous_or_insufficient_evidence"
            accepted_lei = None
        dispositions.append(
            {
                "comparison_run_id": candidates[0]["comparison_run_id"] if candidates else None,
                "cohort_ordinal": ordinal,
                "cohort_stratum": row["cohort_stratum"],
                "mdm_entity_id": row["entity_id"],
                "cik": int(row["cik"]),
                "mdm_canonical_name": row.get("canonical_name"),
                "candidate_count": len(rows),
                "accepted_lei": accepted_lei,
                "disposition": disposition,
                "reason_code": reason,
            }
        )

    def metric(rows: list[dict]) -> dict:
        total = len(rows)
        counts = collections.Counter(row["disposition"] for row in rows)
        result = {"total": total, "counts": dict(sorted(counts.items()))}
        for key in (
            "accepted_same_legal_entity",
            "rejected_different",
            "unresolved",
            "no_candidate",
        ):
            result[key] = {
                "count": counts[key],
                "rate": counts[key] / total if total else None,
                "confidence_interval": wilson(counts[key], total),
            }
        candidate_count = sum(row["candidate_count"] > 0 for row in rows)
        multi_count = sum(row["candidate_count"] > 1 for row in rows)
        result["candidate_rate"] = {
            "count": candidate_count,
            "rate": candidate_count / total if total else None,
            "confidence_interval": wilson(candidate_count, total),
        }
        result["multi_candidate_rate"] = {
            "count": multi_count,
            "rate": multi_count / total if total else None,
            "confidence_interval": wilson(multi_count, total),
        }
        return result

    by_stratum = {
        stratum: metric([row for row in dispositions if row["cohort_stratum"] == stratum])
        for stratum in sorted({row["cohort_stratum"] for row in dispositions})
    }
    candidate_decision_counts = collections.Counter(
        row["manual_review"]["candidate_disposition"] for row in reviewed_candidates
    )
    accepted_by_tier = collections.Counter(
        row["evidence_tier"]
        for row in reviewed_candidates
        if row["manual_review"]["candidate_disposition"] == "same_legal_entity"
    )
    reviewed_by_tier = collections.Counter(row["evidence_tier"] for row in reviewed_candidates)
    precision_by_tier = {
        tier: {
            "accepted": accepted_by_tier[tier],
            "reviewed": reviewed_by_tier[tier],
            "precision": accepted_by_tier[tier] / reviewed_by_tier[tier],
            "confidence_interval": wilson(accepted_by_tier[tier], reviewed_by_tier[tier]),
        }
        for tier in sorted(reviewed_by_tier)
    }
    summary = {
        "summary_version": "gleif-company-identity-summary-v1",
        "comparison_run_id": candidates[0]["comparison_run_id"] if candidates else None,
        "cohort_rows": len(cohort),
        "candidate_rows": len(reviewed_candidates),
        "candidate_manual_disposition_counts": dict(sorted(candidate_decision_counts.items())),
        "overall": metric(dispositions),
        "by_stratum": by_stratum,
        "precision_by_evidence_tier": precision_by_tier,
        "duplicate_candidate_pairs": len(reviewed_candidates)
        - len({(row["mdm_entity_id"], row["lei"]) for row in reviewed_candidates}),
        "duplicate_accepted_leis": sum(
            count - 1
            for count in collections.Counter(
                row["accepted_lei"] for row in dispositions if row["accepted_lei"]
            ).values()
            if count > 1
        ),
        "confidence_interval_note": (
            "Wilson 95% intervals describe each selected stratum. The fixed stratified cohort is "
            "not a simple random sample, so no population-wide inference is claimed."
        ),
    }
    return reviewed_candidates, dispositions, summary


def self_test() -> None:
    import io

    assert normalize_name("Coca-Cola Co.") == "COCA COLA CO"
    assert suffix_normalize("The Coca-Cola Company") == "COCA COLA"
    assert suffix_normalize("COCA COLA CO") == "COCA COLA"
    assert suffix_normalize("ADT, Inc.") == "ADT"
    assert normalize_postal("30313-2420") == "30313"
    assert normalize_region("US-DE") == "DE"
    records = list(
        stream_pretty_printed_records(
            io.BytesIO(b'{"records":[\n{\n  "LEI": {"$": "ONE"}\n},\n{\n  "LEI": {"$": "TWO"}\n}\n]}')
        )
    )
    assert [scalar(row["LEI"]) for row in records] == ["ONE", "TWO"]
    final_line_records = list(
        stream_pretty_printed_records(
            io.BytesIO(b'{"records":[\n{\n  "LEI": {"$": "ONE"}\n}]}')
        )
    )
    assert [scalar(row["LEI"]) for row in final_line_records] == ["ONE"]
    print("self-test passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT)
    parser.add_argument("--finalize-decisions", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cohort_path = ROOT / "01-company-cohort-1000.jsonl"
    manifest = json.loads((ROOT / "01-gleif-snapshot-manifest.json").read_text())
    level1 = next(item for item in manifest["files"] if item["family"] == "lei2")
    archive_path = ROOT / level1["local_file"]
    if sha256(cohort_path) != "33af2a7df8a02a0838bc2b19a72c75dbe7552e7ba73b9004862f1ae3e18f367f":
        raise RuntimeError("frozen cohort digest does not match Ticket 01")
    if sha256(archive_path) != level1["sha256"]:
        raise RuntimeError("Level 1 archive digest does not match frozen manifest")
    cohort = read_jsonl(cohort_path)
    if len(cohort) != 1000:
        raise RuntimeError(f"expected 1,000 cohort rows, found {len(cohort)}")
    candidates, scan = scan_candidates(
        cohort, archive_path, int(level1["record_count"])
    )
    generated_path = output_dir / "02-generated-candidates.jsonl"
    generated_rows, generated_hash = write_jsonl(generated_path, candidates)
    generation_manifest = {
        "manifest_version": "gleif-company-identity-generation-v1",
        "generator_version": GENERATOR_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "candidate_rules": {
            "exact_normalized_name": True,
            "conservative_legal_suffix_normalized_name": True,
            "fuzzy_threshold": FUZZY_THRESHOLD,
            "fuzzy_requires_exact_city_or_postal_block": True,
            "fuzzy_requires_shared_meaningful_name_token": True,
            "name_only_acceptance": False,
            "authority_identifiers_used": [],
            "authority_identifier_note": (
                "No semantically proven identifier shared by the frozen MDM cohort and GLEIF "
                "Level 1 was available; CIK was not compared with registeredAs."
            ),
        },
        "inputs": {
            "cohort_file": cohort_path.name,
            "cohort_sha256": sha256(cohort_path),
            "level1_file": archive_path.name,
            "level1_sha256": sha256(archive_path),
            "level1_member": zipfile.ZipFile(archive_path).infolist()[0].filename,
            "level1_declared_records": level1["record_count"],
            "publication_utc": manifest["publication_utc"],
        },
        "scan": scan,
        "generated_candidates": {
            "file": generated_path.name,
            "rows": generated_rows,
            "sha256": generated_hash,
        },
    }
    (output_dir / "02-generation-manifest.json").write_text(
        canonical_json(generation_manifest) + "\n", encoding="utf-8"
    )
    if args.finalize_decisions:
        reviewed, dispositions, summary = finalize(
            cohort, candidates, args.finalize_decisions.resolve(), output_dir
        )
        reviewed_count, reviewed_hash = write_jsonl(
            output_dir / "02-reviewed-candidates.jsonl", reviewed
        )
        disposition_count, disposition_hash = write_jsonl(
            output_dir / "02-cohort-dispositions.jsonl", dispositions
        )
        summary["artifact_hashes"] = {
            "02-reviewed-candidates.jsonl": {
                "rows": reviewed_count,
                "sha256": reviewed_hash,
            },
            "02-cohort-dispositions.jsonl": {
                "rows": disposition_count,
                "sha256": disposition_hash,
            },
            args.finalize_decisions.name: {
                "rows": len(read_jsonl(args.finalize_decisions.resolve())),
                "sha256": sha256(args.finalize_decisions.resolve()),
            },
        }
        (output_dir / "02-identity-summary.json").write_text(
            canonical_json(summary) + "\n", encoding="utf-8"
        )
    print(json.dumps(generation_manifest, indent=2))


if __name__ == "__main__":
    main()
