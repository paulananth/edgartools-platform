"""Write rules/sources/sec.submissions.company/source.yaml through rules.files.

The mapping decisions and where each came from are in rules-log.md
("Step 6: Write"). Run from repo/ with `uv run --no-sync python`.
"""

from pathlib import Path

from edgar_warehouse.rules import files

HEADER = """\
# SEC EDGAR company submissions: the MDM mapping of one SEC filer as a Company
# candidate. Parsing stays in existing code: the warehouse lands each
# submissions file as silver `sec_company` (+ `_address`, `_filing`,
# `_former_name`) rows (`loaders/bronze_submission_extractors.py`), the ticker
# catalogs as `sec_company_ticker`, and `mdm prepare-clean-company`
# (`mdm/clean/company_source.py`) joins them into one record per filer. This
# file maps that record, so it has no `read`. Field ranks live in the merge
# rules (`rules/merge/kinds/company.yaml`), not here.
#
# The kind is not stated: the Company rule `sec-company-candidate` decides it
# per record, because SEC's entityType "other" covers people, funds and
# foreign issuers alike. The record's `tickers` (from the reference_catalog
# family) and `forms` are read by that rule, not mapped as fields.
#
# DRAFT, not approved. `schema_version` and `adapter.version` are named by the
# agent and both enter every assertion id: confirm both against the registered
# mapping (mdm_v2.dataset_mapping) before activation.
"""

SOURCE = "sec.submissions.company"
SOURCE_CODE = "sec.submissions.company.v1"

body = {
    "source": SOURCE,
    "bronze": {"family": "submissions"},
    "mdm": {
        SOURCE_CODE: {
            "contract": {
                "provider": "SEC",
                "family": "submissions",
                "schema_version": "sec-company-landing-v1",
                "record_key": "the filer's CIK, 10 digits zero-padded",
                "publication_key": (
                    "one capture run's pinned sec_company, sec_company_filing and "
                    "sec_company_address members, the ticker catalog run's "
                    "sec_company_ticker member and the Name Census, each by sha256 "
                    "(as mdm prepare-clean-company builds it)"
                ),
                "effective_time": (
                    "unknown; last_synced_at is when the file was observed, kept as "
                    "provenance observed_at"
                ),
                "semantics": "patch; absence never retires an identity",
                "completeness": (
                    "a bounded sample (at most 1000) of one capture run's Company "
                    "rows; never the whole SEC filer universe, and individual "
                    "filers are not landed as Company rows"
                ),
                "adapter": {
                    "version": "sec-company-landing-v1",
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
                    "identifiers": {"cik": "cik"},
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
                    "provenance": {"observed_at": "last_synced_at"},
                    "matching": {
                        "business_postal_code": "business_address.postal_code",
                        "business_country": "business_address.country",
                        "name_census": "name_census",
                    },
                },
            }
        }
    },
}

text = HEADER + files.dumps(body)
target = files.ROOT / "sources" / SOURCE / "source.yaml"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(text, encoding="utf-8")
assert files.load(target) == body, "the file does not read back exactly"
assert files.source(SOURCE) == body
assert files.mdm_contract(SOURCE, SOURCE_CODE) == body["mdm"][SOURCE_CODE]["contract"]
print(f"wrote {target} ({len(text)} bytes); reads back exactly")
