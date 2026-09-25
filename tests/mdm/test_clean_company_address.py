"""A Company address is one governed value, never mixed source components."""

from edgar_warehouse.mdm.clean.company_source import POLICY
from edgar_warehouse.mdm.clean.evidence import assertion
from edgar_warehouse.mdm.clean.store import digest
from edgar_warehouse.mdm.clean.survivorship import current_claims, select_fields


def test_company_address_comes_from_one_source_with_other_address_retained():
    sec_address = {
        "street": "1 Main Street", "city": "Cupertino", "region": "CA",
        "postcode": "95014", "country": "US",
    }
    gleif_address = {
        "street": "One Main Street", "city": "Cupertino", "region": "US-CA",
        "postcode": "95014", "country": "US",
    }
    sec = assertion(
        source_code="sec.submissions.company.v1", record_key="0000320193",
        publication_key="sec-bronze-1", revision=1, effective_at=None,
        kind="company", fields={"address": sec_address},
    )
    gleif = assertion(
        source_code="gleif.level1.v1", record_key="HWUPKR0MPOU8FGXBT394",
        publication_key="gleif-full-1", revision=1, effective_at=None,
        kind="company", fields={"address": gleif_address},
    )
    as_of = "2026-09-25T00:00:00Z"
    claims = current_claims([sec, gleif], as_of, set())
    fields, _, reviews = select_fields(
        "company", [sec["subject"], gleif["subject"]], claims, POLICY, [],
        as_of=as_of, policy_digest=digest(POLICY), entity_id="company-1",
    )
    assert not reviews
    assert fields["address"]["value"] == sec_address
    assert fields["address"]["winner"]["source_code"] == sec["source_code"]
    assert [c["value"] for c in fields["address"]["conflicts"]] == [gleif_address]
