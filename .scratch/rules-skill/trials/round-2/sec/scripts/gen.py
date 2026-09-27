"""Step 6: the SEC Company Dataset Contract as data, written with files.dumps."""
import sys
from edgar_warehouse.rules import files

VERSION = "sec-company-landing-record-v1"
contract = {
    "provider": "SEC EDGAR",
    "nonblocking_deferred_reasons": [],
    "family": "submissions",
    "schema_version": VERSION,
    "record_key": "CIK, ten digits zero-padded",
    "publication_key": (
        "capture run id and the sha256 of its pinned sec_company, sec_company_filing "
        "and sec_company_address members, the ticker catalog run and its "
        "sec_company_ticker member, and the Name Census digest"
    ),
    "effective_time": "unknown",
    "semantics": "patch; absence never retires an identity",
    "completeness": (
        "one capture run's current submissions header per filer SEC treats as an "
        "entity, with its forms, business address, catalog tickers and Name Census "
        "entry; prepare-clean-company pins a bounded sample of at most 1000 "
        "records, never the whole source"
    ),
    "adapter": {
        "version": VERSION,
        "retain_deferred": True,
        "source_record_provenance": True,
        "field_shape": "nullable_text",
        "classification": {
            "kind": "company",
            "rule_id": "sec-company-candidate",
            "version": "2026-09-25.13",
        },
        "record_key": ["cik"],
        "record_key_format": "sec_cik",
        "identifiers": {"cik": "cik", "ein": "ein"},
        "identifier_formats": {"cik": "sec_cik"},
        "fields": {
            "name": "entity_name",
            "sic": "sic",
            "sic_description": "sic_description",
            "state_of_incorporation": "state_of_incorporation",
            "fiscal_year_end": "fiscal_year_end",
            "description": "description",
            "address": {
                "components": {
                    "street": "business_address.street",
                    "street2": "business_address.street2",
                    "city": "business_address.city",
                    "region": "business_address.region",
                    "postcode": "business_address.postal_code",
                    "country": "business_address.country",
                }
            },
        },
        "matching": {
            "business_postal_code": "business_address.postal_code",
            "business_country": "business_address.country",
            "name_census": "name_census",
        },
    },
}
doc = {
    "source": "sec.submissions.company",
    "bronze": {"family": "submissions"},
    "mdm": {"sec.submissions.company.v1": {"contract": contract}},
}
text = files.dumps(doc)
assert files.loads(text) == doc
sys.stdout.write(text)
