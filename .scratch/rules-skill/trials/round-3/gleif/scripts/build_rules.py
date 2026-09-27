"""Build rules/sources/gleif/source.yaml values; dump with files.dumps; write to scratch/source.values.yaml.

Comments are then added by hand (scratch/add_comments.py) and the result is checked to load
back equal to VALUE.
"""

import json
import sys

sys.path.insert(0, ".")
from edgar_warehouse.rules import files  # noqa: E402

VERSION = "gleif-native-record-v1"
NONBLOCKING = [
    "outside_approved_company_scope",
    "unsupported_identity_kind",
    "unsupported_relationship_type",
    "reported_parent_exception",
]
COMMON = {
    "provider": "GLEIF",
    "family": "gleif",
    "schema_version": VERSION,
}
PUBLICATION_KEY = (
    "one GLEIF Golden Copy publication (its publisher time, e.g. 2026-09-11 16:00 UTC), "
    "numbered by that time; the three member files are verified together"
)
EFFECTIVE = "Registration.LastUpdateDate of the record (the reader sets it)"
COMPLETENESS_FULL = (
    "a full Golden Copy holds every LEI GLEIF has ever published, current and historical, "
    "each once; a delta holds changes only; no retirement by absence"
)
ADAPTER_DEFAULTS = {
    "version": VERSION,
    "retain_deferred": True,
    "source_record_provenance": True,
    "field_shape": "nullable_text",
}

level1 = {
    "contract": {
        **COMMON,
        "record_key": "the LEI (20 characters, ISO 17442 check digits)",
        "publication_key": PUBLICATION_KEY,
        "effective_time": EFFECTIVE,
        "semantics": "patch",
        "completeness": COMPLETENESS_FULL,
        "nonblocking_deferred_reasons": NONBLOCKING,
        "publication_families": ["golden_copy"],
        "adapter": {
            **ADAPTER_DEFAULTS,
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
            "fields": {
                "name": "Entity.LegalName.$",
                "jurisdiction": "Entity.LegalJurisdiction.$",
                "address": {
                    "components": {
                        "street": "Entity.LegalAddress.FirstAddressLine.$",
                        "street2": {"lines": "Entity.LegalAddress.AdditionalAddressLine"},
                        "city": "Entity.LegalAddress.City.$",
                        "region": "Entity.LegalAddress.Region.$",
                        "postcode": "Entity.LegalAddress.PostalCode.$",
                        "country": "Entity.LegalAddress.Country.$",
                    }
                },
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
            },
            "provenance": {"native_record": "_native"},
            "matching": {
                "headquarters_postal_code": "Entity.HeadquartersAddress.PostalCode.$",
                "headquarters_country": "Entity.HeadquartersAddress.Country.$",
            },
        },
    }
}

relationships = {
    "contract": {
        **COMMON,
        "record_key": "start LEI, relationship type and end LEI together",
        "publication_key": PUBLICATION_KEY,
        "effective_time": EFFECTIVE,
        "semantics": "patch",
        "completeness": COMPLETENESS_FULL.replace("every LEI", "every relationship record"),
        "nonblocking_deferred_reasons": NONBLOCKING,
        "publication_families": ["golden_copy"],
        "adapter": {
            **ADAPTER_DEFAULTS,
            "native_member": "relationships",
            "record_key": ["start", "relationship_type", "end"],
            "kind": "company",
            "relationships": [
                {
                    "type_field": "relationship_type",
                    "type_values": {
                        "IS_DIRECTLY_CONSOLIDATED_BY": "IS_DIRECTLY_CONSOLIDATED_BY",
                        "IS_ULTIMATELY_CONSOLIDATED_BY": "IS_ULTIMATELY_CONSOLIDATED_BY",
                    },
                    "target_key": ["end"],
                    "target_source": "gleif.level1.v1",
                    "valid_from": "valid_from",
                    "valid_to": "valid_to",
                    "scope": "accounting consolidation as GLEIF states it",
                    "properties": {
                        "source_relationship_status": "status",
                        "source_registration_status": "registration_status",
                    },
                }
            ],
            "provenance": {"native_record": "_native"},
        },
    }
}

exceptions = {
    "contract": {
        **COMMON,
        "record_key": "the LEI and the exception category together",
        "publication_key": PUBLICATION_KEY,
        "effective_time": "unknown; an exception record carries no dates",
        "semantics": "patch",
        "completeness": COMPLETENESS_FULL.replace("every LEI", "every reporting exception").replace(
            "each once;", "each once, including exceptions GLEIF marks deleted;"
        ),
        "nonblocking_deferred_reasons": NONBLOCKING,
        "publication_families": ["golden_copy"],
        "adapter": {
            **ADAPTER_DEFAULTS,
            "native_member": "reporting_exceptions",
            "record_key": ["LEI.$", "ExceptionCategory.$"],
            "kind": "company",
            "provenance": {"native_record": "_native"},
        },
    }
}

VALUE = {
    "source": "gleif",
    "bronze": {"family": "gleif"},
    "mdm": {
        "gleif.level1.v1": level1,
        "gleif.relationships.v1": relationships,
        "gleif.reporting_exceptions.v1": exceptions,
    },
}

if __name__ == "__main__":
    out = sys.argv[1]
    with open(out, "w") as fh:
        fh.write(files.dumps(VALUE))
    with open(out + ".json", "w") as fh:
        json.dump(VALUE, fh, indent=1)
    print("dumped", out)
