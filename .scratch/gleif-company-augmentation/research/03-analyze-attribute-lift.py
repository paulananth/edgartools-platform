#!/usr/bin/env python3
"""Measure GLEIF Level 1 lift for Ticket 02's accepted Company links."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


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


def nested(value: object, *keys: str) -> object | None:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char)).upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", text)).strip()


def values_under(value: object, key_names: set[str]) -> list[object]:
    result: list[object] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in key_names:
                result.extend(as_list(child))
            result.extend(values_under(child, key_names))
    elif isinstance(value, list):
        for child in value:
            result.extend(values_under(child, key_names))
    return result


def iso_datetime(value: object) -> datetime | None:
    text = scalar(value)
    if not text:
        return None
    return datetime.fromisoformat(text)


def selected_candidates() -> list[dict]:
    dispositions = read_jsonl(ROOT / "02-cohort-dispositions.jsonl")
    accepted = {
        (row["mdm_entity_id"], row["accepted_lei"])
        for row in dispositions
        if row["disposition"] == "accepted_same_legal_entity"
    }
    candidates = [
        row
        for row in read_jsonl(ROOT / "02-reviewed-candidates.jsonl")
        if (row["mdm_entity_id"], row["lei"]) in accepted
    ]
    if len(candidates) != 308:
        raise RuntimeError(f"expected 308 accepted candidate rows, found {len(candidates)}")
    return candidates


def extracted_records() -> dict[str, dict]:
    rows = read_jsonl(ROOT / "03-accepted-level1-records.jsonl")
    result = {}
    for row in rows:
        record = row["record"]
        lei = scalar(record.get("LEI"))
        if not lei or lei in result:
            raise RuntimeError(f"missing or duplicate extracted LEI: {lei}")
        result[lei] = record
    return result


def classify(candidate: dict, record: dict) -> dict:
    entity = record.get("Entity") or {}
    registration = record.get("Registration") or {}
    legal_form = entity.get("LegalForm") or {}
    other_names = candidate["gleif_raw"]["names"][1:]
    gleif_other_normalized = {normalize_text(row["raw"]) for row in other_names}
    mdm_former_normalized = {
        normalize_text(row.get("former_name"))
        for row in candidate["mdm_raw"]["former_names"]
        if row.get("former_name")
    }
    shared_other_names = gleif_other_normalized & mdm_former_normalized
    new_other_names = gleif_other_normalized - mdm_former_normalized
    if not gleif_other_normalized:
        other_name_class = "missing_in_gleif"
    elif not mdm_former_normalized:
        other_name_class = "missing_in_mdm"
    elif shared_other_names and not new_other_names:
        other_name_class = "equal"
    elif shared_other_names:
        other_name_class = "compatible"
    else:
        other_name_class = "different"
    event_values = values_under(
        entity,
        {"LegalEntityEvent", "LegalEntityEventGroup"},
    )
    successor_values = values_under(
        entity,
        {"SuccessorEntity", "SuccessorEntityReference"},
    )
    last_update = iso_datetime(registration.get("LastUpdateDate"))
    publication = datetime.fromisoformat("2026-09-11T16:00:00+00:00")
    age_days = (publication - last_update).days if last_update else None
    name_kind = candidate["name_comparison"]["kind"]
    name_class = {
        "exact": "equal",
        "suffix_exact": "compatible",
        "fuzzy": "different_supported_identity",
    }.get(name_kind, "not_comparable")
    context = candidate["context_comparison"]
    if context["jurisdiction_comparable"]:
        if context["jurisdiction_match"]:
            jurisdiction_class = "equal"
        elif context["gleif_jurisdiction_normalized"] == "US":
            jurisdiction_class = "compatible"
        else:
            jurisdiction_class = "different"
    else:
        jurisdiction_class = "not_comparable"
    return {
        "mdm_entity_id": candidate["mdm_entity_id"],
        "cik": candidate["cik"],
        "lei": candidate["lei"],
        "cohort_stratum": candidate["cohort_stratum"],
        "legal_name": {"classification": name_class, "match_kind": name_kind},
        "other_names": {
            "classification": other_name_class,
            "count": len(other_names),
            "shared_with_sec_former_names": len(shared_other_names),
            "new_to_mdm": len(new_other_names),
        },
        "legal_address": {
            "classification": "compatible" if context["address_support"] else "not_comparable",
            "present": any(
                item["source"] == "gleif_legal" for item in candidate["gleif_raw"]["addresses"]
            ),
        },
        "headquarters_address": {
            "classification": "compatible" if context["address_support"] else "not_comparable",
            "present": any(
                item["source"] == "gleif_headquarters"
                for item in candidate["gleif_raw"]["addresses"]
            ),
        },
        "legal_jurisdiction": {
            "classification": jurisdiction_class,
            "value": scalar(entity.get("LegalJurisdiction")),
        },
        "legal_form": {
            "classification": "missing_in_mdm" if legal_form else "missing_in_gleif",
            "code": scalar(legal_form.get("EntityLegalFormCode")),
            "other": scalar(legal_form.get("OtherLegalForm")),
        },
        "entity_status": {
            "classification": "not_comparable",
            "value": scalar(entity.get("EntityStatus")),
        },
        "entity_creation_date": {
            "classification": "missing_in_mdm"
            if scalar(entity.get("EntityCreationDate"))
            else "missing_in_gleif",
            "value": scalar(entity.get("EntityCreationDate")),
        },
        "entity_expiration": {
            "classification": "missing_in_mdm"
            if scalar(entity.get("EntityExpirationDate"))
            else "missing_in_gleif",
            "date": scalar(entity.get("EntityExpirationDate")),
            "reason": scalar(entity.get("EntityExpirationReason")),
        },
        "successors": {
            "classification": "missing_in_mdm" if successor_values else "missing_in_gleif",
            "count": len(successor_values),
        },
        "legal_entity_events": {
            "classification": "missing_in_mdm" if event_values else "missing_in_gleif",
            "count": len(event_values),
        },
        "registration_authority_identifier": {
            "classification": "missing_in_mdm"
            if candidate["gleif_raw"]["registration_authority_entity_id"]
            else "missing_in_gleif",
            "value": candidate["gleif_raw"]["registration_authority_entity_id"],
        },
        "lei_registration": {
            "classification": "missing_in_mdm",
            "status": scalar(registration.get("RegistrationStatus")),
            "initial_date": scalar(registration.get("InitialRegistrationDate")),
            "last_update_date": scalar(registration.get("LastUpdateDate")),
            "next_renewal_date": scalar(registration.get("NextRenewalDate")),
            "managing_lou": scalar(registration.get("ManagingLOU")),
            "validation_sources": scalar(registration.get("ValidationSources")),
            "age_days_at_publication": age_days,
        },
    }


def counts(rows: list[dict], field: str, child: str = "classification") -> dict:
    return dict(sorted(collections.Counter(row[field][child] for row in rows).items()))


def summarize(rows: list[dict]) -> dict:
    ages = sorted(
        row["lei_registration"]["age_days_at_publication"]
        for row in rows
        if row["lei_registration"]["age_days_at_publication"] is not None
    )
    return {
        "summary_version": "gleif-company-attribute-lift-v1",
        "accepted_links": len(rows),
        "all_cohort_companies": 1000,
        "classifications": {
            field: counts(rows, field)
            for field in (
                "legal_name",
                "other_names",
                "legal_address",
                "headquarters_address",
                "legal_jurisdiction",
                "legal_form",
                "entity_status",
                "entity_creation_date",
                "entity_expiration",
                "successors",
                "legal_entity_events",
                "registration_authority_identifier",
                "lei_registration",
            )
        },
        "entity_status_values": counts(rows, "entity_status", "value"),
        "registration_status_values": counts(rows, "lei_registration", "status"),
        "validation_source_values": counts(rows, "lei_registration", "validation_sources"),
        "last_update_age_days": {
            "present": len(ages),
            "minimum": ages[0] if ages else None,
            "median": ages[len(ages) // 2] if ages else None,
            "maximum": ages[-1] if ages else None,
        },
        "field_presence": {
            "legal_form": sum(row["legal_form"]["classification"] == "missing_in_mdm" for row in rows),
            "other_names": sum(row["other_names"]["count"] > 0 for row in rows),
            "companies_with_new_other_names": sum(
                row["other_names"]["new_to_mdm"] > 0 for row in rows
            ),
            "entity_creation_date": sum(bool(row["entity_creation_date"]["value"]) for row in rows),
            "entity_expiration": sum(bool(row["entity_expiration"]["date"]) for row in rows),
            "successor": sum(row["successors"]["count"] > 0 for row in rows),
            "legal_entity_events": sum(row["legal_entity_events"]["count"] > 0 for row in rows),
            "registration_authority_identifier": sum(
                bool(row["registration_authority_identifier"]["value"]) for row in rows
            ),
        },
        "denominator_note": (
            "All field counts use the 308 accepted links; all-cohort coverage is count/1000. "
            "No population-wide inference is claimed from the fixed stratified cohort."
        ),
    }


def write_jsonl(path: Path, rows: list[dict]) -> str:
    digest = hashlib.sha256()
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            line = canonical_json(row) + "\n"
            handle.write(line)
            digest.update(line.encode())
    return digest.hexdigest()


def self_test() -> None:
    assert scalar({"$": " X "}) == "X"
    assert scalar(None) is None
    assert normalize_text("Coca-Cola Co.") == "COCA COLA CO"
    assert values_under({"a": {"LegalEntityEvent": [{"x": 1}]}}, {"LegalEntityEvent"}) == [
        {"x": 1}
    ]
    print("self-test passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    records = extracted_records()
    candidates = selected_candidates()
    missing = sorted({row["lei"] for row in candidates} - set(records))
    if missing:
        raise RuntimeError(f"missing {len(missing)} accepted Level 1 records")
    comparisons = [classify(row, records[row["lei"]]) for row in candidates]
    comparison_hash = write_jsonl(ROOT / "03-attribute-comparisons.jsonl", comparisons)
    summary = summarize(comparisons)
    summary["comparison_artifact"] = {
        "file": "03-attribute-comparisons.jsonl",
        "rows": len(comparisons),
        "sha256": comparison_hash,
    }
    (ROOT / "03-attribute-lift-summary.json").write_text(
        canonical_json(summary) + "\n", encoding="utf-8"
    )
    print(canonical_json(summary))


if __name__ == "__main__":
    main()
