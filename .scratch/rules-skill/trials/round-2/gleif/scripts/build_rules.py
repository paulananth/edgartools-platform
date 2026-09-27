"""Build rules/sources/gleif/source.yaml values; dump them with files.dumps.

Comments are added by hand afterwards (step 6). Prints the YAML to stdout.
"""

from edgar_warehouse.rules import files

VERSION = "gleif-native-record-v1"  # fixed by gleif_source.VERSION
FAMILY = "gleif"  # operator, answer 4: one capture family, named after the source

COMMON_CONTRACT = {
    "provider": "GLEIF",
    "family": FAMILY,
    "schema_version": VERSION,
}
PUBLICATION_KEY = (
    "one Golden Copy publication: its publisher time (the content date, e.g. "
    "2026-09-11T16:00Z) as its sequence, plus the digest of its verified manifest"
)
EFFECTIVE = "the record's Registration.LastUpdateDate"
COMPLETENESS = (
    "a full Golden Copy file holds every record GLEIF has ever published, current "
    "and historical (lapsed, retired, annulled included); a delta holds only the "
    "records changed in its window. Only records whose LEIs are on the approved "
    "Company LEI scope reach MDM. No retirement by absence"
)
DEFAULTS = {
    "version": VERSION,
    "retain_deferred": True,
    "source_record_provenance": True,
    "field_shape": "nullable_text",
}
NATIVE = {"native_record": "_native"}

RELATIONSHIP_TYPES = [
    "IS_DIRECTLY_CONSOLIDATED_BY",
    "IS_ULTIMATELY_CONSOLIDATED_BY",
    "IS_INTERNATIONAL_BRANCH_OF",
    "IS_FUND-MANAGED_BY",
    "IS_SUBFUND_OF",
    "IS_FEEDER_TO",
]


def address(prefix):
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


level1 = {
    "contract": {
        **COMMON_CONTRACT,
        "record_key": "the LEI: 20 characters, ISO 17442 check digits",
        "publication_key": PUBLICATION_KEY,
        "effective_time": EFFECTIVE,
        "semantics": "patch",
        "completeness": COMPLETENESS,
        "nonblocking_deferred_reasons": [
            "outside_approved_company_scope",
            "unsupported_identity_kind",
        ],
        "publication_families": ["golden_copy"],
        "adapter": {
            **DEFAULTS,
            "native_member": "level1",
            "record_key": ["LEI.$"],
            "record_key_format": "lei",
            "kind_field": "Entity.EntityCategory.$",
            "kind_values": {"GENERAL": "company"},
            "probable_kind_values": {
                "FUND": "fund_structure",
                "BRANCH": "branch",
                "SOLE_PROPRIETOR": "person",
                "RESIDENT_GOVERNMENT_ENTITY": "government",
                "INTERNATIONAL_ORGANIZATION": "international_organization",
            },
            "identifiers": {"lei": "LEI.$"},
            "identifier_formats": {"lei": "lei"},
            "fields": {
                "name": "Entity.LegalName.$",
                "jurisdiction": "Entity.LegalJurisdiction.$",
                "address": address("Entity.LegalAddress"),
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
            "matching": {
                "headquarters_postal_code": "Entity.HeadquartersAddress.PostalCode.$",
                "headquarters_country": "Entity.HeadquartersAddress.Country.$",
            },
            "provenance": NATIVE,
        },
    }
}

relationships = {
    "contract": {
        **COMMON_CONTRACT,
        "record_key": "the start node's LEI plus the relationship type",
        "publication_key": PUBLICATION_KEY,
        "effective_time": EFFECTIVE,
        "semantics": "patch",
        "completeness": COMPLETENESS,
        "nonblocking_deferred_reasons": ["outside_approved_company_scope"],
        "publication_families": ["golden_copy"],
        "adapter": {
            **DEFAULTS,
            "native_member": "relationships",
            "record_key": ["start", "relationship_type"],
            "kind": "company",
            "identifiers": {"lei": "start"},
            "identifier_formats": {"lei": "lei"},
            "relationships": [
                {
                    "type_field": "relationship_type",
                    "type_values": {t: t for t in RELATIONSHIP_TYPES},
                    "target_key": ["end"],
                    "target_source": "gleif.level1.v1",
                    "valid_from": "valid_from",
                    "valid_to": "valid_to",
                    "properties": {
                        "status": "status",
                        "registration_status": "registration_status",
                    },
                }
            ],
            "provenance": NATIVE,
        },
    }
}

reporting_exceptions = {
    "contract": {
        **COMMON_CONTRACT,
        "record_key": "the LEI plus the exception category (direct or ultimate parent)",
        "publication_key": PUBLICATION_KEY,
        "effective_time": "unknown; a reporting exception carries no date",
        "semantics": "patch",
        "completeness": COMPLETENESS,
        "nonblocking_deferred_reasons": [
            "outside_approved_company_scope",
            "reported_parent_exception",
        ],
        "publication_families": ["golden_copy"],
        "adapter": {
            **DEFAULTS,
            "native_member": "reporting_exceptions",
            "record_key": ["LEI.$", "ExceptionCategory.$"],
            "identifiers": {"lei": "LEI.$"},
            "identifier_formats": {"lei": "lei"},
            "provenance": NATIVE,
        },
    }
}

document = {
    "source": "gleif",
    "bronze": {"family": FAMILY},
    "mdm": {
        "gleif.level1.v1": level1,
        "gleif.relationships.v1": relationships,
        "gleif.reporting_exceptions.v1": reporting_exceptions,
    },
}

if __name__ == "__main__":
    text = files.dumps(document)
    assert files.loads(text) == document, "dumps does not read back exactly"
    print(text, end="")
