"""Step 0 of mastering: `rules entity-types` says where each source's records get their entity type, read from
the Dataset Contracts in the rules files."""
import json

from edgar_warehouse.cli import main


def test_each_dataset_contract_is_listed_with_its_entity_type_and_origin(capsys):
    assert main(["rules", "entity-types"]) == 0
    rows = {r["dataset_code"]: (r["source"], r["origin"], r["entity_types"], r["rule_id"])
            for r in json.loads(capsys.readouterr().out)}
    assert rows["sec.company.v1"] == ("sec.company", "rule", "company", "sec-company-candidate")
    assert rows["gleif.level1.v1"] == ("gleif", "source_field", "company", None)
    assert rows["openfigi.security.v4"] == ("openfigi", "fixed", "security", None)
