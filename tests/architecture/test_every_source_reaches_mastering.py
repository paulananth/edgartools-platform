"""Step 1 of mastering: every source record goes through mastering (CONTEXT.md, "Mastering").

Read from the sources' own configuration: a Dataset Contract that gives its records an entity type (a fixed `kind`, a
`kind_field` or a classification rule) must be prepared and then merged by `mastering.merge` in its source's
Bookkeeping target. A contract with no entity type is silver only and is named below. The gaps are named too, so closing
one means removing it here.
"""

from edgar_warehouse.rules import files

# Sources with no Dataset Contract that gives an entity type: they land in silver only.
SILVER_ONLY = {"sec.company-facts", "sec.registration", "sec.thirteenf.filings"}
# Dataset Contracts that name an entity type and never reach mastering. FINDING (ticket 204, 2026-11-09, step 1):
# GLEIF's relationship and reporting-exception files describe links and exceptions between entities, not entities;
# nothing prepares or merges them. Awaiting the operator's ruling; remove a name here when it is fixed.
KNOWN_GAPS = {"gleif.relationships.v1", "gleif.reporting_exceptions.v1"}


def sources() -> dict[str, dict]:
    return {path.name: files.source(path.name) for path in sorted((files.ROOT / "sources").iterdir()) if path.is_dir()}


def typed_contracts(source: dict) -> set[str]:
    found = set()
    for code, contract in (source.get("dataset_contracts") or {}).items():
        adapter = (contract.get("contract") or {}).get("adapter") or {}
        if adapter.get("kind") or adapter.get("kind_field") or adapter.get("classification"):
            found.add(code)
    return found


def merged_datasets(source: dict) -> set[str]:
    """The datasets whose prepared records a `mastering.merge` step of the source requires, through its prepare steps."""
    reached = set()
    for target in ((source.get("bookkeeping") or {}).get("targets") or {}).values():
        steps = {step["name"]: step for step in target["steps"]}
        for merge in (s for s in steps.values() if s["operation"] == "mastering.merge"):
            seen, todo = set(), list(merge.get("requires") or [])
            while todo:
                name = todo.pop()
                if name in seen:
                    continue
                seen.add(name)
                if steps[name]["operation"] == "mdm.prepare":
                    reached.add(steps[name]["input"]["keys"]["dataset"])
                todo += list(steps[name].get("requires") or [])
    return reached


def test_every_typed_dataset_contract_is_prepared_and_merged_by_mastering():
    missing = set()
    for name, source in sources().items():
        missing |= typed_contracts(source) - merged_datasets(source)
    assert missing == KNOWN_GAPS, f"contracts that never reach mastering: {sorted(missing)}"


def test_the_sources_with_no_entity_type_are_the_silver_only_ones():
    untyped = {name for name, source in sources().items() if not typed_contracts(source)}
    assert untyped == SILVER_ONLY


def test_no_dataset_is_merged_that_no_contract_declares():
    for name, source in sources().items():
        assert merged_datasets(source) <= set(source.get("dataset_contracts") or {}), name


def test_the_reading_finds_a_contract_with_no_merge_step():
    """The check on a made source: one typed contract merged, one typed contract with no merge step."""
    made = {
        "dataset_contracts": {"a.v1": {"contract": {"adapter": {"kind": "company"}}},
                              "b.v1": {"contract": {"adapter": {"kind": "company"}}},
                              "c.v1": {"contract": {"adapter": {}}}},
        "bookkeeping": {"targets": {"mastering": {"steps": [
            {"name": "prepare-a", "operation": "mdm.prepare", "requires": [], "input": {"keys": {"dataset": "a.v1"}}},
            {"name": "merge", "operation": "mastering.merge", "requires": ["prepare-a"]},
            {"name": "prepare-b", "operation": "mdm.prepare", "requires": [], "input": {"keys": {"dataset": "b.v1"}}}]}}}}
    assert typed_contracts(made) == {"a.v1", "b.v1"}
    assert merged_datasets(made) == {"a.v1"}
    assert typed_contracts(made) - merged_datasets(made) == {"b.v1"}
