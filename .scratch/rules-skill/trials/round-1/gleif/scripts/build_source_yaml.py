"""Write rules/sources/gleif/source.yaml through edgar_warehouse.rules.files.

The body is built as a dict and written with `files.dumps`; comments are then
inserted as whole lines above named keys, and the file is read back with
`files.source` and compared with the dict, so a comment can never change a value.
Run from repo/: uv run --no-sync python ../scratch/build_source_yaml.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from edgar_warehouse.rules import files

VERSION = "gleif-native-record-v1"  # gleif_source.VERSION; native_consumption requires it
FAMILY = "gleif_golden_copy"  # assumption: no GLEIF acquisition family exists (Question 4)
LEVEL1 = "gleif.level1.v1"
RR = "gleif.relationships.v1"
REPEX = "gleif.reporting_exceptions.v1"
PUBLICATION_KEY = (
    "one Golden Copy publication: its publish date and time (e.g. 20260911-1600, the UTC "
    "data cut-off in GLEIF's file name), shared by its Level 1, RR and REPEX files; read "
    "from the captured publication manifest, never from a file name"
)
RELATIONSHIP_TYPES = [
    "IS_DIRECTLY_CONSOLIDATED_BY",
    "IS_ULTIMATELY_CONSOLIDATED_BY",
    "IS_INTERNATIONAL_BRANCH_OF",
    "IS_FUND-MANAGED_BY",
    "IS_SUBFUND_OF",
    "IS_FEEDER_TO",
]


def address(prefix: str) -> dict:
    return {
        "components": {
            "street": f"{prefix}.FirstAddressLine.$",
            "street2": {"lines": f"{prefix}.AdditionalAddressLine"},
            "city": f"{prefix}.City.$",
            "region": f"{prefix}.Region.$",
            "postcode": f"{prefix}.PostalCode.$",
            "country": f"{prefix}.Country.$",
        }
    }


BODY = {
    "source": "gleif",
    "bronze": {"family": FAMILY},
    "mdm": {
        LEVEL1: {
            "contract": {
                "provider": "GLEIF (Global Legal Entity Identifier Foundation)",
                "family": FAMILY,
                "schema_version": VERSION,
                "record_key": "the LEI: 20 characters, ISO 17442, mod 97 check digits",
                "publication_key": PUBLICATION_KEY,
                "effective_time": "the record's Registration.LastUpdateDate, GLEIF's last "
                "update of the LEI record",
                "semantics": "patch",
                "completeness": "a full Golden Copy holds every LEI record ever published "
                "(GLEIF never deletes one); a delta holds only records new or changed since "
                "its delta start; MDM takes a record only when its LEI is on the run's "
                "approved Company list, and only category GENERAL as a Company",
                "nonblocking_deferred_reasons": [
                    "outside_approved_company_scope",
                    "unsupported_identity_kind",
                    "invalid_lei_checksum",
                ],
                "adapter": {
                    "version": VERSION,
                    "native_member": "level1",
                    "record_key": ["LEI.$"],
                    "record_key_format": "lei",
                    "kind_field": "Entity.EntityCategory.$",
                    "kind_values": {"GENERAL": "company"},
                    "probable_kind_values": {
                        "FUND": "fund_structure",
                        "BRANCH": "branch",
                        "RESIDENT_GOVERNMENT_ENTITY": "government",
                        "INTERNATIONAL_ORGANIZATION": "international_organization",
                    },
                    "identifiers": {"lei": "LEI.$"},
                    "identifier_formats": {"lei": "lei"},
                    "field_shape": "nullable_text",
                    "fields": {
                        "name": "Entity.LegalName.$",
                        "jurisdiction": "Entity.LegalJurisdiction.$",
                        "address": address("Entity.LegalAddress"),
                        "gleif_legal_form": "Entity.LegalForm.EntityLegalFormCode.$",
                        "gleif_entity_status": "Entity.EntityStatus.$",
                        "gleif_entity_creation_date": "Entity.EntityCreationDate.$",
                        "gleif_registration_authority": "Entity.RegistrationAuthority."
                        "RegistrationAuthorityID.$",
                        "gleif_registration_authority_entity_id": "Entity.RegistrationAuthority."
                        "RegistrationAuthorityEntityID.$",
                        "gleif_registration_status": "Registration.RegistrationStatus.$",
                        "gleif_initial_registration": "Registration.InitialRegistrationDate.$",
                        "gleif_last_update": "Registration.LastUpdateDate.$",
                        "gleif_next_renewal": "Registration.NextRenewalDate.$",
                        "gleif_managing_lou": "Registration.ManagingLOU.$",
                        "gleif_validation_source": "Registration.ValidationSources.$",
                    },
                    "matching": {
                        "headquarters_postal_code": "Entity.HeadquartersAddress.PostalCode.$",
                        "headquarters_country": "Entity.HeadquartersAddress.Country.$",
                    },
                },
            }
        },
        RR: {
            "contract": {
                "provider": "GLEIF (Global Legal Entity Identifier Foundation)",
                "family": FAMILY,
                "schema_version": VERSION,
                "record_key": "the child LEI (StartNode) plus the relationship type, "
                "GLEIF's own rule for one relationship record",
                "publication_key": PUBLICATION_KEY,
                "effective_time": "the relationship record's Registration.LastUpdateDate",
                "semantics": "patch",
                "completeness": "a full Golden Copy holds each current relationship record "
                "(registration PUBLISHED or LAPSED); GLEIF drops others, so a missing "
                "relationship is not proof of none; a delta flags removals; MDM takes a "
                "record only when both LEIs are on the run's approved Company list",
                "nonblocking_deferred_reasons": [
                    "outside_approved_company_scope",
                    "invalid_lei_checksum",
                ],
                "adapter": {
                    "version": VERSION,
                    "native_member": "relationships",
                    # Paths below name the record gleif_source.record_evidence builds
                    # (start, end, relationship_type, valid_from, valid_to, status,
                    # registration_status), not the raw RR-CDF record.
                    "record_key": ["start", "relationship_type"],
                    "kind": "company",
                    "identifiers": {"lei": "start"},
                    "identifier_formats": {"lei": "lei"},
                    "relationships": [
                        {
                            "type_field": "relationship_type",
                            "type_values": {t: t for t in RELATIONSHIP_TYPES},
                            "target_key": ["end"],
                            "target_source": LEVEL1,
                            "valid_from": "valid_from",
                            "valid_to": "valid_to",
                            "properties": {
                                "status": "status",
                                "registration_status": "registration_status",
                            },
                        }
                    ],
                },
            }
        },
        REPEX: {
            "contract": {
                "provider": "GLEIF (Global Legal Entity Identifier Foundation)",
                "family": FAMILY,
                "schema_version": VERSION,
                "record_key": "the child LEI plus the exception category (direct or "
                "ultimate accounting parent), GLEIF's own rule for one exception",
                "publication_key": PUBLICATION_KEY,
                "effective_time": "unknown; a reporting exception carries no date",
                "semantics": "patch",
                "completeness": "a full Golden Copy holds each current reporting exception; "
                "a relationship record of the same type replaces it; a missing parent is "
                "not proof of no parent; every exception is kept as evidence only, never a "
                "field or an edge",
                "nonblocking_deferred_reasons": [
                    "outside_approved_company_scope",
                    "reported_parent_exception",
                    "invalid_lei_checksum",
                ],
                "adapter": {
                    "version": VERSION,
                    "native_member": "reporting_exceptions",
                    "record_key": ["LEI.$", "ExceptionCategory.$"],
                    "identifiers": {"lei": "LEI.$"},
                    "identifier_formats": {"lei": "lei"},
                },
            }
        },
    },
}

# Comment lines inserted above the first line that equals `anchor` (stripped),
# searching from the previous insertion point, so each lands where intended.
COMMENTS = [
    ("source: gleif", [
        "# GLEIF Golden Copy: Level 1 LEI records, Level 2 relationship records (RR) and",
        "# reporting exceptions (REPEX), read as one publication. Parsing stays in native",
        "# code (edgar_warehouse/mdm/clean/gleif_source.py: inspect_archive, record_evidence),",
        "# run by `edgar-warehouse mdm mastering --model clean --manifest <native manifest>`,",
        "# so this source has no `read`. The folder is `gleif` because",
        "# gleif_source.dataset_contract() reads rules_files.source(\"gleif\").",
        "# Draft written by the rules skill trial on 2026-09-26: NOT approved.",
    ]),
    ("family: gleif_golden_copy", [
        "  # Assumed name: no GLEIF acquisition family exists in the repo yet (log, Q4).",
    ]),
    ("gleif.level1.v1:", [
        "  # The code the Company merge rules already name (rules/merge/kinds/company.yaml).",
    ]),
    ("nonblocking_deferred_reasons:", [
        "      # Set aside by design, kept as evidence, and not waiting for a person (log, Q6).",
        "      # invalid_lei_checksum: 256 GLEIF LEIs fail the check digit, all ANNULLED or",
        "      # DUPLICATE registrations (log, Q10). Not in REFERENCE.md; read by",
        "      # store.register_dataset, merge.py and migration 030.",
    ]),
    ("kind_values:", [
        "        # GLEIF's category decides the kind. Only GENERAL is a Company; the others",
        "        # wait with the kind they probably are. SOLE_PROPRIETOR names none.",
    ]),
    ("fields:", [
        "        # Field names are the Company fields (store.COMPANY_NAMED_FIELDS). SEC wins",
        "        # `name` and `address` by source order; the gleif_* fields and jurisdiction",
        "        # are GLEIF's alone (operator, 2026-09-24).",
    ]),
    ("address:", [
        "          # The legal address, whole. The headquarters address feeds matching only.",
    ]),
    ("gleif_legal_form: Entity.LegalForm.EntityLegalFormCode.$", [
        "          # The ISO 20275 code; \"8888\" means GLEIF holds free text in",
        "          # OtherLegalForm, which is not mapped (log, Q7).",
    ]),
    ("gleif_last_update: Registration.LastUpdateDate.$", [
        "          # Raw text: the Name Census stores it as written and the name rule",
        "          # compares it exactly.",
    ]),
    ("matching:", [
        "        # What the SEC-to-GLEIF postcode rule compares, outside the fields.",
    ]),
    ("gleif.relationships.v1:", [
        "  # Paths name the record gleif_source.record_evidence builds from an RR record",
        "  # (start, end, relationship_type, valid_from, valid_to, status,",
        "  # registration_status), not the raw RR-CDF record.",
    ]),
    ("kind: company", [
        "        # An RR record does not say what its child is. Only records whose both LEIs",
        "        # are on the approved Company list get this far, so the child is a Company",
        "        # there; a Fund-rooted record (46% of RR) waits outside that list (log, Q8).",
    ]),
    ("target_source: gleif.level1.v1", [
        "          # The other end is the Level 1 record of the parent (or manager, head",
        "          # office, umbrella, master fund) LEI.",
    ]),
    ("gleif.reporting_exceptions.v1:", [
        "  # Every exception is kept as evidence only: record_evidence sets each one aside",
        "  # as reported_parent_exception before any mapping runs, so the adapter maps no",
        "  # kind, field or edge.",
    ]),
]


def render() -> str:
    lines = files.dumps(BODY).splitlines()
    position = 0
    for anchor, comment in COMMENTS:
        for i in range(position, len(lines)):
            if lines[i].strip() == anchor:
                lines[i:i] = comment
                position = i + len(comment) + 1
                break
        else:
            raise SystemExit(f"comment anchor not found after line {position}: {anchor}")
    return "\n".join(lines) + "\n"


def main() -> None:
    root = Path(files.ROOT)
    target = root / "sources" / "gleif" / "source.yaml"
    text = render()
    if files.loads(text, str(target)) != BODY:
        raise SystemExit("rendered file does not read back as the body")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    if files.source("gleif") != BODY:
        raise SystemExit("files.source('gleif') differs from the body")
    print(f"wrote {target} ({len(text)} bytes); reads back exactly", file=sys.stderr)


if __name__ == "__main__":
    main()
