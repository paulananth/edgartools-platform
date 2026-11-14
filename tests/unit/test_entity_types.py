"""Step 0 of mastering: every registered Dataset Contract states where its records' entity type comes from."""

import pytest

from edgar_warehouse.rules import files


def contract(**adapter) -> dict:
    return {"dataset_contracts": {"x.v1": {"contract": {"adapter": adapter}}}}


def test_each_way_of_stating_an_entity_type_is_read():
    assert files.entity_types(contract(kind="security")) == {"x.v1": {"origin": "fixed", "types": ["security"]}}
    assert files.entity_types(contract(classification={"kind": "company", "rule_id": "r"})) == {
        "x.v1": {"origin": "rule", "types": ["company"], "rule_id": "r"}}
    assert files.entity_types(contract(kind_field="Cat", kind_values={"A": "company", "B": "company"})) == {
        "x.v1": {"origin": "source_field", "types": ["company"], "field": "Cat"}}


def test_a_contract_with_no_entity_type_is_refused_at_registration():
    with pytest.raises(files.RulesFileError, match="states no entity type"):
        files.check_document("source", contract(record_key=["id"]))


def test_every_source_in_the_repo_states_its_entity_types():
    stated = {code: found for name in ("gleif", "iapd.adv", "openfigi", "sec.company", "sec.ncen.fund", "sec.nport.fund", "sec.nport.registrant",
                                       "sec.nport.security", "sec.ownership", "sec.submissions.person", "sec.thirteenf.securities")
              for code, found in files.entity_types(files.source(name)).items()}
    assert len(stated) == 15
    assert {v["origin"] for v in stated.values()} == {"fixed", "rule", "source_field"}
