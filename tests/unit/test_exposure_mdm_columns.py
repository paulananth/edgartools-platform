"""The exposure list defines every column of the MDM tables it lets leave the stores, so the manifest of the hosted store generates."""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
EXPOSED = {entry["table"]: entry for entry in yaml.safe_load((ROOT / "destination/authorised_data_sharing.yaml").read_text())["tables"]
           if entry["layer"] == "mdm"}
SCHEMA = (ROOT / "edgar_warehouse/mastering/schema/postgresql.sql").read_text()


def columns_of(table: str) -> list[str]:
    body = re.search(rf"create table if not exists {table}\((.*?)\);", SCHEMA, re.S).group(1)
    names = [part.strip().split()[0] for part in re.split(r",\s*(?![^()]*\))", body)]
    return [name for name in names if name not in ("primary", "unique", "foreign", "constraint")]


def test_every_column_of_an_exposed_mdm_table_has_a_definition_in_the_list():
    for table, entry in EXPOSED.items():
        missing = [c for c in columns_of(table) if not (entry.get("columns") or {}).get(c)]
        assert not missing, f"mdm.{table} columns with no definition in the exposure list: {missing}"
