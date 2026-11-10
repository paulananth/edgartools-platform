"""Step 0 of mastering in the Rules Database: `entity_types()` says where each saved source's records get their
entity type, read from the Dataset Contracts it holds. Read in code, so it is the same on every database (PG16 here)."""
from edgar_warehouse.rules import files
from edgar_warehouse.rules.db import migrate
from tests.integration.test_rules_approval_postgres import pg  # noqa: F401


def test_each_dataset_contract_is_listed_with_its_entity_type_and_origin(pg):
    migrate(pg["owner"])
    for name in ("sec.company", "gleif", "openfigi"):
        pg["agent"].save("source", name, "1", files.source(name))
    rows = {r["dataset_code"]: (r["origin"], r["entity_types"], r["rule_id"]) for r in pg["agent"].entity_types()}
    assert rows["sec.company.v1"] == ("rule", "company", "sec-company-candidate")
    assert rows["gleif.level1.v1"] == ("source_field", "company", None)
    assert rows["openfigi.security.v3"] == ("fixed", "security", None)
