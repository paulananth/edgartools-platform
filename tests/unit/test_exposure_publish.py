"""The exposure's catalog plan: one owned service, the store's types translated, exactly two owned tags a table,
only the manifest's lineage, and no glossary term or certification. Every name here is invented; the readback
against a running server is the ticket's live proof."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "skills/data-platform/scripts/exposure"))

from exposure_publish import APPROVED, PublishError, _owned, column_type, exposure_plan  # noqa: E402

from tests.support.exposure import invented_manifest  # noqa: E402


def manifest():
    return invented_manifest(
        {"layer": "mdm", "table": "golden", "description": "Invented golden records.",
         "columns": [("entity_id", "character(36)", "The id."), ("body", "text", "The record.")]},
        {"layer": "silver", "table": "sale", "description": "Invented sales.", "lineage": ["mdm.golden"],
         "columns": [("amount", "numeric(18,2)", "The amount."), ("sold_at", "timestamp with time zone", "When.")]},
    )


def test_every_table_lives_in_the_one_service_the_manifest_owns_named_by_its_parts():
    plan = exposure_plan(manifest(), service="invented-exposure")
    assert plan["service"]["name"] == "invented-exposure"
    assert {t["databaseSchema"] for t in plan["tables"]} == {"invented-exposure.INVENTED_MIRROR.MDM",
                                                            "invented-exposure.INVENTED_MIRROR.SILVER"}
    assert "planned, not yet read back" in plan["service"]["description"]


def test_each_table_carries_the_exposure_tag_and_its_layers_data_class_and_nothing_else():
    plan = exposure_plan(manifest(), service="s")
    assert plan["tags"] == {"s.INVENTED_MIRROR.MDM.GOLDEN": sorted([APPROVED, "data_class.master_data"]),
                            "s.INVENTED_MIRROR.SILVER.SALE": sorted([APPROVED, "data_class.transaction_data"])}


def test_no_glossary_term_certification_or_classification_is_planned():
    plan = exposure_plan(manifest())
    assert not {"glossary_terms", "glossaries", "certifications", "classifications", "data_class_marks"} & set(plan)


def test_the_lineage_is_the_manifests_and_nothing_more():
    plan = exposure_plan(manifest(), service="s")
    assert [(e["from"], e["to"]) for e in plan["lineage"]] == [("s.INVENTED_MIRROR.MDM.GOLDEN",
                                                               "s.INVENTED_MIRROR.SILVER.SALE")]


@pytest.mark.parametrize("store, catalog", [
    ("text", {"dataType": "TEXT"}),
    ("character(36)", {"dataType": "CHAR", "dataLength": 36}),
    ("character varying(128)", {"dataType": "VARCHAR", "dataLength": 128}),
    ("numeric(38,10)", {"dataType": "NUMERIC"}),
    ("timestamp with time zone", {"dataType": "TIMESTAMPZ"}),
    ("jsonb", {"dataType": "JSON"}),
    ("boolean", {"dataType": "BOOLEAN"}),
])
def test_a_store_type_is_translated_and_kept_for_display(store, catalog):
    assert column_type(store) == {**catalog, "dataTypeDisplay": store}


def test_a_store_type_with_no_catalog_type_is_refused():
    with pytest.raises(PublishError, match="no catalog type"):
        column_type("tsvector")


def test_an_unknown_layer_is_refused_not_dropped():
    with pytest.raises(PublishError, match="no data class"):
        exposure_plan(invented_manifest({"layer": "gold", "table": "x", "description": "Invented.",
                                         "columns": [("id", "text", "The id.")]}))


def test_only_the_tags_of_the_two_owned_classifications_are_this_publications():
    tags = [{"tagFQN": APPROVED}, {"tagFQN": "data_class.master_data"}, {"tagFQN": "PII.None"}]
    assert _owned(tags) == sorted([APPROVED, "data_class.master_data"])
