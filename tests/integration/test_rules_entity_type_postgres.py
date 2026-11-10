"""Step 0 of mastering in the Rules Database: `rules.source_entity_type` says where each saved source's records get
their entity type, read from the Dataset Contracts it holds (PG16)."""
from edgar_warehouse.rules import files
from edgar_warehouse.rules.db import migrate
from tests.integration.test_rules_approval_postgres import pg  # noqa: F401


def test_the_view_lists_each_dataset_contract_with_its_entity_type_and_origin(pg):
    migrate(pg["owner"])
    for name in ("sec.company", "gleif", "openfigi"):
        pg["agent"].save("source", name, "1", files.source(name))
    with pg["agent"].engine.connect() as conn:
        rows = {r[0]: r[1:] for r in conn.exec_driver_sql(
            "select dataset_code, origin, entity_types, rule_id from rules.source_entity_type")}
    assert rows["sec.company.v1"] == ("rule", "company", "sec-company-candidate")
    assert rows["gleif.level1.v1"] == ("source_field", "company", None)
    assert rows["openfigi.security.v3"] == ("fixed", "security", None)
