"""Silver keeps no master field (ticket 143; operator, 2026-10-28: "silver must not have duplicate fields, it
contradicts the data governance principle: one system of record").

A silver table of a source holds the transaction's own facts and its links to masters. It never copies a field
the source's Dataset Contract maps into the master record (a name, a capacity, a title), because MDM is that
field's one system of record. The link keys, the contract's record key and its dates stay: they find the master."""
import pytest

from edgar_warehouse.rules import files

SOURCES = sorted(path.name for path in (files.ROOT / "sources").iterdir() if (path / "source.yaml").is_file())

# A column kept by a ruling, never by habit: (source, column) -> the ruling.
KEPT = {
    ("sec.nport.security", "currency_code"): 'operator, 2026-10-28: "Keep it on the row (Recommended)": the unit of the row\'s value',
}


def mapped_inputs(contract: dict) -> set[str]:
    """The source fields a Dataset Contract copies into the master record: every path of its mapped `fields`,
    and the `held` and `title` columns of its relationships."""
    adapter = contract["contract"]["adapter"]
    found: set[str] = set()

    def walk(value):
        if isinstance(value, dict):
            if isinstance(value.get("path"), str):
                found.add(value["path"].split(".")[0])
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk((((adapter.get("reading") or {}).get("read") or {}).get("tables") or {}).get("mapped", {}).get("columns", {}).get("fields"))
    for relationship in adapter.get("relationships") or []:
        found.update(relationship[k] for k in ("held", "title") if isinstance(relationship.get(k), str))
    return found


def kept_to_find_the_master(spec: dict, contract: dict) -> set[str]:
    links = {c for link in spec.get("links") or [] for c in link["columns"]}
    return links | set(spec["key"]) | {c for c in (spec.get("time") or {}).values() if c} | set(
        contract["contract"]["adapter"].get("record_key") or [])


@pytest.mark.parametrize("name", SOURCES)
def test_a_silver_table_copies_no_field_its_dataset_contract_maps(name):
    reading = files.source(name)
    contracts = reading.get("dataset_contracts") or {}
    specs = [files.load(path) for path in sorted((files.ROOT / "sources" / name).glob("silver-*.yaml"))]
    copies = []
    for spec in specs:
        for code, contract in contracts.items():
            mapped = mapped_inputs(contract)
            for column in spec["columns"]:
                if (column["name"] in mapped and column["name"] not in kept_to_find_the_master(spec, contract)
                        and (name, column["name"]) not in KEPT):
                    copies.append(f"silver.{spec['table']}.{column['name']} copies a field of {code}")
    assert copies == [], copies


def test_the_guard_sees_a_copy():
    """Failing before the guard: the owner's name, as silver kept it, is the field the ownership contract maps."""
    contract = files.source("sec.ownership")["dataset_contracts"]["sec.ownership.reporting_owner.v1"]
    assert {"rpt_owner_name", "is_director", "is_officer", "is_ten_percent_owner", "officer_title"} <= mapped_inputs(contract)
