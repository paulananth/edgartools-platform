"""Write rules/sources/sec.submissions.company/source.yaml with files.dumps (step 6).

Prints the dumped YAML and saves the exact value as JSON, so the hand-commented
file can be checked against it afterwards.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from edgar_warehouse.rules import files

VERSION = "sec-company-landing-record-v1"

VALUE = {
    "source": "sec.submissions.company",
    "bronze": {"family": "submissions"},
    "mdm": {
        "sec.submissions.company.v1": {
            "contract": {
                "provider": "SEC",
                "family": "submissions",
                "schema_version": VERSION,
                "record_key": "SEC CIK, 10 digits zero-padded",
                "publication_key": (
                    "capture run id and sha256 of its sec_company member, plus the run and "
                    "sha256 of each pinned member (filings, addresses, tickers) and the Name "
                    "Census digest"
                ),
                "effective_time": "unknown; last_synced_at is observation time",
                "semantics": "patch; absence never retires an identity",
                "completeness": (
                    "each submissions file is one filer's complete current snapshot; one "
                    "publication is one capture run's bounded sample, never the whole SEC "
                    "universe"
                ),
                "nonblocking_deferred_reasons": ["classification_deferred"],
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
                    "identifiers": {"cik": "cik", "sec_ein": "ein"},
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
                        "name_census": "name_census",
                        "business_postal_code": "business_address.postal_code",
                        "business_country": "business_address.country",
                    },
                },
            }
        }
    },
}

if __name__ == "__main__":
    Path(sys.argv[1]).write_text(json.dumps(VALUE, indent=1))
    sys.stdout.write(files.dumps(VALUE))
